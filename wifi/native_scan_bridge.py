"""Strict, offline-testable macOS WCL scan ↔ AIC firmware conversion.

This module does not open USB or request a scan. The live kernel/user-service
handoff is enabled only after a native interface is safely registered.
"""

import ctypes as c
import struct

from layouts import (NATIVE_PASSIVE_CHANNELS_24GHZ,
                     NATIVE_PASSIVE_CHANNELS_5GHZ,
                     channel_to_frequency, frequency_to_channel)


VERSION = 6
MAX_IES = 1024


class ScanRequest(c.Structure):
    _fields_ = [('version', c.c_uint32), ('sequence', c.c_uint32),
                ('identifier', c.c_uint32), ('type', c.c_uint32),
                ('ssidLength', c.c_uint32), ('channelCount', c.c_uint32),
                ('ssid', c.c_uint8 * 32), ('bssid', c.c_uint8 * 6),
                ('reserved', c.c_uint8 * 2),
                ('selectedChannels', c.c_uint8 * 32)]


class ScanResult(c.Structure):
    _fields_ = [('version', c.c_uint32), ('sequence', c.c_uint32),
                ('length', c.c_uint32), ('data', c.c_uint8 * 1088),
                ('beaconLength', c.c_uint32), ('beacon', c.c_uint8 * 2048)]


class ScanCompletion(c.Structure):
    _fields_ = [('version', c.c_uint32), ('sequence', c.c_uint32),
                ('status', c.c_uint32), ('reserved', c.c_uint32)]


assert c.sizeof(ScanRequest) == 96
assert c.sizeof(ScanResult) == 3152
assert c.sizeof(ScanCompletion) == 16


def decode_request(request):
    if (request.version != VERSION or not request.sequence or
            request.type not in range(1, 5) or request.ssidLength > 32 or
            request.channelCount > 400 or any(request.reserved) or
            any(request.ssid[request.ssidLength:])):
        raise ValueError('Invalid native scan request')
    selected = bytes(request.selectedChannels)
    if bool(request.channelCount) != any(selected):
        raise ValueError('Invalid native scan channel selection')
    supported = [(channel, band) for band, channels in
                 ((0, NATIVE_PASSIVE_CHANNELS_24GHZ),
                  (1, NATIVE_PASSIVE_CHANNELS_5GHZ)) for channel in channels]
    frequencies = tuple(channel_to_frequency(channel, band) for channel, band in supported
                        if not request.channelCount or selected[channel // 8] & (1 << (channel % 8)))
    if not frequencies:
        raise ValueError('No supported native scan channels')
    bssid = bytes(request.bssid)
    if bssid not in (bytes(6), bytes([255]) * 6) and (bssid[0] & 1):
        raise ValueError('Invalid native scan BSSID')
    return {'sequence': request.sequence, 'identifier': request.identifier,
            'type': request.type, 'ssid': bytes(request.ssid[:request.ssidLength]),
            'bssid': None if bssid in (bytes(6), bytes([255]) * 6) else bssid,
            'frequencies': frequencies}


def _ssid_from_ies(ies):
    position = 0
    ssid = b''
    found = False
    while position < len(ies):
        if position + 2 > len(ies):
            raise ValueError('Truncated scan IE')
        kind, size = ies[position:position + 2]
        position += 2
        if position + size > len(ies):
            raise ValueError('Scan IE exceeds packet')
        if kind == 0:
            if found or size > 32:
                raise ValueError('Invalid scan SSID IE')
            ssid = ies[position:position + size]
            found = True
        position += size
    return ssid


def matches_request(request, item):
    """Apply the same selection before crossing the kernel scan mailbox."""
    beacon = item.get('_beacon')
    if not isinstance(beacon, dict) or not isinstance(beacon.get('ies'), bytes):
        return False
    if item.get('frequency') not in request['frequencies']:
        return False
    if request['bssid'] is not None:
        try:
            bssid = bytes.fromhex(item['bssid'].replace(':', ''))
        except (KeyError, AttributeError, ValueError):
            return False
        if bssid != request['bssid']:
            return False
    try:
        ssid = _ssid_from_ies(beacon['ies'])
    except ValueError:
        return False
    return request['type'] == 2 or not request['ssid'] or ssid == request['ssid']


def encode_result(sequence, item):
    if not isinstance(sequence, int) or not 1 <= sequence <= 0xffffffff:
        raise ValueError('Invalid scan sequence')
    beacon = item.get('_beacon')
    if not isinstance(beacon, dict):
        raise ValueError('Missing beacon metadata')
    ies = beacon.get('ies')
    if not isinstance(ies, bytes) or len(ies) > MAX_IES:
        raise ValueError('Invalid scan IE bytes')
    ssid = _ssid_from_ies(ies)
    channel = frequency_to_channel(item.get('frequency'))
    rssi = item.get('rssi')
    interval = beacon.get('interval')
    capability = beacon.get('capability')
    try:
        bssid = bytes.fromhex(item['bssid'].replace(':', ''))
    except (KeyError, AttributeError, ValueError):
        raise ValueError('Invalid scan BSSID') from None
    if (not isinstance(channel, int) or not 1 <= channel <= 196 or
            not isinstance(rssi, int) or not -127 <= rssi <= 0 or
            not isinstance(interval, int) or not 1 <= interval <= 0xffff or
            not isinstance(capability, int) or not 0 <= capability <= 0xffff or
            len(bssid) != 6 or not any(bssid) or bssid[0] & 1):
        raise ValueError('Invalid scan beacon fields')
    metadata = bytearray(64)
    struct.pack_into('<IH', metadata, 0, len(ies),
                     channel | (0xd000 if channel > 14 else 0x1000))
    metadata[6:6 + len(ssid)] = ssid
    metadata[38] = len(ssid)
    metadata[39] = channel
    metadata[41:47] = bssid
    struct.pack_into('<ihhHHI', metadata, 48, rssi, 0, 0, interval,
                     capability, (1 << 1) | (1 << 14))
    payload = metadata + ies
    result = ScanResult()
    result.version = VERSION
    result.sequence = sequence
    result.length = len(payload)
    result.data[:len(payload)] = payload
    frame = beacon.get('frame')
    if frame is not None:
        if (not isinstance(frame, bytes) or not 36 <= len(frame) <= 2048 or
                frame[0] != 0x80 or frame[1] & 0x40 or
                frame[16:22] != bssid or frame[32:34] != struct.pack('<H', interval) or
                frame[34:36] != struct.pack('<H', capability) or frame[36:] != ies):
            raise ValueError('Invalid actual beacon frame')
        result.beaconLength = len(frame)
        result.beacon[:len(frame)] = frame
    return result


def completion(sequence, status=0):
    if not isinstance(sequence, int) or not 1 <= sequence <= 0xffffffff or not (
            isinstance(status, int) and 0 <= status <= 0xffffffff):
        raise ValueError('Invalid scan completion')
    return ScanCompletion(VERSION, sequence, status, 0)
