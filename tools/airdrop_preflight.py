#!/usr/bin/env python3
"""Read-only AirDrop prerequisites probe; never reports network names or MACs.

An AWDL interface is necessary for the intended native peer-to-peer path, but
its presence alone does not prove that AirDrop discovery or transfer works.
"""

import json
import platform
import re
import subprocess


def command_output(*args):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=8)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout if result.returncode == 0 else ""


def probe(run=command_output):
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
        "airdrop_proven": False,
        "next_gate": (
            "Test AIC-backed AWDL discovery and bidirectional transfer."
            if awdl else
            "Implement and validate an AIC-backed native Wi-Fi/AWDL interface."
        ),
    }


if __name__ == "__main__":
    print(json.dumps(probe(), indent=2, sort_keys=True))
