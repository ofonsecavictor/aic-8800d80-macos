import threading
import unittest
from unittest.mock import Mock, patch

from native_radio_control import NativeScanNotReady
from native_radio_control import ETHERNET_FRAME, frame_for_service_rx
from native_scan_service import (NativeLeaveRequested, NativeScanSession,
                                 SCAN_ABORTED, SCAN_FAILED)


class FakeWifi:
    mac = bytes.fromhex('021122334455')
    scan_observer = None
    control_observer = None
    kernel_poll = None

    def __init__(self, fail=False):
        self.fail = fail
        self.closed = False
        self.calls = []

    def identity(self):
        return {'lmac_version': '06090101'}

    def initialize_radio(self):
        self.calls.append('initialize')

    def scan(self, *, scan_frequencies, publish_results):
        self.calls.append(('scan', scan_frequencies, publish_results))
        if self.fail:
            raise RuntimeError('USB scan failed')
        self.scan_observer({
            'frequency': 5220, 'bssid': '02:11:22:33:44:55',
            '_beacon': {'ies': b'\x00\x03AIC', 'interval': 100,
                        'capability': 0x11}, 'rssi': -52})
        self.scan_observer({
            'frequency': 5180, 'bssid': '02:11:22:33:44:66',
            '_beacon': {'ies': b'\x00\x05Other', 'interval': 100,
                        'capability': 0x11}, 'rssi': -60})
        self.control_observer(0x1001, b'\x00')

    def close(self):
        self.closed = True


class FakeBridge:
    def __init__(self):
        self.calls = []
        self.not_ready = 0
        self.power = None
        self.leave = None

    def publish(self, powered, target, mac):
        self.calls.append(('publish', powered, mac))

    def enable_scan_bridge(self):
        self.calls.append(('enable',))
        if self.not_ready:
            self.not_ready -= 1
            raise NativeScanNotReady()

    def submit_scan_result(self, sequence, item):
        self.calls.append(('result', sequence, item['bssid']))

    def complete_scan(self, sequence, status_code=0):
        self.calls.append(('complete', sequence, status_code))

    def close(self):
        self.calls.append(('close',))

    def next_power_command(self):
        power, self.power = self.power, None
        return power

    def next_leave_command(self):
        leave, self.leave = self.leave, None
        return leave


class FakeJoinWifi(FakeWifi):
    radio_observer = None
    kernel_session = None
    target_bssid = None
    target_band = None
    active_vif = None

    def __init__(self):
        super().__init__()
        self.tx_diagnostics = {'data_submitted': 0}

    def scan(self, ssid, key, *, scan_frequencies, publish_results):
        self.calls.append(('join_scan', ssid, len(key), scan_frequencies,
                           publish_results))
        target = {'ssid': ssid, 'bssid': '02:11:22:33:44:55',
                  'frequency': 5220, 'rssi': -52}
        self.radio_observer(True, target, self.mac)
        try:
            self.kernel_session(0, 1, target, lambda frame: self.calls.append(
                ('eapol', len(frame))))
        finally:
            self.radio_observer(False, None, self.mac)

    def receive_native(self):
        self.native_stop.set()
        # Full-MTU IPv4 plus an RX trailer: the native path must trim the
        # protocol boundary rather than discard the entire 1522-byte record.
        ip = b'\x45\x00\x05\xdc' + bytes(1496)
        return [bytes.fromhex('0211223344550211223344550800') + ip + bytes(8)]

    def data_write(self, frame, vif, station, label, *, quiet,
                   require_confirmation, sample_confirmation=False):
        self.calls.append(('tx', frame, vif, station, quiet,
                           require_confirmation, sample_confirmation))
        self.tx_diagnostics['data_submitted'] += 1


