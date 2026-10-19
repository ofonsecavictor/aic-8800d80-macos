#!/usr/bin/python3
"""One ROC while WPA2 STA is authenticated; run only via approved wrapper."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import time

from management import (REMAIN_ON_CHANNEL_REQUEST_ID,
                        REMAIN_ON_CHANNEL_CONFIRMATION_ID,
                        cancel_remain_on_channel_request,
                        parse_remain_on_channel_confirmation,
                        remain_on_channel_request)
from probe_p2p_vif import add_interface, p2p_mac
from iptest import arp_reply, arp_request

SUPPORT = Path('/Library/Application Support/AIC88M80Driver/wifi')


def probe_connected_roc(device, sta_vif, frequency=2437):
    """Test firmware ROC acceptance without resetting an authenticated STA."""
    if frequency != 2437 or not 0 <= sta_vif < 4:
        raise ValueError('Invalid concurrent ROC channel or STA VIF')
    info = device.identity()
    if (info['lmac_version'] != '06090101' or info['max_interfaces'] < 2 or
            not int(info['features'], 16) & (1 << 13)):
        raise RuntimeError('Untested AIC firmware or P2P capability')
    peer = None
    roc_started = False
    try:
        candidate = add_interface(device, p2p_mac(device.mac), True)
        if candidate == sta_vif or candidate >= info['max_interfaces']:
            raise RuntimeError('Invalid P2P VIF during authenticated STA test')
        peer = candidate
        roc_started = True  # A lost confirmation can still leave ROC active.
        response = device.request(
            REMAIN_ON_CHANNEL_REQUEST_ID,
            remain_on_channel_request(peer, frequency, 200, 0),
            confirmation=REMAIN_ON_CHANNEL_CONFIRMATION_ID)
        accepted, context = parse_remain_on_channel_confirmation(response)
        roc_started = accepted
        expired = False
        if accepted:
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                events = list(device.events)
                device.events.clear()
                if not events:
                    events = device.read(poll=True)
                for message, body in events:
                    if message == 0x1805:
                        raise RuntimeError('STA disconnected during ROC')
                    if message == 72 and len(body) >= 2 and body[:2] == bytes((peer, context)):
                        expired = True
                        roc_started = False
                if expired:
                    break
                time.sleep(0.01)
        return {'sta_wpa2_authenticated': True, 'p2p_vif_created': True,
                'roc_while_sta_authenticated_accepted': accepted,
                'roc_expired_indication': expired,
                'sta_data_during_roc_proven': False,
                'airdrop_proven': False}
    finally:
        errors = []
        if roc_started:
            try:
                response = device.request(
                    REMAIN_ON_CHANNEL_REQUEST_ID,
                    cancel_remain_on_channel_request(),
                    confirmation=REMAIN_ON_CHANNEL_CONFIRMATION_ID)
                canceled, _ = parse_remain_on_channel_confirmation(response, operation=1)
                if not canceled:
                    raise RuntimeError('ROC cancel rejected')
            except Exception as error:
                errors.append('ROC_CANCEL: ' + str(error))
        if peer is not None:
            try:device.request(8, bytes((peer,)))
            except Exception as error:errors.append('REMOVE_IF: ' + str(error))
        if errors:
            detail = 'AIC concurrent probe cleanup failed: ' + '; '.join(errors)
            if sys.exc_info()[0] is None:
                raise RuntimeError(detail)
            print(detail, file=sys.stderr)


def probe_ip_recovery(device, sta_vif, lease, ip_result, send, receive, service_eapol):
    """Check gateway ARP before and after ROC on the same diagnostic lease."""
    if not ip_result.get('dhcp_ack') or not ip_result.get('gateway_arp_reply'):
        raise RuntimeError('No verified DHCP/gateway path before ROC')
    gateway = lease.get('routers', b'')[:4]
    if len(gateway) != 4:
        raise RuntimeError('No DHCP gateway for ROC recovery test')
    result = probe_connected_roc(device, sta_vif)
    result['dhcp_ack_before_roc'] = True
    result['gateway_arp_before_roc'] = True
    result['gateway_arp_after_roc'] = False
    for _ in range(2):
        send(arp_request(device.mac, lease['address'], gateway))
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            for frame in receive():
                if frame[12:14] == b'\x88\x8e':
                    service_eapol(frame)
                elif arp_reply(frame, device.mac, lease['address'], gateway):
                    result['gateway_arp_after_roc'] = True
                    break
            if result['gateway_arp_after_roc']:
                break
        if result['gateway_arp_after_roc']:
            break
    result['sta_ip_path_recovered'] = bool(
        result['roc_while_sta_authenticated_accepted'] and
        result['roc_expired_indication'] and result['gateway_arp_after_roc'])
    return result


def run(stage, verify_ip=False):
    import wifi as wifi_module
    config = json.loads((SUPPORT / 'profile.json').read_text())
    ssid = config.get('ssid')
    if not isinstance(ssid, str) or not ssid:
        raise RuntimeError('No configured Wi-Fi network')
    credential = subprocess.run([str(SUPPORT / 'aic-wifi-credential'), '--read', ssid],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                timeout=15)
    key = credential.stdout
    if credential.returncode or len(key) != 32:
        raise RuntimeError('Stored WPA2 key unavailable')
    wifi_module.HERE = stage
    device = None
    result = None
    try:
        device = wifi_module.Wifi()
        device.identity()
        device.target_band = config.get('preferred_band')
        device.research_probe = True
        device.test_ip = verify_ip

        def on_association(vif, _station, _target):
            nonlocal result
            if not verify_ip:
                result = probe_connected_roc(device, vif)

        device.association_observer = on_association
        if verify_ip:
            def on_lease(vif, _station, lease, ip_result, send, receive, service_eapol):
                nonlocal result
                result = probe_ip_recovery(device, vif, lease, ip_result,
                                           send, receive, service_eapol)
            device.lease_observer = on_lease
        print('Autenticando STA e testando '+('DHCP/ARP + ROC' if verify_ip else 'ROC')+
              '; sem quadros P2P de diagnóstico...', flush=True)
        # Wifi logs AP identifiers; discard them and print only bounded findings.
        with contextlib.redirect_stdout(io.StringIO()):
            device.scan(ssid, key)
        if result is None:
            raise RuntimeError('STA authentication did not reach ROC probe')
        result['authentication_flow_completed_after_roc'] = True
        print(json.dumps(result, indent=2, sort_keys=True), flush=True)
    finally:
        key = None
        if device is not None:
            device.close()


if __name__ == '__main__':
    if len(sys.argv) not in (2, 3) or (len(sys.argv) == 3 and sys.argv[2] != '--ip'):
        raise SystemExit('Usage: probe_concurrent_roc.py STAGE [--ip]')
    run(Path(sys.argv[1]).resolve(), verify_ip=len(sys.argv) == 3)
