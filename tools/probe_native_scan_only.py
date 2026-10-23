#!/usr/bin/python3
"""Bounded native scan probe; no join requests or identifying results."""
import os
from pathlib import Path
import subprocess
import sys
import threading

if len(sys.argv) != 2 or os.geteuid() != 0:
    raise SystemExit('Usage (root): probe_native_scan_only.py <CoreWLAN probe>')

from native_radio_control import NativeRadioPublisher
from native_scan_service import NativeScanSession
from wifi import Wifi

bridge = NativeRadioPublisher.open_if_present()
if bridge is None:
    raise SystemExit('Native controller unavailable')

wifi = None
stop = threading.Event()
ready = threading.Event()
finished = threading.Event()
counts = {'requests': 0, 'results': 0, 'completed': 0}
errors = []
try:
    wifi = Wifi()
    wifi.research_probe = True
    session = NativeScanSession(wifi, bridge, stop, scan_only=True)
    original_enable = bridge.enable_scan_bridge
    original_request = bridge.next_scan_request
    original_result = bridge.submit_scan_result
    original_complete = bridge.complete_scan

    def enable():
        result = original_enable()
        ready.set()
        return result

    def request():
        result = original_request()
        if result is not None:
            counts['requests'] += 1
        return result

    def submit(sequence, item):
        result = original_result(sequence, item)
        counts['results'] += 1
        return result

    def complete(sequence, status=0):
        result = original_complete(sequence, status)
        if status == 0:
            counts['completed'] += 1
        return result

    bridge.enable_scan_bridge = enable
    bridge.next_scan_request = request
    bridge.submit_scan_result = submit
    bridge.complete_scan = complete

    def run():
        try:
            session.run()
        except BaseException as error:
            errors.append(error)
        finally:
            finished.set()

    worker = threading.Thread(target=run, name='AIC native scan only', daemon=True)
    worker.start()
    if not ready.wait(20):
        raise RuntimeError('Native scan bridge not ready in 20 seconds')
    print('NATIVE_SCAN_READY=1', flush=True)
    result = subprocess.run([str(Path(sys.argv[1])), 'en2'], timeout=45,
                            text=True, capture_output=True)
    for line in result.stdout.splitlines():
        if line.startswith(('COREWLAN_SCAN_COUNT=', 'COREWLAN_SCAN_ERROR=',
                            'COREWLAN_POWER_BEFORE=', 'COREWLAN_POWER_AFTER=')):
            print(line, flush=True)
    print('NATIVE_SCAN_REQUESTS=%d RESULTS=%d COMPLETED=%d' % (
        counts['requests'], counts['results'], counts['completed']), flush=True)
    if result.returncode or errors or not counts['requests'] or not counts['completed']:
        raise RuntimeError('macOS did not complete a native scan')
finally:
    stop.set()
    if wifi is None:
        bridge.close()
    else:
        worker.join(10)
        if not finished.is_set():
            print('NATIVE_SCAN_SHUTDOWN_TIMEOUT=1', flush=True)
            os._exit(5)  # Supervisor restores the stable launchd service.
        if errors:
            print('NATIVE_SCAN_SESSION_ERROR=%s' % type(errors[0]).__name__, flush=True)
