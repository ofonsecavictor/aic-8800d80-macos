"""Build ephemeral macOS 15 WCL scan-result messages from AIC beacons.

No kernel call is made here. Keep BSSIDs and raw IEs out of JSON reports.
"""

import ctypes as c

from layouts import frequency_band, frequency_to_channel

MAX_IE_BYTES = 1024
SSID_PRESENT = 1 << 1
RSSI_VALID = 1 << 14


class BeaconMetadata(c.Structure):
    _fields_ = [
        ('ie_length', c.c_uint32), ('channel_spec', c.c_uint16),
        ('ssid', c.c_uint8 * 32), ('ssid_length', c.c_uint8),
        ('channel', c.c_uint8), ('reserved0', c.c_uint8),
        ('bssid', c.c_uint8 * 6), ('reserved1', c.c_uint8),
        ('rssi', c.c_int32), ('noise', c.c_int16), ('snr', c.c_int16),
        ('interval', c.c_uint16), ('capability', c.c_uint16),
        ('flags', c.c_uint32),
    ]


assert c.sizeof(BeaconMetadata) == 0x40
assert BeaconMetadata.bssid.offset == 0x29
assert BeaconMetadata.rssi.offset == 0x30
assert BeaconMetadata.flags.offset == 0x3c


def valid_ies(ies):
    if not isinstance(ies, bytes) or len(ies) > MAX_IE_BYTES:
        return False
    cursor = 0
    while cursor < len(ies):
        if len(ies) - cursor < 2:
            return False
        kind = ies[cursor]
        size = ies[cursor + 1]
        cursor += 2
        if size > len(ies) - cursor or (kind == 0 and size > 32):
            return False
        cursor += size
    return True


def raw_ssid(ies):
    cursor = 0
    while cursor < len(ies):
        kind, size = ies[cursor:cursor + 2]
        cursor += 2
        value = ies[cursor:cursor + size]
        cursor += size
        if kind == 0:
            if size > 32:
                raise ValueError('Invalid beacon SSID')
            return value
    return b''  # Hidden network or beacon without an SSID IE.


def encode_beacon(network):
    """Return metadata+IE bytes; raises ValueError on malformed observations."""
    if not isinstance(network, dict):
        raise ValueError('Invalid scan observation')
    beacon = network.get('_beacon')
    if not isinstance(beacon, dict):
        raise ValueError('Missing raw beacon information')
    ies = beacon.get('ies')
    if not valid_ies(ies):
        raise ValueError('Invalid beacon IEs')
    ssid = raw_ssid(ies)
    channel = frequency_to_channel(network.get('frequency'))
    band = frequency_band(network.get('frequency'))
    rssi = network.get('rssi')
    interval = beacon.get('interval')
    capability = beacon.get('capability')
    try:
        bssid = bytes.fromhex(network['bssid'].replace(':', ''))
    except (KeyError, AttributeError, ValueError) as error:
        raise ValueError('Invalid beacon BSSID') from error
    if (not isinstance(channel, int) or not 1 <= channel <= 196 or
            band not in (0, 1) or (band == 0 and channel > 14) or
            (band == 1 and channel <= 14) or
            not isinstance(rssi, int) or not -127 <= rssi <= 0 or
            not isinstance(interval, int) or not 1 <= interval <= 65535 or
            not isinstance(capability, int) or not 0 <= capability <= 65535 or
            len(bssid) != 6 or bssid[0] & 1 or not any(bssid)):
        raise ValueError('Invalid beacon metadata')
    metadata = BeaconMetadata()
    metadata.ie_length = len(ies)
    metadata.channel_spec = channel | (0xd000 if band == 1 else 0x1000)
    metadata.ssid[:len(ssid)] = ssid
    metadata.ssid_length = len(ssid)
    metadata.channel = channel
    metadata.bssid[:] = bssid
    metadata.rssi = rssi
    metadata.interval = interval
    metadata.capability = capability
    metadata.flags = SSID_PRESENT | RSSI_VALID
    return bytes(metadata) + ies
