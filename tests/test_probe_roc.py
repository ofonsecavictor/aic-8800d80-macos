from collections import deque
from pathlib import Path
import sys
from unittest.mock import patch
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import probe_roc


class FakeWifi:
    mac = bytes.fromhex('001122334455')

    def __init__(self, expired=True, timeout_roc=False):
        self.calls = []
        self.events = deque([(72, b'\x01\x02')]) if expired else deque()
        self.timeout_roc = timeout_roc

    def identity(self):
        return {'lmac_version': '06090101', 'features': '01e877d7',
                'max_interfaces': 4}

    def initialize_radio(self):
        self.calls.append(('radio', b''))

    def request(self, message, payload=b'', confirmation=None):
        self.calls.append((message, payload))
        if message == 6:
            return bytes((0, 1 if payload[-2] else 0))
        if message == 70:
            if payload[0] == 0 and self.timeout_roc:
                raise RuntimeError('ROC confirmation timed out')
            return b'\x01\x00\x02' if payload[0] == 1 else b'\x00\x00\x02'
        return b''

    def read(self):
        return []


class ROCProbeTests(unittest.TestCase):
    def test_expiration_cleans_up_without_cancel(self):
        device = FakeWifi()
        result = probe_roc.probe(device)
        self.assertTrue(result['roc_accepted'])
        self.assertTrue(result['roc_expired_indication'])
        self.assertFalse(result['airdrop_proven'])
        self.assertEqual([payload for msg, payload in device.calls if msg == 70][0][0], 0)
        self.assertEqual([payload for msg, payload in device.calls if msg == 8],
                         [b'\x01', b'\x00'])
        self.assertEqual(device.calls[-1][0], 0)

    def test_missing_expiration_cancels_before_removal(self):
        device = FakeWifi(expired=False)
        with patch.object(probe_roc.time, 'monotonic', side_effect=[0, 4]):
            result = probe_roc.probe(device)
        self.assertFalse(result['roc_expired_indication'])
        self.assertEqual([payload[0] for msg, payload in device.calls if msg == 70],
                         [0, 1])
        self.assertEqual(device.calls[-1][0], 0)

    def test_lost_confirmation_still_attempts_cancel(self):
        device = FakeWifi(timeout_roc=True)
        with self.assertRaisesRegex(RuntimeError, 'confirmation timed out'):
            probe_roc.probe(device)
        self.assertEqual([payload[0] for msg, payload in device.calls if msg == 70],
                         [0, 1])
        self.assertEqual(device.calls[-1][0], 0)

    def test_callback_error_cancels_roc_before_removing_vifs(self):
        device = FakeWifi()

        def fail_action(_device, _vif, _frequency):
            raise RuntimeError('Diagnostic USB submission failed')

        with self.assertRaisesRegex(RuntimeError, 'submission failed'):
            probe_roc.probe(device, on_roc=fail_action)
        self.assertEqual([payload[0] for msg, payload in device.calls if msg == 70],
                         [0, 1])
        self.assertEqual([payload for msg, payload in device.calls if msg == 8],
                         [b'\x01', b'\x00'])
        self.assertEqual(device.calls[-1][0], 0)


if __name__ == '__main__':
    unittest.main()
