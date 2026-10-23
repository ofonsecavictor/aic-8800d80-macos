import struct
import unittest

from layouts import association_diagnostics


class AssociationDiagnosticsTests(unittest.TestCase):
    def test_extracts_channel_context_and_capability_ies(self):
        request = bytes([45, 2, 0x63, 0x09, 191, 4, 1, 2, 3, 4,
                         199, 1, 2])
        response = bytes([61, 2, 40, 5, 192, 3, 1, 42, 0])
        body = bytearray(852)
        struct.pack_into('<HH', body, 14, len(request), len(response))
        body[20:20 + len(request)] = request
        body[20 + len(request):20 + len(request) + len(response)] = response
        struct.pack_into('<H', body, 824, 5200)
        body[826] = 2
        struct.pack_into('<II', body, 828, 5210, 0)

        result = association_diagnostics(bytes(body))
        self.assertEqual(result['width_code'], 2)
        self.assertEqual(result['primary_frequency'], 5200)
        self.assertEqual(result['center_frequency_1'], 5210)
        self.assertEqual(result['request_ht_capability'], '6309')
        self.assertEqual(result['request_vht_capability'], '01020304')
        self.assertEqual(result['request_operating_mode'], '02')
        self.assertEqual(result['response_vht_operation'], '012a00')

    def test_rejects_out_of_bounds_ie_lengths(self):
        body = bytearray(852)
        struct.pack_into('<HH', body, 14, 700, 101)
        self.assertIsNone(association_diagnostics(bytes(body)))


if __name__ == '__main__':
    unittest.main()
