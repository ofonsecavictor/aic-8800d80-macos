#!/bin/sh
# Offline build/link/symbol probe. It never installs or loads a kext.
set -eu

if [ "$#" -lt 2 ] || [ "$#" -gt 3 ] ||
    { [ "$#" -eq 3 ] && [ "$3" != '--diagnose' ]; } ||
    [ ! -f "$1/macOS15/IO80211ControllerV2.h" ] ||
    [ ! -f "$1/apple_private_spi.h" ] || [ ! -f "$2/IOKit/IOService.h" ] ||
    [ ! -f "$(dirname "$2")/Library/x86_64/libkmod.a" ]; then
    echo 'Uso: sh tools/check_native_controller.sh /caminho/itlwm-Sequoia/include/Airport /caminho/MacKernelSDK/Headers [--diagnose]' >&2
    exit 2
fi

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)
sdk=$(/usr/bin/xcrun --sdk macosx --show-sdk-path)
kernel_headers="$sdk/System/Library/Frameworks/Kernel.framework/Versions/A/Headers"
stage=$(/usr/bin/mktemp -d /private/tmp/aic-native-compile.XXXXXX)
cleanup() {
    /bin/rm -f "$stage/AICAirPortController.o"
    /bin/rm -f "$stage/AICAirPortController-headless.o"
    /bin/rm -f "$stage/AICNativeBridgeUserClient.o"
    /bin/rm -f "$stage/AICInfraInterface.o"
    /bin/rm -f "$stage/AICProbe" "$stage/AICHeadlessProbe" "$stage/undefined.txt"
    /bin/rm -f "$stage/native_bridge_protocol_test"
    /bin/rm -f "$stage/exports.txt" "$stage/missing.txt"
    /bin/rm -f "$stage/diagnostics.txt"
    /bin/rm -f "$stage/AICNativeProbe.kext/Contents/MacOS/AICNativeProbe"
    /bin/rm -f "$stage/AICNativeProbe.kext/Contents/Info.plist"
    /bin/rmdir "$stage/AICNativeProbe.kext/Contents/MacOS" 2>/dev/null || true
    /bin/rmdir "$stage/AICNativeProbe.kext/Contents" 2>/dev/null || true
    /bin/rmdir "$stage/AICNativeProbe.kext" 2>/dev/null || true
    /bin/rmdir "$stage" 2>/dev/null || true
}
trap cleanup EXIT

/usr/bin/xcrun clang++ -std=c++14 -Wall -Wextra -Werror \
    -o "$stage/native_bridge_protocol_test" \
    "$repo_dir/tests/native_bridge_protocol_test.cpp"
"$stage/native_bridge_protocol_test"
echo 'Contrato de estado de rádio: testes locais OK.'

/usr/bin/xcrun clang++ -std=c++14 -fno-exceptions -fno-rtti -fapple-kext \
    -mkernel -c -o "$stage/AICAirPortController.o" \
    -Wno-deprecated-declarations -Wno-invalid-offsetof \
    -Wno-inconsistent-missing-override \
    -DKERNEL=1 -DAIRPORT_WCL=1 -D__PRIVATE_SPI__=1 -DIO80211FAMILY_V2=1 \
    -D__IO80211_TARGET=__MAC_15_2 -include "$1/apple_private_spi.h" \
    -I"$1" -I"$2" -I"$kernel_headers" \
    "$repo_dir/native/AICAirPortController.cpp"
/usr/bin/file "$stage/AICAirPortController.o"
# Compile the explicitly opt-in lifecycle path as well. The bundled Mach-O
# below still uses the disabled-by-default object, not this test variant.
/usr/bin/xcrun clang++ -std=c++14 -fno-exceptions -fno-rtti -fapple-kext \
    -mkernel -c -o "$stage/AICAirPortController-headless.o" \
    -Wno-deprecated-declarations -Wno-invalid-offsetof \
    -Wno-inconsistent-missing-override \
    -DKERNEL=1 -DAIRPORT_WCL=1 -D__PRIVATE_SPI__=1 -DIO80211FAMILY_V2=1 \
    -D__IO80211_TARGET=__MAC_15_2 -DAIC_HEADLESS_BRIDGE_PROBE=1 \
    -include "$1/apple_private_spi.h" \
    -I"$1" -I"$2" -I"$kernel_headers" \
    "$repo_dir/native/AICAirPortController.cpp"
/usr/bin/file "$stage/AICAirPortController-headless.o"
/usr/bin/xcrun clang++ -std=c++14 -fno-exceptions -fno-rtti -fapple-kext \
    -mkernel -c -o "$stage/AICNativeBridgeUserClient.o" \
    -Wno-deprecated-declarations -Wno-invalid-offsetof \
    -Wno-inconsistent-missing-override \
    -DKERNEL=1 -DAIRPORT_WCL=1 -D__PRIVATE_SPI__=1 -DIO80211FAMILY_V2=1 \
    -D__IO80211_TARGET=__MAC_15_2 -include "$1/apple_private_spi.h" \
    -I"$1" -I"$2" -I"$kernel_headers" \
    "$repo_dir/native/AICNativeBridgeUserClient.cpp"
