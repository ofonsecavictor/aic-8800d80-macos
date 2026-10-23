#!/bin/sh
# Remove only the AIC native test entry and bundle staged by this project.
set -eu

if [ "$(/usr/bin/id -u)" -ne 0 ]; then
    echo 'Execute com sudo no Terminal.' >&2
    exit 2
fi

recovery=/Users/victor/Documents/Codex/2026-10-19/so/work/aic-native-efi-test-recovery
device=disk0s4
[ -f "$recovery/config.plist" ] && [ -f "$recovery/config-test.plist" ] || {
    echo 'Configurações original e de teste não encontradas; não alterar a EFI.' >&2
    exit 1
}
field() { printf '%s\n' "$1" | /usr/bin/plutil -extract "$2" raw -; }
info=$(/usr/sbin/diskutil info -plist "$device")
[ "$(field "$info" DeviceIdentifier)" = "$device" ] &&
    [ "$(field "$info" Content)" = EFI ] &&
    [ "$(field "$info" Internal)" = true ] &&
    [ "$(field "$info" Size)" = 314572800 ] || {
    echo 'A partição interna esperada não foi identificada; não alterar.' >&2
    exit 1
}
efi=$(field "$info" MountPoint)
mounted_here=0
if [ -z "$efi" ]; then
    /usr/sbin/diskutil mount "$device" >/dev/null
    mounted_here=1
    info=$(/usr/sbin/diskutil info -plist "$device")
    efi=$(field "$info" MountPoint)
fi
cleanup() {
    if [ "$mounted_here" -eq 1 ]; then
        attempt=0
        while [ "$attempt" -lt 6 ]; do
            if /usr/sbin/diskutil unmount "$device" >/dev/null 2>&1; then
                return
            fi
            attempt=$((attempt + 1))
            /bin/sleep 3
        done
        echo 'ATENÇÃO: EFI restaurada, mas permaneceu montada; desmonte antes de reiniciar.' >&2
    fi
}
trap cleanup EXIT
[ -n "$efi" ] && [ -f "$efi/EFI/OC/config.plist" ] || exit 1
if ! /usr/bin/cmp -s "$recovery/config-test.plist" "$efi/EFI/OC/config.plist"; then
    echo 'config.plist difere do teste preparado; não sobrescrever alterações desconhecidas.' >&2
    exit 1
fi
target="$efi/EFI/OC/Kexts/AICNativeProbe.kext"
[ -f "$target/Contents/Info.plist" ] && [ -f "$target/Contents/MacOS/AICNativeProbe" ] || {
    echo 'Bundle do teste ausente ou incompleto; não sobrescrever a EFI.' >&2
    exit 1
}
identifier=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$target/Contents/Info.plist")
[ "$identifier" = local.victor.AICNativeProbe ] || {
    echo 'O bundle de destino não é o teste esperado; não remover.' >&2
    exit 1
}
if ! /usr/libexec/PlistBuddy -c 'Print :Kernel:Add' "$efi/EFI/OC/config.plist" |
    /usr/bin/grep -q 'AICNativeProbe.kext'; then
    echo 'Entrada do teste ausente; conferindo apenas o bundle.'
fi
echo 'Restaurando config.plist original e removendo somente AICNativeProbe.kext...'
/bin/cp "$recovery/config.plist" "$efi/EFI/OC/config.plist"
/bin/rm -f "$target/Contents/MacOS/AICNativeProbe" "$target/Contents/Info.plist"
/bin/rmdir "$target/Contents/MacOS" "$target/Contents" "$target"
/bin/sync
/usr/bin/cmp "$recovery/config.plist" "$efi/EFI/OC/config.plist"
[ ! -e "$target" ] || exit 1
echo 'EFI restaurada. Reinicie normalmente pela EFI interna.'
