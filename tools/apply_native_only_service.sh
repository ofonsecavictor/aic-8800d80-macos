#!/bin/sh
set -eu
[ "$(id -u)" = 0 ] || exit 1
repo=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
support='/Library/Application Support/AIC88M80Driver'
backup=$(/usr/bin/mktemp -d "$support/Backups/native-only-service.XXXXXXXX")
stage=$(/usr/bin/mktemp -d /private/tmp/aic-native-service.XXXXXXXX)
/usr/bin/clang -dynamiclib -O2 -arch x86_64 \
    -framework IOKit -framework CoreFoundation -framework SystemConfiguration \
    "$repo/wifi/usb.c" "$repo/wifi/utun.c" "$repo/wifi/netstate.c" \
    -o "$stage/libaicwifi.dylib"
for name in service.py wifi.py wpa2.py layouts.py protocol.py reports.py \
    native_radio_control.py native_scan_bridge.py native_join_bridge.py \
    native_scan_result.py native_scan_service.py native_ethernet.py; do
    if [ -f "$support/wifi/$name" ]; then
        /bin/cp -p "$support/wifi/$name" "$backup/$name"
    fi
    /usr/bin/install -o root -g wheel -m 644 "$repo/wifi/$name" "$support/wifi/$name"
done
if [ -f "$support/wifi/libaicwifi.dylib" ]; then
    /bin/cp -p "$support/wifi/libaicwifi.dylib" "$backup/libaicwifi.dylib"
fi
/usr/bin/install -o root -g wheel -m 755 "$stage/libaicwifi.dylib" \
    "$support/wifi/libaicwifi.dylib"
echo "SERVICE_BACKUP=$backup"
/bin/launchctl kickstart -k system/local.victor.AIC88M80WiFi
