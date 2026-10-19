#!/usr/bin/python3
"""Passive one-second-per-channel AWDL probe; no TX or frame logging."""
import json
from pathlib import Path
import sys

from management import action_frames, is_awdl_action_candidate
from probe_roc import probe

CHANNELS = ((6, 2437), (44, 5220), (149, 5745))


def capture(device):
    channels = []
    for channel, frequency in CHANNELS:
        counts = {'rx_batches': 0, 'action_frames': 0, 'awdl_candidates': 0,
                  'malformed_batches': 0}

        def observe(data):
            counts['rx_batches'] += 1
            try:
                for _, frame in action_frames(data):
                    counts['action_frames'] += 1
                    if is_awdl_action_candidate(frame):
                        counts['awdl_candidates'] += 1
            except ValueError:
                counts['malformed_batches'] += 1

        result = probe(device, on_rx=observe, duration_ms=1000,
                       frequency=frequency)
        result.update(counts)
        result['channel'] = channel
        channels.append(result)
    return {'channels': channels, 'airdrop_proven': False}


if __name__ == '__main__':
    import wifi as wifi_module

    wifi_module.HERE = Path(sys.argv[1]).resolve()
    device = None
    try:
        device = wifi_module.Wifi()
        print(json.dumps(capture(device), indent=2, sort_keys=True))
    finally:
        if device is not None:
            device.close()
