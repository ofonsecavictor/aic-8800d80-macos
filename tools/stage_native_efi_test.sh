#!/bin/sh
# Prepare one experimental OpenCore boot on this exact Mac. No reboot is done.
# The verified external EFI image and working USB boot are mandatory.
set -eu

if [ "$#" -ne 1 ] ||
    { [ "$1" != '--apply' ] &&
      [ "$1" != '--apply-registration-probe' ]; } ||
    [ "$(/usr/bin/id -u)" -ne 0 ]; then
    echo 'Uso: sudo sh tools/stage_native_efi_test.sh --apply | --apply-registration-probe' >&2
    exit 2
fi
mode=$1

if /usr/bin/kmutil inspect --optional-identifier local.victor.AICNativeProbe 2>/dev/null |
    /usr/bin/grep -q '^local\.victor\.AICNativeProbe[[:space:]]'; then
    echo 'Outra cópia de AICNativeProbe está na coleção auxiliar; não preparar a EFI.' >&2
    exit 1
fi

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)
if /usr/bin/grep -Eq 'mExpansionData(2)?->fRegistrationInfo[[:space:]]*=' \
    "$repo_dir/native/AICAirPortController.cpp"; then
    echo 'Registro nativo inseguro: o macOS libera estes ponteiros em zonas próprias. Não gravar na EFI enquanto houver atribuição manual.' >&2
    exit 1
fi
if ! /usr/bin/grep -Eq '^[[:space:]]*[^/].*AICRegisterSkywalkEthernet\(' \
    "$repo_dir/native/AICAirPortController.cpp"; then
    echo 'Registro Skywalk ausente: sem ele prepareBSDInterface causa kernel panic. Não gravar na EFI.' >&2
    exit 1
fi
if [ "$mode" != '--apply-registration-probe' ]; then
    # Skywalk queue callbacks remain placeholders, but this test variant
    # carries Ethernet through the BSD ifnet outputPacket/inputPacket path.
    # Require that bridge path instead of rejecting merely on callback names.
    /usr/bin/grep -q 'AICAirPortController::outputPacket(mbuf_t packet' \
        "$repo_dir/native/AICAirPortController.cpp" &&
    /usr/bin/grep -q 'target->inputPacket(packet, frame.length)' \
        "$repo_dir/native/AICAirPortController.cpp" &&
    /usr/bin/grep -q 'transmitFrames.push(frame, false)' \
        "$repo_dir/native/AICAirPortController.cpp" || {
        echo 'Caminho de dados BSD/USB ausente; não gravar na EFI.' >&2
        exit 1
    }
fi
if [ "$mode" = '--apply-registration-probe' ]; then
    echo 'Diagnóstico de registro apenas: filas Skywalk não transportam pacotes; conexão nativa ainda não comprovada.'
fi
backup=/Volumes/1401/AIC-EFI-backup-2026-10-22.JNSOPthj/efi-disk0s4.img
backup_sha=2e9d1ae102e119684441fd11ed49459a67f951ef9a6cbcfd15d079d4313d5737
recovery=/Users/victor/Documents/Codex/2026-10-19/so/work/aic-native-efi-test-recovery
device=disk0s4
efi=
bundle=
changed=0
success=0
backup_mount=
backup_device=

field() { printf '%s\n' "$1" | /usr/bin/plutil -extract "$2" raw -; }
disk_info=$(/usr/sbin/diskutil info -plist "$device")
[ "$(field "$disk_info" DeviceIdentifier)" = "$device" ] || exit 1
[ "$(field "$disk_info" Content)" = EFI ] || exit 1
[ "$(field "$disk_info" Internal)" = true ] || exit 1
[ "$(field "$disk_info" Size)" = 314572800 ] || exit 1
[ "$(field "$disk_info" MountPoint)" = '' ] || {
    echo 'A EFI interna já está montada; abortando para não modificar um alvo ambíguo.' >&2
    exit 1
}
usb_info=$(/usr/sbin/diskutil info -plist /Volumes/1401)
uuid=$(field "$usb_info" VolumeUUID | /usr/bin/tr '[:upper:]' '[:lower:]')
[ "$uuid" = 7f3560a7-f954-344b-a86f-51b971f855a4 ] || exit 1
[ "$(field "$usb_info" MountPoint)" = /Volumes/1401 ] || exit 1
[ "$(field "$usb_info" Internal)" = false ] || exit 1
[ "$(field "$usb_info" BusProtocol)" = USB ] || exit 1
[ "$(field "$usb_info" Content)" = Windows_FAT_32 ] || exit 1
[ -f /Volumes/1401/EFI/BOOT/BOOTx64.efi ] || exit 1
[ -f /Volumes/1401/EFI/OC/OpenCore.efi ] || exit 1
[ -f "$backup" ] || exit 1
if [ -e "$recovery" ] && [ ! -f "$recovery/config.plist" ]; then
    echo "Recuperação anterior incompleta: $recovery; abortando." >&2
    exit 1
