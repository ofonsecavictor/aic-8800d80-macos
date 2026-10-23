#!/bin/sh
# Replace only the AIC daemon source; leave EFI, kext, app and profile intact.
set -eu

if [ "$#" -ne 0 ] || [ "$(/usr/bin/id -u)" -ne 0 ]; then
    echo 'Uso: sudo sh tools/install_native_power_retry.sh' >&2
    exit 2
fi

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
source_file="$script_dir/../wifi/service.py"
installed_file='/Library/Application Support/AIC88M80Driver/wifi/service.py'
backup_root='/Library/Application Support/AIC88M80Driver/Backups'
service='system/local.victor.AIC88M80WiFi'

[ -f "$source_file" ] && [ -f "$installed_file" ] &&
    /bin/launchctl print "$service" >/dev/null 2>&1 || {
    echo 'Serviço AIC não corresponde ao esperado; nenhum arquivo alterado.' >&2
    exit 1
}

/bin/mkdir -p "$backup_root"
backup=$(/usr/bin/mktemp -d "$backup_root/native-power-retry-XXXXXXXX")
/bin/cp -p "$installed_file" "$backup/service.py"
echo "Backup recuperável: $backup/service.py"

changed=0
on_exit() {
    result=$?
    if [ "$result" -ne 0 ] && [ "$changed" -eq 1 ]; then
        /bin/cp -p "$backup/service.py" "$installed_file"
        /bin/launchctl kickstart -k "$service" || true
        echo 'Serviço anterior restaurado após falha.' >&2
    fi
}
trap on_exit EXIT

changed=1
/usr/bin/install -o root -g wheel -m 644 "$source_file" "$installed_file"
/bin/launchctl kickstart -k "$service"
trap - EXIT
echo 'Serviço AIC reiniciado com novas tentativas de ativação nativa.'
