from collections import deque
from pathlib import Path
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
        self.batches = deque(batches)

    def data_read(self, timeout=0):
        return self.batches.popleft() if self.batches else b''


class PassiveCaptureTests(unittest.TestCase):
    def test_counts_only_and_restores_vifs(self):
        header = b'\xd0\x00' + bytes(22)
        awdl = header + b'\x7f\x00\x17\xf2\x08\x10\x03'
        other = header + b'\x04'
        device = ReceivingWifi([record(awdl) + record(other), b'not a record'])
        result = probe_action_rx.capture(device)
        self.assertEqual(result['rx_batches'], 2)
        self.assertEqual(result['action_frames'], 2)
        self.assertEqual(result['awdl_candidates'], 1)
        self.assertEqual(result['malformed_batches'], 1)
        self.assertFalse(result['airdrop_proven'])
        self.assertEqual(result['channel'], 44)
        self.assertEqual([payload for msg, payload in device.calls if msg == 8],
                         [b'\x01', b'\x00'])
        self.assertNotIn('mac', result)
        self.assertNotIn('frame', result)


if __name__ == '__main__':
    unittest.main()
