#!/usr/bin/python3
"""Controlled AIC STA + P2P VIF creation probe; run only via its shell wrapper.

This does not transmit P2P frames, test concurrent traffic, or enable AirDrop.
"""
import json
import struct
import sys


def p2p_mac(station_mac):
    if len(station_mac) != 6 or station_mac[0] & 1:
        raise ValueError('Invalid station MAC')
    result = bytearray(station_mac)
    result[0] = (result[0] | 2) & 0xfe
    result[5] ^= 1
    return bytes(result)


def add_interface(device, mac, p2p):
    body = device.request(6, struct.pack('<Bx6sBx', 0, mac, int(p2p)))
    if len(body) < 2 or body[0] != 0:
        raise RuntimeError('ADD_IF rejected for %s: %s' %
                           ('P2P' if p2p else 'STA', body[:2].hex()))
    return body[1]


def probe(device):
    info = device.identity()
    if info['lmac_version'] != '06090101':
        raise RuntimeError('Untested firmware revision')
    features = int(info['features'], 16)
    if info['max_interfaces'] < 2 or not features & (1 << 13):
        raise RuntimeError('Firmware does not advertise P2P and two VIFs')

    created = []
    reset_started = False
    try:
        device.initialize_radio()
        reset_started = True
        device.request(0)
        device.request(2, bytes(64) + struct.pack('<IH2x', 300, 20))
        device.request(0x65, struct.pack('<5B3x2I', 1, 0, 1, 0, 0, 0, 0))
        station = add_interface(device, device.mac, False)
        created.append(station)
        peer = add_interface(device, p2p_mac(device.mac), True)
        created.append(peer)
        if station == peer or station >= info['max_interfaces'] or peer >= info['max_interfaces']:
            raise RuntimeError('Firmware returned invalid or duplicate VIF indices')
        return {'station_vif_created': True, 'p2p_vif_created': True,
                'distinct_vifs': True, 'airdrop_proven': False}
    finally:
        cleanup_errors = []
        for vif in reversed(created):
            try:
                device.request(8, bytes([vif]))
            except Exception as error:
                cleanup_errors.append('REMOVE_IF %d: %s' % (vif, error))
        if reset_started:
            try:
                device.request(0)
            except Exception as error:
                cleanup_errors.append('RESET: %s' % error)
        if cleanup_errors:
            detail = 'AIC cleanup failed: ' + '; '.join(cleanup_errors)
            if sys.exc_info()[0] is None:
                raise RuntimeError(detail)
            print(detail, file=sys.stderr)


if __name__ == '__main__':
    from wifi import Wifi

    device = None
    try:
        device = Wifi()
        print(json.dumps(probe(device), indent=2, sort_keys=True))
    finally:
        if device is not None:
            device.close()