/usr/bin/file "$stage/AICNativeBridgeUserClient.o"

/usr/bin/xcrun clang++ -std=c++14 -fno-exceptions -fno-rtti -fapple-kext \
    -mkernel -c -o "$stage/AICInfraInterface.o" \
    -Wno-deprecated-declarations -Wno-invalid-offsetof \
    -Wno-inconsistent-missing-override \
    -DKERNEL=1 -DAIRPORT_WCL=1 -D__PRIVATE_SPI__=1 -DIO80211FAMILY_V2=1 \
    -D__IO80211_TARGET=__MAC_15_2 -include "$1/apple_private_spi.h" \
    -I"$1" -I"$2" -I"$kernel_headers" \
    "$repo_dir/native/AICInfraInterface.cpp"
/usr/bin/file "$stage/AICInfraInterface.o"

# Dynamic lookup only creates a Mach-O kext shape; it does not resolve an ABI.
/usr/bin/xcrun ld -kext -arch x86_64 -undefined dynamic_lookup \
    -o "$stage/AICProbe" \
    "$stage/AICAirPortController.o" "$stage/AICNativeBridgeUserClient.o" \
    "$stage/AICInfraInterface.o" \
    "$(dirname "$2")/Library/x86_64/libkmod.a"
/usr/bin/file "$stage/AICProbe"
/usr/bin/xcrun ld -kext -arch x86_64 -undefined dynamic_lookup \
    -o "$stage/AICHeadlessProbe" \
    "$stage/AICAirPortController-headless.o" "$stage/AICNativeBridgeUserClient.o" \
    "$stage/AICInfraInterface.o" \
    "$(dirname "$2")/Library/x86_64/libkmod.a"
/usr/bin/file "$stage/AICHeadlessProbe"

boot_kc=/System/Library/KernelCollections/BootKernelExtensions.kc
system_kc=/System/Library/KernelCollections/SystemKernelExtensions.kc
if [ -f "$boot_kc" ] && [ -f "$system_kc" ]; then
    { /usr/bin/xcrun nm -u "$stage/AICProbe"
      /usr/bin/xcrun nm -u "$stage/AICHeadlessProbe"; } |
        /usr/bin/awk 'NF {print $NF}' | /usr/bin/sort -u > "$stage/undefined.txt"
    { /usr/bin/xcrun nm -g "$boot_kc" 2>/dev/null
      /usr/bin/xcrun nm -g "$system_kc" 2>/dev/null; } |
        /usr/bin/awk '$2 != "U" {print $3}' | /usr/bin/sort -u > "$stage/exports.txt"
    /usr/bin/comm -23 "$stage/undefined.txt" "$stage/exports.txt" > "$stage/missing.txt"
    if [ -s "$stage/missing.txt" ]; then
        echo 'Símbolos externos ausentes das coleções locais:' >&2
        /bin/cat "$stage/missing.txt" >&2
        exit 1
    fi
    count=$(/usr/bin/wc -l < "$stage/undefined.txt" | /usr/bin/tr -d ' ')
    echo "$count símbolos externos encontrados nas coleções locais."
fi

bundle="$stage/AICNativeProbe.kext"
/bin/mkdir -p "$bundle/Contents/MacOS"
/bin/cp "$stage/AICProbe" "$bundle/Contents/MacOS/AICNativeProbe"
/bin/chmod 755 "$bundle/Contents/MacOS/AICNativeProbe"
/bin/cp "$repo_dir/native/AICNativeProbe-Info.plist" "$bundle/Contents/Info.plist"
/usr/bin/plutil -lint "$bundle/Contents/Info.plist"
if ! /usr/bin/xcrun nm -g "$bundle/Contents/MacOS/AICNativeProbe" |
    /usr/bin/awk '$3 == "_kmod_info" {found = 1} END {exit !found}'; then
    echo 'Pacote inválido: símbolo kmod_info ausente.' >&2
    exit 1
fi
echo 'Pacote temporário estruturado; coleção, carregamento e Wi-Fi não verificados.'
if [ "$#" -eq 3 ]; then
    if ! /usr/bin/kmutil print-diagnostics -Z -z -p "$bundle" > "$stage/diagnostics.txt" 2>&1; then
        /bin/cat "$stage/diagnostics.txt"
        echo 'Diagnóstico do kext falhou; não carregar este pacote.' >&2
        exit 1
    fi
    /bin/cat "$stage/diagnostics.txt"
    if /usr/bin/grep -Eq '^Error:|^[[:space:]]+Filesystem error:' "$stage/diagnostics.txt"; then
        echo 'Diagnóstico do kext falhou; não carregar este pacote.' >&2
        exit 1
    fi
fi