fi

echo 'Verificando SHA-256 do backup e identidade da EFI atual...'
actual_sha=$(/usr/bin/shasum -a 256 "$backup" | /usr/bin/awk '{print $1}')
[ "$actual_sha" = "$backup_sha" ] || {
    echo 'O hash do backup mudou; abortando.' >&2
    exit 1
}
preflight_cleanup() {
    if [ -n "$efi" ]; then /usr/sbin/diskutil unmount "$device" >/dev/null || true; fi
    if [ -n "$backup_device" ]; then
        /usr/bin/hdiutil detach "$backup_device" >/dev/null || true
    fi
    if [ -n "$backup_mount" ]; then /bin/rmdir "$backup_mount" 2>/dev/null || true; fi
}
trap preflight_cleanup EXIT
backup_mount=$(/usr/bin/mktemp -d /private/tmp/aic-efi-image-check.XXXXXX)
image_attach=$(/usr/bin/hdiutil attach -readonly -nobrowse \
    -mountpoint "$backup_mount" "$backup")
backup_device=$(printf '%s\n' "$image_attach" | /usr/bin/awk 'NR == 1 {print $1}')
case "$backup_device" in /dev/disk[0-9]*) ;; *) exit 1 ;; esac
[ -d "$backup_mount/EFI" ] || exit 1
/usr/sbin/diskutil mount readOnly "$device" >/dev/null
disk_info=$(/usr/sbin/diskutil info -plist "$device")
efi=$(field "$disk_info" MountPoint)
[ -n "$efi" ] && [ -d "$efi/EFI" ] || exit 1
echo 'Comparando todos os arquivos da EFI com a imagem, sem gravar...'
diff_code=0
differences=$(/usr/bin/diff -qr "$efi/EFI" "$backup_mount/EFI" 2>&1) || diff_code=$?
unexpected=
if [ -n "$differences" ]; then
    unexpected=$(printf '%s\n' "$differences" | /usr/bin/grep -Fvx \
        -e "Files $efi/EFI/Microsoft/Boot/BCD and $backup_mount/EFI/Microsoft/Boot/BCD differ" \
        -e "Files $efi/EFI/Microsoft/Boot/BCD.LOG and $backup_mount/EFI/Microsoft/Boot/BCD.LOG differ" \
        -e "Files $efi/EFI/Microsoft/Boot/BOOTSTAT.DAT and $backup_mount/EFI/Microsoft/Boot/BOOTSTAT.DAT differ" \
        -e "Only in $efi/EFI/OC: config.plist.nullmoth-20261019-203805" \
        -e "Only in $efi/EFI/OC: config.plist.nullmoth-20261019-211036") || true
fi
if [ "$diff_code" -gt 1 ] || [ -n "$unexpected" ]; then
    printf '%s\n' "$differences" >&2
    echo 'Diferença não esperada na EFI; abortando sem gravar.' >&2
    exit 1
fi
if [ -n "$differences" ]; then
    echo 'Apenas BCD, BCD.LOG e BOOTSTAT.DAT do Windows e dois backups extras de config.plist diferem; OpenCore coincide com a imagem.'
fi
/usr/sbin/diskutil unmount "$device" >/dev/null
efi=
/usr/bin/hdiutil detach "$backup_device" >/dev/null
backup_device=
/bin/rmdir "$backup_mount"
backup_mount=
trap - EXIT

echo 'Compilando e diagnosticando o pacote USB nativo experimental...'
output=$(sh "$script_dir/check_native_controller.sh" \
    /Users/victor/Documents/Codex/2026-10-19/so/work/aic-native-build-deps/itlwm/include/Airport \
    /Users/victor/Documents/Codex/2026-10-19/so/work/aic-native-build-deps/MacKernelSDK/Headers --stage-usb-test) || {
    printf '%s\n' "$output"
    exit 1
}
printf '%s\n' "$output"
bundle=$(printf '%s\n' "$output" | /usr/bin/sed -n 's/^USB_TEST_BUNDLE=//p')
case "$bundle" in
    /private/tmp/aic-native-compile.*/AICNativeRegistrationProbe.kext) ;;
    *) echo 'Caminho do pacote inesperado; abortando.' >&2; exit 1 ;;
esac
bundle_version=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' \
    "$bundle/Contents/Info.plist")
[ "$bundle_version" = 0.0.15 ] || {
    echo 'Pacote nativo experimental 0.0.15 não encontrado; abortando.' >&2
    exit 1
}

