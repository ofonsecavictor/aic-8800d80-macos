#!/bin/sh
# Briefly pauses the installed AIC Wi-Fi daemon to query non-identifying
# firmware capabilities. Run manually with sudo; never run during critical use.
set -eu

daemon='/Library/LaunchDaemons/local.victor.AIC88M80WiFi.plist'
support='/Library/Application Support/AIC88M80Driver/wifi'
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
    echo 'Execute com sudo no Terminal. A conexão AIC será interrompida por alguns segundos.' >&2
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

echo 'Pausando temporariamente o serviço AIC para consultar o firmware...'
/bin/launchctl bootout system "$daemon"
stopped=1
/bin/sleep 2

/usr/bin/python3 - "$support" <<'PY'
import json
import sys

sys.path.insert(0, sys.argv[1])
from wifi import Wifi

device = None
try:
    device = Wifi()
    info = device.identity()
    keys = ('lmac_version', 'features', 'max_stations', 'max_interfaces')
    print(json.dumps({key: info[key] for key in keys}, indent=2, sort_keys=True))
finally:
    if device is not None:
        device.close()
PY

echo 'Consulta concluída. Reativando o serviço AIC...'
