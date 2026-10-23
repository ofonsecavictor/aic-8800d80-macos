#!/bin/sh
# One-machine, reversible replacement of the already configured native kext.
# Does not change OpenCore config.plist or reboot the Mac.
set -eu

if [ "$#" -ne 1 ] || { [ "$1" != '--apply' ] && [ "$1" != '--rollback' ]; } ||
    [ "$(/usr/bin/id -u)" -ne 0 ]; then
    echo 'Uso: sudo sh tools/upgrade_native_capabilities_probe.sh --apply|--rollback' >&2
    exit 2
fi

mode=$1
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
backup_dir=/Volumes/1401/AIC-EFI-backup-2026-10-21.9IZNSYSv
image="$backup_dir/efi-disk0s4.img"
image_sha=4d2d24faac42c734543819504a2d7e88387196cdb5480a52291bb5bdb39b6e2b
device=disk0s4
mountpoint=
mounted_here=0
changed=0
success=0
stage=

field() { printf '%s\n' "$1" | /usr/bin/plutil -extract "$2" raw -; }
usb_info=$(/usr/sbin/diskutil info -plist /Volumes/1401)
[ "$(field "$usb_info" VolumeUUID)" = 7F3560A7-F954-344B-A86F-51B971F855A4 ] &&
    [ "$(field "$usb_info" Internal)" = false ] &&
    [ "$(field "$usb_info" BusProtocol)" = USB ] &&
    [ "$(field "$usb_info" MountPoint)" = /Volumes/1401 ] &&
    [ -f /Volumes/1401/EFI/BOOT/BOOTx64.efi ] &&
    [ -f /Volumes/1401/EFI/OC/OpenCore.efi ] || {
    echo 'Pendrive de recuperação inesperado; EFI intacta.' >&2
    exit 1
}
disk_info=$(/usr/sbin/diskutil info -plist "$device")
[ "$(field "$disk_info" DeviceIdentifier)" = "$device" ] &&
    [ "$(field "$disk_info" Content)" = EFI ] &&
    [ "$(field "$disk_info" Internal)" = true ] &&
    [ "$(field "$disk_info" Size)" = 314572800 ] || {
    echo 'EFI interna inesperada; nada alterado.' >&2
    exit 1
}

version() {
    /usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' "$1/Contents/Info.plist"
}
identifier() {
    /usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$1/Contents/Info.plist"
}
unmount_if_needed() {
    if [ "$mounted_here" -eq 1 ]; then
        attempt=0
        while [ "$attempt" -lt 6 ]; do
            if /usr/sbin/diskutil unmount "$device" >/dev/null 2>&1; then
                mounted_here=0
                return 0
            fi
            attempt=$((attempt + 1))
            /bin/sleep 2
        done
        echo 'ATENÇÃO: EFI ainda montada; não reinicie antes de desmontá-la.' >&2
        return 1
    fi
}
on_exit() {
    result=$?
    trap - EXIT HUP INT TERM
    if [ "$mode" = '--apply' ] && [ "$changed" -eq 1 ] &&
        [ "$success" -eq 0 ] && [ -n "$mountpoint" ]; then
        target="$mountpoint/EFI/OC/Kexts/AICNativeProbe.kext"
        old="$mountpoint/EFI/OC/Kexts/AICNativeProbe-pre-0012.kext"
        incomplete="$mountpoint/EFI/OC/Kexts/AICNativeProbe-incomplete-0012.kext"
        if [ -e "$target" ] && [ ! -e "$incomplete" ]; then
            /bin/mv "$target" "$incomplete" || true
        fi
        if [ -e "$old" ] && [ ! -e "$target" ]; then
            /bin/mv "$old" "$target" || true
        fi
        /bin/sync
        echo 'Preparação falhou; a versão 0.0.11 foi restaurada quando possível.' >&2
    fi
    unmount_if_needed || true
    if [ -n "$stage" ]; then
        echo "Pacote temporário preservado para inspeção em $stage" >&2
    fi
    exit "$result"
}
trap on_exit EXIT HUP INT TERM

