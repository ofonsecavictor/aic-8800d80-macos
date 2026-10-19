#!/usr/bin/python3
"""Passive one-second-per-channel AWDL probe; no TX or frame logging."""
import json
from pathlib import Path
import sys

from management import (action_frames, is_awdl_action_candidate,
                        other_bssid_filter_request)
from probe_roc import probe

CHANNELS = ((6, 2437), (44, 5220), (149, 5745))


def capture(device, use_filter=False):
    channels = []
    for channel, frequency in CHANNELS:
        counts = {'rx_batches': 0, 'action_frames': 0, 'awdl_candidates': 0,
                  'awdl_vif_indices': {}, 'malformed_batches': 0}

        def observe(data):
            counts['rx_batches'] += 1
            try:
                for vif_index, frame in action_frames(data):
                    counts['action_frames'] += 1
                    if is_awdl_action_candidate(frame):
                        counts['awdl_candidates'] += 1
                        key = str(vif_index)
                        counts['awdl_vif_indices'][key] = (
                            counts['awdl_vif_indices'].get(key, 0) + 1)
            except ValueError:
                counts['malformed_batches'] += 1

        result = probe(device, on_rx=observe, duration_ms=1000,
                       frequency=frequency,
                       rx_filter=other_bssid_filter_request() if use_filter else None)
        result.update(counts)
        result['channel'] = channel
        channels.append(result)
    return {'channels': channels, 'other_bssid_filter': use_filter,
            'airdrop_proven': False}


if __name__ == '__main__':
    import wifi as wifi_module

    if len(sys.argv) not in (2, 3) or (len(sys.argv) == 3 and sys.argv[2] != '--filtered'):
        raise SystemExit('Usage: probe_action_rx.py STAGE [--filtered]')
    wifi_module.HERE = Path(sys.argv[1]).resolve()
    device = None
    try:
        device = wifi_module.Wifi()
        print(json.dumps(capture(device, use_filter=len(sys.argv) == 3),
                         indent=2, sort_keys=True))
    finally:
        if device is not None:
            device.close()
