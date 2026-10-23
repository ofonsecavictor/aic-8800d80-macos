#!/bin/sh
# Build the complete native package; never install it.
set -eu
if [ "$#" -ne 2 ] || [ "$(/usr/bin/id -u)" -ne 0 ]; then
    echo 'Uso: sudo sh tools/build_native_pkg.sh KEXT_DE_TESTE PACOTE_DE_SAIDA' >&2
    exit 2
fi
bundle=$1
output=$2
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)
base='/Users/victor/Documents/Codex/2026-10-19/so/work/release-1.1.2'
case "$bundle" in
    /private/tmp/aic-native-compile.*/AICNativeRegistrationProbe.kext) ;;
    *) echo 'Kext de origem inesperado.' >&2; exit 1 ;;
esac
case "$output" in
    /Users/victor/Documents/ChatGPT/WIFI/output/*.pkg) ;;
    *) echo 'Saída deve estar na pasta output do workspace WIFI.' >&2; exit 1 ;;
esac
[ ! -e "$output" ] || { echo 'Pacote de saída já existe; não sobrescrever.' >&2; exit 1; }
[ -f "$base/payload/Library/Application Support/AIC88M80Driver/wifi/libaicwifi.dylib" ] || exit 1
[ -f "$bundle/Contents/MacOS/AICNativeProbe" ] || exit 1
version=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' "$bundle/Contents/Info.plist")
identifier=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$bundle/Contents/Info.plist")
[ "$version" = 0.0.18 ] && [ "$identifier" = local.victor.AICNativeProbe ] || exit 1
stage=$(/usr/bin/mktemp -d /private/tmp/aic-native-package.XXXXXXXX)
echo "Build staging: $stage"
/bin/mkdir "$stage/payload" "$stage/scripts" "$stage/resources"
/usr/bin/ditto "$base/payload" "$stage/payload"
/bin/cp "$base/scripts/preinstall" "$stage/scripts/preinstall-legacy"
/bin/cp "$repo_dir/installer/native-preinstall" "$stage/scripts/preinstall"
/bin/cp "$base/scripts/postinstall" "$stage/scripts/postinstall-legacy"
/bin/cp "$repo_dir/installer/native-postinstall" "$stage/scripts/postinstall"
/bin/chmod 755 "$stage/scripts/preinstall" "$stage/scripts/preinstall-legacy" \
    "$stage/scripts/postinstall" "$stage/scripts/postinstall-legacy"
wifi="$stage/payload/Library/Application Support/AIC88M80Driver/wifi"
for source in "$repo_dir"/wifi/*.py; do
    /bin/cp "$source" "$wifi/${source##*/}"
done
/usr/bin/clang -dynamiclib -O2 -arch x86_64 \
    -framework IOKit -framework CoreFoundation -framework SystemConfiguration \
    "$repo_dir/wifi/usb.c" "$repo_dir/wifi/utun.c" "$repo_dir/wifi/netstate.c" \
    -o "$wifi/libaicwifi.dylib"
/usr/bin/swiftc "$repo_dir/tools/native_scan_request.swift" \
    -o "$wifi/aic-native-scan-request"
/bin/chmod 755 "$wifi/libaicwifi.dylib" "$wifi/aic-native-scan-request"
native="$stage/payload/Library/Application Support/AIC88M80Driver/NativeMode"
/bin/mkdir "$native"
/bin/cp "$repo_dir/installer/native_release.py" "$native/native_release.py"
/bin/cp "$repo_dir/installer/native_upgrade.py" "$native/native_upgrade.py"
/bin/cp "$repo_dir/installer/efi_installer.py" "$native/efi_installer.py"
/bin/cp "$repo_dir/tools/rollback_native_efi_test.sh" "$native/rollback_native_efi_test.sh"
/usr/bin/ditto "$bundle" "$native/AICNativeProbe.kext"
/bin/cp "$repo_dir/installer/Voltar ao AIC.command" \
    "$stage/payload/Applications/Voltar ao AIC.command"
/bin/chmod 755 "$stage/payload/Applications/Voltar ao AIC.command"
/bin/cp "$repo_dir/installer/LEIA-ME-VELOCIDADE.txt" "$stage/resources/LEIA-ME-VELOCIDADE.txt"
/usr/bin/pkgbuild --root "$stage/payload" --scripts "$stage/scripts" \
    --identifier local.victor.AIC8800D80.Native --version 1.3.4 \
    --install-location / "$stage/AIC8800D80-native-speed-component.pkg"
/usr/bin/productbuild --distribution "$repo_dir/installer/speed-Distribution.xml" \
    --resources "$stage/resources" --package-path "$stage" "$output"
/usr/sbin/pkgutil --check-signature "$output" || true
/usr/bin/shasum -a 256 "$output"
echo "PACKAGE=$output"
echo 'Pacote criado; não instalado. Staging preservado para auditoria.'