if [ "$mode" = '--apply' ]; then
    [ -f "$image" ] &&
        [ "$(/usr/bin/stat -f %z "$image")" = 314572800 ] &&
        [ "$(/usr/bin/shasum -a 256 "$image" | /usr/bin/awk '{print $1}')" = "$image_sha" ] || {
        echo 'Backup novo da EFI ausente ou alterado; nada gravado.' >&2
        exit 1
    }
    [ "$(field "$disk_info" MountPoint)" = '' ] || {
        echo 'EFI interna já montada; nada gravado.' >&2
        exit 1
    }
    echo 'Comparando novamente o backup novo com a EFI interna...'
    /usr/bin/cmp -s -n 314572800 "$image" /dev/rdisk0s4 || {
        echo 'EFI mudou desde o backup; nada gravado.' >&2
        exit 1
    }
    /usr/bin/kmutil showloaded --list-only 2>/dev/null |
        /usr/bin/grep -Eq 'local\.victor\.AICNativeProbe \(0\.0\.11\)' || {
        echo 'O driver 0.0.11 não está carregado; nada gravado.' >&2
        exit 1
    }
    [ ! -e "$backup_dir/pre-0012" ] || {
        echo 'Já existe um backup desta atualização; não sobrescrever.' >&2
        exit 1
    }
    echo 'Compilando e diagnosticando o driver 0.0.12...'
    output=$(/bin/sh "$script_dir/check_native_controller.sh" \
        /Users/victor/Documents/Codex/2026-10-19/so/work/aic-native-build-deps/itlwm/include/Airport \
        /Users/victor/Documents/Codex/2026-10-19/so/work/aic-native-build-deps/MacKernelSDK/Headers \
        --stage-usb-test)
    printf '%s\n' "$output"
    stage=$(printf '%s\n' "$output" | /usr/bin/sed -n 's/^USB_TEST_BUNDLE=//p')
    case "$stage" in
        /private/tmp/aic-native-compile.*/AICNativeRegistrationProbe.kext) ;;
        *) echo 'Pacote compilado em local inesperado.' >&2; exit 1 ;;
    esac
    [ "$(version "$stage")" = 0.0.12 ] &&
        [ "$(identifier "$stage")" = local.victor.AICNativeProbe ] || exit 1
fi

if [ -z "$(field "$disk_info" MountPoint)" ]; then
    /usr/sbin/diskutil mount "$device" >/dev/null
    mounted_here=1
fi
disk_info=$(/usr/sbin/diskutil info -plist "$device")
mountpoint=$(field "$disk_info" MountPoint)
[ -n "$mountpoint" ] && [ -f "$mountpoint/EFI/OC/config.plist" ] || exit 1
target="$mountpoint/EFI/OC/Kexts/AICNativeProbe.kext"
old="$mountpoint/EFI/OC/Kexts/AICNativeProbe-pre-0012.kext"
failed="$mountpoint/EFI/OC/Kexts/AICNativeProbe-failed-0012.kext"

if [ "$mode" = '--rollback' ]; then
    [ -d "$target" ] && [ -d "$old" ] && [ ! -e "$failed" ] &&
        [ "$(version "$target")" = 0.0.12 ] &&
        [ "$(version "$old")" = 0.0.11 ] &&
        [ "$(identifier "$target")" = local.victor.AICNativeProbe ] &&
        [ "$(identifier "$old")" = local.victor.AICNativeProbe ] || {
        echo 'EFI não corresponde à troca 0.0.12; não reverter às cegas.' >&2
        exit 1
    }
    /bin/mv "$target" "$failed"
    /bin/mv "$old" "$target"
    /bin/sync
    [ "$(version "$target")" = 0.0.11 ] || exit 1
    echo 'Driver 0.0.11 restaurado. A EFI e o arquivo 0.0.12 permanecem recuperáveis.'
    exit 0
fi

[ -d "$target" ] && [ ! -e "$old" ] && [ ! -e "$failed" ] &&
    [ "$(version "$target")" = 0.0.11 ] &&
    [ "$(identifier "$target")" = local.victor.AICNativeProbe ] || {
    echo 'Kext atual inesperado; nada gravado.' >&2
    exit 1
}
if ! /usr/libexec/PlistBuddy -c 'Print :Kernel:Add' "$mountpoint/EFI/OC/config.plist" |
    /usr/bin/grep -q 'AICNativeProbe.kext'; then
    echo 'OpenCore não contém a entrada AIC; nada gravado.' >&2
    exit 1
fi
/bin/mkdir -m 700 "$backup_dir/pre-0012"
/bin/cp -p "$mountpoint/EFI/OC/config.plist" "$backup_dir/pre-0012/config.plist"
/bin/cp -R "$target" "$backup_dir/pre-0012/AICNativeProbe.kext"
/usr/bin/diff -qr "$target" "$backup_dir/pre-0012/AICNativeProbe.kext" >/dev/null

echo 'Trocando apenas AICNativeProbe.kext na EFI; config.plist inalterado...'
changed=1
/bin/mv "$target" "$old"
/bin/cp -R "$stage" "$target"
/usr/bin/cmp "$stage/Contents/MacOS/AICNativeProbe" "$target/Contents/MacOS/AICNativeProbe"
/usr/bin/cmp "$stage/Contents/Info.plist" "$target/Contents/Info.plist"
/usr/bin/plutil -lint "$target/Contents/Info.plist"
/usr/bin/cmp "$backup_dir/pre-0012/config.plist" "$mountpoint/EFI/OC/config.plist"
/bin/sync
unmount_if_needed
success=1
echo 'EFI preparada com 0.0.12. Nenhum reinício foi iniciado.'
echo "Reversão: sudo sh $script_dir/upgrade_native_capabilities_probe.sh --rollback"
