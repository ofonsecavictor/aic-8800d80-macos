#!/usr/bin/python3
"""Bounded test of the uninstrumented native service loop."""
import ipaddress
import json
import os
import re
import subprocess
import threading
import time
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

if os.geteuid() != 0 or len(sys.argv) != 2:
    raise SystemExit('Usage (root): probe_native_service_once.py <CoreWLAN scan tool>')

from native_radio_control import NativeRadioPublisher
from native_scan_service import NativeScanSession
from wifi import Wifi

REPORT = Path('/private/tmp/aic-native-service-last.json')
report = {'phase': 'starting', 'sites': {}}
requested_network = os.environ.get('AIC_NATIVE_TEST_SSID')


def save_report():
    """Keep only link/site metrics, never Wi-Fi identifiers or packets."""
    descriptor, temporary = tempfile.mkstemp(
        prefix='.aic-native-service-', dir=str(REPORT.parent))
    try:
        with os.fdopen(descriptor, 'w') as stream:
            json.dump(report, stream, sort_keys=True)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, REPORT)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


save_report()


def en2_state():
    interface = subprocess.run(['/sbin/ifconfig', 'en2'], text=True,
                               capture_output=True, timeout=3)
    if interface.returncode:
        return False, False, False
    active = 'status: active' in interface.stdout
    addresses = [line.split()[1] for line in interface.stdout.splitlines()
                 if line.lstrip().startswith('inet ') and len(line.split()) > 1]
    ipv4 = any(not (address.is_link_local or address.is_loopback or
                    address.is_unspecified)
               for address in (ipaddress.ip_address(value) for value in addresses))
    route = subprocess.run(['/sbin/route', '-n', 'get', 'default'], text=True,
                           capture_output=True, timeout=3)
    routed = route.returncode == 0 and any(
        line.strip() == 'interface: en2' for line in route.stdout.splitlines())
    return active, ipv4, routed


def https_over_en2(url, label, expected_status=200, minimum_bytes=0):
    result = subprocess.run(
        ['/usr/bin/curl', '--interface', 'en2', '--silent', '--show-error',
         '--location', '--output', '/dev/null',
         '--write-out', '%{http_code} %{size_download} %{time_total}',
         '--connect-timeout', '4', '--max-time', '12', url],
        text=True, capture_output=True, timeout=14)
    fields = result.stdout.split()
    code = fields[0] if fields else '-'
    size = int(float(fields[1])) if len(fields) > 1 else 0
    elapsed = fields[2] if len(fields) > 2 else '-'
    ok = (result.returncode == 0 and code == str(expected_status) and
          size >= minimum_bytes)
    report['sites'][label] = {'ok': ok, 'http': code, 'bytes': size,
                              'seconds': elapsed, 'curl_exit': result.returncode}
    save_report()
    print('NATIVE_SERVICE_%s_EN2=%s HTTP=%s BYTES=%d SECONDS=%s CURL_EXIT=%d' % (
        label, str(ok).lower(), code, size, elapsed, result.returncode), flush=True)
    return ok


