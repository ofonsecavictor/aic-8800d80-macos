import unittest

from management import (action_frames, has_complete_awdl_action_header,
                        is_awdl_action_candidate,
                        CONFIG_MONITOR_REQUEST_ID, CONFIG_MONITOR_CONFIRMATION_ID,
                        SET_FILTER_REQUEST_ID, other_bssid_filter_request,
                        configure_monitor_request, parse_monitor_confirmation,
                        remain_on_channel_request,
                        parse_remain_on_channel_confirmation,
                        cancel_remain_on_channel_request,
                        transmit_action_frame)


def record(frame, flags):
    header = bytearray(60)
    header[:2] = len(frame).to_bytes(2, 'little')
    header[48:52] = flags.to_bytes(4, 'little')
    return bytes(header) + frame


class ActionFrameTests(unittest.TestCase):
    def test_awdl_candidate_requires_vendor_prefix_and_subtype(self):
        header = b'\xd0\x00' + bytes(22)
        candidate = header + b'\x7f\x00\x17\xf2\x08\x10\x03'
        self.assertTrue(is_awdl_action_candidate(candidate))
        self.assertFalse(is_awdl_action_candidate(candidate[:-1]))
        self.assertFalse(is_awdl_action_candidate(candidate[:28] + b'\x09' + candidate[29:]))
        self.assertFalse(is_awdl_action_candidate(header + b'\x7f\x00\x17\xf2\x08\x10\x02'))
        self.assertFalse(is_awdl_action_candidate(b'\x08' + candidate[1:]))

    def test_complete_awdl_header_requires_all_public_fixed_fields(self):
        header = b'\xd0\x00' + bytes(22)
        short = header + b'\x7f\x00\x17\xf2\x08\x10\x03'
        complete = short + bytes(9)
        self.assertTrue(is_awdl_action_candidate(short))
        self.assertFalse(has_complete_awdl_action_header(short))
        self.assertFalse(has_complete_awdl_action_header(complete[:-1]))
        self.assertTrue(has_complete_awdl_action_header(complete))
        self.assertFalse(has_complete_awdl_action_header(b'\x08' + complete[1:]))

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


class MonitorConfigurationTests(unittest.TestCase):
    def test_passive_channel_44_request_and_confirmation(self):
        self.assertEqual((CONFIG_MONITOR_REQUEST_ID, CONFIG_MONITOR_CONFIRMATION_ID),
                         (0x1411, 0x1412))
        payload = configure_monitor_request(5220)
        self.assertEqual(len(payload), 14)
        self.assertEqual(payload.hex(), '0100641464140000000001000000')
        response = b'\x01\x00' + payload[:10]
        self.assertEqual(parse_monitor_confirmation(response, 5220), 1)

    def test_rejects_wrong_or_unset_channel(self):
        with self.assertRaises(ValueError):
            configure_monitor_request(5260)
        payload = configure_monitor_request(5220)
        for response in (b'\xff\x00' + payload[:10],
                         b'\x01\x00' + configure_monitor_request(5745)[:10],
                         b'\x01\x00' + payload[:4] + b'\x00\x00' + payload[6:10],
                         b'\x01\x00' + payload[:9]):
            with self.subTest(response=response), self.assertRaises(ValueError):
                parse_monitor_confirmation(response, 5220)


class RXFilterTests(unittest.TestCase):
    def test_uses_reference_management_mask_without_other_data(self):
        self.assertEqual(SET_FILTER_REQUEST_ID, 14)
        payload = other_bssid_filter_request()
        self.assertEqual(payload.hex(), '98a70615')
        mask = int.from_bytes(payload, 'little')
        self.assertTrue(mask & (1 << 4))   # OTHER_BSSID
        self.assertTrue(mask & (1 << 15))  # OTHER_MGMT_FRAMES
        self.assertFalse(mask & (1 << 29)) # OTHER_DATA_FRAMES


class ActionTransmitTests(unittest.TestCase):
    def setUp(self):
        self.source = bytes.fromhex('021122334455')
        self.frame = (b'\xd0\x00' + bytes(2) + bytes.fromhex('ffffffffffff')
                      + self.source + bytes.fromhex('ffffffffffff')
                      + bytes(2) + b'\x04')

    def test_encodes_confirmed_management_descriptor(self):
        packet = transmit_action_frame(self.frame, 1, self.source, 7)
        self.assertEqual(int.from_bytes(packet[:2], 'little'), len(packet))
        self.assertEqual(packet[2:4], b'\x01\x00')
        self.assertEqual(int.from_bytes(packet[4:6], 'little'), len(self.frame))
        self.assertEqual(int.from_bytes(packet[8:12], 'little'), 0x80000007)
        self.assertEqual(packet[12:26], bytes(14))
        self.assertEqual(packet[26:32], b'\x03\xff\x01\xff\x08\x00')
        self.assertEqual(packet[32:32 + len(self.frame)], self.frame)
        self.assertEqual(packet[32 + len(self.frame):], bytes((-len(self.frame)) % 4))

    def test_rejects_non_action_or_spoofed_source(self):
        invalid = (self.frame[:10] + bytes.fromhex('021122334456') + self.frame[16:])
        with self.assertRaises(ValueError):
            transmit_action_frame(invalid, 1, self.source, 0)
        with self.assertRaises(ValueError):
            transmit_action_frame(b'\x08' + self.frame[1:], 1, self.source, 0)
        with self.assertRaises(ValueError):
            transmit_action_frame(self.frame, 4, self.source, 0)
        with self.assertRaises(ValueError):
            transmit_action_frame(self.frame, 1, self.source, 1 << 31)
        robust = self.frame[:24] + b'\x08' + self.frame[25:]
        with self.assertRaisesRegex(ValueError, 'non-robust'):
            transmit_action_frame(robust, 1, self.source, 0)
        vendor = self.frame[:24] + b'\x7f' + self.frame[25:]
        self.assertTrue(transmit_action_frame(vendor, 1, self.source, 0))


if __name__ == '__main__':
    unittest.main()
