#!/bin/sh
# Offline build/link/symbol probe. It never installs or loads a kext.
set -eu

if [ "$#" -lt 2 ] || [ "$#" -gt 3 ] ||
    { [ "$#" -eq 3 ] && [ "$3" != '--diagnose' ] &&
      [ "$3" != '--stage-load-only' ] &&
      [ "$3" != '--stage-usb-test' ]; } ||
    [ ! -f "$1/macOS15/IO80211ControllerV2.h" ] ||
    [ ! -f "$1/apple_private_spi.h" ] || [ ! -f "$2/IOKit/IOService.h" ] ||
    [ ! -f "$(dirname "$2")/Library/x86_64/libkmod.a" ]; then
    echo 'Uso: sh tools/check_native_controller.sh /caminho/itlwm-Sequoia/include/Airport /caminho/MacKernelSDK/Headers [--diagnose|--stage-load-only|--stage-usb-test]' >&2
    exit 2
fi
if [ "$#" -eq 3 ] && [ "$(/usr/bin/id -u)" -ne 0 ]; then
    echo 'O diagnóstico kmutil exige pacote temporário root:wheel. Execute a checagem com sudo; nada será instalado ou carregado.' >&2
    exit 2
fi
keep_native=0
stage_load_only=0
stage_usb_test=0
if [ "$#" -eq 3 ] && [ "$3" = '--stage-load-only' ]; then
    stage_load_only=1
fi
if [ "$#" -eq 3 ] && [ "$3" = '--stage-usb-test' ]; then
    stage_usb_test=1
fi

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)
/usr/bin/python3 "$repo_dir/tools/generate_native_protocol_stubs.py" --check \
    "$1/macOS15/IO80211InfraProtocol.h" \
    "$repo_dir/native/AICInfraProtocolStubs.inc"
sdk=$(/usr/bin/xcrun --sdk macosx --show-sdk-path)
kernel_headers="$sdk/System/Library/Frameworks/Kernel.framework/Versions/A/Headers"
stage=$(/usr/bin/mktemp -d /private/tmp/aic-native-compile.XXXXXX)
cleanup() {
    /bin/rm -f "$stage/AICAirPortController.o"
    /bin/rm -f "$stage/AICAirPortController-headless.o"
    /bin/rm -f "$stage/AICAirPortController-native.o"
    /bin/rm -f "$stage/AICNativeBridgeUserClient.o"
    /bin/rm -f "$stage/AICInfraInterface.o"
    /bin/rm -f "$stage/AICNativeEthernetInterface.o"
    /bin/rm -f "$stage/AICProbe" "$stage/AICHeadlessProbe" "$stage/AICNativeRegistrationProbe" "$stage/undefined.txt"
    /bin/rm -f "$stage/native_bridge_protocol_test"
    /bin/rm -f "$stage/native_batch_transfer_test"
    /bin/rm -f "$stage/native_scan_request_test"
    /bin/rm -f "$stage/native_join_request_test"
    /bin/rm -f "$stage/native_join_mailbox_test"
    /bin/rm -f "$stage/native_wcl_beacon_test"
    /bin/rm -f "$stage/native_wcl_bss_cache_test"
    /bin/rm -f "$stage/native_wcl_extended_bss_test"
    /bin/rm -f "$stage/native_scan_mailbox_test"
    /bin/rm -f "$stage/native_wcl_hardware_address_test"
    /bin/rm -f "$stage/native_startup_policy_test"
    /bin/rm -f "$stage/exports.txt" "$stage/missing.txt"
    /bin/rm -f "$stage/diagnostics.txt"
    /bin/rm -f "$stage/AICNativeProbe.kext/Contents/MacOS/AICNativeProbe"
    /bin/rm -f "$stage/AICNativeProbe.kext/Contents/Info.plist"
    /bin/rmdir "$stage/AICNativeProbe.kext/Contents/MacOS" 2>/dev/null || true
    /bin/rmdir "$stage/AICNativeProbe.kext/Contents" 2>/dev/null || true
    /bin/rmdir "$stage/AICNativeProbe.kext" 2>/dev/null || true
    if [ "$keep_native" -eq 0 ]; then
        /bin/rm -f "$stage/AICNativeRegistrationProbe.kext/Contents/MacOS/AICNativeProbe"
        /bin/rm -f "$stage/AICNativeRegistrationProbe.kext/Contents/Info.plist"
        /bin/rmdir "$stage/AICNativeRegistrationProbe.kext/Contents/MacOS" 2>/dev/null || true
        /bin/rmdir "$stage/AICNativeRegistrationProbe.kext/Contents" 2>/dev/null || true
        /bin/rmdir "$stage/AICNativeRegistrationProbe.kext" 2>/dev/null || true
    fi
    /bin/rmdir "$stage" 2>/dev/null || true
}
trap cleanup EXIT

