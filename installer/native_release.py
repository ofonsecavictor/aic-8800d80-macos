#!/usr/bin/env python3
"""Prepare or undo the AIC native OpenCore entry without touching other kexts.

The EFI writer is deliberately separate from the legacy AIC installer.  A
native release keeps the legacy app and its saved profile as the recovery path.
"""

import copy
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tempfile
import time


SUPPORT = Path('/Library/Application Support/AIC88M80Driver')
KEXT_NAME = 'AICNativeProbe.kext'
BUNDLE_ID = 'local.victor.AICNativeProbe'
VERSION = '0.0.24'
RECORD = SUPPORT / 'native-release.json'
PROFILE = SUPPORT / 'wifi/profile.json'
VOLUMES = Path('/Volumes')


def native_entry():
    return {
        'Arch': 'x86_64',
        'BundlePath': KEXT_NAME,
        'Comment': 'AIC 8800D80 native Wi-Fi (reversible)',
        'Enabled': True,
        'ExecutablePath': 'Contents/MacOS/AICNativeProbe',
        'MaxKernel': '24.6.0',
        'MinKernel': '24.6.0',
        'PlistPath': 'Contents/Info.plist',
    }


def add_native_entry(config):
    result = copy.deepcopy(config)
    entries = result['Kernel']['Add']
    if not isinstance(entries, list):
        raise ValueError('Kernel/Add inválido')
    if any(isinstance(item, dict) and item.get('BundlePath') == KEXT_NAME
           for item in entries):
        raise ValueError('A EFI já contém AICNativeProbe; não sobrescrever')
    entries.append(native_entry())
    return result


def switch_profile(profile, native):
    """Change only the native preference; never overwrite saved networks."""
    result = copy.deepcopy(profile)
    if not isinstance(result, dict):
        raise ValueError('Perfil AIC inválido')
    result['native_enabled'] = bool(native)
    if native:
        result['native_scan_only'] = False
    return result


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def run(*args):
    return subprocess.run(args, check=True, capture_output=True)


def boot_efi():
    """Resolve the OpenCore EFI actually used for this boot."""
    from efi_installer import boot_partition
    raw = run('/usr/sbin/nvram', 'efi-boot-device').stdout.decode('utf-8', 'replace')
    device = boot_partition(raw)
    info = plistlib.loads(run('/usr/sbin/diskutil', 'info', '-plist', device).stdout)
    if info.get('DeviceIdentifier') != device or info.get('Content') != 'EFI' or not info.get('Internal'):
        raise RuntimeError('A EFI usada no boot não é a EFI interna esperada')
    mounted_here = not info.get('MountPoint')
    if mounted_here:
        run('/usr/sbin/diskutil', 'mount', device)
        info = plistlib.loads(run('/usr/sbin/diskutil', 'info', '-plist', device).stdout)
    mount = Path(info.get('MountPoint') or '')
    oc = mount / 'EFI/OC'
    if not (oc / 'OpenCore.efi').is_file() or not (oc / 'config.plist').is_file():
        if mounted_here:
            run('/usr/sbin/diskutil', 'unmount', device)
        raise RuntimeError('OpenCore não encontrado na EFI usada no boot')
    return device, oc, mounted_here


def unmount_if_needed(device, mounted_here):
    if mounted_here:
        for attempt in range(6):
            try:
                run('/usr/sbin/diskutil', 'unmount', device)
                return
            except subprocess.CalledProcessError:
                if attempt == 5:
                    raise
                time.sleep(3)


def validate_bundle(bundle):
    info = plistlib.loads((bundle / 'Contents/Info.plist').read_bytes())
    binary = bundle / 'Contents/MacOS/AICNativeProbe'
    if info.get('CFBundleIdentifier') != BUNDLE_ID or info.get('CFBundleVersion') != VERSION or not binary.is_file():
        raise RuntimeError('Pacote nativo inesperado; nenhum arquivo alterado')
    return binary


def recovery_volume_valid(mount, info):
    """Accept a mounted external USB only when it contains a bootable OpenCore."""
    return (info.get('MountPoint') == str(mount) and
            not info.get('Internal', True) and
            str(info.get('BusProtocol', '')).upper() == 'USB' and
            (mount / 'EFI/BOOT/BOOTx64.efi').is_file() and
            (mount / 'EFI/OC/OpenCore.efi').is_file())


def verify_external_recovery():
    """Require a generic, mounted OpenCore recovery USB before editing EFI."""
    if VOLUMES.is_dir():
        for mount in sorted(VOLUMES.iterdir()):
            try:
                info = plistlib.loads(run('/usr/sbin/diskutil', 'info',
                                           '-plist', str(mount)).stdout)
            except (OSError, subprocess.CalledProcessError, plistlib.InvalidFileException):
                continue
            if recovery_volume_valid(mount, info):
                return str(mount)
    raise RuntimeError(
        'Conecte e monte um pendrive USB bootável com EFI/BOOT/BOOTx64.efi '
        'e EFI/OC/OpenCore.efi; a EFI interna permaneceu intacta')


