from collections import deque
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import probe_concurrent_roc
from probe_concurrent_roc import probe_connected_roc


class FakeAssociatedWifi:
    mac = bytes.fromhex('001122334455')

    def __init__(self, accepted=True, timeout=False):
        self.events = deque([(72, b'\x01\x02')])
        self.calls = []
        self.accepted = accepted
        self.timeout = timeout

    def identity(self):
        return {'lmac_version': '06090101', 'max_interfaces': 4,
                'features': '01e877d7'}

    def request(self, message, payload=b'', confirmation=None):
        self.calls.append((message, payload))
        if message == 6:
            return b'\x00\x01'
        if message == 70:
            if payload[0] == 1:
                return b'\x01\x00\x02'
            if self.timeout:
                raise RuntimeError('ROC confirmation timed out')
            return b'\x00\x00\x02' if self.accepted else b'\x00\x08\x02'
        return b''

    def read(self, poll=False):
        return []


class ConcurrentROCTests(unittest.TestCase):
    def test_duplicate_vif_never_removes_authenticated_sta(self):
        device = FakeAssociatedWifi()
        with patch.object(probe_concurrent_roc, 'add_interface', return_value=0):
            with self.assertRaisesRegex(RuntimeError, 'Invalid P2P VIF'):
                probe_connected_roc(device, 0)
        self.assertNotIn(8, [message for message, _ in device.calls])

    def test_runner_initializes_identity_before_scan(self):
        class FakeWifiRunner:
            def __init__(self):
                self.info = None

            def identity(self):
                self.info = {'lmac_version': '06090101'}
                return self.info

            def scan(self, ssid, key):
                if self.info is None:
                    raise AssertionError('identity must precede scan')
                self.association_observer(0, 1, {})

            def close(self):
                pass

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'profile.json').write_text(json.dumps({'ssid': 'test'}))
            with patch.object(probe_concurrent_roc, 'SUPPORT', root), \
                 patch.object(probe_concurrent_roc.subprocess, 'run',
                              return_value=SimpleNamespace(returncode=0, stdout=b'k' * 32)), \
                 patch('wifi.Wifi', FakeWifiRunner), \
                 patch.object(probe_concurrent_roc, 'probe_connected_roc',
                              return_value={'roc_while_sta_authenticated_accepted': True}):
                probe_concurrent_roc.run(root)

    def test_accepted_roc_preserves_sta_and_removes_only_p2p(self):
        device = FakeAssociatedWifi()
        result = probe_connected_roc(device, 0)
        self.assertTrue(result['roc_while_sta_authenticated_accepted'])
        self.assertTrue(result['roc_expired_indication'])
        self.assertFalse(result['sta_data_during_roc_proven'])
        self.assertEqual([payload for message, payload in device.calls if message == 8],
                         [b'\x01'])
        self.assertNotIn(0, [message for message, _ in device.calls])  # no MAC reset

    def test_rejected_roc_still_removes_p2p(self):
        device = FakeAssociatedWifi(accepted=False)
        result = probe_connected_roc(device, 0)
        self.assertFalse(result['roc_while_sta_authenticated_accepted'])
        self.assertEqual([payload for message, payload in device.calls if message == 8],
                         [b'\x01'])

    def test_lost_confirmation_cancels_before_removing_p2p(self):
        device = FakeAssociatedWifi(timeout=True)
        with self.assertRaisesRegex(RuntimeError, 'confirmation timed out'):
            probe_connected_roc(device, 0)
        self.assertEqual([payload[0] for message, payload in device.calls if message == 70],
                         [0, 1])
        self.assertEqual(device.calls[-1], (8, b'\x01'))

    def test_no_expiry_cancels_before_removing_p2p(self):
        device = FakeAssociatedWifi()
        device.events.clear()
        with patch('probe_concurrent_roc.time.monotonic', side_effect=[0, 4]):
            result = probe_connected_roc(device, 0)
        self.assertFalse(result['roc_expired_indication'])
        self.assertEqual([payload[0] for message, payload in device.calls if message == 70],
                         [0, 1])


if __name__ == '__main__':
    unittest.main()
