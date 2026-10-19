#!/bin/sh
# Standalone, manual ROC research probe. Stops/restores AIC service; never
# replaces installed source, library, package, kext, or EFI files.
set -eu

if [ "$#" -gt 1 ] || { [ "$#" -eq 1 ] && [ "$1" != '--capture' ] && [ "$1" != '--capture-filtered' ] && [ "$1" != '--monitor' ] && [ "$1" != '--tx-check' ]; }; then
    echo 'Uso: sudo sh tools/probe_roc.sh [--capture|--capture-filtered|--monitor|--tx-check]' >&2
    exit 2
fi

daemon='/Library/LaunchDaemons/local.victor.AIC88M80WiFi.plist'
support='/Library/Application Support/AIC88M80Driver/wifi'
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)
stage=''
stopped=0

cleanup() {
    status=$?
    if [ "$stopped" -eq 1 ]; then
        if ! /bin/launchctl bootstrap system "$daemon"; then
            echo 'ERRO: serviço AIC não reiniciou; reinicie o Mac ou carregue o LaunchDaemon manualmente.' >&2
            status=1
        fi
    fi
    case "$stage" in
        /private/tmp/aic-roc.*)
            /bin/rm -f "$stage/libaicwifi.dylib" "$stage/power-default.bin" "$stage/radio-state.json"
            /bin/rmdir "$stage" 2>/dev/null || true
            ;;
    esac
    trap - EXIT
    exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if [ "$(/usr/bin/id -u)" -ne 0 ]; then
    echo 'Execute com sudo; o Wi-Fi AIC será interrompido temporariamente.' >&2
    exit 1
fi
if [ ! -f "$daemon" ] || [ ! -f "$support/power-default.bin" ]; then
    echo 'Instalação AIC não encontrada; nenhum serviço foi interrompido.' >&2
    exit 1
fi
if ! /bin/launchctl print system/local.victor.AIC88M80WiFi >/dev/null 2>&1; then
    echo 'Serviço AIC não está carregado; nenhum serviço foi interrompido.' >&2
    exit 1
fi

stage=$(/usr/bin/mktemp -d /private/tmp/aic-roc.XXXXXX)
/bin/chmod 700 "$stage"
/bin/cp "$support/power-default.bin" "$stage/power-default.bin"
if [ -f "$support/radio-state.json" ]; then
    /bin/cp "$support/radio-state.json" "$stage/radio-state.json"
fi
/usr/bin/clang -dynamiclib -O2 -framework IOKit -framework CoreFoundation \
    -o "$stage/libaicwifi.dylib" "$repo_dir/wifi/usb.c"

echo 'Pausando temporariamente o Wi-Fi AIC para teste de rádio...'
/bin/launchctl bootout system "$daemon"
stopped=1
/bin/sleep 2
if [ "$#" -eq 1 ] && [ "$1" = '--monitor' ]; then
    PYTHONPATH="$repo_dir/wifi:$script_dir" /usr/bin/python3 "$script_dir/probe_monitor.py" "$stage"
elif [ "$#" -eq 1 ] && [ "$1" = '--tx-check' ]; then
    PYTHONPATH="$repo_dir/wifi:$script_dir" /usr/bin/python3 "$script_dir/probe_action_tx.py" "$stage"
elif [ "$#" -eq 1 ] && [ "$1" = '--capture-filtered' ]; then
    PYTHONPATH="$repo_dir/wifi:$script_dir" /usr/bin/python3 "$script_dir/probe_action_rx.py" "$stage" --filtered
elif [ "$#" -eq 1 ]; then
    PYTHONPATH="$repo_dir/wifi:$script_dir" /usr/bin/python3 "$script_dir/probe_action_rx.py" "$stage"
else
    PYTHONPATH="$repo_dir/wifi:$script_dir" /usr/bin/python3 "$script_dir/probe_roc.py" "$stage"
fi
echo 'Teste concluído. Reativando o serviço AIC...'
