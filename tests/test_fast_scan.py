import json
import threading
import types
import unittest
from collections import deque
from unittest.mock import patch

import wifi
import service
from layouts import Scan, me_channel_config_request, me_config_request


TARGET = {
    'ssid': 'Test Network 5G', 'bssid': '01:02:03:04:05:06',
    'frequency': 5200, 'rssi': -45, 'rsn': 'test',
}


class ReportPath:
    def __truediv__(self, name):
        return self

    def read_text(self):
        return json.dumps({'networks': [
            {'ssid': TARGET['ssid'], 'band_id': 1, 'channel': 40},
        ]})


class FastScanTests(unittest.TestCase):
    def make_wifi(self, miss_cached=False):
        w = object.__new__(wifi.Wifi)
        w.info = {'lmac_version': '06090101'}
        w.mac = bytes.fromhex('020304050607')
        w.target_band = 1
        w.target_bssid = None
        w.native_stop = threading.Event()
        w.events = deque()
        w.scan_observer = None
        w.control_observer = None
        w.kernel_poll = None
        w.initialize_radio = lambda: None
        w.scans = []
        w.published = []
        w.probed = []
        w.pending = False
        w.publish_networks = lambda *args, **kwargs: w.published.append((args, kwargs))
        w.probe = lambda *args: w.probed.append(args)

        def request(message_id, payload=b'', confirmation=None):
            if message_id == 6:
                return b'\x00\x00'
            if message_id == 0x1000:
                w.scans.append(Scan.from_buffer_copy(payload).channel_count)
                w.pending = True
                return b'\x00\x01'
            return b'\x00'

        def read():
            if not w.pending:
                return []
            w.pending = False
            if miss_cached and len(w.scans) == 1:
                return [(0x1001, b'\x00')]
            return [(0x1004, b'beacon'), (0x1001, b'\x00')]

        w.request = request
        w.read = read
        return w

    def test_uses_cached_channel_first(self):
        w = self.make_wifi()
        with patch.object(wifi, 'HERE', ReportPath()), patch.object(wifi, 'network', return_value=TARGET):
            result = w.scan(TARGET['ssid'], b'key')
        self.assertEqual(w.scans, [1])
        self.assertEqual(result[0]['ssid'], TARGET['ssid'])
        self.assertTrue(w.published[0][1]['merge_existing'])
        self.assertEqual(len(w.probed), 1)

    def test_configures_vht80_before_starting_firmware(self):
        w = self.make_wifi()
        calls = []
        original_request = w.request

        def request(message_id, payload=b'', confirmation=None):
            calls.append((message_id, payload))
            return original_request(message_id, payload, confirmation)

        w.request = request
        with patch.object(wifi, 'HERE', ReportPath()), \
             patch.object(wifi, 'network', return_value=TARGET):
            w.scan(TARGET['ssid'], b'key')
        ids = [message_id for message_id, _ in calls]
        self.assertLess(ids.index(0), ids.index(0x1400))
        self.assertLess(ids.index(0x1400), ids.index(0x1402))
        self.assertLess(ids.index(0x1402), ids.index(2))
        self.assertEqual(next(payload for message_id, payload in calls
                              if message_id == 0x1400),
                         me_config_request(enable_he=True))
        self.assertEqual(next(payload for message_id, payload in calls
                              if message_id == 0x1402),
                         me_channel_config_request())

    def test_falls_back_to_band_scan(self):
        w = self.make_wifi(miss_cached=True)
        with patch.object(wifi, 'HERE', ReportPath()), patch.object(wifi, 'network', return_value=TARGET):
            w.scan(TARGET['ssid'], b'key')
        self.assertEqual(w.scans, [1, 25])
        self.assertFalse(w.published[0][1]['merge_existing'])
        self.assertEqual(len(w.probed), 1)

    def test_native_scan_uses_requested_channel_without_app_report(self):
        w = self.make_wifi()
        w.target_band = None
        w.scan_observer = lambda item: None
        with patch.object(wifi, 'network', return_value=TARGET):
            w.scan(scan_frequencies=(5220,), publish_results=False)
        self.assertEqual(w.scans, [1])
        self.assertEqual(w.published, [])

    def test_native_join_scans_only_selected_channel_without_app_report(self):
        w = self.make_wifi()
        w.scan_observer = lambda item: None
        with patch.object(wifi, 'network', return_value=TARGET):
            w.scan(TARGET['ssid'], b'k' * 32,
                   scan_frequencies=(5200,), publish_results=False)
        self.assertEqual(w.scans, [1])
        self.assertEqual(w.published, [])
        self.assertEqual(len(w.probed), 1)

    def test_cleanup_usb_timeout_does_not_hide_join_failure(self):
        w = self.make_wifi()
        w.scan_observer = lambda item: None
        w.probe = lambda *args: (_ for _ in ()).throw(RuntimeError('native join failed'))
        original_request = w.request

        def request(message_id, payload=b'', confirmation=None):
            if message_id == 8:
                raise RuntimeError('USB write 0008: e0004051')
            return original_request(message_id, payload, confirmation)

        w.request = request
        with patch.object(wifi, 'network', return_value=TARGET):
            with self.assertRaisesRegex(RuntimeError, 'native join failed'):
                w.scan(TARGET['ssid'], b'k' * 32,
                       scan_frequencies=(5200,), publish_results=False)

    def test_menu_scan_does_not_interrupt_connection(self):
        controller = service.Controller()
        controller.config = lambda: {'enabled': True}
        controller.wifi = types.SimpleNamespace(active_vif=0)
        controller.interrupt = lambda: self.fail('active connection interrupted')
        self.assertEqual(controller.handle({'action': 'scan'}),
                         {'ok': True, 'scan_deferred': True})

    def test_menu_scan_does_not_restart_ongoing_scan(self):
        controller = service.Controller()
        controller.config = lambda: {'enabled': True}
        controller.wifi = types.SimpleNamespace(active_vif=None)
        controller.interrupt = lambda: self.fail('ongoing scan interrupted')
        self.assertEqual(controller.handle({'action': 'scan'}), {'ok': True})

    def test_first_use_scans_without_reading_empty_credential(self):
        done = threading.Event()
        calls = []

        class FakeController:
            def __init__(self):
                self.wake = threading.Event()
                self.wifi = None
                self.session_stop = None

            def start(self):
                pass

            def close(self):
                pass

            def interrupt(self):
                self.wake.set()

            def set_native_active(self, _value):
                pass

            def config(self):
                return {'ssid': '', 'enabled': True}

            def dongle_present(self):
                return True

        controller = FakeController()

        class FakeWifi:
            def __init__(self):
                self.native_stop = None

            def identity(self):
                calls.append('identity')

            def scan(self, ssid=None, key=None):
                calls.append(('scan', ssid, key))
                controller.wake.set()
                done.set()

            def close(self):
                calls.append('close')

        with patch.object(service, 'stop', done), \
             patch.object(service, 'Controller', return_value=controller), \
             patch.object(service, 'Wifi', FakeWifi), \
             patch.object(service.os, 'geteuid', return_value=0), \
             patch.object(service.signal, 'signal'), \
             patch.object(service, 'credential', side_effect=AssertionError('empty credential read')):
            service.main()
        self.assertEqual(calls, ['identity', ('scan', None, None), 'close'])

    def test_first_use_requests_password_then_saves_selection(self):
        controller = service.Controller()
        controller.config = lambda: {'ssid': '', 'enabled': True}
        saved = []
        interrupted = []
        controller.save = lambda config: saved.append(config.copy())
        controller.interrupt = lambda: interrupted.append(True)
        with patch.object(service, 'credential', side_effect=RuntimeError('not saved')):
            self.assertEqual(controller.handle({
                'action': 'select', 'ssid': 'New WPA2 Network', 'band': 1,
            }), {'ok': False, 'needs_password': True})
        with patch.object(service, 'store_credential') as store:
            response = controller.handle({
                'action': 'select', 'ssid': 'New WPA2 Network', 'band': 1,
                'pmk': 'ab' * 32,
            })
        self.assertEqual(response, {'ok': True})
        store.assert_called_once_with('New WPA2 Network', bytes.fromhex('ab' * 32))
        self.assertEqual(saved[0]['ssid'], 'New WPA2 Network')
        self.assertEqual(saved[0]['preferred_band'], 1)
        self.assertEqual(interrupted, [True])

    def test_legacy_menu_cannot_disable_native_mode_by_selecting_a_network(self):
        controller = service.Controller()
        controller.set_native_active(True)
        controller.config = lambda: {'enabled': True, 'native_enabled': True}
        controller.save = lambda _config: self.fail('native mode changed')
        controller.interrupt = lambda: self.fail('native session interrupted')
        with patch.object(service, 'credential') as credential:
            response = controller.handle({
                'action': 'select', 'ssid': 'Test Network 5G', 'band': 1,
            })
        self.assertFalse(response['ok'])
        credential.assert_not_called()


if __name__ == '__main__':
    unittest.main()
