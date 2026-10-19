from collections import deque
from pathlib import Path
import queue
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import probe_action_rx
from test_probe_roc import FakeWifi


def record(frame):
    header = bytearray(60)
    header[:2] = len(frame).to_bytes(2, 'little')
    header[48:52] = (2 | (1 << 8)).to_bytes(4, 'little')
    return bytes(header) + frame


class ReceivingWifi(FakeWifi):
    def __init__(self, batches):
        super().__init__()
        self.rx = queue.Queue()
        self.batches = deque(batches)

    def request(self, message, payload=b'', confirmation=None):
        if message == 70 and payload[0] == 0:
            while self.batches:
                self.rx.put(self.batches.popleft())
            self.events.append((72, b'\x01\x02'))
        return super().request(message, payload, confirmation)


class PassiveCaptureTests(unittest.TestCase):
    def test_counts_only_and_restores_vifs(self):
        header = b'\xd0\x00' + bytes(22)
        awdl = header + b'\x7f\x00\x17\xf2\x08\x10\x03'
        other = header + b'\x04'
        device = ReceivingWifi([record(awdl) + record(other), b'not a record'])
        result = probe_action_rx.capture(device)
        self.assertEqual([item['channel'] for item in result['channels']], [6, 44, 149])
        first = result['channels'][0]
        self.assertEqual(first['rx_batches'], 2)
        self.assertEqual(first['action_frames'], 2)
        self.assertEqual(first['awdl_candidates'], 1)
        self.assertEqual(first['awdl_vif_indices'], {'1': 1})
        self.assertEqual(first['station_vif_index'], 0)
        self.assertEqual(first['p2p_vif_index'], 1)
        self.assertEqual(first['malformed_batches'], 1)
        self.assertEqual([item['rx_batches'] for item in result['channels'][1:]], [0, 0])
        self.assertFalse(result['airdrop_proven'])
        self.assertEqual([payload for msg, payload in device.calls if msg == 8],
                         [b'\x01', b'\x00'] * 3)
        self.assertEqual([int.from_bytes(payload[4:6], 'little') for msg, payload
                          in device.calls if msg == 70 and payload[0] == 0],
                         [2437, 5220, 5745])
        self.assertNotIn('mac', result)
        self.assertNotIn('frame', result)

    def test_filtered_capture_sets_mask_only_in_opted_in_runs(self):
        device = ReceivingWifi([])
        result = probe_action_rx.capture(device, use_filter=True)
        self.assertTrue(result['other_bssid_filter'])
        self.assertEqual([payload.hex() for msg, payload in device.calls if msg == 14],
                         ['98a70615'] * 3)
        self.assertEqual([payload for msg, payload in device.calls if msg == 8],
                         [b'\x01', b'\x00'] * 3)


if __name__ == '__main__':
    unittest.main()
