import unittest

from native_join_bridge import JoinRequest, decode_join_request, join_completion
from native_radio_control import NativeRadioPublisher, NOT_READY
from test_native_radio_control import FakeIOKit


RSN = bytes.fromhex('30140100000fac040100000fac040100000fac020000')


def request():
    item = JoinRequest()
    item.version = 2
    item.sequence = 7
    item.ssidLength = 4
    item.ssid[:4] = b'test'
    item.channelSpec = 0xd02c
    item.bssid[:] = bytes.fromhex('021122334455')
    item.pmk[:] = bytes([0xa5]) * 32  # Synthetic, never a real credential.
    item.rsnLength = len(RSN)
    item.rsn[:len(RSN)] = RSN
    return item


class NativeJoinBridgeTests(unittest.TestCase):
    def test_decodes_and_erases_one_use_pmk(self):
        raw = request()
        result = decode_join_request(raw)
        self.assertEqual((result['sequence'], result['ssid'],
                          result['frequency']), (7, 'test', 5220))
        self.assertEqual(result['bssid'], '02:11:22:33:44:55')
        self.assertEqual(result['key'], bytes([0xa5]) * 32)
        self.assertEqual(result['rsn'], RSN)
        self.assertFalse(any(bytes(raw)))

    def test_rejects_and_erases_unsupported_join(self):
        for modify in (lambda item: setattr(item, 'channelSpec', 0x102c),
                       lambda item: setattr(item, 'version', 1),
                       lambda item: setattr(item, 'ssidLength', 33)):
            raw = request()
            modify(raw)
            with self.assertRaises(ValueError):
                decode_join_request(raw)
            self.assertFalse(any(bytes(raw)))
        raw = request()
        raw.bssid[0] = 3
        with self.assertRaises(ValueError):
            decode_join_request(raw)
        self.assertFalse(any(bytes(raw)))

    def test_user_client_selectors_and_completion(self):
        io = FakeIOKit(command=request())
        bridge = NativeRadioPublisher(io, 7)
        decoded = bridge.next_join_request()
        bridge.complete_join(decoded['sequence'])
        self.assertEqual([call[1:3] for call in io.calls],
                         [(9, 0), (10, 16)])
        self.assertEqual(join_completion(7).sequence, 7)
        self.assertIsNone(NativeRadioPublisher(FakeIOKit(status=NOT_READY), 7)
                          .next_join_request())
        with self.assertRaises(ValueError):
            join_completion(0)


if __name__ == '__main__':
    unittest.main()