class FakeJoinBridge(FakeBridge):
    def __init__(self):
        super().__init__()
        self.outgoing = frame_for_service_rx(
            ETHERNET_FRAME, bytes.fromhex('0211223344550211223344550800') +
            b'outbound', 1, 0)
        self.join = None
        self.scan_request = None
        self.leave_after_complete = None
        self.power_after_complete = None

    def next_scan_request(self):
        request, self.scan_request = self.scan_request, None
        return request

    def next_join_request(self):
        join, self.join = self.join, None
        return join

    def complete_join(self, sequence, status_code=0):
        self.calls.append(('join_complete', sequence, status_code))
        if status_code == 0:
            self.leave = self.leave_after_complete
            self.power = self.power_after_complete

    def submit_received_frame(self, frame):
        self.calls.append(('rx', bytes(frame.data[:frame.length])))

    def next_transmit_frame(self):
        frame, self.outgoing = self.outgoing, None
        return frame


class NativeScanServiceTests(unittest.TestCase):
    def setUp(self):
        self.wifi = FakeWifi()
        self.bridge = FakeBridge()
        self.session = NativeScanSession(self.wifi, self.bridge, threading.Event())
        self.request = {'sequence': 5, 'type': 1, 'ssid': b'AIC',
                        'bssid': None, 'frequencies': (5220,)}

    def test_prepare_publishes_before_enabling_and_retries_registration(self):
        self.bridge.not_ready = 1
        self.session.prepare(timeout=1)
        self.assertEqual(self.bridge.calls[0][:2], ('publish', True))
        self.assertEqual(self.bridge.calls[-2:], [('enable',), ('enable',)])

    def test_filtered_beacons_and_real_completion(self):
        self.session.execute(self.request)
        self.assertEqual(self.wifi.calls, [('scan', (5220,), False)])
        self.assertEqual(self.bridge.calls, [
            ('result', 5, '02:11:22:33:44:55'), ('complete', 5, 0)])
        self.assertIsNone(self.wifi.scan_observer)
        self.assertIsNone(self.wifi.control_observer)
        with self.assertRaises(RuntimeError):
            self.session.execute(self.request)

    def test_failed_firmware_scan_is_not_reported_as_success(self):
        self.wifi.fail = True
        with self.assertRaises(RuntimeError):
            self.session.execute(self.request)
        self.assertEqual(self.bridge.calls, [('complete', 5, SCAN_FAILED)])

    def test_connected_scan_uses_recent_beacons_without_another_usb_scan(self):
        self.session.execute(self.request)
        self.wifi.calls.clear()
        self.bridge.calls.clear()
        request = dict(self.request, sequence=6)
        self.session.answer_connected_scan(request)
        self.assertEqual(self.wifi.calls, [])
        self.assertEqual(self.bridge.calls, [
            ('result', 6, '02:11:22:33:44:55'), ('complete', 6, 0)])

    def test_connected_join_answers_scan_before_mac_times_out(self):
        wifi = FakeJoinWifi()
        bridge = FakeJoinBridge()
        session = NativeScanSession(wifi, bridge, threading.Event())
        session.remember_beacon({
            'frequency': 5220, 'bssid': '02:11:22:33:44:55',
            '_beacon': {'ies': b'\x00\x04test', 'interval': 100,
                        'capability': 0x11}, 'rssi': -52})
        bridge.scan_request = {'sequence': 17, 'type': 1, 'ssid': b'test',
                               'bssid': None, 'frequencies': (5220,)}
        join = {'sequence': 18, 'ssid': 'test',
                'bssid': '02:11:22:33:44:55', 'frequency': 5220,
                'key': b'k' * 32, 'rsn': b'', 'station_mac': wifi.mac}
        session.execute_join(join)
        self.assertIn(('result', 17, '02:11:22:33:44:55'), bridge.calls)
        self.assertIn(('complete', 17, 0), bridge.calls)

    def test_shutdown_releases_usb_and_publishes_radio_off(self):
        self.session.stop.set()
        with self.assertRaises(KeyboardInterrupt):
            self.session.run()
        self.assertEqual(self.bridge.calls[-2][0:2], ('publish', False))
        self.assertEqual(self.bridge.calls[-1], ('close',))
        self.assertTrue(self.wifi.closed)

    def test_join_uses_saved_pmk_once_and_pumps_native_ethernet(self):
        wifi = FakeJoinWifi()
        bridge = FakeJoinBridge()
        session = NativeScanSession(wifi, bridge, threading.Event())
        request = {'sequence': 8, 'ssid': 'test',
                   'bssid': '02:11:22:33:44:55', 'frequency': 5220,
                   'key': b'k' * 32, 'rsn': b'',
                   'station_mac': wifi.mac}
        session.execute_join(request)
        self.assertEqual(wifi.calls[0], ('join_scan', 'test', 32, (5220,), False))
        self.assertIn(('join_complete', 8, 0), bridge.calls)
        self.assertTrue(any(call[0] == 'rx' for call in bridge.calls))
        self.assertEqual(session.rx_ingress, {'accepted': 1, 'trimmed': 1, 'rejected': 0})
        self.assertTrue(any(call[0] == 'tx' for call in wifi.calls))
        self.assertNotIn('key', request)
        self.assertIsNone(wifi.radio_observer)
        self.assertIsNone(wifi.kernel_session)

    def test_temporary_probe_samples_radio_tx_status(self):
        wifi = FakeJoinWifi()
        bridge = FakeJoinBridge()
        with patch.dict('os.environ', {'AIC_NATIVE_TX_SAMPLE': '1'}):
            session = NativeScanSession(wifi, bridge, threading.Event())
        request = {'sequence': 8, 'ssid': 'test',
                   'bssid': '02:11:22:33:44:55', 'frequency': 5220,
                   'key': b'k' * 32, 'rsn': b'', 'station_mac': wifi.mac}
        session.execute_join(request)
        self.assertTrue(any(call[0] == 'tx' and call[-1] is True
                            for call in wifi.calls))

    def test_busy_data_batch_does_not_sleep_before_draining_next_batch(self):
        wifi = FakeJoinWifi()
        bridge = FakeJoinBridge()
        stop = threading.Event()
        stop.wait = Mock(wraps=stop.wait)
        session = NativeScanSession(wifi, bridge, stop)
        request = {'sequence': 19, 'ssid': 'test',
                   'bssid': '02:11:22:33:44:55', 'frequency': 5220,
                   'key': b'k' * 32, 'rsn': b'', 'station_mac': wifi.mac}
        session.execute_join(request)
        stop.wait.assert_not_called()

    def test_join_uses_private_station_address_then_restores_hardware_address(self):
        wifi = FakeJoinWifi()
        bridge = FakeJoinBridge()
        session = NativeScanSession(wifi, bridge, threading.Event())
        hardware_mac = wifi.mac
        private_mac = bytes.fromhex('061122334455')
        request = {'sequence': 15, 'ssid': 'test',
                   'bssid': '02:11:22:33:44:55', 'frequency': 5220,
                   'station_mac': private_mac, 'key': b'k' * 32, 'rsn': b''}
        original_scan = wifi.scan

        def verify_scan(*args, **kwargs):
            self.assertEqual(wifi.mac, private_mac)
            return original_scan(*args, **kwargs)

        wifi.scan = verify_scan
        session.execute_join(request)
        self.assertEqual(wifi.mac, hardware_mac)
        self.assertIn(('publish', True, private_mac), bridge.calls)
        self.assertEqual(bridge.calls[-1], ('publish', True, hardware_mac))
        self.assertNotIn('key', request)

    def test_join_failure_completes_error_and_clears_key(self):
        wifi = FakeJoinWifi()
        bridge = FakeJoinBridge()
        session = NativeScanSession(wifi, bridge, threading.Event())
        wifi.scan = lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError('firmware rejected association'))
        request = {'sequence': 9, 'ssid': 'test',
                   'bssid': '02:11:22:33:44:55', 'frequency': 5220,
                   'key': b'k' * 32, 'rsn': b'',
                   'station_mac': wifi.mac}
        with self.assertRaises(RuntimeError):
            session.execute_join(request)
        self.assertEqual(bridge.calls, [('join_complete', 9, SCAN_FAILED)])
        self.assertNotIn('key', request)

    def test_research_loop_dispatches_join_and_releases_usb(self):
        wifi = FakeJoinWifi()
        bridge = FakeJoinBridge()
        bridge.join = {'sequence': 10, 'ssid': 'test',
                       'bssid': '02:11:22:33:44:55', 'frequency': 5220,
                       'key': b'k' * 32, 'rsn': b'',
                       'station_mac': wifi.mac}
        NativeScanSession(wifi, bridge, threading.Event()).run()
        self.assertIn(('join_complete', 10, 0), bridge.calls)
        self.assertEqual(bridge.calls[-1], ('close',))
        self.assertTrue(wifi.closed)

    def test_scan_only_rejects_join_without_touching_usb_or_retaining_key(self):
        wifi = FakeJoinWifi()
        bridge = FakeJoinBridge()
        stop = threading.Event()
        request = {'sequence': 14, 'ssid': 'test',
                   'bssid': '02:11:22:33:44:55', 'frequency': 5220,
                   'key': b'k' * 32, 'rsn': b'',
                   'station_mac': wifi.mac}
        bridge.join = request
        complete = bridge.complete_join
        def finish(sequence, status_code=0):
            complete(sequence, status_code)
            stop.set()
        bridge.complete_join = finish
        NativeScanSession(wifi, bridge, stop, scan_only=True).run()
        self.assertEqual(wifi.calls, ['initialize'])
        self.assertIn(('join_complete', 14, SCAN_ABORTED), bridge.calls)
        self.assertNotIn('key', request)
        self.assertTrue(wifi.closed)

    def test_leave_cancels_connected_session_without_stopping_service(self):
        wifi = FakeJoinWifi()
        bridge = FakeJoinBridge()
        bridge.leave_after_complete = 12
        session = NativeScanSession(wifi, bridge, threading.Event())
        request = {'sequence': 11, 'ssid': 'test',
                   'bssid': '02:11:22:33:44:55', 'frequency': 5220,
                   'key': b'k' * 32, 'rsn': b'',
                   'station_mac': wifi.mac}
        with self.assertRaises(NativeLeaveRequested):
            session.execute_join(request)
        self.assertIn(('join_complete', 11, 0), bridge.calls)
        self.assertEqual(bridge.calls[-1][0:2], ('publish', False))
        self.assertNotIn('key', request)
        self.assertIsNone(wifi.active_vif)

    def test_power_off_cancels_connection_and_power_on_restores_idle_radio(self):
        wifi = FakeJoinWifi()
        bridge = FakeJoinBridge()
        bridge.power_after_complete = (2, False)
        session = NativeScanSession(wifi, bridge, threading.Event())
        request = {'sequence': 12, 'ssid': 'test',
                   'bssid': '02:11:22:33:44:55', 'frequency': 5220,
                   'key': b'k' * 32, 'rsn': b'',
                   'station_mac': wifi.mac}
        with self.assertRaises(NativeLeaveRequested):
            session.execute_join(request)
        self.assertFalse(session.powered)
        self.assertIn(('publish', False, wifi.mac), bridge.calls)
        bridge.power = (3, True)
        session.poll_control()
        self.assertTrue(session.powered)
        self.assertEqual(bridge.calls[-1], ('publish', True, wifi.mac))

    def test_redundant_power_on_does_not_clear_connected_state(self):
        wifi = FakeJoinWifi()
        bridge = FakeJoinBridge()
        bridge.power = (5, True)
        session = NativeScanSession(wifi, bridge, threading.Event())
        session.poll_control(active=True)
        self.assertEqual(bridge.calls, [])

    def test_powered_off_request_cancels_before_touching_usb(self):
        wifi = FakeJoinWifi()
        bridge = FakeJoinBridge()
        session = NativeScanSession(wifi, bridge, threading.Event())
        session.powered = False
        request = {'sequence': 13, 'ssid': 'test',
                   'bssid': '02:11:22:33:44:55', 'frequency': 5220,
                   'key': b'k' * 32, 'rsn': b'',
                   'station_mac': wifi.mac}
        with self.assertRaises(NativeLeaveRequested):
            session.execute_join(request)
        self.assertEqual(wifi.calls, [])
        self.assertEqual(bridge.calls, [('join_complete', 13, SCAN_ABORTED)])
        self.assertNotIn('key', request)


if __name__ == '__main__':
    unittest.main()
