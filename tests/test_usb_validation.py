import ctypes
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from management import transmit_action_frame
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

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def valid(self, frame):
        return self.lib.wifi_validate_data_frame(ctypes.create_string_buffer(frame), len(frame)) == 0

    def test_accepts_bounded_action_and_existing_ethernet(self):
        source = bytes.fromhex('021122334455')
        action = (b'\xd0\x00' + bytes(2) + bytes.fromhex('ffffffffffff') + source
                  + bytes.fromhex('ffffffffffff') + bytes(2) + b'\x04')
        self.assertTrue(self.valid(transmit_action_frame(action, 1, source, 7)))
        ethernet = bytes.fromhex('00112233445566778899aabb0800') + bytes(50)
        self.assertTrue(self.valid(transmit_frame(ethernet, 0, 0, 0x80000000)))

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
