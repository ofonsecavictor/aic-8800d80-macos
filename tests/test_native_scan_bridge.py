import struct
import unittest

from native_scan_bridge import ScanRequest, completion, decode_request, encode_result


class NativeScanBridgeTests(unittest.TestCase):
    def test_selected_five_ghz_channel_and_binary_ssid(self):
        request = ScanRequest()
        request.version = 2
        request.sequence = 9
        request.identifier = 12
        request.type = 1
        request.ssidLength = 3
        request.ssid[:3] = b'A\xffC'
        request.channelCount = 1
        request.selectedChannels[44 // 8] |= 1 << (44 % 8)
        decoded = decode_request(request)
        self.assertEqual(decoded['ssid'], b'A\xffC')
        self.assertEqual(decoded['frequencies'], (5220,))
        self.assertEqual(decoded['sequence'], 9)

    def test_invalid_channel_request_rejected(self):
        request = ScanRequest()
        request.version = 2
        request.sequence = 1
        request.type = 1
        request.channelCount = 1
        request.selectedChannels[200 // 8] |= 1 << (200 % 8)
        with self.assertRaises(ValueError):
            decode_request(request)
        request.selectedChannels[200 // 8] = 0
        request.channelCount = 0
        request.reserved[0] = 1
        with self.assertRaises(ValueError):
            decode_request(request)

    def test_beacon_result_layout_and_padding(self):
        ies = bytes([0, 3]) + b'AIC' + bytes([3, 1, 44])
        item = {'bssid': '02:11:22:33:44:55', 'frequency': 5220,
                'rssi': -57, '_beacon': {'interval': 100,
                                        'capability': 0x11, 'ies': ies}}
        result = encode_result(9, item)
        payload = bytes(result.data[:result.length])
        self.assertEqual((result.version, result.sequence, result.length),
                         (2, 9, 64 + len(ies)))
        self.assertEqual(struct.unpack_from('<I', payload, 0)[0], len(ies))
        self.assertEqual(struct.unpack_from('<H', payload, 4)[0], 0xd02c)
        self.assertEqual(payload[6:9], b'AIC')
        self.assertEqual(payload[38:40], bytes([3, 44]))
        self.assertEqual(payload[41:47], bytes.fromhex('021122334455'))
        self.assertEqual(struct.unpack_from('<i', payload, 48)[0], -57)
        self.assertEqual(payload[64:], ies)
        self.assertFalse(any(result.data[result.length:]))

    def test_malformed_beacon_and_completion_rejected(self):
        item = {'bssid': '02:11:22:33:44:55', 'frequency': 5220,
                'rssi': -57, '_beacon': {'interval': 100,
                                        'capability': 0x11, 'ies': b'\x00\x04A'}}
        with self.assertRaises(ValueError):
            encode_result(1, item)
        item['_beacon']['ies'] = bytes([0, 0])
        item['bssid'] = 'ff:ff:ff:ff:ff:ff'
        with self.assertRaises(ValueError):
            encode_result(1, item)
        self.assertEqual(completion(9).sequence, 9)
        with self.assertRaises(ValueError):
            completion(0)


if __name__ == '__main__':
    unittest.main()
