import ctypes
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import probe_action_tx
from test_probe_roc import FakeWifi


class RecordingLibrary:
    def __init__(self, device):
        self.device = device
        self.packets = []

    def wifi_write_data(self, handle, buffer, length):
        self.packets.append(ctypes.string_at(buffer, length))
        self.device.tx_confirmations[0] = 1
        return 0


class TransmittingWifi(FakeWifi):
    def __init__(self):
        super().__init__()
        self.handle = 1
        self.tx_sequence = 0
        self.tx_confirmations = {}
        self.lib = RecordingLibrary(self)


class ActionTXTests(unittest.TestCase):
    def test_one_public_diagnostic_frame_and_cleanup(self):
        device = TransmittingWifi()
        result = probe_action_tx.run(device)
        self.assertTrue(result['roc_accepted'])
        self.assertEqual(result['p2p_vif_index'], 1)
        self.assertEqual(result['roc_action_result'], {
            'usb_submitted': True, 'firmware_confirmation': True,
            'firmware_tx_done': True, 'peer_ack_expected': False,
            'airdrop_proven': False})
        self.assertEqual(len(device.lib.packets), 1)
        packet = device.lib.packets[0]
        self.assertEqual(packet[2:4], b'\x01\x00')
        self.assertEqual(packet[26:32], b'\x03\xff\x01\xff\x08\x00')
        self.assertEqual(packet[32 + 24:32 + 30], b'\x04\x09\x02\x00\x00\x01')
        self.assertEqual([payload for msg, payload in device.calls if msg == 8],
                         [b'\x01', b'\x00'])
        self.assertEqual(device.calls[-1][0], 0)

    def test_refuses_other_channel(self):
        device = TransmittingWifi()
        with self.assertRaisesRegex(ValueError, 'channel 6'):
            probe_action_tx.submit_once(device, 1, 5220)
        self.assertEqual(device.lib.packets, [])


if __name__ == '__main__':
    unittest.main()
