#!/bin/sh
# Runtime class-loading gate only. Never matches USB or changes EFI/services.
set -eu

if [ "$(/usr/bin/id -u)" -ne 0 ]; then
    echo 'Execute com sudo; a senha deve ficar somente no Terminal.' >&2
    exit 2
fi

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
output=$(sh "$script_dir/check_native_controller.sh" \
    /Users/victor/Documents/Codex/2026-10-19/so/work/aic-native-build-deps/itlwm/include/Airport \
    /Users/victor/Documents/Codex/2026-10-19/so/work/aic-native-build-deps/MacKernelSDK/Headers --stage-load-only) || {
    printf '%s\n' "$output"
    exit 1
}
printf '%s\n' "$output"
bundle=$(printf '%s\n' "$output" | /usr/bin/sed -n 's/^LOAD_ONLY_BUNDLE=//p')
case "$bundle" in
    /private/tmp/aic-native-compile.*/AICNativeRegistrationProbe.kext) ;;
    *) echo 'Caminho temporário inesperado; não carregar.' >&2; exit 1 ;;
esac
if [ ! -f "$bundle/Contents/MacOS/AICNativeProbe" ] ||
    [ ! -f "$bundle/Contents/Info.plist" ]; then
    echo 'Pacote temporário incompleto; não carregar.' >&2
    exit 1
fi

load_attempted=0
unloaded=0
cleanup() {
    if [ "$load_attempted" -eq 1 ] && [ "$unloaded" -eq 0 ]; then
        echo "Carga/descarga inconclusiva; pacote preservado em $bundle" >&2
        return
    fi
    /bin/rm -f "$bundle/Contents/MacOS/AICNativeProbe" "$bundle/Contents/Info.plist"
    /bin/rmdir "$bundle/Contents/MacOS" "$bundle/Contents" "$bundle" "$(dirname "$bundle")" 2>/dev/null || true
}
trap cleanup EXIT

echo 'Carregando classes do kext SEM correspondência com o dongle; EFI e Wi-Fi atual intactos...'
load_attempted=1
/usr/bin/kmutil load --load-style start-only -p "$bundle"
echo 'Descarregando o kext experimental...'
/usr/bin/kmutil unload -b local.victor.AICNativeProbe
unloaded=1
echo 'Carga e descarga sem match concluídas. Ainda não é um teste da interface Wi-Fi.'
