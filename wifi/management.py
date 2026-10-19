"""Bounded extraction of 802.11 action frames from AIC USB RX records.

This is an offline parser only. It does not enable reception on the firmware,
transmit frames, implement AWDL, or change the installed Wi-Fi service.
"""
import struct

from layouts import connectable_frequency, frequency_band


RX_HEADER_LENGTH = 60
IS_80211_MPDU = 1 << 1
ACTION_SUBTYPE = 0x00d0
REMAIN_ON_CHANNEL_REQUEST_ID = 70
REMAIN_ON_CHANNEL_CONFIRMATION_ID = 71


def remain_on_channel_request(vif, frequency, duration_ms, tx_power_dbm):
    """Encode MM_REMAIN_ON_CHANNEL_REQ for a bounded 20 MHz test channel.

    Returns only the 20-byte firmware payload. Nothing in this module sends it.
    """
    if not 0 <= vif < 4 or not connectable_frequency(frequency):
        raise ValueError('Invalid VIF or channel for ROC test')
    if not 100 <= duration_ms <= 1000 or not -128 <= tx_power_dbm <= 127:
        raise ValueError('Invalid ROC duration or TX power')
    return struct.pack('<BBBBHHH2xIb3x', 0, vif, frequency_band(frequency), 0,
                       frequency, frequency, 0, duration_ms, tx_power_dbm)


def parse_remain_on_channel_confirmation(body, operation=0):
    """Return (accepted, context_index) from MM_REMAIN_ON_CHANNEL_CFM."""
    if operation not in (0, 1) or len(body) != 3 or body[0] != operation:
        raise ValueError('Invalid ROC start confirmation')
    return body[1] == 0, body[2]


def cancel_remain_on_channel_request():
    """Encode MM_ROC_OP_CANCEL; all fields except op_code remain zero."""
    return bytes([1]) + bytes(19)


def transmit_action_frame(frame, vif, source_mac, confirmation_index):
    """Encode one unprotected 802.11 action frame for experimental AIC USB TX.

    This returns bytes only; it never calls the USB transport. The caller must
    own the P2P VIF and arrange a channel and an explicit test peer.
    """
    if not isinstance(frame, bytes) or not 25 <= len(frame) <= 512:
        raise ValueError('Invalid action frame length')
    if not 0 <= vif < 4 or not 0 <= confirmation_index < (1 << 31):
        raise ValueError('Invalid VIF or confirmation index')
    if len(source_mac) != 6 or source_mac[0] & 1 or frame[10:16] != source_mac:
        raise ValueError('Action frame source does not match VIF MAC')
    if not any(frame[4:10]):
        raise ValueError('Invalid action frame destination')
    frame_control = struct.unpack_from('<H', frame)[0]
    if frame_control & 0x00ff != ACTION_SUBTYPE or frame_control & 0x4000:
        raise ValueError('Only unprotected 802.11 action frames are supported')
    descriptor = (struct.pack('<HHI', len(frame), 0, 0x80000000 | confirmation_index)
                  + bytes(14) + struct.pack('<4BH', 3, 0xff, vif, 0xff, 8))
    body = descriptor + frame
    body += bytes((-len(body)) % 4)
    return struct.pack('<HBB', 4 + len(body), 1, 0) + body


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
