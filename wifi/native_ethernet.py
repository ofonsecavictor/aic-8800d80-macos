"""Bound native Ethernet ingress by the encapsulated protocol's length.

USB RX records can retain trailer bytes after the decrypted MSDU. Never
guess a fixed MIC/FCS size: IPv4, IPv6 and ARP supply their own boundaries.
"""
import struct


def normalize_native_ethernet(frame):
    if len(frame) < 14:
        return None
    kind = frame[12:14]
    length = len(frame)
    if kind == b'\x08\x00':
        if length < 34 or frame[14] >> 4 != 4:
            return None
        header = (frame[14] & 15) * 4
        payload = struct.unpack_from('>H', frame, 16)[0]
        if header < 20 or payload < header:
            return None
        length = 14 + payload
    elif kind == b'\x86\xdd':
        if length < 54 or frame[14] >> 4 != 6:
            return None
        length = 54 + struct.unpack_from('>H', frame, 18)[0]
    elif kind == b'\x08\x06':
        if length < 22 or not frame[18] or not frame[19]:
            return None
        length = 22 + 2 * (frame[18] + frame[19])
    if not 14 <= length <= 1514 or length > len(frame):
        return None
    return frame[:length]