/usr/bin/xcrun clang++ -std=c++14 -Wall -Wextra -Werror \
    -o "$stage/native_bridge_protocol_test" \
    "$repo_dir/tests/native_bridge_protocol_test.cpp"
"$stage/native_bridge_protocol_test"
echo 'Contrato de estado e comando de energia: testes locais OK.'
/usr/bin/xcrun clang++ -std=c++14 -Wall -Wextra -Werror \
    -o "$stage/native_batch_transfer_test" \
    "$repo_dir/tests/native_batch_transfer_test.cpp"
"$stage/native_batch_transfer_test"
echo 'Transferência inline e por descritores de memória: testes locais OK.'
/usr/bin/xcrun clang++ -std=c++14 -Wall -Wextra -Werror \
    -o "$stage/native_startup_policy_test" \
    "$repo_dir/tests/native_startup_policy_test.cpp"
"$stage/native_startup_policy_test"
echo 'Topologia segura da fila nativa: teste local OK.'
/usr/bin/xcrun clang++ -std=c++14 -Wall -Wextra -Werror \
    -o "$stage/native_scan_request_test" \
    "$repo_dir/tests/native_scan_request_test.cpp"
"$stage/native_scan_request_test"
echo 'Decodificador WCL de varredura: testes locais OK.'
/usr/bin/xcrun clang++ -std=c++14 -Wall -Wextra -Werror \
    -o "$stage/native_join_request_test" \
    "$repo_dir/tests/native_join_request_test.cpp"
"$stage/native_join_request_test"
echo 'Decodificador WCL de conexão WPA2: testes locais OK.'
/usr/bin/xcrun clang++ -std=c++14 -Wall -Wextra -Werror \
    -o "$stage/native_join_mailbox_test" \
    "$repo_dir/tests/native_join_mailbox_test.cpp"
"$stage/native_join_mailbox_test"
echo 'Handoff de conexão WPA2: testes locais OK.'
/usr/bin/xcrun clang++ -std=c++14 -Wall -Wextra -Werror \
    -o "$stage/native_wcl_beacon_test" \
    "$repo_dir/tests/native_wcl_beacon_test.cpp"
"$stage/native_wcl_beacon_test"
echo 'Formato WCL de resultado de varredura: testes locais OK.'
/usr/bin/xcrun clang++ -std=c++14 -Wall -Wextra -Werror \
    -o "$stage/native_wcl_bss_cache_test" \
    "$repo_dir/tests/native_wcl_bss_cache_test.cpp"
"$stage/native_wcl_bss_cache_test"
echo 'Resposta WCL de rede conectada: testes locais OK.'
/usr/bin/xcrun clang++ -std=c++14 -Wall -Wextra -Werror \
    -o "$stage/native_wcl_extended_bss_test" \
    "$repo_dir/tests/native_wcl_extended_bss_test.cpp"
"$stage/native_wcl_extended_bss_test"
echo 'Detalhes WCL da rede conectada: testes locais OK.'
/usr/bin/xcrun clang++ -std=c++14 -Wall -Wextra -Werror \
    -o "$stage/native_scan_mailbox_test" \
    "$repo_dir/tests/native_scan_mailbox_test.cpp"
"$stage/native_scan_mailbox_test"
echo 'Ciclo de vida WCL de varredura: testes locais OK.'
/usr/bin/xcrun clang++ -std=c++14 -Wall -Wextra -Werror \
    -o "$stage/native_wcl_hardware_address_test" \
    "$repo_dir/tests/native_wcl_hardware_address_test.cpp"
"$stage/native_wcl_hardware_address_test"
echo 'Endereço MAC WCL nativo: teste local OK.'

/usr/bin/xcrun clang++ -std=c++14 -fno-exceptions -fno-rtti -fapple-kext \
    -mkernel -c -o "$stage/AICAirPortController.o" \
    -Wno-deprecated-declarations -Wno-invalid-offsetof \
    -Wno-inconsistent-missing-override \
    -DKERNEL=1 -DAIRPORT_WCL=1 -D__PRIVATE_SPI__=1 -DIO80211FAMILY_V2=1 \
    -D__IO80211_TARGET=__MAC_15_2 -include "$1/apple_private_spi.h" \
    -I"$(dirname "$1")" -I"$1" -I"$2" -I"$kernel_headers" \
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
    -I"$(dirname "$1")" -I"$1" -I"$2" -I"$kernel_headers" \
    "$repo_dir/native/AICAirPortController.cpp"
