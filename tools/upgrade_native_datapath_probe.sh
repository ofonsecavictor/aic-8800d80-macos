#!/bin/sh
# Reversible 0.0.12 -> 0.0.13 data-path test on this one Mac. Never reboots.
set -eu

if [ "$#" -ne 1 ] || { [ "$1" != '--apply' ] && [ "$1" != '--rollback' ]; } ||
    [ "$(/usr/bin/id -u)" -ne 0 ]; then
    echo 'Usage: sudo sh tools/upgrade_native_datapath_probe.sh --apply|--rollback' >&2
    exit 2
fi
mode=$1
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
device=disk0s4
usb=/Volumes/1401
backup="$usb/AIC-EFI-backup-pre-0013-20261022"
efi=
mounted=0
changed=0
success=0
bundle=

field() { printf '%s\n' "$1" | /usr/bin/plutil -extract "$2" raw -; }
version() { /usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' "$1/Contents/Info.plist"; }
identifier() { /usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$1/Contents/Info.plist"; }
unmount_efi() {
    if [ "$mounted" -eq 1 ]; then
        attempt=0
        while [ "$attempt" -lt 6 ]; do
            if /usr/sbin/diskutil unmount "$device" >/dev/null 2>&1; then
                mounted=0
                return 0
            fi
            attempt=$((attempt + 1))
            /bin/sleep 2
        done
        echo 'EFI ainda montada; não reinicie.' >&2
        return 1
    fi
}
cleanup() {
    result=$?
    trap - EXIT HUP INT TERM
    if [ "$mode" = '--apply' ] && [ "$changed" -eq 1 ] &&
        [ "$success" -eq 0 ] && [ -n "$efi" ]; then
        target="$efi/EFI/OC/Kexts/AICNativeProbe.kext"
        old="$efi/EFI/OC/Kexts/AICNativeProbe-pre-0013.kext"
        incomplete="$efi/EFI/OC/Kexts/AICNativeProbe-incomplete-0013.kext"
        if [ -e "$target" ] && [ ! -e "$incomplete" ]; then
            /bin/mv "$target" "$incomplete" || true
        fi
        if [ -e "$old" ] && [ ! -e "$target" ]; then
            /bin/mv "$old" "$target" || true
        fi
        /bin/sync
        echo 'Preparação falhou; tentativa de restaurar 0.0.12 concluída.' >&2
    fi
    unmount_efi || true
    if [ -n "$bundle" ]; then
        echo "Pacote compilado preservado em $bundle" >&2
    fi
    exit "$result"
}
trap cleanup EXIT HUP INT TERM

usb_info=$(/usr/sbin/diskutil info -plist "$usb")
[ "$(field "$usb_info" VolumeUUID)" = 7F3560A7-F954-344B-A86F-51B971F855A4 ] &&
    [ "$(field "$usb_info" Internal)" = false ] &&
    [ "$(field "$usb_info" BusProtocol)" = USB ] &&
    [ "$(field "$usb_info" MountPoint)" = "$usb" ] &&
    [ -f "$usb/EFI/BOOT/BOOTx64.efi" ] &&
    [ -f "$usb/EFI/OC/OpenCore.efi" ] || {
    echo 'Pendrive 1401 de recuperação não identificado; nada alterado.' >&2
    exit 1
}
disk_info=$(/usr/sbin/diskutil info -plist "$device")
[ "$(field "$disk_info" DeviceIdentifier)" = "$device" ] &&
    [ "$(field "$disk_info" Content)" = EFI ] &&
    [ "$(field "$disk_info" Internal)" = true ] &&
    [ "$(field "$disk_info" Size)" = 314572800 ] &&
    [ "$(field "$disk_info" MountPoint)" = '' ] || {
    echo 'EFI interna inesperada ou já montada; nada alterado.' >&2
    exit 1
}

if [ "$mode" = '--apply' ]; then
    [ ! -e "$backup" ] || {
        echo 'Backup pré-0.0.13 já existe; não sobrescrever.' >&2
        exit 1
    }
    available_kb=$(/bin/df -Pk "$usb" | /usr/bin/awk 'NR == 2 {print $4}')
    [ -n "$available_kb" ] && [ "$available_kb" -ge 400000 ] || {
        echo 'Pendrive sem espaço suficiente para backup verificado; nada alterado.' >&2
        exit 1
    }
    /usr/bin/kmutil showloaded --list-only 2>/dev/null |
        /usr/bin/grep -Eq 'local\.victor\.AICNativeProbe \(0\.0\.12\)' || {
        echo 'O driver carregado não é 0.0.12; nada alterado.' >&2
        exit 1
    }
    echo 'Compilando e diagnosticando 0.0.13 sem instalar...'
    output=$(/bin/sh "$script_dir/check_native_controller.sh" \
        /Users/victor/Documents/Codex/2026-10-19/so/work/aic-native-build-deps/itlwm/include/Airport \
        /Users/victor/Documents/Codex/2026-10-19/so/work/aic-native-build-deps/MacKernelSDK/Headers \
        --stage-usb-test)
    printf '%s\n' "$output"
    bundle=$(printf '%s\n' "$output" | /usr/bin/sed -n 's/^USB_TEST_BUNDLE=//p')
    case "$bundle" in
        /private/tmp/aic-native-compile.*/AICNativeRegistrationProbe.kext) ;;
        *) echo 'Pacote compilado em local inesperado.' >&2; exit 1 ;;
    esac
    [ "$(version "$bundle")" = 0.0.13 ] &&
        [ "$(identifier "$bundle")" = local.victor.AICNativeProbe ] || exit 1
