#!/usr/bin/env python3
"""Read-only AirDrop prerequisites probe; never reports network names or MACs.

An AWDL interface is necessary for the intended native peer-to-peer path, but
its presence alone does not prove that AirDrop discovery or transfer works.
"""

import json
import platform
import re
import subprocess
from pathlib import Path


CAPABILITIES = Path('/Library/Application Support/AIC88M80Driver/wifi/hardware-capabilities.json')


def command_output(*args):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=8)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout if result.returncode == 0 else ""


def read_capabilities(path=CAPABILITIES):
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    keys = ('lmac_version', 'features', 'max_stations', 'max_interfaces')
    if not isinstance(data, dict) or not all(key in data for key in keys):
        return None
    if not all(isinstance(data[key], str) and re.fullmatch(r'[0-9a-fA-F]{8}', data[key])
               for key in keys[:2]):
        return None
    if not all(isinstance(data[key], int) and 0 <= data[key] <= 255
               for key in keys[2:]):
        return None
    return {key: data[key] for key in keys}


def probe(run=command_output, capabilities=None):
    interfaces = set(run("/sbin/ifconfig", "-l").split())
    usb = run("/usr/sbin/ioreg", "-p", "IOUSB", "-l", "-n", "AIC 8800D80", "-r")
    native = run("/usr/sbin/ioreg", "-r", "-c", "IO80211Interface", "-l")

    vendor = bool(re.search(r'"idVendor"\s*=\s*42652\b', usb))
    ready = vendor and bool(re.search(r'"idProduct"\s*=\s*36225\b', usb))
    loader = vendor and bool(re.search(r'"idProduct"\s*=\s*36224\b', usb))
    usb_stage = "ready" if ready else "loader" if loader else "not_found"
    awdl = "awdl0" in interfaces
    io80211 = "IO80211Interface" in native

    return {
        "architecture": platform.machine(),
        "aic_usb_stage": usb_stage,
        "io80211_interface_present": io80211,
        "awdl0_present": awdl,
        "firmware_capabilities": read_capabilities() if capabilities is None else capabilities,
        "airdrop_proven": False,
        # An IO80211Interface anywhere in the registry is not proof that the
        # AIC owns it or that scan, association, and packet I/O work.
        "next_gate": (
            "Verify AIC ownership and native scan, association, and packet I/O."
            if io80211 else
            "Implement and validate an AIC-backed native Wi-Fi interface."
        ),
    }


if __name__ == "__main__":
    print(json.dumps(probe(), indent=2, sort_keys=True))
