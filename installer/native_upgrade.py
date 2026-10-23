#!/usr/bin/env python3
"""Update a registered older AIC native installation to the current release.

This deliberately refuses every other starting point.  The OpenCore entry and
its original pre-native backup remain unchanged; only the bundle bytes and the
matching release record advance together.
"""

import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

from native_release import (BUNDLE_ID, PROFILE, RECORD, SUPPORT, VERSION,
                            boot_efi, sha256, unmount_if_needed,
                            validate_bundle, write_profile)


PREVIOUS_VERSIONS = ('0.0.15', '0.0.16', '0.0.17', '0.0.18', '0.0.19', '0.0.20', '0.0.21', '0.0.22')


def atomic_record(record):
    fd, name = tempfile.mkstemp(prefix='.native-record-', dir=RECORD.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(record, stream, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(name, 0o600)
        os.replace(name, RECORD)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def upgrade(candidate):
    if not RECORD.is_file():
        raise RuntimeError('Nenhuma instalação nativa anterior foi registrada')
    record = json.loads(RECORD.read_text())
    previous_version = record.get('version')
    original_record = dict(record)
    if previous_version not in PREVIOUS_VERSIONS:
        raise RuntimeError('A atualização requer um nativo entre 0.0.15 e 0.0.22')
    validate_bundle(candidate)
    device, oc, mounted_here = boot_efi()
    destination = oc / 'Kexts' / 'AICNativeProbe.kext'
    backup = SUPPORT / ('Backups/native-speed-' + previous_version)
    staged = None
    replaced = False
    try:
        if device != record.get('efi_device'):
            raise RuntimeError('A EFI atual difere da instalação registrada')
        config = oc / 'config.plist'
        if sha256(config) != record.get('installed_sha256'):
            raise RuntimeError('A configuração da EFI mudou; atualização recusada')
        if sha256(destination / 'Contents/MacOS/AICNativeProbe') != record.get('binary_sha256'):
            raise RuntimeError('O binário nativo atual não confere; atualização recusada')
        import plistlib
        info = plistlib.loads((destination / 'Contents/Info.plist').read_bytes())
        if (info.get('CFBundleIdentifier') != BUNDLE_ID or
                info.get('CFBundleVersion') != previous_version):
            raise RuntimeError('A identidade do driver atual não confere')
        if backup.exists():
            raise RuntimeError('Backup desta versão já existe; atualização recusada')
        backup.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        shutil.copytree(destination, backup, symlinks=False)
        if sha256(backup / 'Contents/MacOS/AICNativeProbe') != record['binary_sha256']:
            raise RuntimeError('Backup do driver atual não confere')
        staged = Path(tempfile.mkdtemp(prefix='.aic-native-upgrade-', dir=oc))
        shutil.copytree(candidate, staged / destination.name, symlinks=False)
        new_bundle = staged / destination.name
        new_binary = sha256(new_bundle / 'Contents/MacOS/AICNativeProbe')
        old = oc / ('Kexts/AICNativeProbe-pre-' + VERSION + '.kext')
        if old.exists():
            raise RuntimeError('Destino temporário de atualização já existe')
        os.rename(destination, old)
        try:
            os.rename(new_bundle, destination)
            replaced = True
            if sha256(destination / 'Contents/MacOS/AICNativeProbe') != new_binary:
                raise RuntimeError('Verificação do novo binário falhou')
            record['version'] = VERSION
            record['binary_sha256'] = new_binary
            record['upgrade_backup'] = str(backup)
            atomic_record(record)
            write_profile(True)
            shutil.rmtree(old)
            shutil.rmtree(staged)
            staged = None
            os.sync()
        except BaseException:
            if old.exists() and destination.exists():
                shutil.rmtree(destination)
            if old.exists():
                os.rename(old, destination)
                atomic_record(original_record)
            raise
    finally:
        if staged:
            shutil.rmtree(staged, ignore_errors=True)
        unmount_if_needed(device, mounted_here)


def main():
    if os.geteuid() != 0 or len(sys.argv) != 2:
        raise SystemExit('Uso: sudo native_upgrade.py CAMINHO_DO_KEXT')
    upgrade(Path(sys.argv[1]).resolve())
    print('Atualização nativa '+VERSION+' preparada; reinicie para ativar.')


if __name__ == '__main__':
    main()
