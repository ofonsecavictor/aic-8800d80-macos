#!/bin/sh
# Offline build/link/symbol probe. It never installs or loads a kext.
set -eu

if [ "$#" -ne 2 ] || [ ! -f "$1/macOS15/IO80211ControllerV2.h" ] ||
    [ ! -f "$1/apple_private_spi.h" ] || [ ! -f "$2/IOKit/IOService.h" ]; then
    echo 'Uso: sh tools/check_native_controller.sh /caminho/itlwm-Sequoia/include/Airport /caminho/MacKernelSDK/Headers' >&2
    exit 2
fi

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)
sdk=$(/usr/bin/xcrun --sdk macosx --show-sdk-path)
kernel_headers="$sdk/System/Library/Frameworks/Kernel.framework/Versions/A/Headers"
stage=$(/usr/bin/mktemp -d /private/tmp/aic-native-compile.XXXXXX)
cleanup() {
    /bin/rm -f "$stage/AICAirPortController.o"
    /bin/rm -f "$stage/AICNativeBridgeUserClient.o"
    /bin/rm -f "$stage/AICProbe" "$stage/undefined.txt"
    /bin/rm -f "$stage/exports.txt" "$stage/missing.txt"
    /bin/rmdir "$stage" 2>/dev/null || true
}
trap cleanup EXIT

/usr/bin/xcrun clang++ -std=c++14 -fno-exceptions -fno-rtti -fapple-kext \
    -mkernel -c -o "$stage/AICAirPortController.o" \
    -Wno-deprecated-declarations -Wno-invalid-offsetof \
    -Wno-inconsistent-missing-override \
    -DKERNEL=1 -DAIRPORT_WCL=1 -D__PRIVATE_SPI__=1 -DIO80211FAMILY_V2=1 \
    -D__IO80211_TARGET=__MAC_15_2 -include "$1/apple_private_spi.h" \
    -I"$1" -I"$2" -I"$kernel_headers" \
    "$repo_dir/native/AICAirPortController.cpp"
/usr/bin/file "$stage/AICAirPortController.o"
/usr/bin/xcrun clang++ -std=c++14 -fno-exceptions -fno-rtti -fapple-kext \
    -mkernel -c -o "$stage/AICNativeBridgeUserClient.o" \
    -Wno-deprecated-declarations -Wno-invalid-offsetof \
    -Wno-inconsistent-missing-override \
    -DKERNEL=1 -DAIRPORT_WCL=1 -D__PRIVATE_SPI__=1 -DIO80211FAMILY_V2=1 \
    -D__IO80211_TARGET=__MAC_15_2 -include "$1/apple_private_spi.h" \
    -I"$1" -I"$2" -I"$kernel_headers" \
    "$repo_dir/native/AICNativeBridgeUserClient.cpp"
/usr/bin/file "$stage/AICNativeBridgeUserClient.o"

# Dynamic lookup only creates a Mach-O kext shape; it does not resolve an ABI.
/usr/bin/xcrun ld -kext -arch x86_64 -undefined dynamic_lookup \
    -o "$stage/AICProbe" \
    "$stage/AICAirPortController.o" "$stage/AICNativeBridgeUserClient.o"
/usr/bin/file "$stage/AICProbe"

boot_kc=/System/Library/KernelCollections/BootKernelExtensions.kc
system_kc=/System/Library/KernelCollections/SystemKernelExtensions.kc
if [ -f "$boot_kc" ] && [ -f "$system_kc" ]; then
    /usr/bin/xcrun nm -u "$stage/AICProbe" |
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
echo 'Link permissivo apenas: ABI, carregamento e interface Wi-Fi não verificados.'
