#!/usr/bin/python3
"""Standalone physical ROC probe, run only via probe_roc.sh with approval."""
import json
from pathlib import Path
import struct
import sys
import time

from management import (REMAIN_ON_CHANNEL_REQUEST_ID,
                        REMAIN_ON_CHANNEL_CONFIRMATION_ID,
                        cancel_remain_on_channel_request,
                        parse_remain_on_channel_confirmation,
                        remain_on_channel_request)
from probe_p2p_vif import add_interface, p2p_mac


def probe(device, on_rx=None, duration_ms=200):
    info = device.identity()
    if info['lmac_version'] != '06090101':
        raise RuntimeError('Untested firmware revision')
    if info['max_interfaces'] < 2 or not int(info['features'], 16) & (1 << 13):
        raise RuntimeError('Firmware does not advertise P2P and two VIFs')

    created = []
    reset_started = False
    roc_started = False
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

        payload = remain_on_channel_request(peer, 5220, duration_ms, 0)
        # If the confirmation is lost, the firmware may still have entered ROC.
        # Keep cancellation armed until rejection or matching expiry is proven.
        roc_started = True
        response = device.request(REMAIN_ON_CHANNEL_REQUEST_ID, payload,
                                  confirmation=REMAIN_ON_CHANNEL_CONFIRMATION_ID)
        accepted, context = parse_remain_on_channel_confirmation(response)
        roc_started = accepted
        expired = False
        if accepted:
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                if on_rx is not None:
                    data = device.data_read(timeout=0)
                    if data:
                        on_rx(data)
                events = list(device.events)
                device.events.clear()
                if not events:
                    events = device.read()
                for message, body in events:
                    if message == 72 and len(body) >= 2 and body[0] == peer and body[1] == context:
                        expired = True
                        roc_started = False
                        break
                if expired:
                    break
            if on_rx is not None:
                while True:
                    data = device.data_read(timeout=0)
                    if not data:
                        break
                    on_rx(data)
        return {'station_vif_created': True, 'p2p_vif_created': True,
                'roc_accepted': accepted, 'roc_expired_indication': expired,
                'airdrop_proven': False}
    finally:
        cleanup_errors = []
        if roc_started:
            try:
                response = device.request(REMAIN_ON_CHANNEL_REQUEST_ID,
                                          cancel_remain_on_channel_request(),
                                          confirmation=REMAIN_ON_CHANNEL_CONFIRMATION_ID)
                canceled, _ = parse_remain_on_channel_confirmation(response, operation=1)
                if not canceled:
                    raise RuntimeError('ROC cancel rejected')
            except Exception as error:
                cleanup_errors.append('ROC_CANCEL: %s' % error)
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
    import wifi as wifi_module

    wifi_module.HERE = Path(sys.argv[1]).resolve()
    device = None
    try:
        device = wifi_module.Wifi()
        print(json.dumps(probe(device), indent=2, sort_keys=True))
    finally:
        if device is not None:
            device.close()
