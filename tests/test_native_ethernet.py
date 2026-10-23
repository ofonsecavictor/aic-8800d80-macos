import struct
import unittest

from native_ethernet import normalize_native_ethernet


class NativeEthernetTests(unittest.TestCase):
    def ipv4(self, size=1500):
        packet = bytearray(14 + size)
        packet[12:14] = b'\x08\x00'
        packet[14] = 0x45
        struct.pack_into('>H', packet, 16, size)
        return bytes(packet)

    def test_full_mtu_ipv4_with_trailer_is_not_dropped(self):
        frame = self.ipv4()
        for trailer in (b'', b'\xff' * 4, b'\xff' * 8, b'\xff' * 12):
            self.assertEqual(normalize_native_ethernet(frame + trailer), frame)

    def test_truncated_or_oversize_ip_is_rejected(self):
        self.assertIsNone(normalize_native_ethernet(self.ipv4()[:-1]))
        self.assertIsNone(normalize_native_ethernet(self.ipv4(1501)))
        frame = bytearray(self.ipv4())
        frame[14] = 0x4f
        struct.pack_into('>H', frame, 16, 20)
        self.assertIsNone(normalize_native_ethernet(bytes(frame)))

    def test_ipv6_uses_payload_length(self):
        frame = bytearray(1514)
        frame[12:14] = b'\x86\xdd'
        frame[14] = 0x60
        struct.pack_into('>H', frame, 18, 1460)
        self.assertEqual(normalize_native_ethernet(bytes(frame) + bytes(8)), bytes(frame))
        self.assertIsNone(normalize_native_ethernet(bytes(frame[:-1])))

    def test_arp_uses_address_lengths(self):
        frame = bytearray(42)
        frame[12:14] = b'\x08\x06'
        frame[18:20] = bytes([6, 4])
        self.assertEqual(normalize_native_ethernet(bytes(frame) + bytes(18)), bytes(frame))

    def test_unknown_protocol_is_not_blindly_trimmed(self):
        self.assertEqual(normalize_native_ethernet(bytes(1514)), bytes(1514))
        self.assertIsNone(normalize_native_ethernet(bytes(1522)))
        self.assertIsNone(normalize_native_ethernet(bytes(13)))
