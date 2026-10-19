"""Bounded extraction of 802.11 action frames from AIC USB RX records.

This is an offline parser only. It does not enable reception on the firmware,
transmit frames, implement AWDL, or change the installed Wi-Fi service.
"""
import struct


RX_HEADER_LENGTH = 60
IS_80211_MPDU = 1 << 1
ACTION_SUBTYPE = 0x00d0


def action_frames(data):
    """Yield (vif_index, raw_80211_frame) for valid action-frame records.

    The 60-byte header and flags layout follow the pinned AIC Linux USB driver.
    Unknown VIF index 0xff is retained; consumers must not treat it as a VIF.
    """
    offset = 0
    while offset < len(data):
        if len(data) - offset < RX_HEADER_LENGTH:
            raise ValueError('Truncated AIC RX header')
        size = struct.unpack_from('<H', data, offset)[0]
        end = offset + RX_HEADER_LENGTH + size
        if size < 24 or end > len(data):
            raise ValueError('Truncated AIC 802.11 record')
        flags = struct.unpack_from('<I', data, offset + 48)[0]
        frame = data[offset + RX_HEADER_LENGTH:end]
        offset = end
        if not flags & IS_80211_MPDU:
            continue
        frame_control = struct.unpack_from('<H', frame)[0]
        if frame_control & 0x00fc != ACTION_SUBTYPE:
            continue
        if len(frame) < 25:
            raise ValueError('Truncated 802.11 action frame')
        yield (flags >> 8) & 0xff, frame