/usr/bin/file "$stage/AICAirPortController-headless.o"
# Compile registration in a separate object. An offline-only, disabled-match
# bundle below permits diagnostics of these exact bytes, never installation.
/usr/bin/xcrun clang++ -std=c++14 -fno-exceptions -fno-rtti -fapple-kext \
    -mkernel -c -o "$stage/AICAirPortController-native.o" \
    -Wno-deprecated-declarations -Wno-invalid-offsetof \
    -Wno-inconsistent-missing-override \
    -DKERNEL=1 -DAIRPORT_WCL=1 -D__PRIVATE_SPI__=1 -DIO80211FAMILY_V2=1 \
    -D__IO80211_TARGET=__MAC_15_2 -DAIC_HEADLESS_BRIDGE_PROBE=1 \
    -DAIC_NATIVE_INTERFACE_PROBE=1 -include "$1/apple_private_spi.h" \
    -I"$(dirname "$1")" -I"$1" -I"$2" -I"$kernel_headers" \
    "$repo_dir/native/AICAirPortController.cpp"
/usr/bin/file "$stage/AICAirPortController-native.o"
/usr/bin/xcrun clang++ -std=c++14 -fno-exceptions -fno-rtti -fapple-kext \
    -mkernel -c -o "$stage/AICNativeBridgeUserClient.o" \
    -Wno-deprecated-declarations -Wno-invalid-offsetof \
    -Wno-inconsistent-missing-override \
    -DKERNEL=1 -DAIRPORT_WCL=1 -D__PRIVATE_SPI__=1 -DIO80211FAMILY_V2=1 \
    -D__IO80211_TARGET=__MAC_15_2 -include "$1/apple_private_spi.h" \
    -I"$(dirname "$1")" -I"$1" -I"$2" -I"$kernel_headers" \
    "$repo_dir/native/AICNativeBridgeUserClient.cpp"
/usr/bin/file "$stage/AICNativeBridgeUserClient.o"

/usr/bin/xcrun clang++ -std=c++14 -fno-exceptions -fno-rtti -fapple-kext \
    -mkernel -c -o "$stage/AICInfraInterface.o" \
    -Wno-deprecated-declarations -Wno-invalid-offsetof \
    -Wno-inconsistent-missing-override \
    -DKERNEL=1 -DAIRPORT_WCL=1 -D__PRIVATE_SPI__=1 -DIO80211FAMILY_V2=1 \
    -D__IO80211_TARGET=__MAC_15_2 -include "$1/apple_private_spi.h" \
    -I"$(dirname "$1")" -I"$1" -I"$2" -I"$kernel_headers" \
    "$repo_dir/native/AICInfraInterface.cpp"
/usr/bin/file "$stage/AICInfraInterface.o"

/usr/bin/xcrun clang++ -std=c++14 -fno-exceptions -fno-rtti -fapple-kext \
    -mkernel -c -o "$stage/AICNativeEthernetInterface.o" \
    -Wno-deprecated-declarations -Wno-invalid-offsetof \
    -Wno-inconsistent-missing-override \
    -DKERNEL=1 -DAIRPORT_WCL=1 -D__PRIVATE_SPI__=1 -DIO80211FAMILY_V2=1 \
    -D__IO80211_TARGET=__MAC_15_2 -include "$1/apple_private_spi.h" \
    -I"$(dirname "$1")" -I"$1" -I"$2" -I"$kernel_headers" \
    "$repo_dir/native/AICNativeEthernetInterface.cpp"
/usr/bin/file "$stage/AICNativeEthernetInterface.o"

# Dynamic lookup only creates a Mach-O kext shape; it does not resolve an ABI.
/usr/bin/xcrun ld -kext -arch x86_64 -undefined dynamic_lookup \
    -o "$stage/AICProbe" \
    "$stage/AICAirPortController.o" "$stage/AICNativeBridgeUserClient.o" \
    "$stage/AICInfraInterface.o" "$stage/AICNativeEthernetInterface.o" \
    "$(dirname "$2")/Library/x86_64/libkmod.a"
/usr/bin/file "$stage/AICProbe"
/usr/bin/xcrun ld -kext -arch x86_64 -undefined dynamic_lookup \
    -o "$stage/AICHeadlessProbe" \
    "$stage/AICAirPortController-headless.o" "$stage/AICNativeBridgeUserClient.o" \
    "$stage/AICInfraInterface.o" "$stage/AICNativeEthernetInterface.o" \
    "$(dirname "$2")/Library/x86_64/libkmod.a"
/usr/bin/file "$stage/AICHeadlessProbe"
/usr/bin/xcrun ld -kext -arch x86_64 -undefined dynamic_lookup \
    -o "$stage/AICNativeRegistrationProbe" \
    "$stage/AICAirPortController-native.o" "$stage/AICNativeBridgeUserClient.o" \
    "$stage/AICInfraInterface.o" "$stage/AICNativeEthernetInterface.o" \
    "$(dirname "$2")/Library/x86_64/libkmod.a"
