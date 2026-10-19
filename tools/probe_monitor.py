#!/usr/bin/python3
"""Temporary passive monitor RX control; no TX, payload logging, or install."""
import json
from pathlib import Path
import queue
import struct
import sys
import time

from management import (CONFIG_MONITOR_REQUEST_ID,
                        CONFIG_MONITOR_CONFIRMATION_ID,
                        configure_monitor_request, is_awdl_action_candidate,
                        parse_monitor_confirmation)

FREQUENCY = 5220
CHANNEL = 44
LISTEN_SECONDS = 3


def count_records(data, counts):
    offset = 0
    while offset < len(data):
        if len(data) - offset < 60:
            counts['unparsed_batches'] += 1
            return
        length = struct.unpack_from('<H', data, offset)[0]
        end = offset + 60 + length
        if length < 24 or end > len(data):
            counts['unparsed_batches'] += 1
            return
        frame = data[offset + 60:end]
        offset = end
        counts['bounded_records'] += 1
        subtype = struct.unpack_from('<H', frame)[0] & 0x00fc
        if subtype == 0x0080:
            counts['beacons'] += 1
        elif subtype == 0x00d0:
            counts['action_frames'] += 1
            if is_awdl_action_candidate(frame):
                counts['awdl_candidates'] += 1


def probe(device, now=time.monotonic):
    info = device.identity()
    if info['lmac_version'] != '06090101':
        raise RuntimeError('Untested firmware revision')
    if info['max_interfaces'] < 1:
        raise RuntimeError('Firmware has no VIF capacity')
    created = None
    reset_started = False
    try:
        device.initialize_radio()
        reset_started = True
        device.request(0)
        device.request(2, bytes(64) + struct.pack('<IH2x', 300, 20))
        device.request(0x65, struct.pack('<5B3x2I', 1, 0, 1, 0, 0, 0, 0))
        response = device.request(6, struct.pack('<Bx6sBx', 4, device.mac, 0))
        if len(response) < 2 or response[0] != 0:
            raise RuntimeError('Monitor VIF rejected')
        created = response[1]
        if created >= info['max_interfaces']:
            raise RuntimeError('Monitor VIF index out of range')
        response = device.request(CONFIG_MONITOR_REQUEST_ID,
                                  configure_monitor_request(FREQUENCY),
                                  confirmation=CONFIG_MONITOR_CONFIRMATION_ID)
        context = parse_monitor_confirmation(response, FREQUENCY)
        counts = {'usb_batches': 0, 'bounded_records': 0, 'beacons': 0,
                  'action_frames': 0, 'awdl_candidates': 0, 'unparsed_batches': 0}
        deadline = now() + LISTEN_SECONDS
        while now() < deadline:
            try:
                data = device.rx.get(timeout=min(0.2, max(0, deadline - now())))
            except queue.Empty:
                continue
            if isinstance(data, Exception):
                raise data
            if data:
                counts['usb_batches'] += 1
                count_records(data, counts)
        return {'monitor_vif_created': True, 'monitor_context_configured': context != 0xff,
                'channel': CHANNEL, 'listen_seconds': LISTEN_SECONDS,
                **counts, 'airdrop_proven': False}
    finally:
        errors = []
        if created is not None:
            try:
                device.request(8, bytes([created]))
            except Exception as error:
                errors.append('REMOVE_IF: %s' % error)
        if reset_started:
            try:
                device.request(0)
            except Exception as error:
                errors.append('RESET: %s' % error)
        if errors:
            detail = 'AIC monitor cleanup failed: ' + '; '.join(errors)
            if sys.exc_info()[0] is None:
                raise RuntimeError(detail)
            print(detail, file=sys.stderr)


if __name__ == '__main__':
    import wifi as wifi_module

    wifi_module.HERE = Path(sys.argv[1]).resolve()
    device = None
    try:
        device = wifi_module.Wifi()
        print(json.dumps(probe(device), indent=2, sort_keys=True))
    finally:
        if device is not None:
            device.close()