fi

/usr/sbin/diskutil mount "$device" >/dev/null
mounted=1
disk_info=$(/usr/sbin/diskutil info -plist "$device")
efi=$(field "$disk_info" MountPoint)
[ -n "$efi" ] && [ -f "$efi/EFI/OC/config.plist" ] || exit 1
target="$efi/EFI/OC/Kexts/AICNativeProbe.kext"
old="$efi/EFI/OC/Kexts/AICNativeProbe-pre-0013.kext"
failed="$efi/EFI/OC/Kexts/AICNativeProbe-failed-0013.kext"

if [ "$mode" = '--rollback' ]; then
    [ -d "$target" ] && [ -d "$old" ] && [ ! -e "$failed" ] &&
        [ "$(version "$target")" = 0.0.13 ] &&
        [ "$(version "$old")" = 0.0.12 ] &&
        [ "$(identifier "$target")" = local.victor.AICNativeProbe ] &&
        [ "$(identifier "$old")" = local.victor.AICNativeProbe ] || {
        echo 'EFI não corresponde à troca 0.0.13; nada alterado.' >&2
        exit 1
    }
    /bin/mv "$target" "$failed"
    /bin/mv "$old" "$target"
    /bin/sync
    [ "$(version "$target")" = 0.0.12 ] || exit 1
    echo 'Driver 0.0.12 restaurado; arquivo 0.0.13 preservado na EFI.'
    exit 0
fi

[ -d "$target" ] && [ ! -e "$old" ] && [ ! -e "$failed" ] &&
    [ "$(version "$target")" = 0.0.12 ] &&
    [ "$(identifier "$target")" = local.victor.AICNativeProbe ] &&
    /usr/libexec/PlistBuddy -c 'Print :Kernel:Add' "$efi/EFI/OC/config.plist" |
        /usr/bin/grep -q 'AICNativeProbe.kext' || {
    echo 'EFI atual não contém o driver 0.0.12 esperado; nada alterado.' >&2
    exit 1
}
config_sha=$(/usr/bin/shasum -a 256 "$efi/EFI/OC/config.plist" | /usr/bin/awk '{print $1}')
unmount_efi
efi=

echo 'Copiando a EFI inteira para o pendrive e verificando byte a byte...'
/bin/mkdir -m 700 "$backup"
/bin/dd if=/dev/rdisk0s4 of="$backup/efi-disk0s4.img" bs=1m count=300
[ "$(/usr/bin/stat -f %z "$backup/efi-disk0s4.img")" = 314572800 ]
/usr/bin/cmp -s -n 314572800 "$backup/efi-disk0s4.img" /dev/rdisk0s4 || {
    echo 'Backup da EFI não coincide; nada gravado.' >&2
    exit 1
}
/usr/bin/shasum -a 256 "$backup/efi-disk0s4.img" > "$backup/efi-disk0s4.sha256"

/usr/sbin/diskutil mount "$device" >/dev/null
mounted=1
disk_info=$(/usr/sbin/diskutil info -plist "$device")
efi=$(field "$disk_info" MountPoint)
[ -n "$efi" ] && [ -d "$efi/EFI/OC/Kexts" ] &&
    [ -d "$efi/EFI/OC/Kexts/AICNativeProbe.kext" ] &&
    [ "$(version "$efi/EFI/OC/Kexts/AICNativeProbe.kext")" = 0.0.12 ] &&
    [ "$(/usr/bin/shasum -a 256 "$efi/EFI/OC/config.plist" | /usr/bin/awk '{print $1}')" = "$config_sha" ] || {
    echo 'EFI mudou após o backup; nada gravado.' >&2
    exit 1
}
target="$efi/EFI/OC/Kexts/AICNativeProbe.kext"
old="$efi/EFI/OC/Kexts/AICNativeProbe-pre-0013.kext"
changed=1
/bin/mv "$target" "$old"
/bin/cp -R "$bundle" "$target"
/usr/bin/cmp "$bundle/Contents/MacOS/AICNativeProbe" "$target/Contents/MacOS/AICNativeProbe"
/usr/bin/cmp "$bundle/Contents/Info.plist" "$target/Contents/Info.plist"
/usr/bin/plutil -lint "$target/Contents/Info.plist"
[ "$(/usr/bin/shasum -a 256 "$efi/EFI/OC/config.plist" | /usr/bin/awk '{print $1}')" = "$config_sha" ]
/bin/sync
unmount_efi
efi=
success=1
echo "EFI preparada com 0.0.13. Backup verificado: $backup/efi-disk0s4.img"
echo 'Nenhum reinício foi iniciado.'
