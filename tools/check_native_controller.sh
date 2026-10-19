#!/bin/sh
# Object-only check for the compile-only AIC AirPort class. No kext is linked.
set -eu

if [ "$#" -ne 1 ] || [ ! -f "$1/IO80211Controller.h" ]; then
    echo 'Uso: sh tools/check_native_controller.sh /caminho/para/cabecalhos-IO80211' >&2
    exit 2
fi

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)
sdk=$(/usr/bin/xcrun --sdk macosx --show-sdk-path)
kernel_headers="$sdk/System/Library/Frameworks/Kernel.framework/Versions/A/Headers"
stage=$(/usr/bin/mktemp -d /private/tmp/aic-native-compile.XXXXXX)
cleanup() {
    /bin/rm -f "$stage/AICAirPortController.o"
    /bin/rmdir "$stage" 2>/dev/null || true
}
trap cleanup EXIT

/usr/bin/xcrun clang++ -std=c++14 -fno-exceptions -fno-rtti -fapple-kext \
    -mkernel -c -o "$stage/AICAirPortController.o" \
    -Wno-deprecated-declarations -DKERNEL=1 -D__IO80211_TARGET=__MAC_15_0 \
    -I"$1" -I"$kernel_headers" \
    "$repo_dir/native/AICAirPortController.cpp"
/usr/bin/file "$stage/AICAirPortController.o"
echo 'Objeto compilado; vínculo com IO80211Family e carregamento não verificados.'
