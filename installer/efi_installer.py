#!/usr/bin/env python3
"""Install the tested AIC 8800D80 OpenCore components with rollback."""
import copy
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import tempfile
import urllib.parse

SUPPORT=Path('/Library/Application Support/AIC88M80Driver')
KEXT_SOURCE=SUPPORT/'Installer/Kexts'
GUID='7C436110-AB2A-4BBB-A880-FE41995C9F82'
KEXTS=('Lilu','AIC88M80ModeSwitch','BlueToolFixup','AICUSBTransportFixup')

def run(*args,**kwargs):
    return subprocess.run(args,check=True,**kwargs)

def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def boot_partition(output):
    value=output.split('\t',1)[-1]
    decoded=urllib.parse.unquote(value).replace('\x00','')
    if 'OpenCore.efi' not in decoded:
        raise RuntimeError('O Mac não iniciou por uma EFI OpenCore identificável.')
    match=re.search(r'<key>BLLastBSDName</key>\s*<string>(disk\d+s\d+)</string>',decoded)
    if not match:
        raise RuntimeError('Não foi possível identificar a partição EFI usada neste boot.')
    return match.group(1)

def kext_entry(name):
    executable='' if name=='Lilu' and False else f'Contents/MacOS/{name}'
    return {'Arch':'x86_64','BundlePath':name+'.kext',
        'Comment':'AIC 8800D80 installer' if name!='Lilu' else 'Lilu dependency',
        'Enabled':True,'ExecutablePath':executable,'MaxKernel':'24.99.99',
        'MinKernel':'24.0.0','PlistPath':'Contents/Info.plist'}

def prepare_config(config):
    changed=copy.deepcopy(config)
    try: entries=changed['Kernel']['Add']
    except (KeyError,TypeError): raise RuntimeError('Kernel/Add não foi encontrado no config.plist.')
    if not isinstance(entries,list):raise RuntimeError('Kernel/Add inválido no config.plist.')
    existing={}
    for entry in entries:
        path=entry.get('BundlePath') if isinstance(entry,dict) else None
        if path in {name+'.kext' for name in KEXTS}:
            if path in existing:raise RuntimeError('Há entradas duplicadas para '+path+'.')
            existing[path]=entry
    entries[:]=[entry for entry in entries if not isinstance(entry,dict) or
        entry.get('BundlePath') not in {name+'.kext' for name in KEXTS}]
    new=[]
    for name in KEXTS:
        path=name+'.kext';entry=copy.deepcopy(existing.get(path,kext_entry(name)))
        entry.update(BundlePath=path,Enabled=True,ExecutablePath=f'Contents/MacOS/{name}',
            PlistPath='Contents/Info.plist')
        if name!='Lilu':
            entry.update(Arch='x86_64',MinKernel='24.0.0',MaxKernel='24.99.99')
        new.append(entry)
    entries[0:0]=new
    try:
        add=changed['NVRAM']['Add'].setdefault(GUID,{})
        deletes=changed['NVRAM']['Delete'].setdefault(GUID,[])
    except (KeyError,TypeError):raise RuntimeError('Estrutura NVRAM inválida no config.plist.')
    args=add.get('boot-args','')
    if not isinstance(args,str):raise RuntimeError('boot-args não é texto.')
    words=args.split()
    for flag in ('-btlfxboardid','-aicusbfix'):
        if flag not in words:words.append(flag)
    add['boot-args']=' '.join(words)
    metadata={'bluetoothInternalControllerInfo':bytes(14),'bluetoothExternalDongleFailed':bytes(1)}
    add.update(metadata)
    if not isinstance(deletes,list):raise RuntimeError('NVRAM/Delete inválido.')
    for key in metadata:
        if key not in deletes:deletes.append(key)
    return changed

