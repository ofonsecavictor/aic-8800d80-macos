import ctypes
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from management import transmit_action_frame
from layouts import me_channel_config_request, me_config_request
from protocol import command
from wpa2 import transmit_frame


@unittest.skipUnless(sys.platform == 'darwin', 'AIC IOKit transport is macOS-only')
class USBValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='aic-usb-validation-')
        source = Path(__file__).resolve().parents[1] / 'wifi' / 'usb.c'
        library = Path(cls.temp.name) / 'libaicwifi.dylib'
        subprocess.run(['/usr/bin/clang', '-dynamiclib', '-O2',
                        '-framework', 'IOKit', '-framework', 'CoreFoundation',
                        '-o', str(library), str(source)], check=True,
                       capture_output=True)
        cls.lib = ctypes.CDLL(str(library))
        cls.lib.wifi_validate_data_frame.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        cls.lib.wifi_validate_data_frame.restype = ctypes.c_uint32
        cls.lib.wifi_validate_command_frame.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        cls.lib.wifi_validate_command_frame.restype = ctypes.c_uint32

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def valid(self, frame):
        return self.lib.wifi_validate_data_frame(ctypes.create_string_buffer(frame), len(frame)) == 0

    def valid_command(self, frame):
        return self.lib.wifi_validate_command_frame(
            ctypes.create_string_buffer(frame), len(frame)) == 0

    def test_accepts_only_exact_me_config_frame(self):
        frame = command(0x1400, me_config_request())
        self.assertEqual(len(frame), 128)
        self.assertTrue(self.valid_command(frame))
        self.assertFalse(self.valid_command(frame[:-1]))
        changed = bytearray(frame)
        changed[14] = 111
        self.assertFalse(self.valid_command(bytes(changed)))

    def test_accepts_only_exact_me_channel_config_frame(self):
        frame = command(0x1402, me_channel_config_request())
        self.assertEqual(len(frame), 270)
        self.assertTrue(self.valid_command(frame))
        self.assertFalse(self.valid_command(frame[:-1]))

    def test_accepts_bounded_action_and_existing_ethernet(self):
        source = bytes.fromhex('021122334455')
        action = (b'\xd0\x00' + bytes(2) + bytes.fromhex('ffffffffffff') + source
                  + bytes.fromhex('ffffffffffff') + bytes(2) + b'\x04')
        self.assertTrue(self.valid(transmit_action_frame(action, 1, source, 7)))
        robust = bytearray(transmit_action_frame(action, 1, source, 7))
        robust[56] = 8
        self.assertFalse(self.valid(bytes(robust)))
        ethernet = bytes.fromhex('00112233445566778899aabb0800') + bytes(50)
        self.assertTrue(self.valid(transmit_frame(ethernet, 0, 0, 0x80000000)))

    def test_unconfirmed_ethernet_avoids_exact_usb_packet_boundary(self):
        header = bytes.fromhex('00112233445566778899aabb0800')
        for size in (494, 1006):
            with self.subTest(size=size):
                packet = transmit_frame(header + bytes(size - 14), 0, 0)
                self.assertEqual(len(packet), size + 19)
                self.assertEqual(len(packet) % 512, 1)
                self.assertEqual(packet[-1], 0)
                self.assertTrue(self.valid(packet))

    def test_rejects_malformed_management_descriptor(self):
        source = bytes.fromhex('021122334455')
        action = (b'\xd0\x00' + bytes(2) + bytes.fromhex('ffffffffffff') + source
                  + bytes.fromhex('ffffffffffff') + bytes(2) + b'\x04')
        packet = transmit_action_frame(action, 1, source, 0)
        for index, value in ((29, 0), (30, 0), (32, 0x08), (12, 1)):
            changed = bytearray(packet)
            changed[index] = value
            with self.subTest(index=index):
                self.assertFalse(self.valid(bytes(changed)))


if __name__ == '__main__':
    unittest.main()