def parallel_github_assets():
    """Exercise the concurrent JS/CSS downloads that a browser actually makes."""
    page = subprocess.run(
        ['/usr/bin/curl', '--interface', 'en2', '--silent', '--show-error',
         '--location', '--connect-timeout', '4', '--max-time', '12',
         'https://github.com/nullmoth/nvidia-macos-driver/releases/tag/v2.4.4'],
        capture_output=True, timeout=14)
    assets = list(dict.fromkeys(re.findall(
        rb'https://github\.githubassets\.com/assets/[A-Za-z0-9._-]+\.(?:js|css)',
        page.stdout)))[:20]
    if page.returncode or len(assets) < 20:
        report['assets'] = {'page_curl_exit': page.returncode,
                            'discovered': len(assets), 'passed': 0,
                            'attempted': 0, 'ok': False}
        save_report()
        print('NATIVE_SERVICE_ASSETS_EN2=false DISCOVERED=%d PAGE_CURL_EXIT=%d' %
              (len(assets), page.returncode), flush=True)
        return False

    def interface_counters():
        result = subprocess.run(['/usr/sbin/netstat', '-ib', '-I', 'en2'],
                                text=True, capture_output=True, timeout=3)
        lines = [line.split() for line in result.stdout.splitlines()
                 if line.startswith('en2 ') and '<Link#' in line]
        if result.returncode or not lines or len(lines[0]) < 7:
            return None
        fields = lines[0]
        return {'rx_packets': int(fields[-7]), 'rx_errors': int(fields[-6]),
                'tx_packets': int(fields[-4]), 'tx_errors': int(fields[-3])}

    def fetch(url, ipv4):
        args = ['/usr/bin/curl']
        if ipv4:
            args.append('-4')
        result = subprocess.run(
            args + ['--interface', 'en2', '--silent', '--show-error',
             '--location', '--output', '/dev/null',
             '--write-out', '%{http_code} %{size_download} %{time_total} %{remote_ip}',
             '--connect-timeout', '4', '--max-time', '15', url.decode('ascii')],
            text=True, capture_output=True, timeout=17)
        fields = result.stdout.split()
        status = fields[0] if fields else '-'
        size = int(float(fields[1])) if len(fields) > 1 else 0
        try:
            family = 'ipv%d' % ipaddress.ip_address(fields[3]).version
        except (IndexError, ValueError):
            family = 'none'
        return {'ok': result.returncode == 0 and status == '200' and size > 0,
                'http': status, 'bytes': size, 'curl_exit': result.returncode,
                'family': family}

    report['assets'] = {'page_curl_exit': page.returncode,
                        'discovered': len(assets)}
    all_ok = True
    # Reverse the order after the first pair: a later default batch distinguishes
    # address-family failures from a cold radio or an overloaded first batch.
    for label, ipv4 in (('default_a', False), ('ipv4_a', True),
                        ('ipv4_b', True), ('default_b', False)):
        before = interface_counters()
        dropped_before = wifi.rx_diagnostics['queue_dropped']
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda url: fetch(url, ipv4), assets))
        after = interface_counters()
        link_after = en2_state()
        passed = sum(item['ok'] for item in results)
        exits = sorted(set(item['curl_exit'] for item in results))
        families = {family: sum(item['family'] == family for item in results)
                    for family in ('ipv4', 'ipv6', 'none')}
        failed_families = {family: sum(item['family'] == family and not item['ok']
                                       for item in results)
                           for family in ('ipv4', 'ipv6', 'none')}
        delta = ({key: after[key] - before[key] for key in before}
                 if before is not None and after is not None else None)
        batch_ok = passed == len(results)
        all_ok &= batch_ok
        report['assets'][label] = {
            'attempted': len(results), 'passed': passed, 'curl_exits': exits,
            'families': families, 'failed_families': failed_families,
            'interface_delta': delta,
            'link_after': {'active': link_after[0], 'ipv4': link_after[1],
                           'route_en2': link_after[2]},
            'usb_rx_queue_dropped': wifi.rx_diagnostics['queue_dropped'] - dropped_before,
            'usb_rx_queue_highwater': wifi.rx_diagnostics['queue_highwater'],
            'ok': batch_ok}
        save_report()
        print('NATIVE_SERVICE_ASSETS_%s_EN2=%s PASSED=%d ATTEMPTED=%d '
              'CURL_EXITS=%s FAMILIES=%s FAILED_FAMILIES=%s '
              'IFACE_DELTA=%s RX_QUEUE_DROPPED=%d '
              'RX_QUEUE_HIGHWATER=%d ROUTE_EN2_AFTER=%s' % (
                  label.upper(), str(batch_ok).lower(), passed, len(results),
                  exits, families, failed_families, delta,
                  report['assets'][label]['usb_rx_queue_dropped'],
                  report['assets'][label]['usb_rx_queue_highwater'],
                  str(link_after[2]).lower()),
              flush=True)
    return all_ok


bridge = NativeRadioPublisher.open_if_present()
if bridge is None:
    raise SystemExit('Native controller unavailable')
