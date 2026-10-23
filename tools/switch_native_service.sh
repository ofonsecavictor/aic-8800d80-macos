#!/bin/sh
# Reversible pilot: run the installed AIC daemon as the macOS native Wi-Fi
# radio bridge. Does not touch OpenCore, the kext, credentials, or saved networks.
set -eu

if [ "$#" -ne 1 ] ||
    { [ "$1" != '--activate' ] && [ "$1" != '--rollback' ]; } ||
    [ "$(/usr/bin/id -u)" -ne 0 ]; then
    echo 'Uso: sudo sh tools/switch_native_service.sh --activate | --rollback' >&2
    exit 2
fi

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
source_dir=$(CDPATH= cd -- "$script_dir/../wifi" && pwd)
support='/Library/Application Support/AIC88M80Driver/wifi'
helper="$support/aic-native-scan-request"
backup='/Library/Application Support/AIC88M80Driver/Backups/native-mode-pilot-20261021-0012-b'
profile="$support/profile.json"
service='system/local.victor.AIC88M80WiFi'

[ -d "$support" ] && [ -f "$profile" ] && [ -f "$support/service.py" ] || {
    echo 'Instalação AIC incompleta; nenhum arquivo alterado.' >&2
    exit 1
}

set_mode() {
    /usr/bin/python3 - "$profile" "$1" <<'PY'
import json
import os
from pathlib import Path
import sys

target = Path(sys.argv[1])
enabled = sys.argv[2] == 'true'
config = json.loads(target.read_text())
if not isinstance(config, dict):
    raise ValueError('Invalid AIC profile')
config['native_enabled'] = enabled
if enabled:
    config['native_scan_only'] = False
temporary = target.with_name(target.name + '.native-pilot-tmp')
descriptor = os.open(str(temporary), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
try:
    with os.fdopen(descriptor, 'w') as stream:
        json.dump(config, stream, ensure_ascii=False, separators=(',', ':'))
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(str(temporary), str(target))
except BaseException:
    try:
        temporary.unlink()
    except FileNotFoundError:
        pass
    raise
PY
}

restore() {
    [ -d "$backup/previous" ] && [ -f "$backup/profile-before.json" ] || {
        echo 'Backup do serviço anterior não encontrado; abortando.' >&2
        return 1
    }
    for old_file in "$backup/previous"/*.py; do
        [ -f "$old_file" ] || continue
        /usr/bin/install -o root -g wheel -m 644 "$old_file" \
            "$support/${old_file##*/}"
    done
    if [ -f "$backup/previous/aic-native-scan-request" ]; then
        /usr/bin/install -o root -g wheel -m 755 \
            "$backup/previous/aic-native-scan-request" "$helper"
    else
        /bin/rm -f "$helper"
    fi
    /usr/bin/install -o root -g wheel -m 600 "$backup/profile-before.json" "$profile"
    /bin/launchctl kickstart -k "$service"
    echo 'Serviço AIC anterior restaurado; a EFI não foi modificada.'
}

if [ "$1" = '--rollback' ]; then
    restore
    exit 0
fi

[ ! -e "$backup" ] || {
    echo 'Backup deste piloto já existe; nenhum arquivo será sobrescrito.' >&2
    exit 1
}
if ! /usr/bin/kmutil showloaded --list-only 2>/dev/null |
    /usr/bin/grep -Eq 'local\.victor\.AICNativeProbe \(0\.0\.12\)'; then
    echo 'Kext nativo 0.0.12 não está carregado; Wi-Fi atual intacto.' >&2
    exit 1
fi
if ! /bin/launchctl print "$service" >/dev/null 2>&1; then
    echo 'Serviço AIC atual não está registrado; Wi-Fi atual intacto.' >&2
    exit 1
fi
recovery_image='/Volumes/1401/AIC-EFI-backup-2026-10-21.9IZNSYSv/efi-disk0s4.img'
recovery_info=$(/usr/sbin/diskutil info -plist /Volumes/1401) || {
    echo 'Pendrive de recuperação 1401 ausente; nenhum arquivo alterado.' >&2
    exit 1
}
recovery_uuid=$(printf '%s\n' "$recovery_info" |
    /usr/bin/plutil -extract VolumeUUID raw - | /usr/bin/tr '[:upper:]' '[:lower:]')
if [ "$recovery_uuid" != '7f3560a7-f954-344b-a86f-51b971f855a4' ] ||
    [ ! -f "$recovery_image" ]; then
    echo 'Pendrive ou imagem de recuperação inesperados; nenhum arquivo alterado.' >&2
    exit 1
