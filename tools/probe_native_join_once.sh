#!/bin/sh
# Temporary native observation. Always restore the installed service.
set -eu
[ "$(/usr/bin/id -u)" -eq 0 ] || { echo 'Root required' >&2; exit 2; }
mode=${1:-join}
[ "$#" -le 1 ] && { [ "$mode" = join ] || [ "$mode" = service ]; } || {
    echo 'Usage: probe_native_join_once.sh [service]' >&2
    exit 2
}
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)
support='/Library/Application Support/AIC88M80Driver/wifi'
daemon='/Library/LaunchDaemons/local.victor.AIC88M80WiFi.plist'
stage=$(/usr/bin/mktemp -d /private/tmp/aic-native-join.XXXXXX)
stopped=0
restore() {
    if [ "$stopped" -eq 1 ]; then
        echo 'Restaurando serviço AIC instalado...'
        /bin/launchctl bootstrap system "$daemon" || true
    fi
    /bin/rm -rf "$stage"
}
trap restore EXIT HUP INT TERM

[ -f "$daemon" ] && [ -f "$support/libaicwifi.dylib" ] || exit 1
/usr/bin/kmutil showloaded --list-only 2>/dev/null |
    /usr/bin/grep -Eq 'local\.victor\.AICNativeProbe \(0\.0\.15\)' || {
        echo 'Kext nativo 0.0.15 não carregado; Wi-Fi atual intacto.' >&2
        exit 1
    }
echo 'Teste temporário usando o kext nativo 0.0.15 carregado.'
/bin/cp -R "$repo_dir/wifi" "$stage/wifi"
/bin/cp "$support/libaicwifi.dylib" "$stage/wifi/"
/bin/cp "$support/power-default.bin" "$stage/wifi/"
if [ -f "$support/radio-state.json" ]; then
    /bin/cp "$support/radio-state.json" "$stage/wifi/"
fi
/usr/bin/swiftc "$script_dir/native_scan_request.swift" -o "$stage/native-scan-request"

echo 'Pausando temporariamente o serviço AIC para conexão nativa...'
stopped=1
/bin/launchctl bootout system "$daemon"
/usr/bin/python3 - "$stage" "$script_dir/probe_native_join_once.py" \
    "$script_dir/probe_native_service_once.py" "$mode" <<'PY'
import os, subprocess, sys
stage, join_probe, service_probe, mode = sys.argv[1:]
env = dict(os.environ, PYTHONPATH=stage + '/wifi', PYTHONDONTWRITEBYTECODE='1')
command = (['/usr/bin/python3', '-B', service_probe] if mode == 'service' else
           ['/usr/bin/python3', '-B', join_probe, stage + '/native-scan-request'])
if mode == 'service':
    command.append(stage + '/native-scan-request')
try:
    observation = int(env.get('AIC_NATIVE_SERVICE_OBSERVE_SECONDS', '180')) if mode == 'service' else 180
    result = subprocess.run(command, env=env, timeout=max(360, observation + 120))
except subprocess.TimeoutExpired:
    print('NATIVE_JOIN_SUPERVISOR_TIMEOUT=1', flush=True)
    raise SystemExit(124)
raise SystemExit(result.returncode)
PY
