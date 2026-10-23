#!/usr/bin/python3
"""Read-only parallel GitHub asset baseline on the currently routed interface."""

import collections
from concurrent.futures import ThreadPoolExecutor
import re
import subprocess
import sys


if len(sys.argv) != 2 or sys.argv[1] not in ('utun4', 'en2'):
    raise SystemExit('Usage: probe_asset_baseline.py <utun4|en2>')

interface = sys.argv[1]
page = subprocess.run(
    ['/usr/bin/curl', '--interface', interface, '--silent', '--show-error',
     '--location', '--connect-timeout', '4', '--max-time', '12',
     'https://github.com/nullmoth/nvidia-macos-driver/releases/tag/v2.4.4'],
    capture_output=True, timeout=14)
assets = list(dict.fromkeys(re.findall(
    rb'https://github\.githubassets\.com/assets/[A-Za-z0-9._-]+\.(?:js|css)',
    page.stdout)))[:20]
if page.returncode or len(assets) != 20:
    raise SystemExit('Could not retrieve 20 diagnostic asset URLs')


def fetch(url):
    result = subprocess.run(
        ['/usr/bin/curl', '--interface', interface, '--silent', '--show-error',
         '--location', '--output', '/dev/null',
         '--write-out', '%{http_code} %{size_download}',
         '--connect-timeout', '4', '--max-time', '15', url.decode('ascii')],
        text=True, capture_output=True, timeout=17)
    fields = result.stdout.split()
    passed = (result.returncode == 0 and len(fields) >= 2 and
              fields[0] == '200' and float(fields[1]) > 0)
    return result.returncode, passed


for batch in range(4):
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(fetch, assets))
    codes = dict(sorted(collections.Counter(code for code, _ in results).items()))
    print('BATCH=%d INTERFACE=%s PASSED=%d/20 CURL_EXITS=%s' % (
        batch + 1, interface, sum(passed for _, passed in results), codes),
        flush=True)