fi
image_sha=$(/usr/bin/shasum -a 256 "$recovery_image" | /usr/bin/awk '{print $1}')
if [ "$image_sha" != '4d2d24faac42c734543819504a2d7e88387196cdb5480a52291bb5bdb39b6e2b' ]; then
    echo 'Backup EFI não confere; nenhum arquivo alterado.' >&2
    exit 1
fi
/usr/bin/python3 - "$profile" <<'PY'
import json
import sys
config = json.load(open(sys.argv[1]))
if not config.get('enabled', False) or config.get('native_enabled', False):
    raise SystemExit('AIC profile is disabled or already native; no changes made')
PY

helper_stage=$(/usr/bin/mktemp -d /private/tmp/aic-native-helper.XXXXXXXX)
if ! /usr/bin/swiftc -module-cache-path "$helper_stage/module-cache" \
    "$script_dir/native_scan_request.swift" \
    -o "$helper_stage/aic-native-scan-request"; then
    /bin/rm -rf "$helper_stage"
    echo 'Não foi possível preparar o inicializador CoreWLAN; Wi-Fi atual intacto.' >&2
    exit 1
fi

/bin/mkdir -m 700 "$backup"
/bin/mkdir -m 700 "$backup/previous"
/bin/cp -p "$profile" "$backup/profile-before.json"
for source_file in "$source_dir"/*.py; do
    [ -f "$source_file" ] || continue
    target="$support/${source_file##*/}"
    if [ -f "$target" ]; then /bin/cp -p "$target" "$backup/previous/"; fi
done
if [ -f "$helper" ]; then /bin/cp -p "$helper" "$backup/previous/"; fi

changed=0
rollback_on_failure() {
    result=$?
    /bin/rm -rf "$helper_stage"
    if [ "$result" -ne 0 ] && [ "$changed" -eq 1 ]; then
        echo 'Ativação falhou; restaurando o serviço AIC anterior.' >&2
        restore || echo 'Reversão automática falhou; use --rollback.' >&2
    fi
}
trap rollback_on_failure EXIT

changed=1
for source_file in "$source_dir"/*.py; do
    [ -f "$source_file" ] || continue
    /usr/bin/install -o root -g wheel -m 644 "$source_file" \
        "$support/${source_file##*/}"
done
/usr/bin/install -o root -g wheel -m 755 \
    "$helper_stage/aic-native-scan-request" "$helper"
set_mode true
/bin/launchctl kickstart -k "$service"
echo 'Aguardando a interface nativa obter IP e rota (até 120 segundos)...'
ready=0
attempt=0
while [ "$attempt" -lt 40 ]; do
    attempt=$((attempt + 1))
    if /sbin/route -n get default 2>/dev/null |
            /usr/bin/grep -Eq '^[[:space:]]*interface: en2$' &&
        /sbin/ifconfig en2 2>/dev/null |
            /usr/bin/grep -Eq '^[[:space:]]*inet [0-9]+\.'; then
        if /usr/bin/curl --interface en2 --fail --silent --show-error \
                --location --output /dev/null --connect-timeout 4 \
                --max-time 12 https://www.apple.com/ &&
            /usr/bin/curl --interface en2 --fail --silent --show-error \
                --location --output /dev/null --connect-timeout 4 \
                --max-time 12 https://github.com/ &&
            /usr/bin/curl --interface en2 --fail --silent --show-error \
                --location --output /dev/null --connect-timeout 4 \
                --max-time 12 https://www.google.com/; then
            ready=1
            break
        fi
    fi
    /bin/sleep 3
done
[ "$ready" -eq 1 ] || {
    echo 'Conexão nativa não passou na verificação; revertendo.' >&2
    exit 1
}
echo 'IP, rota e três downloads completos pela en2 confirmados.'
echo 'Conferindo se a rota nativa permanece ativa por 20 segundos...'
/bin/sleep 20
/sbin/route -n get default 2>/dev/null |
    /usr/bin/grep -Eq '^[[:space:]]*interface: en2$' || {
        echo 'A rota nativa caiu; revertendo.' >&2
        exit 1
    }
trap - EXIT
/bin/rm -rf "$helper_stage"
echo 'Ponte nativa ativada; arquivos anteriores guardados em:'
echo "$backup"
echo 'Se precisar voltar: sudo sh tools/switch_native_service.sh --rollback'
