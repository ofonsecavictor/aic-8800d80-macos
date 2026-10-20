"""Research-only macOS 15 WCL WPA2 join handoff; no USB session here."""

import ctypes as c

from layouts import channel_to_frequency
from wpa2 import validate_rsn


VERSION = 2


class JoinRequest(c.Structure):
    _fields_ = [('version', c.c_uint32), ('sequence', c.c_uint32),
                ('ssidLength', c.c_uint32), ('channelSpec', c.c_uint32),
                ('rsnLength', c.c_uint32), ('ssid', c.c_uint8 * 32),
                ('bssid', c.c_uint8 * 6), ('pmk', c.c_uint8 * 32),
                ('rsn', c.c_uint8 * 257), ('reserved', c.c_uint8)]


class JoinCompletion(c.Structure):
    _fields_ = [('version', c.c_uint32), ('sequence', c.c_uint32),
                ('status', c.c_uint32), ('reserved', c.c_uint32)]


assert c.sizeof(JoinRequest) == 348
assert c.sizeof(JoinCompletion) == 16


def decode_join_request(request):
    """Return the one-use PMK and scrub the C buffer, even on rejection."""
    try:
        if (request.version != VERSION or not request.sequence or
                not 1 <= request.ssidLength <= 32 or
                request.rsnLength > 257 or request.reserved or
                any(request.ssid[request.ssidLength:]) or
                any(request.rsn[request.rsnLength:])):
            raise ValueError('Invalid native AIC join request')
        bssid = bytes(request.bssid)
        if not any(bssid) or bssid[0] & 1:
            raise ValueError('Invalid native AIC BSSID')
        channel = request.channelSpec & 0xff
        band = 0 if channel <= 14 else 1
        if (not 1 <= channel <= 196 or
                request.channelSpec != channel | (0x1000 if band == 0 else 0xd000)):
            raise ValueError('Unsupported native AIC channel specifier')
        frequency = channel_to_frequency(channel, band)
        if frequency is None:
            raise ValueError('Unsupported native AIC channel')
        rsn = bytes(request.rsn[:request.rsnLength])
        if rsn:
            if len(rsn) < 2 or rsn[0] != 48 or rsn[1] != len(rsn) - 2:
                raise ValueError('Invalid native AIC RSN IE')
            validate_rsn(rsn[2:])
        return {'sequence': request.sequence,
                'ssid': bytes(request.ssid[:request.ssidLength]).decode('utf-8'),
                'bssid': bssid.hex(':'), 'frequency': frequency,
                'key': bytes(request.pmk), 'rsn': rsn}
    finally:
        c.memset(c.addressof(request), 0, c.sizeof(request))


def join_completion(sequence, status=0):
    if not 1 <= sequence <= 0xffffffff or not 0 <= status <= 0xffffffff:
        raise ValueError('Invalid native AIC join completion')
    return JoinCompletion(VERSION, sequence, status, 0)
