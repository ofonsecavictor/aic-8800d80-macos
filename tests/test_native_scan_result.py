import ctypes as c
import unittest

from native_scan_result import BeaconMetadata, encode_beacon


class NativeScanResultTests(unittest.TestCase):
    def setUp(self):
        self.network = {
            'bssid': '02:11:22:33:44:55', 'frequency': 5220, 'rssi': -55,
            '_beacon': {'interval': 100, 'capability': 0x11,
                        'ies': b'\x00\x03AIC\x30\x02\x01\x00'},
        }

    def test_packs_sequoia_metadata_and_raw_ies(self):
        payload = encode_beacon(self.network)
        metadata = BeaconMetadata.from_buffer_copy(payload[:c.sizeof(BeaconMetadata)])
        self.assertEqual((metadata.channel, metadata.channel_spec), (44, 0xd02c))
        self.assertEqual(bytes(metadata.ssid[:metadata.ssid_length]), b'AIC')
        self.assertEqual(bytes(metadata.bssid), bytes.fromhex('021122334455'))
        self.assertEqual((metadata.rssi, metadata.interval), (-55, 100))
        self.assertEqual(metadata.ie_length, len(self.network['_beacon']['ies']))
        self.assertEqual(payload[c.sizeof(BeaconMetadata):],
                         self.network['_beacon']['ies'])

    def test_rejects_truncated_ies(self):
        self.network['_beacon']['ies'] = b'\x30\x03\x01'
        with self.assertRaises(ValueError):
            encode_beacon(self.network)

    def test_rejects_oversized_ssid_ie(self):
        self.network['_beacon']['ies'] = b'\x00\x21' + b'A' * 33
        with self.assertRaises(ValueError):
            encode_beacon(self.network)

    def test_rejects_invalid_band_and_bssid(self):
        self.network['frequency'] = 5955
        with self.assertRaises(ValueError):
            encode_beacon(self.network)
        self.network['frequency'] = 5220
        self.network['bssid'] = '01:11:22:33:44:55'
        with self.assertRaises(ValueError):
            encode_beacon(self.network)

    def test_keeps_non_utf8_ssid_bytes(self):
        self.network['_beacon']['ies'] = b'\x00\x02\xff\xfe'
        payload = encode_beacon(self.network)
        metadata = BeaconMetadata.from_buffer_copy(payload[:c.sizeof(BeaconMetadata)])
        self.assertEqual(bytes(metadata.ssid[:metadata.ssid_length]), b'\xff\xfe')


if __name__ == '__main__':
    unittest.main()