def write_profile(native):
    current = json.loads(PROFILE.read_text())
    payload = json.dumps(switch_profile(current, native), ensure_ascii=False,
                         separators=(',', ':')).encode() + b'\n'
    fd, name = tempfile.mkstemp(prefix='.native-profile-', dir=PROFILE.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, PROFILE)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def install(bundle):
    if RECORD.exists():
        raise RuntimeError('Instalação nativa já registrada; não sobrescrever backup')
    validate_bundle(bundle)
    verify_external_recovery()
    device, oc, mounted_here = boot_efi()
    config = oc / 'config.plist'
    destination = oc / 'Kexts' / KEXT_NAME
    if destination.exists() or destination.is_symlink():
        unmount_if_needed(device, mounted_here)
        raise RuntimeError('Driver nativo já existe na EFI; reverta o teste anterior antes de instalar')
    original = config.read_bytes()
    updated = plistlib.dumps(add_native_entry(plistlib.loads(original)), sort_keys=False)
    # Reinstallation after rollback must preserve the previous recovery copy.
    backup_root = SUPPORT / 'Backups'
    backup_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix='native-release-', dir=backup_root))
    (backup / 'config-before.plist').write_bytes(original)
    os.chmod(backup / 'config-before.plist', 0o600)
    staged = Path(tempfile.mkdtemp(prefix='.aic-native-', dir=oc))
    changed = False
    recorded = False
    try:
        shutil.copytree(bundle, staged / KEXT_NAME, symlinks=False)
        (staged / 'config.plist').write_bytes(updated)
        run('/usr/bin/plutil', '-lint', str(staged / 'config.plist'))
        if config.read_bytes() != original:
            raise RuntimeError('config.plist mudou durante a preparação')
        os.rename(staged / KEXT_NAME, destination)
        changed = True
        os.replace(staged / 'config.plist', config)
        if config.read_bytes() != updated:
            raise RuntimeError('Verificação da EFI falhou')
        run('/bin/sync')
        record = {'version': VERSION, 'efi_device': device,
                  'original_sha256': hashlib.sha256(original).hexdigest(),
                  'installed_sha256': hashlib.sha256(updated).hexdigest(),
                  'binary_sha256': sha256(destination / 'Contents/MacOS/AICNativeProbe'),
                  'backup': str(backup / 'config-before.plist')}
        RECORD.write_text(json.dumps(record, indent=2) + '\n')
        os.chmod(RECORD, 0o600)
        recorded = True
        write_profile(True)
    except BaseException:
        if changed:
            config.write_bytes(original)
            shutil.rmtree(destination, ignore_errors=True)
            run('/bin/sync')
        if recorded:
            RECORD.unlink()
        raise
    finally:
        shutil.rmtree(staged, ignore_errors=True)
        unmount_if_needed(device, mounted_here)


def rollback():
    record = json.loads(RECORD.read_text())
    device, oc, mounted_here = boot_efi()
    try:
        if device != record['efi_device']:
            raise RuntimeError('A EFI atual difere da instalação registrada')
        config = oc / 'config.plist'
        destination = oc / 'Kexts' / KEXT_NAME
        original = Path(record['backup']).read_bytes()
        if hashlib.sha256(original).hexdigest() != record['original_sha256']:
            raise RuntimeError('Backup da configuração não confere')
        if sha256(config) != record['installed_sha256']:
            raise RuntimeError('A configuração da EFI mudou; não sobrescrever')
        if sha256(destination / 'Contents/MacOS/AICNativeProbe') != record['binary_sha256']:
            raise RuntimeError('O driver nativo mudou; não remover')
        info = plistlib.loads((destination / 'Contents/Info.plist').read_bytes())
        if info.get('CFBundleIdentifier') != BUNDLE_ID or info.get('CFBundleVersion') != VERSION:
            raise RuntimeError('Identidade do driver nativo mudou; não remover')
        write_profile(False)
        config.write_bytes(original)
        (destination / 'Contents/MacOS/AICNativeProbe').unlink()
        (destination / 'Contents/Info.plist').unlink()
        (destination / 'Contents/MacOS').rmdir()
        (destination / 'Contents').rmdir()
        destination.rmdir()
        run('/bin/sync')
        if sha256(config) != record['original_sha256'] or destination.exists():
            raise RuntimeError('A reversão da EFI não foi confirmada')
        RECORD.unlink()
        run('/bin/launchctl', 'kickstart', '-k',
            'system/local.victor.AIC88M80WiFi')
    finally:
        unmount_if_needed(device, mounted_here)


def verify_installed():
    """Check an existing native install before replacing userspace files."""
    record = json.loads(RECORD.read_text())
    if record.get('version') != VERSION:
        raise RuntimeError('Versão nativa instalada diferente; atualização recusada')
    device, oc, mounted_here = boot_efi()
    try:
        if device != record['efi_device']:
            raise RuntimeError('A EFI atual difere da instalação registrada')
        config = oc / 'config.plist'
        bundle = oc / 'Kexts' / KEXT_NAME
        if sha256(config) != record['installed_sha256'] or \
                sha256(bundle / 'Contents/MacOS/AICNativeProbe') != record['binary_sha256'] or \
                sha256(Path(record['backup'])) != record['original_sha256']:
            raise RuntimeError('A instalação nativa na EFI mudou; atualização recusada')
        validate_bundle(bundle)
    finally:
        unmount_if_needed(device, mounted_here)


def main():
    if os.geteuid() != 0 or len(sys.argv) not in (2, 3):
        raise SystemExit('Uso: sudo native_release.py --install BUNDLE | --rollback | --verify')
    if sys.argv[1] == '--install' and len(sys.argv) == 3:
        install(Path(sys.argv[2]).resolve())
        print('Wi-Fi nativo preparado; reinicie para ativar.')
    elif sys.argv[1] == '--rollback' and len(sys.argv) == 2:
        rollback()
        print('EFI restaurada e AIC selecionado; reinicie para descarregar o driver nativo.')
    elif sys.argv[1] == '--verify' and len(sys.argv) == 2:
        verify_installed()
        print('Instalação nativa existente verificada; EFI preservada.')
    else:
        raise SystemExit('Argumentos inválidos')


if __name__ == '__main__':
    main()
