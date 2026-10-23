import importlib.util
from pathlib import Path
import json
import plistlib
import tempfile
import unittest
from unittest import mock


SOURCE = Path(__file__).resolve().parents[1] / 'installer/native_release.py'
SPEC = importlib.util.spec_from_file_location('native_release', SOURCE)
native_release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(native_release)


class NativeReleaseConfigTests(unittest.TestCase):
    def test_generic_usb_opencore_recovery_is_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            mount = Path(directory) / 'Recovery'
            (mount / 'EFI/BOOT').mkdir(parents=True)
            (mount / 'EFI/OC').mkdir(parents=True)
            (mount / 'EFI/BOOT/BOOTx64.efi').write_bytes(b'boot')
            (mount / 'EFI/OC/OpenCore.efi').write_bytes(b'oc')
            info = {'MountPoint': str(mount), 'Internal': False,
                    'BusProtocol': 'USB'}
            self.assertTrue(native_release.recovery_volume_valid(mount, info))

    def test_internal_or_incomplete_recovery_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            mount = Path(directory) / 'Recovery'
            (mount / 'EFI/BOOT').mkdir(parents=True)
            (mount / 'EFI/BOOT/BOOTx64.efi').write_bytes(b'boot')
            info = {'MountPoint': str(mount), 'Internal': True,
                    'BusProtocol': 'USB'}
            self.assertFalse(native_release.recovery_volume_valid(mount, info))

    def test_add_entry_does_not_modify_other_kexts(self):
        original = {'Kernel': {'Add': [{'BundlePath': 'Lilu.kext', 'Enabled': True}]}}
        updated = native_release.add_native_entry(original)
        self.assertEqual(len(updated['Kernel']['Add']), 2)
        self.assertEqual(updated['Kernel']['Add'][0], original['Kernel']['Add'][0])
        self.assertEqual(updated['Kernel']['Add'][1], native_release.native_entry())
        self.assertEqual(len(original['Kernel']['Add']), 1)

    def test_existing_native_entry_is_rejected(self):
        config = {'Kernel': {'Add': [native_release.native_entry()]}}
        with self.assertRaises(ValueError):
            native_release.add_native_entry(config)

    def test_switch_profile_preserves_network_and_fallback_power(self):
        profile = {'ssid': 'Example', 'enabled': False, 'preferred_band': 1,
                   'credential': 'System Keychain', 'native_scan_only': True}
        native = native_release.switch_profile(profile, True)
        self.assertTrue(native['native_enabled'])
        self.assertFalse(native['native_scan_only'])
        self.assertFalse(native['enabled'])
        self.assertEqual(native['ssid'], 'Example')
        self.assertNotIn('native_enabled', profile)
        legacy = native_release.switch_profile(native, False)
        self.assertFalse(legacy['native_enabled'])
        self.assertFalse(legacy['enabled'])
        self.assertEqual(legacy['credential'], 'System Keychain')

    def test_install_and_rollback_preserve_saved_network(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            support = root / 'support'
            (support / 'wifi').mkdir(parents=True)
            profile = support / 'wifi/profile.json'
            profile.write_text(json.dumps({'ssid': 'Example', 'enabled': True,
                                           'credential': 'System Keychain'}))
            oc = root / 'EFI/OC'
            (oc / 'Kexts').mkdir(parents=True)
            original = {'Kernel': {'Add': [{'BundlePath': 'Lilu.kext',
                                           'Enabled': True}]}}
            config = oc / 'config.plist'
            config.write_bytes(plistlib.dumps(original))
            bundle = root / 'source.kext'
            (bundle / 'Contents/MacOS').mkdir(parents=True)
            (bundle / 'Contents/Info.plist').write_bytes(plistlib.dumps({
                'CFBundleIdentifier': native_release.BUNDLE_ID,
                'CFBundleVersion': native_release.VERSION}))
            (bundle / 'Contents/MacOS/AICNativeProbe').write_bytes(b'probe')

            real_run = native_release.run
            def run_without_launchctl(*args):
                if args[:2] == ('/bin/launchctl', 'kickstart'):
                    return None
                return real_run(*args)

            with mock.patch.object(native_release, 'SUPPORT', support), \
                    mock.patch.object(native_release, 'PROFILE', profile), \
                    mock.patch.object(native_release, 'RECORD', support / 'native-release.json'), \
                    mock.patch.object(native_release, 'verify_external_recovery'), \
                    mock.patch.object(native_release, 'boot_efi', return_value=('disk0s4', oc, False)), \
                    mock.patch.object(native_release, 'run', side_effect=run_without_launchctl):
                native_release.install(bundle)
                updated = plistlib.loads(config.read_bytes())
                self.assertEqual(updated['Kernel']['Add'][-1], native_release.native_entry())
                self.assertTrue(json.loads(profile.read_text())['native_enabled'])
                native_release.verify_installed()
                native_release.rollback()
                self.assertEqual(plistlib.loads(config.read_bytes()), original)
                restored = json.loads(profile.read_text())
                self.assertEqual(restored['ssid'], 'Example')
                self.assertFalse(restored['native_enabled'])
                self.assertFalse((oc / 'Kexts' / native_release.KEXT_NAME).exists())
                backups_before = set((support / 'Backups').iterdir())
                native_release.install(bundle)
                self.assertTrue(backups_before < set((support / 'Backups').iterdir()))
                native_release.verify_installed()
                native_release.rollback()
                self.assertEqual(plistlib.loads(config.read_bytes()), original)


if __name__ == '__main__':
    unittest.main()
