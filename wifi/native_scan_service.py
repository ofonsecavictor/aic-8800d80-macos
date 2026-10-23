"""Native scan/join and bounded AWDL action-frame bridge for AIC FullMAC."""

import os
import threading
import time

from native_radio_control import NativeScanNotReady
from native_radio_control import (ACTION_FRAME, ETHERNET_FRAME,
                                  frame_for_service_rx)
from native_scan_bridge import matches_request
from native_ethernet import normalize_native_ethernet
from management import SET_FILTER_REQUEST_ID, other_bssid_filter_request
from layouts import channel_to_frequency, connectable_frequency


SCAN_FAILED = 0xe00002bc
SCAN_ABORTED = 0xe00002eb


class NativeLeaveRequested(RuntimeError):
    pass


class NativeScanSession:
    def __init__(self, wifi, bridge, stop=None, scan_only=False, ready=None):
        self.wifi = wifi
        self.bridge = bridge
        self.stop = stop if stop is not None else threading.Event()
        self.wifi.native_stop = self.stop
        self.wifi.write_auth_report = False
        self.last_sequence = None
        self.last_join_sequence = None
        self.frame_sequence = 0
        # In-memory beacons from the most recent physical scans. A scan while
        # associated must not reconfigure the firmware station VIF: doing so
        # interrupts DHCP/data and can time out the USB control endpoint.
        self.scan_cache = {}
        self.powered = True
        self.scan_only = scan_only
        self.ready = ready
        # Only the temporary diagnostic requests sparse radio TX status.
        self.tx_sample = os.environ.get('AIC_NATIVE_TX_SAMPLE') == '1'
        self.rx_ingress = {'accepted': 0, 'trimmed': 0, 'rejected': 0}
        now = time.monotonic()
        self.rx_report_at = now + 30
        self.rate_previous = (now, 0, 0)
        self.awdl = None
        self.last_awdl_sequence = None

    def poll_awdl(self, station_vif):
        reader = getattr(self.bridge, 'next_awdl_state', None)
        state = reader() if reader is not None else None
        if state is None:
            return
        if state['sequence'] == self.last_awdl_sequence:
            raise RuntimeError('Repeated native AIC AWDL state sequence')
        self.last_awdl_sequence = state['sequence']
        if self.awdl is not None and (not state['enabled'] or
                                      state['mac'] != self.awdl['mac']):
            self.wifi.remove_interface(self.awdl['vif'])
            self.awdl = None
        if not state['enabled']:
            return
        band = 0 if state['channel'] <= 14 else 1
        frequency = channel_to_frequency(state['channel'], band)
        if frequency is None or not connectable_frequency(frequency):
            raise RuntimeError('Unsupported AIC AWDL channel %u' %
                               state['channel'])
        if self.awdl is None:
            vif = self.wifi.add_p2p_interface(state['mac'])
            if vif == station_vif:
                self.wifi.remove_interface(vif)
                raise RuntimeError('AIC firmware reused the station VIF for AWDL')
            try:
                self.wifi.request(SET_FILTER_REQUEST_ID,
                                  other_bssid_filter_request())
            except BaseException:
                self.wifi.remove_interface(vif)
                raise
            self.awdl = {'vif': vif, 'mac': state['mac'],
                         'channel': state['channel'], 'frequency': frequency}
        else:
            self.awdl['channel'] = state['channel']
            self.awdl['frequency'] = frequency

    def stop_awdl(self):
        if self.awdl is not None:
            vif = self.awdl['vif']
            self.awdl = None
            self.wifi.remove_interface(vif)

    def poll_control(self, active=False):
        power = self.bridge.next_power_command()
        if power is not None:
            _, powered = power
            changed = powered != self.powered
            self.powered = powered
            if changed or not powered:
                self.bridge.publish(powered, None, self.wifi.mac)
        leave = self.bridge.next_leave_command()
        if active and (leave is not None or not self.powered):
            raise NativeLeaveRequested('AIC session cancelled by macOS')

    def prepare(self, timeout=10):
        info = self.wifi.identity()
        if info['lmac_version'] != '06090101':
            raise RuntimeError('Untested AIC firmware revision')
        self.wifi.initialize_radio()
        self.bridge.publish(True, None, self.wifi.mac)
        deadline = time.monotonic() + timeout
        while not self.stop.is_set():
            try:
                self.bridge.enable_scan_bridge()
                if self.ready is not None:
                    self.ready.set()
                return
            except NativeScanNotReady:
                if time.monotonic() >= deadline:
                    raise RuntimeError('Native AIC interface registration timed out') from None
                self.stop.wait(.1)
        raise KeyboardInterrupt

    def execute(self, request):
        sequence = request['sequence']
        if sequence == self.last_sequence:
            raise RuntimeError('Repeated native AIC scan sequence')
        previous_beacon = self.wifi.scan_observer
        previous_control = self.wifi.control_observer
        previous_poll = self.wifi.kernel_poll
        completion_attempted = False

        def beacon(item):
            self.remember_beacon(item)
            if matches_request(request, item):
                try:
                    self.bridge.submit_scan_result(sequence, item)
                except ValueError:
                    # A malformed beacon is omitted, never sent to the kernel.
                    pass

        def control(message, body):
            nonlocal completion_attempted
            if message == 0x1001:
                completion_attempted = True
                self.bridge.complete_scan(sequence, 0 if body[:1] == b'\x00'
                                          else SCAN_FAILED)

        self.wifi.scan_observer = beacon
        self.wifi.control_observer = control
        self.wifi.kernel_poll = lambda: self.poll_control(active=True)
        try:
            self.poll_control(active=True)
            self.wifi.scan(scan_frequencies=request['frequencies'],
                           publish_results=False)
            if not completion_attempted:
                raise RuntimeError('AIC scan ended without firmware completion')
            self.last_sequence = sequence
        except BaseException as error:
            if not completion_attempted:
                try:
                    self.bridge.complete_scan(sequence,
                                              SCAN_ABORTED if isinstance(error, (KeyboardInterrupt,
                                                                                 NativeLeaveRequested))
                                              else SCAN_FAILED)
                except RuntimeError:
                    pass  # Kernel timeout or teardown is already authoritative.
            raise
        finally:
            self.wifi.scan_observer = previous_beacon
            self.wifi.control_observer = previous_control
            self.wifi.kernel_poll = previous_poll

    def remember_beacon(self, item):
        beacon = item.get('_beacon') if isinstance(item, dict) else None
        if not isinstance(beacon, dict) or not isinstance(beacon.get('ies'), bytes):
            return
        key = (item.get('bssid'), item.get('frequency'))
        if key[0] is None or key[1] is None:
            return
        self.scan_cache.pop(key, None)
        self.scan_cache[key] = item
        if len(self.scan_cache) > 64:
            self.scan_cache.pop(next(iter(self.scan_cache)))

    def answer_connected_scan(self, request):
        # WCL still scans periodically after joining. Serve the last observed
        # beacons promptly; an on-air scan on this VIF is not yet safe.
        sequence = request['sequence']
        if sequence == self.last_sequence:
            raise RuntimeError('Repeated native AIC scan sequence')
        for item in self.scan_cache.values():
            if matches_request(request, item):
                try:
                    self.bridge.submit_scan_result(sequence, item)
                except ValueError:
                    pass
        self.bridge.complete_scan(sequence)
        self.last_sequence = sequence

    def execute_join(self, request):
        sequence = request['sequence']
        if sequence == self.last_join_sequence:
            raise RuntimeError('Repeated native AIC join sequence')
        previous_observer = self.wifi.radio_observer
        previous_session = self.wifi.kernel_session
        previous_target_bssid = getattr(self.wifi, 'target_bssid', None)
        previous_target_band = getattr(self.wifi, 'target_band', None)
        hardware_mac = self.wifi.mac
        previous_scan_observer = self.wifi.scan_observer
        previous_poll = self.wifi.kernel_poll
        completed = False

        def radio(powered, target, mac):
            available = powered and self.powered
            self.bridge.publish(available, target if available else None, mac)

        def connected(vif, station, target, service_eapol):
            nonlocal completed
            if (target['bssid'] != request['bssid'] or
                    target['frequency'] != request['frequency']):
                raise RuntimeError('AIC joined a different access point')
            self.bridge.complete_join(sequence)
            completed = True
            self.last_join_sequence = sequence
            self.wifi.active_vif = vif
            try:
                while not self.stop.is_set():
                    self.poll_control(active=True)
                    self.poll_awdl(vif)
                    scan_request = self.bridge.next_scan_request()
                    if scan_request is not None:
                        self.answer_connected_scan(scan_request)
                    received = self.wifi.receive_native()
                    receive_batch = []
                    action_batch = []
                    direct_submit = getattr(
                        self.bridge, 'submit_received_ethernet', None)
                    for frame in received:
                        if frame[12:14] == b'\x88\x8e':
                            service_eapol(frame)
                        else:
                            bounded = normalize_native_ethernet(frame)
                            if bounded is None:
                                self.rx_ingress['rejected'] += 1
                                continue
                            self.rx_ingress['accepted'] += 1
                            self.rx_ingress['trimmed'] += len(bounded) != len(frame)
                            self.frame_sequence = (self.frame_sequence + 1) & 0xffffffff
                            if not self.frame_sequence:
                                self.frame_sequence = 1
                            if direct_submit is not None:
                                receive_batch.append((bounded, self.frame_sequence))
                            else:
                                packet = frame_for_service_rx(
                                    ETHERNET_FRAME, bounded, self.frame_sequence, 0)
                                receive_batch.append(packet)
                    action_reader = getattr(
                        self.wifi, 'take_native_action_frames', None)
                    actions = action_reader() if action_reader is not None else ()
                    if self.awdl is not None:
                        for _, action in actions:
                            self.frame_sequence = (self.frame_sequence + 1) & 0xffffffff
                            if not self.frame_sequence:
                                self.frame_sequence = 1
                            action_batch.append(frame_for_service_rx(
                                ACTION_FRAME, action, self.frame_sequence, 255,
                                self.awdl['channel']))
                    if time.monotonic() >= self.rx_report_at:
                        report_now = time.monotonic()
                        transport = {
                            key: self.wifi.rx_diagnostics.get(key)
                            for key in ('records', 'malformed', 'ethernet_frames',
                                        'ethernet_bytes', 'queue_highwater',
                                        'queue_dropped')
                        }
                        previous_at, previous_rx, previous_tx = self.rate_previous
                        current_rx = transport.get('ethernet_bytes') or 0
                        current_tx = self.wifi.tx_diagnostics.get(
                            'ethernet_bytes_submitted', 0)
                        interval = max(report_now - previous_at, .001)
                        rates = {
                            'rx_mbps': round(max(0, current_rx-previous_rx)*8/
                                             interval/1_000_000, 2),
                            'tx_mbps': round(max(0, current_tx-previous_tx)*8/
                                             interval/1_000_000, 2),
                            'interval_seconds': round(interval, 2),
                        }
                        self.rate_previous = (report_now, current_rx, current_tx)
                        print('AIC native RX ingress: '+str(self.rx_ingress)
                              +' transport: '+str(transport)
                              +' RATE: '+str(rates)
                              +' PHY: '+str(self.wifi.rx_diagnostics.get('phy',{}))
                              +' TX: '+str(self.wifi.tx_diagnostics)
                              +' USB TX: '+str(self.wifi.tx_transport_diagnostics())
                              +' header: '+str(self.wifi.rx_diagnostics.get('sample_header')),
                              flush=True)
                        self.rx_report_at = report_now + 30
                    if receive_batch:
                        submit = getattr(self.bridge, 'submit_received_frames', None)
                        if direct_submit is not None:
                            direct_submit(receive_batch)
                        elif submit is not None:
                            submit(receive_batch)
                        else:
                            for packet in receive_batch:
                                self.bridge.submit_received_frame(packet)
                    if action_batch:
                        submit = getattr(self.bridge, 'submit_received_frames', None)
                        if submit is not None:
                            submit(action_batch)
                        else:
                            for packet in action_batch:
                                self.bridge.submit_received_frame(packet)
                    transmitted = 0
                    batch_reader = getattr(self.bridge, 'next_transmit_frames', None)
                    if batch_reader is not None:
                        packets = batch_reader()
                    else:
                        packets = []
                        for _ in range(32):
                            packet = self.bridge.next_transmit_frame()
                            if packet is None:
                                break
                            packets.append(packet)
                    outbound = []
                    for packet in packets:
                        transmitted += 1
                        if packet.kind == ACTION_FRAME:
                            if (self.awdl is not None and packet.vif == 1 and
                                    packet.channel == self.awdl['channel']):
                                action = bytes(packet.data[:packet.length])
                                self.wifi.action_write(
                                    action, self.awdl['vif'], self.awdl['mac'])
                            continue
                        if packet.kind != ETHERNET_FRAME:
                            continue
                        frame = bytes(packet.data[:packet.length])
                        if frame[12:14] != b'\x88\x8e':
                            outbound.append(frame)
                    if outbound:
                        batch_writer = getattr(self.wifi, 'data_write_batch', None)
                        if batch_writer is not None and not self.tx_sample:
                            batch_writer(outbound, vif, station)
                        else:
                            for frame in outbound:
                                sample = ({'sample_confirmation':
                                           self.wifi.tx_diagnostics['data_submitted'] % 16 == 0}
                                          if self.tx_sample else {})
                                self.wifi.data_write(frame, vif, station, 'dados',
                                                     quiet=True, require_confirmation=False,
                                                     **sample)
                    # The bounded kernel TX mailbox can still fill during a
                    # browser asset burst. Yield only when both directions
                    # were idle; otherwise immediately drain the next batch.
                    if not received and not transmitted:
                        self.stop.wait(.002)
            finally:
                try:
                    self.stop_awdl()
                except Exception as error:
                    print('AIC: falha ao remover VIF AWDL: '+str(error),
                          flush=True)
                self.wifi.active_vif = None

        self.wifi.radio_observer = radio
        self.wifi.kernel_session = connected
        self.wifi.scan_observer = self.remember_beacon  # Preserve beacon IEs for WPA2 validation.
        self.wifi.kernel_poll = lambda: self.poll_control(active=True)
        self.wifi.target_bssid = request['bssid']
        self.wifi.target_band = 0 if request['frequency'] < 3000 else 1
        try:
            station_mac = request['station_mac']
            if (not isinstance(station_mac, bytes) or len(station_mac) != 6 or
                    not any(station_mac) or station_mac[0] & 1):
                raise ValueError('Invalid native station address')
            self.poll_control(active=True)
            # The firmware VIF, EAPOL supplicant and kernel data path must all
            # use the address selected by macOS for this specific network.
            self.wifi.mac = station_mac
            self.wifi.scan(request['ssid'], request['key'],
                           scan_frequencies=(request['frequency'],),
                           publish_results=False)
            if not completed:
                raise RuntimeError('AIC authentication ended without native join')
        except BaseException as error:
            if not completed:
                try:
                    self.bridge.complete_join(
                        sequence, SCAN_ABORTED if isinstance(error, (KeyboardInterrupt,
                                                                    NativeLeaveRequested))
                        else SCAN_FAILED)
                except RuntimeError:
                    pass  # Kernel timeout or cancellation is authoritative.
            raise
        finally:
            self.wifi.radio_observer = previous_observer
            self.wifi.kernel_session = previous_session
            self.wifi.scan_observer = previous_scan_observer
            self.wifi.kernel_poll = previous_poll
            self.wifi.target_bssid = previous_target_bssid
            self.wifi.target_band = previous_target_band
            self.wifi.mac = hardware_mac
            if hardware_mac != request.get('station_mac'):
                try:
                    self.bridge.publish(self.powered, None, hardware_mac)
                except RuntimeError:
                    pass  # The bridge may already be closing after cancellation.
            request.pop('key', None)

    def run(self):
        try:
            self.prepare()
            while not self.stop.is_set():
                self.poll_control()
                request = self.bridge.next_scan_request()
                if request is not None:
                    if not self.powered:
                        self.bridge.complete_scan(request['sequence'], SCAN_ABORTED)
                        continue
                    try:
                        self.execute(request)
                    except NativeLeaveRequested:
                        pass
                    continue
                join = self.bridge.next_join_request()
                if join is not None:
                    if self.scan_only or not self.powered:
                        try:
                            self.bridge.complete_join(join['sequence'], SCAN_ABORTED)
                        finally:
                            join.pop('key', None)
                        continue
                    try:
                        self.execute_join(join)
                    except NativeLeaveRequested:
                        pass
                    except (RuntimeError, ValueError) as error:
                        # A rejected AP or invalid WPA2 handshake should not
                        # make the native service disappear after one attempt.
                        # USB/bridge failures still require supervisor recovery.
                        if ('USB' in str(error) or 'native ' in str(error)):
                            raise
                        print('AIC: conexão nativa falhou: '+str(error), flush=True)
                    continue
                self.stop.wait(.05)
        finally:
            try:
                self.bridge.publish(False, None, self.wifi.mac)
            except (AttributeError, RuntimeError, ValueError):
                pass
            self.bridge.close()
            self.wifi.close()