rollback() {
    if [ "$success" -eq 0 ] && [ "$changed" -eq 1 ] && [ -n "$efi" ]; then
        echo 'Falha na preparação; restaurando somente as alterações deste teste.' >&2
        /bin/cp "$recovery/config.plist" "$efi/EFI/OC/config.plist" || true
        target="$efi/EFI/OC/Kexts/AICNativeProbe.kext"
        /bin/rm -f "$target/Contents/MacOS/AICNativeProbe" "$target/Contents/Info.plist"
        /bin/rmdir "$target/Contents/MacOS" "$target/Contents" "$target" 2>/dev/null || true
        /bin/sync
    fi
    if [ -n "$efi" ]; then /usr/sbin/diskutil unmount "$device" >/dev/null || true; fi
}
trap rollback EXIT

echo 'Montando a EFI interna e conferindo o OpenCore...'
/usr/sbin/diskutil mount "$device" >/dev/null
disk_info=$(/usr/sbin/diskutil info -plist "$device")
efi=$(field "$disk_info" MountPoint)
[ -n "$efi" ] && [ -f "$efi/EFI/OC/config.plist" ] &&
    [ -f "$efi/EFI/OC/OpenCore.efi" ] &&
    [ -d "$efi/EFI/OC/Kexts" ] || exit 1
[ ! -e "$efi/EFI/OC/Kexts/AICNativeProbe.kext" ] || exit 1
if /usr/libexec/PlistBuddy -c 'Print :Kernel:Add' "$efi/EFI/OC/config.plist" |
    /usr/bin/grep -q 'AICNativeProbe.kext'; then
    echo 'Entrada experimental já presente; abortando.' >&2
    exit 1
fi
if [ -d "$recovery" ]; then
    /usr/bin/cmp -s "$recovery/config.plist" "$efi/EFI/OC/config.plist" || {
        echo 'O config.plist atual não corresponde à cópia original; abortando.' >&2
        exit 1
    }
else
    /bin/mkdir "$recovery"
    /bin/cp "$efi/EFI/OC/config.plist" "$recovery/config.plist"
fi
/bin/cp "$recovery/config.plist" "$recovery/config-test.plist"
count=$(/usr/libexec/PlistBuddy -c 'Print :Kernel:Add' "$recovery/config-test.plist" |
    /usr/bin/awk '/^[[:space:]]+Dict \{/ {n++} END {print n+0}')
edit=/usr/libexec/PlistBuddy
"$edit" -c "Add :Kernel:Add:$count dict" "$recovery/config-test.plist"
"$edit" -c "Add :Kernel:Add:$count:Arch string Any" "$recovery/config-test.plist"
"$edit" -c "Add :Kernel:Add:$count:BundlePath string AICNativeProbe.kext" "$recovery/config-test.plist"
"$edit" -c "Add :Kernel:Add:$count:Comment string 'AIC native USB test - remove after test'" "$recovery/config-test.plist"
"$edit" -c "Add :Kernel:Add:$count:Enabled bool true" "$recovery/config-test.plist"
"$edit" -c "Add :Kernel:Add:$count:ExecutablePath string Contents/MacOS/AICNativeProbe" "$recovery/config-test.plist"
"$edit" -c "Add :Kernel:Add:$count:PlistPath string Contents/Info.plist" "$recovery/config-test.plist"
"$edit" -c "Add :Kernel:Add:$count:MinKernel string 24.6.0" "$recovery/config-test.plist"
"$edit" -c "Add :Kernel:Add:$count:MaxKernel string 24.6.0" "$recovery/config-test.plist"
/usr/bin/plutil -lint "$recovery/config-test.plist"

echo 'Gravando apenas o novo kext e uma entrada Kernel/Add na EFI interna...'
changed=1
/bin/cp -R "$bundle" "$efi/EFI/OC/Kexts/AICNativeProbe.kext"
/bin/cp "$recovery/config-test.plist" "$efi/EFI/OC/config.plist"
/usr/bin/plutil -lint "$efi/EFI/OC/config.plist"
/usr/bin/cmp "$bundle/Contents/MacOS/AICNativeProbe" \
    "$efi/EFI/OC/Kexts/AICNativeProbe.kext/Contents/MacOS/AICNativeProbe"
/usr/bin/cmp "$bundle/Contents/Info.plist" \
    "$efi/EFI/OC/Kexts/AICNativeProbe.kext/Contents/Info.plist"
/bin/sync
unmounted=0
attempt=0
while [ "$attempt" -lt 6 ]; do
    if /usr/sbin/diskutil unmount "$device" >/dev/null 2>&1; then
        unmounted=1
        break
    fi
    attempt=$((attempt + 1))
    /bin/sleep 3
done
if [ "$unmounted" -ne 1 ]; then
    echo 'A EFI continuou ocupada; revertendo o teste.' >&2
    exit 1
fi
efi=
success=1
echo "Teste preparado. Original salvo em $recovery/config.plist"
echo 'NÃO reinicie até combinar a observação do primeiro boot e a reversão.'
