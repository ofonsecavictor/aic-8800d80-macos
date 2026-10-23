import importlib.util
import json
from pathlib import Path
import plistlib
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'installer'))
import native_upgrade as upgrade


class NativeUpgradeTests(unittest.TestCase):
    def exercise(self, fail_profile=False, previous_version='0.0.16'):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            support = root / 'support'
            support.mkdir()
            oc = root / 'OC'
            old = oc / 'Kexts/AICNativeProbe.kext'
            candidate = root / 'candidate.kext'
            for bundle, version, binary in ((old, previous_version, b'old'),
                                             (candidate, upgrade.VERSION, b'new')):
                (bundle / 'Contents/MacOS').mkdir(parents=True)
                (bundle / 'Contents/MacOS/AICNativeProbe').write_bytes(binary)
                (bundle / 'Contents/Info.plist').write_bytes(plistlib.dumps({
                    'CFBundleIdentifier': upgrade.BUNDLE_ID,
                    'CFBundleVersion': version}))
            (oc / 'config.plist').write_bytes(b'preserved config')
            record = {'version': previous_version, 'efi_device': 'disk0s4',
                      'installed_sha256': upgrade.sha256(oc / 'config.plist'),
                      'binary_sha256': upgrade.sha256(old / 'Contents/MacOS/AICNativeProbe')}
            record_path = support / 'native-release.json'
            record_path.write_text(json.dumps(record))
            with patch.object(upgrade, 'SUPPORT', support), \
                    patch.object(upgrade, 'RECORD', record_path), \
                    patch.object(upgrade, 'boot_efi', return_value=('disk0s4', oc, False)), \
                    patch.object(upgrade, 'unmount_if_needed'), \
                    patch.object(upgrade.os, 'sync'), \
                    patch.object(upgrade, 'write_profile',
                                 side_effect=RuntimeError('profile failure') if fail_profile else None):
                if fail_profile:
                    with self.assertRaisesRegex(RuntimeError, 'profile failure'):
                        upgrade.upgrade(candidate)
                    self.assertEqual(json.loads(record_path.read_text()), record)
                    self.assertEqual((old / 'Contents/MacOS/AICNativeProbe').read_bytes(), b'old')
                else:
                    upgrade.upgrade(candidate)
                    self.assertEqual(json.loads(record_path.read_text())['version'], upgrade.VERSION)
                    self.assertEqual((old / 'Contents/MacOS/AICNativeProbe').read_bytes(), b'new')
                self.assertEqual((oc / 'config.plist').read_bytes(), b'preserved config')
                self.assertEqual((support / ('Backups/native-speed-' + previous_version) / 'Contents/MacOS/AICNativeProbe').read_bytes(), b'old')

    def test_upgrade_from_0016_preserves_config_and_backup(self):
        self.exercise()

    def test_profile_failure_restores_driver_and_record(self):
        self.exercise(fail_profile=True)

    def test_upgrade_from_panic_version_0017(self):
        self.exercise(previous_version='0.0.17')

    def test_upgrade_from_stable_0018(self):
        self.exercise(previous_version='0.0.18')

    def test_upgrade_from_airdrop_preview_0019(self):
        self.exercise(previous_version='0.0.19')

    def test_upgrade_from_airdrop_preview_0020(self):
        self.exercise(previous_version='0.0.20')

    def test_upgrade_from_airdrop_preview_0021(self):
        self.exercise(previous_version='0.0.21')

    def test_upgrade_from_panicking_airdrop_preview_0022(self):
        self.exercise(previous_version='0.0.22')

    def test_upgrade_from_stable_airdrop_0023(self):
        self.exercise(previous_version='0.0.23')
