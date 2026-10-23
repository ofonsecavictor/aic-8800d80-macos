import threading
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import ANY, patch

import service


class NativeServiceSwitchTests(unittest.TestCase):
    def test_boot_usb_recovery_is_delayed_and_runs_only_once(self):
        previous = (service.native_usb_failure_since,
                    service.native_usb_recovery_attempted)
        try:
            service.native_usb_failure_since = None
            service.native_usb_recovery_attempted = False
            with patch.object(service.time, 'monotonic', return_value=100):
                service.note_native_usb_open_result(
                    RuntimeError('Cannot open AIC Wi-Fi interface: e00002bc'))
            with patch.object(service.time, 'monotonic', return_value=119), \
                    patch.object(service.ctypes, 'CDLL') as library:
                self.assertFalse(service.recover_stuck_native_usb())
                library.assert_not_called()
            with patch.object(service.time, 'monotonic', return_value=121), \
                    patch.object(service.ctypes, 'CDLL') as library, \
                    patch.object(service.stop, 'wait'):
                library.return_value.wifi_reenumerate_verified.return_value = 0
                self.assertTrue(service.recover_stuck_native_usb())
                self.assertFalse(service.recover_stuck_native_usb())
                library.assert_called_once()
        finally:
            (service.native_usb_failure_since,
             service.native_usb_recovery_attempted) = previous

    def test_other_usb_error_never_triggers_reenumeration(self):
        previous = (service.native_usb_failure_since,
                    service.native_usb_recovery_attempted)
        try:
            service.native_usb_failure_since = None
            service.native_usb_recovery_attempted = False
            service.note_native_usb_open_result(
                RuntimeError('Cannot open AIC Wi-Fi interface: e00002c0'))
            with patch.object(service.ctypes, 'CDLL') as library:
                self.assertFalse(service.recover_stuck_native_usb())
                library.assert_not_called()
        finally:
            (service.native_usb_failure_since,
             service.native_usb_recovery_attempted) = previous

    def test_native_power_retries_until_macos_accepts_interface(self):
        ready = threading.Event()
        ready.set()
        with patch.object(service, 'native_interface_name', return_value='en2'), \
                patch.object(service.subprocess, 'run', side_effect=[
                CompletedProcess([], 1, '', 'Wireless is not available.'),
                CompletedProcess([], 0, '', '')]) as run:
            self.assertTrue(service.request_native_power_when_ready(
                ready, threading.Event(), timeout=2, retry_delay=0))
        self.assertEqual(run.call_count, 2)

    def test_native_startup_uses_successful_pilot_corewlan_scan(self):
        ready = threading.Event()
        ready.set()
        with tempfile.TemporaryDirectory() as temporary:
            helper = Path(temporary) / 'aic-native-scan-request'
            helper.touch()
            with patch.object(service, 'HERE', Path(temporary)), \
                    patch.object(service, 'native_interface_name', return_value='en2'), \
                    patch.object(service.subprocess, 'run', side_effect=[
                        CompletedProcess([], 1, '', 'Wireless is not available.'),
                        CompletedProcess([], 0, 'COREWLAN_SCAN_COUNT=2', '')]) as run:
                self.assertTrue(service.request_native_power_when_ready(
                    ready, threading.Event(), timeout=2, retry_delay=0))
            self.assertEqual(run.call_args_list[1].args[0], [str(helper), 'en2'])

    def test_hotplug_powers_new_interface_instead_of_stale_en2(self):
        ready = threading.Event()
        ready.set()
        with patch.object(service, 'native_interface_name', return_value='en3'), \
                patch.object(service.subprocess, 'run', side_effect=[
                    CompletedProcess([], 0, '', '')]) as run:
            self.assertTrue(service.request_native_power_when_ready(
                ready, threading.Event(), timeout=2, retry_delay=0))
        self.assertEqual(run.call_args.args[0][-2:], ['en3', 'on'])

    def test_native_startup_retries_corewlan_after_registration_delay(self):
        ready = threading.Event()
        ready.set()
        with tempfile.TemporaryDirectory() as temporary:
            (Path(temporary) / 'aic-native-scan-request').touch()
            with patch.object(service, 'HERE', Path(temporary)), \
                    patch.object(service, 'native_interface_name', return_value='en2'), \
                    patch.object(service.subprocess, 'run', side_effect=[
                        CompletedProcess([], 1, '', 'Wireless is not available.'),
                        CompletedProcess([], 3, '', 'CoreWLAN interface unavailable'),
                        CompletedProcess([], 1, '', 'Wireless is not available.'),
                        CompletedProcess([], 0, 'COREWLAN_SCAN_COUNT=2', '')]) as run:
                self.assertTrue(service.request_native_power_when_ready(
                    ready, threading.Event(), timeout=2, retry_delay=0))
            self.assertEqual(run.call_count, 4)

    def test_native_power_does_not_start_after_session_stops(self):
        ready = threading.Event()
        ready.set()
        stopped = threading.Event()
        stopped.set()
        with patch.object(service, 'native_interface_name', return_value='en2'), \
                patch.object(service.subprocess, 'run') as run:
            self.assertFalse(service.request_native_power_when_ready(
                ready, stopped, timeout=1, retry_delay=0))
        run.assert_not_called()

    def test_legacy_menu_scan_cannot_interrupt_native_mode(self):
        controller = service.Controller()
        controller.set_native_active(True)
        with patch.object(controller, 'config', return_value={
                'enabled': True, 'native_enabled': True}):
            response = controller.handle({'action': 'scan'})
        self.assertFalse(response['ok'])
        self.assertFalse(controller.wake.is_set())

    def test_legacy_menu_power_changes_only_fallback_during_native_mode(self):
        controller = service.Controller()
        controller.set_native_active(True)
        with patch.object(controller, 'config', return_value={
                'enabled': True, 'native_enabled': True}), \
                patch.object(controller, 'save') as save, \
                patch.object(controller, 'interrupt') as interrupt:
            response = controller.handle({'action': 'power', 'enabled': False})
        self.assertTrue(response['ok'])
        saved = save.call_args.args[0]
        self.assertFalse(saved['enabled'])
        self.assertTrue(saved['native_enabled'])
        interrupt.assert_not_called()

    def test_legacy_menu_forget_cannot_disable_native_mode(self):
        controller = service.Controller()
        controller.set_native_active(True)
        with patch.object(controller, 'config', return_value={
                'enabled': True, 'native_enabled': True}), \
                patch.object(controller, 'save') as save, \
                patch.object(controller, 'interrupt') as interrupt:
            response = controller.handle({'action': 'forget', 'ssid': 'Example'})
        self.assertFalse(response['ok'])
        save.assert_not_called()
        interrupt.assert_not_called()

    def test_fallback_reports_legacy_mode_despite_native_preference(self):
        controller = service.Controller()
        with patch.object(controller, 'config', return_value={
                'enabled': True, 'native_enabled': True}), \
                patch.object(controller, 'dongle_present', return_value=True):
            response = controller.handle({'action': 'status'})
        self.assertFalse(response['native_mode'])
        self.assertTrue(response['native_preferred'])

    def test_fallback_menu_can_scan_despite_native_preference(self):
        controller = service.Controller()
        with patch.object(controller, 'config', return_value={
                'enabled': True, 'native_enabled': True}):
            response = controller.handle({'action': 'scan'})
        self.assertTrue(response['ok'])
        self.assertTrue(controller.wake.is_set())

    def test_fallback_selection_preserves_native_preference(self):
        controller = service.Controller()
        saved = []
        with patch.object(controller, 'config', return_value={
                'enabled': True, 'native_enabled': True}), \
                patch.object(controller, 'save', side_effect=lambda value: saved.append(value.copy())), \
                patch.object(controller, 'interrupt'), \
                patch.object(service, 'credential', return_value=b'x' * 32):
            response = controller.handle({'action': 'select',
                                          'ssid': 'Example', 'band': 1})
        self.assertTrue(response['ok'])
        self.assertTrue(saved[0]['native_enabled'])

    def test_disabling_legacy_app_still_starts_native_session(self):
        done = threading.Event()
        controller = service.Controller()
        with patch.object(service, 'stop', done), \
                patch.object(service, 'Controller', return_value=controller), \
                patch.object(service.os, 'geteuid', return_value=0), \
                patch.object(service.signal, 'signal'), \
                patch.object(controller, 'config', return_value={
                    'enabled': False, 'native_enabled': True}), \
                patch.object(controller, 'dongle_present', return_value=True), \
                patch.object(controller, 'start'), \
                patch.object(controller, 'close'), \
                patch.object(service, 'run_native_session_if_available',
                             side_effect=lambda *_args, **_kwargs: done.set() or True) as native:
            service.main()
        native.assert_called_once()

    def test_failed_native_start_never_opens_legacy_connection(self):
        done = threading.Event()
        controller = service.Controller()
        scans = []

        class LegacyWifi:
            mac = None

            def identity(self):
                return {}

            def scan(self, ssid, key):
                scans.append((ssid, key, self.native_stop.is_set()))
                done.set()

            def close(self):
                pass

        def failed_native(_config, native_stop, **_kwargs):
            native_stop.set()
            return False

        with patch.object(service, 'stop', done), \
                patch.object(service, 'Controller', return_value=controller), \
                patch.object(service.os, 'geteuid', return_value=0), \
                patch.object(service.signal, 'signal'), \
                patch.object(controller, 'config', return_value={
                    'ssid': 'Example', 'enabled': True, 'native_enabled': True}), \
                patch.object(controller, 'dongle_present', return_value=True), \
                patch.object(controller, 'start'), \
                patch.object(controller, 'close'), \
                patch.object(controller.wake, 'wait', side_effect=lambda *_: done.set()), \
                patch.object(service, 'recover_stuck_native_usb', return_value=False), \
                patch.object(service, 'run_native_session_if_available',
                             side_effect=failed_native), \
                patch.object(service, 'optional_radio_bridge', return_value=None), \
                patch.object(service, 'credential', return_value=b'key'), \
                patch.object(service, 'Wifi', LegacyWifi):
            service.main()
        self.assertEqual(scans, [])

    def test_disabled_mode_does_not_open_native_controller(self):
        with patch.object(service, 'optional_radio_bridge') as opener:
            self.assertFalse(service.run_native_session_if_available(
                {'native_enabled': False}, threading.Event()))
            opener.assert_not_called()

    def test_missing_controller_falls_back_without_opening_usb(self):
        with patch.object(service, 'optional_radio_bridge', return_value=None), \
                patch.object(service, 'Wifi') as wifi:
            self.assertFalse(service.run_native_session_if_available(
                {'native_enabled': True}, threading.Event()))
            wifi.assert_not_called()

    def test_native_mode_needs_no_legacy_saved_ssid_or_credential(self):
        stop = threading.Event()
        with patch.object(service, 'optional_radio_bridge') as opener, \
                patch.object(service, 'Wifi') as wifi, \
                patch.object(service, 'NativeScanSession') as session, \
                patch.object(service, 'credential') as credential:
            self.assertTrue(service.run_native_session_if_available(
                {'native_enabled': True}, stop))
            session.assert_called_once_with(wifi.return_value,
                                            opener.return_value, stop,
                                            scan_only=False, ready=ANY)
            session.return_value.run.assert_called_once_with()
            self.assertIs(wifi.return_value.native_stop, stop)
            opener.return_value.close.assert_called_once_with()
            credential.assert_not_called()

    def test_native_mode_callback_clears_when_session_ends(self):
        stop = threading.Event()
        changes = []
        with patch.object(service, 'optional_radio_bridge'), \
                patch.object(service, 'Wifi'), \
                patch.object(service, 'NativeScanSession'):
            self.assertTrue(service.run_native_session_if_available(
                {'native_enabled': True}, stop, on_mode_change=changes.append))
        self.assertEqual(changes, [True, False])

    def test_native_power_failure_returns_dongle_to_fallback(self):
        stopped = threading.Event()
        with patch.object(service, 'optional_radio_bridge'), \
                patch.object(service, 'Wifi'), \
                patch.object(service, 'NativeScanSession') as session, \
                patch.object(service, 'request_native_power_when_ready',
                             return_value=False):
            session.return_value.run.side_effect = lambda: stopped.wait(1)
            self.assertFalse(service.run_native_session_if_available(
                {'native_enabled': True}, stopped))
        self.assertTrue(stopped.is_set())

    def test_scan_only_mode_cannot_join(self):
        with patch.object(service, 'optional_radio_bridge') as opener, \
                patch.object(service, 'Wifi') as wifi, \
                patch.object(service, 'NativeScanSession') as session:
            self.assertTrue(service.run_native_session_if_available(
                {'native_enabled': True, 'native_scan_only': True},
                threading.Event()))
            self.assertTrue(session.call_args.kwargs['scan_only'])

    def test_constructor_failure_releases_usb_and_user_client(self):
        with patch.object(service, 'optional_radio_bridge') as opener, \
                patch.object(service, 'Wifi') as wifi, \
                patch.object(service, 'NativeScanSession',
                             side_effect=RuntimeError('setup failed')):
            self.assertFalse(service.run_native_session_if_available(
                {'native_enabled': True}, threading.Event()))
            wifi.return_value.close.assert_called_once_with()
            opener.return_value.close.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
