"""Research-only native scan/join session using the AIC FullMAC USB owner.

Not installed or started by the stable service. The Wifi session lock prevents
simultaneous ownership with the UTUN implementation. Native connection is
still untested; no AirDrop path is supplied by this module.
"""

import threading
import time

from native_radio_control import NativeScanNotReady
from native_radio_control import ETHERNET_FRAME, frame_for_service_rx
from native_scan_bridge import matches_request


SCAN_FAILED = 0xe00002bc
SCAN_ABORTED = 0xe00002eb


class NativeLeaveRequested(RuntimeError):
    pass


class NativeScanSession:
    def __init__(self, wifi, bridge, stop=None):
        self.wifi = wifi
        self.bridge = bridge
        self.stop = stop if stop is not None else threading.Event()
        self.wifi.native_stop = self.stop
        self.wifi.write_auth_report = False
        self.last_sequence = None
        self.last_join_sequence = None
        self.frame_sequence = 0
        self.powered = True

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

    def execute_join(self, request):
        sequence = request['sequence']
        if sequence == self.last_join_sequence:
            raise RuntimeError('Repeated native AIC join sequence')
        previous_observer = self.wifi.radio_observer
        previous_session = self.wifi.kernel_session
        previous_target_bssid = getattr(self.wifi, 'target_bssid', None)
        previous_target_band = getattr(self.wifi, 'target_band', None)
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
                    for frame in self.wifi.receive_native():
                        if frame[12:14] == b'\x88\x8e':
                            service_eapol(frame)
                        elif 14 <= len(frame) <= 1514:
                            self.frame_sequence = (self.frame_sequence + 1) & 0xffffffff
                            if not self.frame_sequence:
                                self.frame_sequence = 1
                            packet = frame_for_service_rx(
                                ETHERNET_FRAME, frame, self.frame_sequence, 0)
                            self.bridge.submit_received_frame(packet)
                    for _ in range(32):
                        packet = self.bridge.next_transmit_frame()
                        if packet is None:
                            break
                        if packet.kind != ETHERNET_FRAME:
                            continue  # No peer-to-peer action-frame path in this phase.
                        frame = bytes(packet.data[:packet.length])
                        if frame[12:14] != b'\x88\x8e':
                            self.wifi.data_write(frame, vif, station, 'dados',
                                                 quiet=True, require_confirmation=False)
                    self.stop.wait(.002)
            finally:
                self.wifi.active_vif = None

        self.wifi.radio_observer = radio
        self.wifi.kernel_session = connected
        self.wifi.scan_observer = lambda _item: None  # Preserve beacon IEs for WPA2 validation.
        self.wifi.kernel_poll = lambda: self.poll_control(active=True)
        self.wifi.target_bssid = request['bssid']
        self.wifi.target_band = 0 if request['frequency'] < 3000 else 1
        try:
            self.poll_control(active=True)
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
                    if not self.powered:
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
                        print('AIC: conexão nativa falhou; pronto para nova tentativa.',
                              flush=True)
                    continue
                self.stop.wait(.05)
        finally:
            try:
                self.bridge.publish(False, None, self.wifi.mac)
            except (AttributeError, RuntimeError, ValueError):
                pass
            self.bridge.close()
            self.wifi.close()
