#!/usr/bin/python3
"""One bounded non-AWDL public-action TX probe; never run without approval."""
import ctypes
import json
from pathlib import Path
import sys
import time

from management import transmit_action_frame
from probe_p2p_vif import p2p_mac
from probe_roc import probe


def diagnostic_action_frame(source_mac):
    """Broadcast an unregistered local vendor payload; no peer reply expected."""
    if len(source_mac) != 6 or source_mac[0] & 1:
        raise ValueError('Invalid source MAC')
    broadcast = bytes([0xff]) * 6
    header = (b'\xd0\x00\x00\x00' + broadcast + source_mac + broadcast +
              b'\x00\x00')
    # Public action, vendor-specific action code, local experimental OUI.
    return header + b'\x04\x09\x02\x00\x00\x01'


def submit_once(device, vif, frequency):
    if frequency != 2437:
        raise ValueError('Diagnostic action limited to channel 6')
    source = p2p_mac(device.mac)
    index = device.tx_sequence
    if not 0 <= index < (1 << 31):
        raise ValueError('TX confirmation index exhausted')
    device.tx_sequence += 1
    packet = transmit_action_frame(diagnostic_action_frame(source), vif,
                                   source, index)
    status = device.lib.wifi_write_data(
        device.handle, ctypes.create_string_buffer(packet), len(packet))
    if status:
        raise RuntimeError('USB action write: %08x' % status)
    deadline = time.monotonic() + 0.5
    value = device.tx_confirmations.pop(index, None)
    while value is None and time.monotonic() < deadline:
        device.events.extend(device.read(poll=True))
        value = device.tx_confirmations.pop(index, None)
        if value is None:
            time.sleep(0.01)
    return {'usb_submitted': True, 'firmware_confirmation': value is not None,
            'firmware_tx_done': bool(value & 1) if value is not None else False,
            'peer_ack_expected': False, 'airdrop_proven': False}


def run(device):
    result = probe(device, duration_ms=1000, frequency=2437, on_roc=submit_once)
    return result


if __name__ == '__main__':
    import wifi as wifi_module

    if len(sys.argv) != 2:
        raise SystemExit('Usage: probe_action_tx.py STAGE')
    wifi_module.HERE = Path(sys.argv[1]).resolve()
    device = None
    try:
        device = wifi_module.Wifi()
        print(json.dumps(run(device), indent=2, sort_keys=True))
    finally:
        if device is not None:
            device.close()
