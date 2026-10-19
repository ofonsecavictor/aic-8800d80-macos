#!/bin/sh
# Syntax-only check for the compile-only AIC AirPort class. No kext is built.
set -eu

if [ "$#" -ne 1 ] || [ ! -f "$1/IO80211Controller.h" ]; then
    echo 'Uso: sh tools/check_native_controller.sh /caminho/para/cabecalhos-IO80211' >&2
    exit 2
fi

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)
sdk=$(/usr/bin/xcrun --sdk macosx --show-sdk-path)
kernel_headers="$sdk/System/Library/Frameworks/Kernel.framework/Versions/A/Headers"

/usr/bin/xcrun clang++ -std=c++14 -fno-exceptions -fno-rtti -fsyntax-only \
    -Wno-deprecated-declarations -DKERNEL=1 -D__IO80211_TARGET=__MAC_15_0 \
    -I"$1" -I"$kernel_headers" \
    "$repo_dir/native/AICAirPortController.cpp"