/usr/bin/file "$stage/AICNativeRegistrationProbe"

boot_kc=/System/Library/KernelCollections/BootKernelExtensions.kc
system_kc=/System/Library/KernelCollections/SystemKernelExtensions.kc
if [ -f "$boot_kc" ] && [ -f "$system_kc" ]; then
    { /usr/bin/xcrun nm -u "$stage/AICProbe"
      /usr/bin/xcrun nm -u "$stage/AICHeadlessProbe"
      /usr/bin/xcrun nm -u "$stage/AICNativeRegistrationProbe"; } |
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
native_bundle="$stage/AICNativeRegistrationProbe.kext"
/bin/mkdir -p "$native_bundle/Contents/MacOS"
/bin/cp "$stage/AICNativeRegistrationProbe" "$native_bundle/Contents/MacOS/AICNativeProbe"
/bin/chmod 755 "$native_bundle/Contents/MacOS/AICNativeProbe"
if [ "$stage_usb_test" -eq 1 ]; then
    /bin/cp "$repo_dir/native/AICNativeProbe-USBTest-Info.plist" "$native_bundle/Contents/Info.plist"
else
    /bin/cp "$repo_dir/native/AICNativeProbe-Info.plist" "$native_bundle/Contents/Info.plist"
fi
/usr/bin/plutil -lint "$native_bundle/Contents/Info.plist"
if ! /usr/bin/xcrun nm -g "$native_bundle/Contents/MacOS/AICNativeProbe" |
    /usr/bin/awk '$3 == "_kmod_info" {found = 1} END {exit !found}'; then
    echo 'Variante nativa inválida: símbolo kmod_info ausente.' >&2
    exit 1
fi
if [ "$stage_usb_test" -eq 1 ]; then
    echo 'Variante nativa temporária preparada para match USB; nada instalado.'
else
    echo 'Variante nativa temporária estruturada com match desativado; nada instalado.'
fi
if [ "$#" -eq 3 ]; then
    if [ "$stage_usb_test" -eq 0 ]; then
        match=$(/usr/libexec/PlistBuddy -c "Print :IOKitPersonalities:'Disabled Native Probe':IOResourceMatch" "$native_bundle/Contents/Info.plist")
        provider=$(/usr/libexec/PlistBuddy -c "Print :IOKitPersonalities:'Disabled Native Probe':IOProviderClass" "$native_bundle/Contents/Info.plist")
        if [ "$match" != 'local.victor.AICNativeProbe.NoAutoMatch' ] ||
            [ "$provider" != 'IOResources' ]; then
            echo 'Match automático inesperado; recusando diagnóstico/carga.' >&2
            exit 1
        fi
    else
        usb_provider=$(/usr/libexec/PlistBuddy -c "Print :IOKitPersonalities:'AIC 8800D80 WLAN Provider TEST ONLY':IOProviderClass" "$native_bundle/Contents/Info.plist")
        wifi_number=$(/usr/libexec/PlistBuddy -c "Print :IOKitPersonalities:'AIC 8800D80 WLAN Provider TEST ONLY':bInterfaceNumber" "$native_bundle/Contents/Info.plist")
        controller_provider=$(/usr/libexec/PlistBuddy -c "Print :IOKitPersonalities:'AIC Native Controller TEST ONLY':IOProviderClass" "$native_bundle/Contents/Info.plist")
        if [ "$usb_provider" != IOUSBHostInterface ] ||
            [ "$wifi_number" != 2 ] ||
            [ "$controller_provider" != AICNativeUSBProvider ]; then
            echo 'Personalidade USB de teste inesperada; recusando.' >&2
            exit 1
        fi
    fi
    if ! /usr/bin/kmutil print-diagnostics -Z -z -p "$native_bundle" > "$stage/diagnostics.txt" 2>&1; then
        /bin/cat "$stage/diagnostics.txt"
        echo 'Diagnóstico do kext falhou; não carregar este pacote.' >&2
        exit 1
    fi
    /bin/cat "$stage/diagnostics.txt"
    if /usr/bin/grep -Eq '^Error:|^[[:space:]]+Filesystem error:' "$stage/diagnostics.txt"; then
        echo 'Diagnóstico do kext falhou; não carregar este pacote.' >&2
        exit 1
    fi
    if [ "$stage_load_only" -eq 1 ] || [ "$stage_usb_test" -eq 1 ]; then
        keep_native=1
        if [ "$stage_usb_test" -eq 1 ]; then
            echo "USB_TEST_BUNDLE=$native_bundle"
            echo 'Pacote USB de teste preservado; nada instalado ou carregado.'
        else
            echo "LOAD_ONLY_BUNDLE=$native_bundle"
            echo 'Pacote temporário preservado apenas para carga sem match; nada instalado ou carregado.'
        fi
    fi
fi
