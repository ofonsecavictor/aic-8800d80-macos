#!/bin/sh
# Install the native-mode menu guard without changing the EFI or Wi-Fi profile.
# The previous service and full app bundle remain in a unique backup folder.
set -eu

if [ "$#" -ne 1 ] || [ "$(/usr/bin/id -u)" -ne 0 ] || [ ! -f "$1" ]; then
    echo 'Uso: sudo sh tools/install_native_menu_guard.sh <menu-binario-compilado>' >&2
    exit 2
fi

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
source_service="$script_dir/../wifi/service.py"
installed_service='/Library/Application Support/AIC88M80Driver/wifi/service.py'
app='/Applications/AIC Wi-Fi.app'
app_binary="$app/Contents/MacOS/AIC Wi-Fi"
agent='/Library/LaunchAgents/local.victor.AICWiFiMenu.plist'
service='system/local.victor.AIC88M80WiFi'
backup_root='/Library/Application Support/AIC88M80Driver/Backups'

[ -f "$source_service" ] && [ -f "$installed_service" ] &&
    [ -f "$app_binary" ] && [ -f "$agent" ] &&
    /bin/launchctl print "$service" >/dev/null 2>&1 || {
    echo 'Instalação AIC não corresponde ao esperado; nenhum arquivo alterado.' >&2
    exit 1
}
console_uid=$(/usr/bin/stat -f %u /dev/console)
console_user=$(/usr/bin/stat -f %Su /dev/console)
if [ "$console_uid" -lt 500 ] || [ "$console_user" = loginwindow ]; then
    echo 'Nenhuma sessão de usuário ativa; nenhum arquivo alterado.' >&2
    exit 1
fi

/bin/mkdir -p "$backup_root"
backup=$(/usr/bin/mktemp -d "$backup_root/native-menu-guard-XXXXXXXX")
/bin/cp -p "$installed_service" "$backup/service.py"
/usr/bin/ditto "$app" "$backup/AIC Wi-Fi.app"
echo "Backup recuperável: $backup"

changed=0
restore() {
    /bin/launchctl bootout "gui/$console_uid" "$agent" >/dev/null 2>&1 || true
    /usr/bin/pkill -u "$console_uid" -f '/Applications/AIC Wi-Fi.app/Contents/MacOS/AIC Wi-Fi$' >/dev/null 2>&1 || true
    /bin/cp -p "$backup/service.py" "$installed_service"
    /usr/bin/ditto "$backup/AIC Wi-Fi.app" "$app"
    /bin/launchctl kickstart -k "$service" || true
    /bin/launchctl bootstrap "gui/$console_uid" "$agent" || true
    echo 'Arquivos originais restaurados após falha.' >&2
}
on_exit() {
    result=$?
    if [ "$result" -ne 0 ] && [ "$changed" -eq 1 ]; then restore; fi
}
trap on_exit EXIT

/bin/launchctl bootout "gui/$console_uid" "$agent" >/dev/null 2>&1 || true
/usr/bin/pkill -u "$console_uid" -f '/Applications/AIC Wi-Fi.app/Contents/MacOS/AIC Wi-Fi$' >/dev/null 2>&1 || true
changed=1
/usr/bin/install -o root -g wheel -m 644 "$source_service" "$installed_service"
/usr/bin/install -o root -g wheel -m 755 "$1" "$app_binary.next"
/bin/mv -f "$app_binary.next" "$app_binary"
/usr/bin/codesign --force --sign - --timestamp=none "$app"
/usr/bin/codesign --verify --deep --strict "$app"
/bin/launchctl bootstrap "gui/$console_uid" "$agent"
/bin/launchctl kickstart -k "$service"
trap - EXIT
# The old installer registered both a LaunchAgent and a login item. Only the
# LaunchAgent is needed; remove the exact duplicate after successful install.
if ! /bin/launchctl asuser "$console_uid" /usr/bin/sudo -u "$console_user" \
    /usr/bin/osascript <<'APPLESCRIPT'
tell application "System Events"
    if exists login item "AIC Wi-Fi" then delete login item "AIC Wi-Fi"
end tell
APPLESCRIPT
then
    echo 'Aviso: item de login duplicado não pôde ser removido.' >&2
fi
echo 'Proteção do modo nativo instalada; app e serviço reiniciados.'
echo "Reversão: restaure service.py e AIC Wi-Fi.app de $backup"
