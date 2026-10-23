#!/usr/bin/python3
"""Read-only comparison after an interrupted native package installation."""

from pathlib import Path
import plistlib
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'installer'))
from efi_installer import prepare_config


def load(path):
    return plistlib.loads(path.read_bytes())


def main():
    recovery = Path('/Users/victor/Documents/Codex/2026-10-19/so/work/aic-native-efi-test-recovery')
    current = load(Path('/Volumes/WINDOWSEFI/EFI/OC/config.plist'))
    original = load(recovery / 'config.plist')
    test = load(recovery / 'config-test.plist')
    expected = prepare_config(test)
    expected_without_native = prepare_config(original)
    current_without_native = dict(current)
    current_without_native['Kernel'] = dict(current['Kernel'])
    current_without_native['Kernel']['Add'] = [
        entry for entry in current['Kernel']['Add']
        if entry.get('BundlePath') != 'AICNativeProbe.kext']
    print('current_equals_test:', current == test)
    print('current_equals_legacy_after_test:', current == expected)
    print('current_without_native_equals_legacy_original:',
          current_without_native == expected_without_native)
    print('native_entries:', sum(entry.get('BundlePath') == 'AICNativeProbe.kext'
                                 for entry in current['Kernel']['Add']))


if __name__ == '__main__':
    main()
