import unittest

from management import action_frames


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


if __name__ == '__main__':
    unittest.main()
