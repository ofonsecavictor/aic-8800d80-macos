#!/bin/sh
# Manual, disruptive probe: briefly stops AIC Wi-Fi and restores its daemon.
set -eu

daemon='/Library/LaunchDaemons/local.victor.AIC88M80WiFi.plist'
support='/Library/Application Support/AIC88M80Driver/wifi'
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
stopped=0

restore_service() {
    if [ "$stopped" -eq 1 ]; then
        if ! /bin/launchctl bootstrap system "$daemon"; then
            echo 'ERRO: serviço Wi-Fi não reiniciou; reinicie o Mac ou carregue o LaunchDaemon manualmente.' >&2
        fi
    fi
}
trap restore_service EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if [ "$(/usr/bin/id -u)" -ne 0 ]; then
    echo 'Execute com sudo no Terminal. O Wi-Fi AIC será interrompido temporariamente.' >&2
    exit 1
fi
if [ ! -f "$daemon" ] || [ ! -f "$support/wifi.py" ]; then
    echo 'Instalação AIC não encontrada; nenhum serviço foi interrompido.' >&2
    exit 1
fi
if ! /bin/launchctl print system/local.victor.AIC88M80WiFi >/dev/null 2>&1; then
    echo 'Serviço AIC não está carregado; nenhum serviço foi interrompido.' >&2
    exit 1
fi

echo 'Pausando temporariamente o Wi-Fi AIC para testar duas interfaces virtuais...'
/bin/launchctl bootout system "$daemon"
stopped=1
/bin/sleep 2
PYTHONPATH="$support" /usr/bin/python3 "$script_dir/probe_p2p_vif.py"
echo 'Teste concluído. Reativando o serviço AIC...'
