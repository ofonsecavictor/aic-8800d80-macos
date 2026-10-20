import threading
import unittest

from native_radio_control import NativeScanNotReady
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


if __name__ == '__main__':
    unittest.main()
