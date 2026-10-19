from collections import deque
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import probe_concurrent_roc
from probe_concurrent_roc import probe_connected_roc, probe_ip_recovery


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
    def test_ip_recovery_requires_verified_gateway_before_roc(self):
        device = FakeAssociatedWifi()
        with patch.object(probe_concurrent_roc, 'probe_connected_roc') as roc:
            with self.assertRaisesRegex(RuntimeError, 'No verified DHCP'):
                probe_ip_recovery(device, 0, {}, {}, lambda frame: None,
                                  lambda: [], lambda frame: None)
            roc.assert_not_called()

    def test_ip_recovery_reports_only_after_roc_and_arp_reply(self):
        device = FakeAssociatedWifi()
        lease = {'address': b'\xc0\xa8\x01\x64', 'routers': b'\xc0\xa8\x01\x01'}
        sent = []
        with patch.object(probe_concurrent_roc, 'probe_connected_roc',
                          return_value={'roc_while_sta_authenticated_accepted': True,
                                        'roc_expired_indication': True}) as roc, \
             patch.object(probe_concurrent_roc, 'arp_reply', return_value=b'gateway'):
            result = probe_ip_recovery(device, 0, lease,
                                       {'dhcp_ack': True, 'gateway_arp_reply': True},
                                       sent.append, lambda: [b'arp-reply'], lambda frame: None)
        roc.assert_called_once_with(device, 0)
        self.assertEqual(len(sent), 1)
        self.assertTrue(result['gateway_arp_after_roc'])
        self.assertTrue(result['sta_ip_path_recovered'])

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

    def test_runner_wires_dhcp_lease_callback_for_ip_mode(self):
        class FakeWifiRunner:
            def identity(self):
                return {'lmac_version': '06090101'}

            def scan(self, ssid, key):
                self.assert_ip_mode()
                self.lease_observer(0, 1, {}, {}, lambda frame: None,
                                    lambda: [], lambda frame: None)

            def assert_ip_mode(self):
                if not self.test_ip:
                    raise AssertionError('DHCP test was not enabled')

            def close(self):
                pass

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'profile.json').write_text(json.dumps({'ssid': 'test'}))
            with patch.object(probe_concurrent_roc, 'SUPPORT', root), \
                 patch.object(probe_concurrent_roc.subprocess, 'run',
                              return_value=SimpleNamespace(returncode=0, stdout=b'k' * 32)), \
                 patch('wifi.Wifi', FakeWifiRunner), \
                 patch.object(probe_concurrent_roc, 'probe_ip_recovery',
                              return_value={'sta_ip_path_recovered': True}) as recovery:
                probe_concurrent_roc.run(root, verify_ip=True)
                self.assertEqual(recovery.call_count, 1)

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