stop = threading.Event()
finished = threading.Event()
ready = threading.Event()
errors = []
wifi = None
worker = None
join_requests = [0]
join_matches = []
join_bands = []
try:
    wifi = Wifi()
    session = NativeScanSession(wifi, bridge, stop)
    enable_scan = bridge.enable_scan_bridge
    next_join = bridge.next_join_request

    def mark_ready():
        result = enable_scan()
        ready.set()
        return result

    bridge.enable_scan_bridge = mark_ready

    def count_join_requests():
        request = next_join()
        if request is not None:
            join_requests[0] += 1
            join_matches.append(request['ssid'] == requested_network)
            join_bands.append('5ghz' if request['frequency'] >= 5000 else '2.4ghz')
        return request

    bridge.next_join_request = count_join_requests

    def run():
        try:
            session.run()
        except BaseException as error:
            errors.append(error)
        finally:
            finished.set()

    worker = threading.Thread(target=run, name='Native AIC service pilot', daemon=True)
    worker.start()
    if not ready.wait(20):
        raise RuntimeError('Native interface was not ready for macOS scan')
    report['phase'] = 'scanning'
    save_report()
    # After a failed native session, airportd may take a few seconds to
    # rediscover an already-registered en2. Match the installed service's
    # bounded power/scan retry instead of classifying the first lookup as a
    # site-transfer failure.
    power_deadline = time.monotonic() + 30
    while True:
        power = subprocess.run(['/usr/sbin/networksetup', '-setairportpower',
                                'en2', 'on'], text=True, capture_output=True,
                               timeout=10)
        scan = subprocess.run([sys.argv[1], 'en2'], text=True,
                              capture_output=True, timeout=30)
        if scan.returncode == 0 or time.monotonic() >= power_deadline:
            break
        if finished.is_set():
            break
        stop.wait(2)
    print('NATIVE_SERVICE_POWER_REQUEST_EXIT=%d' % power.returncode, flush=True)
    if power.returncode:
        print('NATIVE_SERVICE_POWER_ERROR=%s' %
              (power.stderr or power.stdout).strip()[:200], flush=True)
    print('COREWLAN_SCAN_EXIT=%d' % scan.returncode, flush=True)
    if scan.returncode:
        print('COREWLAN_SCAN_STDERR=%s' % scan.stderr.strip()[:200], flush=True)
    for line in scan.stdout.splitlines():
        if line.startswith(('COREWLAN_POWER_BEFORE=', 'COREWLAN_POWER_AFTER=',
                            'COREWLAN_SCAN_COUNT=', 'COREWLAN_SCAN_ERROR=')):
            print(line, flush=True)
    if scan.returncode:
        raise RuntimeError('CoreWLAN scan did not start')
    if requested_network:
        # Ask macOS to use its saved credentials. Never pass or log a password.
        join = subprocess.run(
            ['/usr/sbin/networksetup', '-setairportnetwork', 'en2',
             requested_network], text=True, capture_output=True, timeout=20)
        print('NATIVE_SERVICE_SAVED_JOIN_EXIT=%d' % join.returncode, flush=True)
        report['saved_join_exit'] = join.returncode
        save_report()
    seconds = int(os.environ.get('AIC_NATIVE_SERVICE_OBSERVE_SECONDS', '180'))
    if not 60 <= seconds <= 2100:
        raise ValueError('Native service observation duration is out of range')
    print('NATIVE_SERVICE_OBSERVE_SECONDS=%d' % seconds, flush=True)
    report['phase'] = 'observing'
    save_report()
    deadline = time.monotonic() + seconds
    observed_at = time.monotonic()
    longest_healthy = 0
    healthy_since = None
    startup_seconds = None
    active = ipv4 = routed = False
    previous_state = None
    state_transitions = []
    healthy_interruptions = 0
    next_report = observed_at
    next_https = observed_at
    https_ok = False
    periodic_https_ok = True
    https_checks = []
    assets_tested = False
    assets_ok = False
    while time.monotonic() < deadline and not finished.is_set():
        active, ipv4, routed = en2_state()
        current_state = (active, ipv4, routed)
        now = time.monotonic()
        if current_state != previous_state and len(state_transitions) < 32:
            state_transitions.append({
                'second': int(now - observed_at), 'active': active,
                'ipv4': ipv4, 'route_en2': routed})
        if current_state != previous_state or now >= next_report:
            print('NATIVE_SERVICE_STATE_SEC=%d ACTIVE=%s IPV4=%s ROUTE_EN2=%s' % (
                int(now - observed_at), str(active).lower(), str(ipv4).lower(),
                str(routed).lower()), flush=True)
            previous_state = current_state
            next_report = now + 15
        if active and ipv4 and routed:
            if healthy_since is None:
                healthy_since = time.monotonic()
                if startup_seconds is None:
                    startup_seconds = int(healthy_since - observed_at)
            longest_healthy = max(longest_healthy,
                                  int(time.monotonic() - healthy_since))
            if now >= next_https:
                check_ok = all((
                    https_over_en2('https://www.apple.com/', 'APPLE',
                                   minimum_bytes=100000),
                    https_over_en2('https://github.com/', 'GITHUB',
                                   minimum_bytes=100000),
                    https_over_en2('https://www.google.com/', 'GOOGLE',
                                   minimum_bytes=50000),
                    https_over_en2('https://www.wikipedia.org/', 'WIKIPEDIA',
                                   minimum_bytes=50000),
                ))
                # The same unauthenticated curl request gets HTTP 403 over
                # the known-working AIC route, so this is reachability only.
                chatgpt_ok = https_over_en2('https://chatgpt.com/', 'CHATGPT',
                                           expected_status=403, minimum_bytes=1000)
                https_ok |= check_ok
                periodic_https_ok &= check_ok and chatgpt_ok
                https_checks.append({'second': int(now - observed_at),
                                     'sites_ok': check_ok,
                                     'chatgpt_reachable': chatgpt_ok})
                report['https_checks'] = https_checks
                save_report()
                next_https = time.monotonic() + (180 if seconds > 240 else 15)
            if https_ok and not assets_tested:
                assets_tested = True
                assets_ok = parallel_github_assets()
        else:
            if healthy_since is not None:
                healthy_interruptions += 1
            healthy_since = None
        stop.wait(1)
    print('NATIVE_SERVICE_ACTIVE=%s IPV4=%s ROUTE_EN2=%s LONGEST_HEALTHY_SECONDS=%d' % (
        str(active).lower(), str(ipv4).lower(), str(routed).lower(), longest_healthy),
        flush=True)
    print('NATIVE_SERVICE_JOIN_REQUESTS=%d' % join_requests[0], flush=True)
    print('NATIVE_SERVICE_JOIN_MATCHES=%s BANDS=%s' % (
        join_matches, join_bands), flush=True)
    report['link'] = {'active': active, 'ipv4': ipv4, 'route_en2': routed,
                      'longest_healthy_seconds': longest_healthy,
                      'startup_seconds': startup_seconds,
                      'healthy_interruptions': healthy_interruptions,
                      'state_transitions': state_transitions,
                      'join_requests': join_requests[0],
                      'requested_network_joined': bool(join_matches and join_matches[-1]),
                      'join_bands': join_bands}
    report['usb_rx'] = {
        key: wifi.rx_diagnostics[key]
        for key in ('records', 'malformed', 'ethernet_frames',
                    'queue_dropped', 'queue_highwater', 'hardware', 'ether_types')}
    report['usb_tx'] = dict(wifi.tx_diagnostics,
                            sample_pending=len(wifi.tx_sample_pending))
    print('NATIVE_SERVICE_USB_RX_RECORDS=%d MALFORMED=%d FRAMES=%d '
          'QUEUE_DROPPED=%d QUEUE_HIGHWATER=%d HARDWARE=%s' % (
              report['usb_rx']['records'], report['usb_rx']['malformed'],
              report['usb_rx']['ethernet_frames'],
              report['usb_rx']['queue_dropped'], report['usb_rx']['queue_highwater'],
              report['usb_rx']['hardware']), flush=True)
    print('NATIVE_SERVICE_USB_TX=%s' % report['usb_tx'], flush=True)
    save_report()
    if errors:
        print('NATIVE_SERVICE_ERROR=%r' % errors[0], flush=True)
        raise RuntimeError('Native service ended: ' + repr(errors[0]))
    if finished.is_set():
        print('NATIVE_SERVICE_STOPPED_EARLY=1', flush=True)
        raise RuntimeError('Native service stopped before observation ended')
    # The join can consume part of a bounded observation window. Require a
    # meaningful interval after first routed IP, not 60 seconds from launch.
    required_healthy = min(60, max(30, seconds - (startup_seconds or 0) - 5))
    report['link']['required_healthy_seconds'] = required_healthy
    save_report()
    if not (active and ipv4 and routed and
            (not requested_network or (join_matches and join_matches[-1]))
            and longest_healthy >= required_healthy
            and healthy_interruptions == 0
            and https_ok and periodic_https_ok and assets_ok):
        raise RuntimeError('Native service did not hold a routed IPv4/HTTPS link')
finally:
    failure = sys.exc_info()[0]
    report['phase'] = 'failed' if failure else 'complete'
    if failure:
        report['error_type'] = failure.__name__
    save_report()
    stop.set()
    if worker:
        worker.join(15)
        if not finished.is_set():
            print('NATIVE_SERVICE_SHUTDOWN_TIMEOUT=1', flush=True)
            os._exit(5)
    elif wifi:
        wifi.close()
        bridge.close()
    else:
        bridge.close()
