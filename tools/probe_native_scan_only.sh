#!/bin/sh
# Temporary scan-only handoff. Always restore the installed launchd service.
set -eu
[ "$(/usr/bin/id -u)" -eq 0 ] || { echo 'Root required' >&2; exit 2; }
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)
support='/Library/Application Support/AIC88M80Driver/wifi'
daemon='/Library/LaunchDaemons/local.victor.AIC88M80WiFi.plist'
stage=$(/usr/bin/mktemp -d /private/tmp/aic-native-scan.XXXXXX)
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
    /usr/bin/grep -Eq 'local\.victor\.AICNativeProbe \(0\.0\.2\)' || {
        echo 'Versão corrigida do kext nativo não carregada; Wi-Fi atual intacto.' >&2
        exit 1
    }
/bin/cp -R "$repo_dir/wifi" "$stage/wifi"
/bin/cp "$support/libaicwifi.dylib" "$stage/wifi/"
/bin/cp "$support/power-default.bin" "$stage/wifi/"
if [ -f "$support/radio-state.json" ]; then
    /bin/cp "$support/radio-state.json" "$stage/wifi/"
fi
/usr/bin/swiftc "$script_dir/native_scan_request.swift" -o "$stage/native-scan-request"

echo 'Pausando o serviço AIC por até 75 segundos para busca nativa...'
stopped=1
/bin/launchctl bootout system "$daemon"
/usr/bin/python3 - "$stage" "$script_dir/probe_native_scan_only.py" <<'PY'
import os, subprocess, sys
stage, probe = sys.argv[1:]
env = dict(os.environ, PYTHONPATH=stage + '/wifi', PYTHONDONTWRITEBYTECODE='1')
try:
    result = subprocess.run(['/usr/bin/python3', '-B', probe,
                             stage + '/native-scan-request'],
                            env=env, timeout=75)
except subprocess.TimeoutExpired:
    print('NATIVE_SCAN_SUPERVISOR_TIMEOUT=1', flush=True)
    raise SystemExit(124)
raise SystemExit(result.returncode)
PY
