#!/bin/sh
# Update only the AIC userspace service/USB transport; EFI is untouched.
set -eu
[ "$#" -eq 0 ] && [ "$(/usr/bin/id -u)" -eq 0 ] || exit 2
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)
support='/Library/Application Support/AIC88M80Driver'
wifi="$support/wifi"
service='system/local.victor.AIC88M80WiFi'
[ -f "$support/native-release.json" ] && [ -f "$wifi/service.py" ] &&
    [ -f "$wifi/wifi.py" ] && [ -f "$wifi/libaicwifi.dylib" ] &&
    /bin/launchctl print "$service" >/dev/null || {
    echo 'Instalação nativa esperada não encontrada; nada alterado.' >&2
    exit 1
}
stage=$(/usr/bin/mktemp -d /private/tmp/aic-native-boot-fix.XXXXXXXX)
/usr/bin/clang -dynamiclib -O2 -arch x86_64 \
    -framework IOKit -framework CoreFoundation -framework SystemConfiguration \
    "$repo_dir/wifi/usb.c" "$repo_dir/wifi/utun.c" \
    "$repo_dir/wifi/netstate.c" -o "$stage/libaicwifi.dylib"
/usr/bin/python3 - "$repo_dir/wifi/service.py" "$repo_dir/wifi/wifi.py" <<'PY'
import pathlib, sys
for name in sys.argv[1:]:
    compile(pathlib.Path(name).read_bytes(), name, 'exec')
PY
/bin/mkdir -p "$support/Backups"
backup=$(/usr/bin/mktemp -d "$support/Backups/native-boot-usb-XXXXXXXX")
/bin/cp -p "$wifi/service.py" "$wifi/wifi.py" "$wifi/libaicwifi.dylib" "$backup/"
echo "Backup: $backup"
changed=0
restore() {
    if [ "$changed" -eq 1 ]; then
        /bin/cp -p "$backup/service.py" "$backup/wifi.py" "$backup/libaicwifi.dylib" "$wifi/"
        /bin/launchctl kickstart -k "$service" || true
        echo 'Serviço anterior restaurado.' >&2
    fi
}
trap restore EXIT HUP INT TERM
changed=1
/usr/bin/install -o root -g wheel -m 644 "$repo_dir/wifi/service.py" "$stage/service.py"
/usr/bin/install -o root -g wheel -m 644 "$repo_dir/wifi/wifi.py" "$stage/wifi.py"
/usr/bin/install -o root -g wheel -m 755 "$stage/libaicwifi.dylib" "$stage/libaicwifi.dylib.next"
/bin/mv -f "$stage/service.py" "$wifi/service.py"
/bin/mv -f "$stage/wifi.py" "$wifi/wifi.py"
/bin/mv -f "$stage/libaicwifi.dylib.next" "$wifi/libaicwifi.dylib"
/bin/launchctl kickstart -k "$service"
/bin/sleep 3
/bin/launchctl print "$service" | /usr/bin/grep -q 'state = running'
changed=0
trap - EXIT HUP INT TERM
echo 'Recuperação de USB no boot instalada; EFI e redes salvas intactas.'
