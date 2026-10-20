import threading
import unittest

from native_radio_control import NativeScanNotReady
from native_radio_control import ETHERNET_FRAME, frame_for_service_rx
from native_scan_service import NativeScanSession, SCAN_FAILED


class FakeWifi:
    mac = bytes.fromhex('021122334455')
    scan_observer = None
    control_observer = None

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


class FakeJoinWifi(FakeWifi):
    radio_observer = None
    kernel_session = None
    target_bssid = None
    target_band = None
    active_vif = None

    def scan(self, ssid, key, *, scan_frequencies, publish_results):
        self.calls.append(('join_scan', ssid, len(key), scan_frequencies,
                           publish_results))
        target = {'ssid': ssid, 'bssid': '02:11:22:33:44:55',
                  'frequency': 5220, 'rssi': -52}
        self.radio_observer(True, target, self.mac)
        self.kernel_session(0, 1, target, lambda frame: self.calls.append(
            ('eapol', len(frame))))
        self.radio_observer(False, None, self.mac)

    def receive_native(self):
        self.native_stop.set()
        return [bytes.fromhex('0211223344550211223344550800') + b'payload']

    def data_write(self, frame, vif, station, label, *, quiet,
                   require_confirmation):
        self.calls.append(('tx', frame, vif, station, quiet,
                           require_confirmation))


class FakeJoinBridge(FakeBridge):
    def __init__(self):
        super().__init__()
        self.outgoing = frame_for_service_rx(
            ETHERNET_FRAME, bytes.fromhex('0211223344550211223344550800') +
            b'outbound', 1, 0)
        self.join = None

    def next_scan_request(self):
        return None

    def next_join_request(self):
        join, self.join = self.join, None
        return join

    def complete_join(self, sequence, status_code=0):
        self.calls.append(('join_complete', sequence, status_code))

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
                   'key': b'k' * 32, 'rsn': b''}
        session.execute_join(request)
        self.assertEqual(wifi.calls[0], ('join_scan', 'test', 32, (5220,), False))
        self.assertIn(('join_complete', 8, 0), bridge.calls)
        self.assertTrue(any(call[0] == 'rx' for call in bridge.calls))
        self.assertTrue(any(call[0] == 'tx' for call in wifi.calls))
        self.assertNotIn('key', request)
        self.assertIsNone(wifi.radio_observer)
        self.assertIsNone(wifi.kernel_session)

    def test_join_failure_completes_error_and_clears_key(self):
        wifi = FakeJoinWifi()
        bridge = FakeJoinBridge()
        session = NativeScanSession(wifi, bridge, threading.Event())
        wifi.scan = lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError('firmware rejected association'))
        request = {'sequence': 9, 'ssid': 'test',
                   'bssid': '02:11:22:33:44:55', 'frequency': 5220,
                   'key': b'k' * 32, 'rsn': b''}
        with self.assertRaises(RuntimeError):
            session.execute_join(request)
        self.assertEqual(bridge.calls, [('join_complete', 9, SCAN_FAILED)])
        self.assertNotIn('key', request)

    def test_research_loop_dispatches_join_and_releases_usb(self):
        wifi = FakeJoinWifi()
        bridge = FakeJoinBridge()
        bridge.join = {'sequence': 10, 'ssid': 'test',
                       'bssid': '02:11:22:33:44:55', 'frequency': 5220,
                       'key': b'k' * 32, 'rsn': b''}
        NativeScanSession(wifi, bridge, threading.Event()).run()
        self.assertIn(('join_complete', 10, 0), bridge.calls)
        self.assertEqual(bridge.calls[-1], ('close',))
        self.assertTrue(wifi.closed)


if __name__ == '__main__':
    unittest.main()
