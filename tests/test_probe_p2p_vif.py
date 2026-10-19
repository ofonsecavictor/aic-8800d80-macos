import importlib.util
from pathlib import Path
import struct
import unittest


SPEC = importlib.util.spec_from_file_location(
    'probe_p2p_vif', Path(__file__).resolve().parents[1] / 'tools' / 'probe_p2p_vif.py')
probe_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe_module)


class FakeWifi:
    mac = bytes.fromhex('001122334455')

    def __init__(self, fail_p2p=False, fail_remove=False):
        self.calls = []
        self.fail_p2p = fail_p2p
        self.fail_remove = fail_remove

    def identity(self):
        return {'lmac_version': '06090101', 'features': '01e877d7',
                'max_interfaces': 4}

    def initialize_radio(self):
        self.calls.append(('radio', b''))

    def request(self, message, payload=b''):
        self.calls.append((message, payload))
        if message == 6:
            if payload[-2] == 1 and self.fail_p2p:
                return b'\x01\x00'
            return bytes((0, 1 if payload[-2] == 1 else 0))
        if message == 8 and self.fail_remove:
            raise RuntimeError('remove failed')
        return b''


class P2PVifTests(unittest.TestCase):
    def test_encodes_distinct_sta_and_p2p_then_removes_both(self):
        device = FakeWifi()
        result = probe_module.probe(device)
        adds = [payload for msg, payload in device.calls if msg == 6]
        self.assertEqual(len(adds), 2)
        self.assertEqual(struct.unpack('<Bx6sBx', adds[0]), (0, device.mac, 0))
        self.assertEqual(struct.unpack('<Bx6sBx', adds[1]),
                         (0, probe_module.p2p_mac(device.mac), 1))
        self.assertEqual([payload for msg, payload in device.calls if msg == 8],
                         [b'\x01', b'\x00'])
        self.assertEqual(device.calls[-1][0], 0)
        self.assertFalse(result['airdrop_proven'])

    def test_p2p_rejection_cleans_up_station_and_resets(self):
        device = FakeWifi(fail_p2p=True)
        with self.assertRaisesRegex(RuntimeError, 'ADD_IF rejected'):
            probe_module.probe(device)
        self.assertEqual([payload for msg, payload in device.calls if msg == 8],
                         [b'\x00'])
        self.assertEqual(device.calls[-1][0], 0)

    def test_cleanup_failure_is_not_reported_as_success(self):
        device = FakeWifi(fail_remove=True)
        with self.assertRaisesRegex(RuntimeError, 'cleanup failed'):
            probe_module.probe(device)
        self.assertEqual(device.calls[-1][0], 0)


if __name__ == '__main__':
    unittest.main()
