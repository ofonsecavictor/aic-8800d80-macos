import unittest

from management import (action_frames, remain_on_channel_request,
                        parse_remain_on_channel_confirmation,
                        cancel_remain_on_channel_request)


def record(frame, flags):
    header = bytearray(60)
    header[:2] = len(frame).to_bytes(2, 'little')
    header[48:52] = flags.to_bytes(4, 'little')
    return bytes(header) + frame


class ActionFrameTests(unittest.TestCase):
    def test_extracts_only_action_frames_with_vif(self):
        action = b'\xd0\x00' + bytes(22) + b'\x7f\x00\x17\xf2'
        data = b'\x08\x00' + bytes(22)
        payload = (record(data, 2 | (1 << 8)) +
                   record(action, 2 | (3 << 8)) +
                   record(action, 0))
        self.assertEqual(list(action_frames(payload)), [(3, action)])

    def test_rejects_truncated_record(self):
        with self.assertRaisesRegex(ValueError, 'Truncated'):
            list(action_frames(bytes(59)))
        with self.assertRaisesRegex(ValueError, 'Truncated'):
            list(action_frames(record(bytes(24), 2)[:-1]))

    def test_rejects_too_short_80211_frame(self):
        with self.assertRaisesRegex(ValueError, 'Truncated'):
            list(action_frames(record(bytes(23), 2)))
        with self.assertRaisesRegex(ValueError, 'Truncated'):
            list(action_frames(record(b'\xd0\x00' + bytes(22), 2)))


class RemainOnChannelTests(unittest.TestCase):
    def test_encodes_20_mhz_listen_request(self):
        payload = remain_on_channel_request(2, 5220, 200, 0)
        self.assertEqual(len(payload), 20)
        self.assertEqual(payload.hex(), '000201006414641400000000c800000000000000')

    def test_rejects_dfs_and_unbounded_requests(self):
        for args in ((0, 5260, 200, 0), (4, 5220, 200, 0),
                     (0, 5220, 1001, 0), (0, 5220, 200, 128)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                remain_on_channel_request(*args)

    def test_parses_confirmation_without_claiming_awdl(self):
        self.assertEqual(parse_remain_on_channel_confirmation(b'\x00\x00\x03'),
                         (True, 3))
        self.assertEqual(parse_remain_on_channel_confirmation(b'\x00\x08\x00'),
                         (False, 0))
        self.assertEqual(parse_remain_on_channel_confirmation(b'\x01\x00\x00', operation=1),
                         (True, 0))
        with self.assertRaises(ValueError):
            parse_remain_on_channel_confirmation(b'\x00\x00')

    def test_cancel_request_matches_zero_initialized_linux_structure(self):
        self.assertEqual(cancel_remain_on_channel_request(), b'\x01' + bytes(19))


if __name__ == '__main__':
    unittest.main()