def verify_environment():
    if os.geteuid()!=0:raise RuntimeError('O instalador precisa ser executado como administrador.')
    if subprocess.check_output(['/usr/bin/uname','-m'],text=True).strip()!='x86_64':
        raise RuntimeError('Este pacote suporta somente Hackintosh Intel x86_64.')
    if subprocess.check_output(['/usr/bin/uname','-r'],text=True).split('.')[0]!='24':
        raise RuntimeError('Este pacote foi validado somente no macOS 15 Sequoia.')
    identities={'Lilu':'as.vit9696.Lilu','BlueToolFixup':'as.acidanthera.BlueToolFixup',
        'AIC88M80ModeSwitch':'local.victor.AIC88M80ModeSwitch',
        'AICUSBTransportFixup':'local.victor.AICUSBTransportFixup'}
    for name,identifier in identities.items():
        source=KEXT_SOURCE/(name+'.kext')
        info=plistlib.loads((source/'Contents/Info.plist').read_bytes())
        if info.get('CFBundleIdentifier')!=identifier or not (source/'Contents/MacOS'/name).is_file():
            raise RuntimeError('Componente inválido no pacote: '+name)
    lilu=plistlib.loads((KEXT_SOURCE/'Lilu.kext/Contents/Info.plist').read_bytes())
    if lilu.get('CFBundleVersion')!='1.7.3':raise RuntimeError('Versão Lilu inesperada no pacote.')

def locate_oc():
    raw=subprocess.check_output(['/usr/sbin/nvram','efi-boot-device'],text=True,errors='replace')
    device=boot_partition(raw)
    run('/usr/sbin/diskutil','mount',device,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    info=plistlib.loads(subprocess.check_output(['/usr/sbin/diskutil','info','-plist',device]))
    mount=Path(info.get('MountPoint',''))
    oc=mount/'EFI/OC'
    if not info.get('WritableVolume') or not (oc/'OpenCore.efi').is_file() or not (oc/'config.plist').is_file():
        raise RuntimeError('A EFI OpenCore usada no boot não está gravável ou está incompleta.')
    if (oc/'config.plist').is_symlink():raise RuntimeError('config.plist não pode ser link simbólico.')
    return device,oc

def install():
    verify_environment();device,oc=locate_oc();config_path=oc/'config.plist'
    original=config_path.read_bytes();config=plistlib.loads(original)
    output=plistlib.dumps(prepare_config(config),sort_keys=False)
    stamp=datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    backup=SUPPORT/'Backups'/('EFI-'+stamp)
    backup.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    shutil.copytree(oc,backup/'OC',symlinks=True)
    stage=Path(tempfile.mkdtemp(prefix='.aic-install-',dir=str(oc)))
    installed=[];displaced={};config_written=False
    try:
        pending=stage/'config.plist';pending.write_bytes(output)
        run('/usr/bin/plutil','-lint',str(pending),stdout=subprocess.PIPE)
        for name in KEXTS:
            source=KEXT_SOURCE/(name+'.kext');target=stage/(name+'.kext')
            shutil.copytree(source,target,symlinks=False)
        if config_path.read_bytes()!=original:raise RuntimeError('config.plist mudou durante a instalação.')
        for name in KEXTS:
            destination=oc/'Kexts'/(name+'.kext')
            if destination.is_symlink():raise RuntimeError('Destino EFI é link simbólico: '+name)
            if destination.exists():
                old=stage/('anterior-'+name+'.kext');os.rename(destination,old);displaced[destination]=old
            os.rename(stage/(name+'.kext'),destination);installed.append(destination)
        os.replace(pending,config_path);config_written=True
        if config_path.read_bytes()!=output:raise RuntimeError('A conferência do config.plist gravado falhou.')
        run('/bin/sync')
        record={'version':'1.0.2','installed_at':stamp,'efi_device':device,
            'backup':str(backup),'installed_config_sha256':hashlib.sha256(output).hexdigest()}
        (SUPPORT/'last-install.json').write_text(json.dumps(record,indent=2)+'\n')
        os.chmod(SUPPORT/'last-install.json',0o600)
    except BaseException:
        if config_written:config_path.write_bytes(original)
        for path in installed:
            if path.exists():shutil.rmtree(path)
        for destination,old in displaced.items():
            if old.exists():os.rename(old,destination)
        run('/bin/sync')
        raise
    finally:shutil.rmtree(stage,ignore_errors=True)
    print('EFI OpenCore atualizada. Backup: '+str(backup),flush=True)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--preflight',action='store_true')
    args=parser.parse_args()
    if args.preflight:
        verify_environment();print('AIC installer preflight: OK');return
    install()

if __name__=='__main__':main()
