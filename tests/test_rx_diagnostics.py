import queue
import struct
import unittest

import wifi


class RxDiagnosticsTests(unittest.TestCase):
    def test_decodes_packed_d80_vector_as_vht80(self):
        record = bytearray(84)
        struct.pack_into('<H', record, 0, 24)
        record[12] = 4 | (2 << 4)  # FORMATMOD_VHT, PHY_CHNL_BW_80
        struct.pack_into('<I', record, 48, 1 << 6)

        adapter = object.__new__(wifi.Wifi)
        adapter.rx = queue.Queue()
        adapter.rx.put(bytes(record))
        adapter.rx_diagnostics = {
            'records': 0, 'malformed': 0, 'ethernet_frames': 0,
            'queue_dropped': 0, 'queue_highwater': 0,
            'hardware': {}, 'phy': {}, 'ether_types': {},
            'sample_header': None,
        }

        self.assertEqual(adapter.data_read(0), bytes(record))
        self.assertEqual(adapter.rx_diagnostics['phy'], {'vht-80MHz': 1})


if __name__ == '__main__':
    unittest.main()
