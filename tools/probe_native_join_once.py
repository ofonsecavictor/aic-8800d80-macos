#!/usr/bin/python3
"""Bounded native auto-join observation; never print names or credentials."""
import os
import ipaddress
from pathlib import Path
import subprocess
import sys
import threading
import time

if len(sys.argv) != 2 or os.geteuid() != 0:
    raise SystemExit('Usage (root): probe_native_join_once.py <CoreWLAN scan tool>')

from native_radio_control import ETHERNET_FRAME, NativeRadioPublisher
from native_scan_service import NativeScanSession
from wifi import Wifi


def is_dhcp_frame(frame, source, destination):
    if len(frame) < 42 or frame[12:14] != b'\x08\x00':
        return False
    ip = frame[14:]
    if ip[0] >> 4 != 4 or ip[9] != 17:
        return False
    ihl = (ip[0] & 15) * 4
    return ihl >= 20 and len(ip) >= ihl + 8 and ip[ihl:ihl + 4] == bytes(
        (source >> 8, source & 255, destination >> 8, destination & 255))


bridge = NativeRadioPublisher.open_if_present()
if bridge is None:
    raise SystemExit('Native controller unavailable')

wifi = None
stop = threading.Event()
ready = threading.Event()
finished = threading.Event()
counts = {'scans': 0, 'joins': 0, 'completed': 0,
          'ethernet_tx': 0, 'ethernet_rx': 0,
          'scan_results': 0, 'actual_beacons': 0,
          'join_targets_with_beacon': 0,
          'dhcp_tx': 0, 'dhcp_firmware_ack': 0, 'dhcp_rx': 0,
          'dhcp_source_matches_station': 0,
          'private_mac_joins': 0}
beacon_bssids = set()
station_mac_holder = [None]
join_targets = {}
joined_ssid = [None]
target_dhcp_rx_baseline = [0]
target_ssid = os.environ.get('AIC_NATIVE_JOIN_TARGET_SSID')
errors = []
try:
    wifi = Wifi()
    wifi.research_probe = True
    original_data_write = wifi.data_write

    def radio_write(ethernet, vif, station, label='EAPOL', quiet=False,
                    require_confirmation=True):
        if is_dhcp_frame(ethernet, 68, 67):
            # Diagnostic only: verify radio ACK for the macOS DHCP request.
            acknowledged = original_data_write(
                ethernet, vif, station, label='DHCP', quiet=True,
                require_confirmation=True)
            if acknowledged:
                counts['dhcp_firmware_ack'] += 1
            return acknowledged
        return original_data_write(
            ethernet, vif, station, label=label, quiet=quiet,
            require_confirmation=require_confirmation)

    wifi.data_write = radio_write
    session = NativeScanSession(wifi, bridge, stop)
    original_enable = bridge.enable_scan_bridge
    original_scan = bridge.next_scan_request
    original_join = bridge.next_join_request
    original_scan_result = bridge.submit_scan_result
    original_complete = bridge.complete_join
    original_transmit = bridge.next_transmit_frame
    original_receive = bridge.submit_received_frame

    def enable():
        result = original_enable()
        ready.set()
        return result

    def scan():
        request = original_scan()
        if request is not None:
            counts['scans'] += 1
        return request

    def join():
        request = original_join()
        if request is not None:
            counts['joins'] += 1
            join_targets[request['sequence']] = request['ssid']
            joined_ssid[0] = None
            if request['bssid'].lower() in beacon_bssids:
                counts['join_targets_with_beacon'] += 1
            selected_mac = request['station_mac']
            if selected_mac != wifi.mac:
                counts['private_mac_joins'] += 1
            station_mac_holder[0] = selected_mac
        return request

    def scan_result(sequence, item):
        result = original_scan_result(sequence, item)
        counts['scan_results'] += 1
        if isinstance(item.get('_beacon', {}).get('frame'), bytes):
            counts['actual_beacons'] += 1
            beacon_bssids.add(item['bssid'].lower())
        return result

    def complete(sequence, status=0):
        result = original_complete(sequence, status)
        if status == 0:
            counts['completed'] += 1
            joined_ssid[0] = join_targets.get(sequence)
            if joined_ssid[0] == target_ssid:
                target_dhcp_rx_baseline[0] = counts['dhcp_rx']
        return result

    def transmit():
        packet = original_transmit()
        if packet is not None and packet.kind == ETHERNET_FRAME:
            counts['ethernet_tx'] += 1
            if is_dhcp_frame(bytes(packet.data[:packet.length]), 68, 67):
                counts['dhcp_tx'] += 1
                if station_mac_holder[0] is not None and bytes(
                    packet.data[6:12]) == station_mac_holder[0]:
                    counts['dhcp_source_matches_station'] += 1
        return packet

    def receive(packet):
        result = original_receive(packet)
        if packet.kind == ETHERNET_FRAME:
            counts['ethernet_rx'] += 1
            if is_dhcp_frame(bytes(packet.data[:packet.length]), 67, 68):
                counts['dhcp_rx'] += 1
        return result

    bridge.enable_scan_bridge = enable
    bridge.next_scan_request = scan
    bridge.next_join_request = join
    bridge.submit_scan_result = scan_result
    bridge.complete_join = complete
    bridge.next_transmit_frame = transmit
    bridge.submit_received_frame = receive

    def run():
        try:
            session.run()
        except BaseException as error:
            errors.append(error)
        finally:
            finished.set()

    worker = threading.Thread(target=run, name='AIC native join observation', daemon=True)
    worker.start()
    if not ready.wait(20):
        raise RuntimeError('Native AIC bridge not ready in 20 seconds')
    print('NATIVE_JOIN_READY=1', flush=True)
    interface_address = subprocess.run(
        ['/sbin/ifconfig', 'en2'], text=True, capture_output=True, timeout=3)
    addresses = [line.strip().split()[1] for line in interface_address.stdout.splitlines()
                 if line.strip().startswith('ether ') and len(line.strip().split()) >= 2]
    interface_mac_present = interface_address.returncode == 0 and len(addresses) == 1
    mac_matches_radio = (interface_mac_present and
                         addresses[0].lower() == wifi.mac.hex(':'))
    print('NATIVE_INTERFACE_MAC_PRESENT=%s' %
          str(interface_mac_present).lower(), flush=True)
    print('NATIVE_INTERFACE_MAC_MATCH=%s' % str(mac_matches_radio).lower(),
          flush=True)
    if not interface_mac_present:
        raise RuntimeError('Native interface has no BSD MAC address')
    power_command = subprocess.run(
        ['/usr/sbin/networksetup', '-setairportpower', 'en2', 'on'],
        text=True, capture_output=True, timeout=10)
    powered = False
    for _ in range(10):
        power_state = subprocess.run(
            ['/usr/sbin/networksetup', '-getairportpower', 'en2'],
            text=True, capture_output=True, timeout=10)
        powered = (power_state.returncode == 0 and
                   power_state.stdout.strip().endswith(': On'))
        if powered:
            break
        stop.wait(.5)
    print('NATIVE_POWER_ON=%s SET_EXIT=%d' %
          (str(powered).lower(), power_command.returncode), flush=True)
    if not powered:
        raise RuntimeError('macOS native Wi-Fi interface remained powered off')
    scan_result = subprocess.run([str(Path(sys.argv[1])), 'en2'], timeout=30,
                                 text=True, capture_output=True)
    for line in scan_result.stdout.splitlines():
        if line.startswith(('COREWLAN_SCAN_COUNT=', 'COREWLAN_SCAN_ERROR=')):
            print(line, flush=True)
    if scan_result.returncode:
        raise RuntimeError('CoreWLAN scan failed before join observation')
    # Power-on triggers macOS auto-join. Never issue a second association from
    # this observer: it can disassociate an in-flight or completed auto-join.
    # The user may also choose a network in the native menu during this window.
    observation_seconds = int(os.environ.get('AIC_NATIVE_JOIN_OBSERVE_SECONDS', '150'))
    minimum_connected_seconds = int(os.environ.get(
        'AIC_NATIVE_JOIN_MIN_CONNECTED_SECONDS', '0'))
    if not 30 <= observation_seconds <= 300 or not 0 <= minimum_connected_seconds <= 180:
        raise ValueError('Native join observation duration is out of range')
    deadline = time.monotonic() + observation_seconds
    associated = False
    ever_associated = False
    link_active = False
    ever_link_active = False
    ipv4_assigned = False
    ever_ipv4_assigned = False
    routable_ipv4 = False
    ever_routable_ipv4 = False
    link_since = None
    stable_since = None
    longest_link_seconds = 0
    stable_connected_seconds = 0
    while time.monotonic() < deadline and not errors:
        state = subprocess.run(['/usr/sbin/networksetup', '-getairportnetwork', 'en2'],
                               text=True, capture_output=True, timeout=3)
        associated = state.returncode == 0 and state.stdout.startswith('Current Wi-Fi Network:')
        interface = subprocess.run(['/sbin/ifconfig', 'en2'], text=True,
                                   capture_output=True, timeout=3)
        link_active = (interface.returncode == 0 and
                       'status: active' in interface.stdout)
        ipv4_addresses = [line.split()[1] for line in interface.stdout.splitlines()
                          if line.lstrip().startswith('inet ') and len(line.split()) > 1]
        ipv4_assigned = interface.returncode == 0 and bool(ipv4_addresses)
        routable_ipv4 = ipv4_assigned and any(
            not (address.is_link_local or address.is_loopback or
                 address.is_unspecified)
            for address in (ipaddress.ip_address(value) for value in ipv4_addresses))
        ever_associated |= associated
        ever_link_active |= link_active
        ever_ipv4_assigned |= ipv4_assigned
        ever_routable_ipv4 |= routable_ipv4
        if link_active:
            if link_since is None:
                link_since = time.monotonic()
            longest_link_seconds = max(longest_link_seconds,
                                       int(time.monotonic() - link_since))
        else:
            link_since = None
        # networksetup can report no current SSID while WCL has completed
        # the join and BSD already has a live link. Keep it diagnostic only.
        target_joined = (target_ssid is None and counts['completed'] > 0 or
                         target_ssid is not None and joined_ssid[0] == target_ssid)
        target_dhcp_ready = (target_ssid is None or
                             counts['dhcp_rx'] > target_dhcp_rx_baseline[0])
        stable = link_active and routable_ipv4 and target_joined and target_dhcp_ready
        if stable:
            if stable_since is None:
                stable_since = time.monotonic()
            stable_connected_seconds = int(time.monotonic() - stable_since)
        else:
            stable_since = None
        if stable and stable_connected_seconds >= minimum_connected_seconds:
            break
        stop.wait(1)
    print('MACOS_JOIN_TRIGGER=system_or_user', flush=True)
    print('NATIVE_JOIN_SCANS=%d REQUESTS=%d COMPLETED=%d MACOS_ASSOCIATED=%s EVER_ASSOCIATED=%s' % (
        counts['scans'], counts['joins'], counts['completed'],
        str(associated).lower(), str(ever_associated).lower()), flush=True)
    print('NATIVE_SCAN_RESULTS=%d ACTUAL_BEACONS=%d JOIN_TARGETS_WITH_BEACON=%d' % (
        counts['scan_results'], counts['actual_beacons'],
        counts['join_targets_with_beacon']), flush=True)
    print('NATIVE_LINK_ACTIVE=%s EVER_ACTIVE=%s LONGEST_SECONDS=%d' % (
        str(link_active).lower(), str(ever_link_active).lower(),
        longest_link_seconds), flush=True)
    print('NATIVE_DATA_ETHERNET_TX=%d RX=%d IPV4_ASSIGNED=%s EVER_IPV4=%s' % (
        counts['ethernet_tx'], counts['ethernet_rx'],
        str(ipv4_assigned).lower(), str(ever_ipv4_assigned).lower()), flush=True)
    print('NATIVE_ROUTABLE_IPV4=%s EVER_ROUTABLE_IPV4=%s' % (
        str(routable_ipv4).lower(), str(ever_routable_ipv4).lower()), flush=True)
    print('NATIVE_STABLE_CONNECTED_SECONDS=%d' % stable_connected_seconds,
          flush=True)
    print('NATIVE_DHCP_TX=%d FIRMWARE_ACK=%d RX=%d' % (
        counts['dhcp_tx'], counts['dhcp_firmware_ack'],
        counts['dhcp_rx']), flush=True)
    print('NATIVE_PRIVATE_MAC_JOINS=%d DHCP_SOURCE_MATCHES_STATION=%d' % (
        counts['private_mac_joins'], counts['dhcp_source_matches_station']),
        flush=True)
    print('NATIVE_TARGET_JOINED=%s TARGET_DHCP_RX=%s' % (
        str(target_ssid is None or joined_ssid[0] == target_ssid).lower(),
        str(target_ssid is None or
            counts['dhcp_rx'] > target_dhcp_rx_baseline[0]).lower()), flush=True)
    if errors:
        raise RuntimeError('Native join session stopped unexpectedly')
    if not counts['completed'] or (target_ssid and joined_ssid[0] != target_ssid):
        raise RuntimeError('Requested native Wi-Fi association was not completed')
    if not link_active or not routable_ipv4:
        raise RuntimeError('Native Wi-Fi link or usable IPv4 data path was not completed')
    if target_ssid and counts['dhcp_rx'] <= target_dhcp_rx_baseline[0]:
        raise RuntimeError('No DHCP reply after joining the requested network')
    if stable_connected_seconds < minimum_connected_seconds:
        raise RuntimeError('Native Wi-Fi did not remain connected long enough')
    route = subprocess.run(['/sbin/route', '-n', 'get', 'default'],
                           text=True, capture_output=True, timeout=5)
    route_en2 = route.returncode == 0 and any(
        line.strip() == 'interface: en2' for line in route.stdout.splitlines())
    print('NATIVE_DEFAULT_ROUTE_EN2=%s' % str(route_en2).lower(), flush=True)
    request = subprocess.run(
        ['/usr/bin/curl', '--silent', '--show-error', '--interface', 'en2',
         '--connect-timeout', '5', '--max-time', '10', '--output', '/dev/null',
         '--write-out', '%{http_code}', 'https://example.com/'],
        text=True, capture_output=True, timeout=15)
    http_code = request.stdout.strip()
    http_ok = request.returncode == 0 and http_code.isdigit() and 200 <= int(http_code) < 400
    print('NATIVE_HTTPS_EN2=%s HTTP_CODE=%s' % (
        str(http_ok).lower(), http_code if http_code.isdigit() else 'none'),
        flush=True)
finally:
    stop.set()
    if wifi is None:
        bridge.close()
    else:
        worker.join(10)
        if not finished.is_set():
            print('NATIVE_JOIN_SHUTDOWN_TIMEOUT=1', flush=True)
            os._exit(5)  # Outer supervisor restores the installed service.
        if errors:
            print('NATIVE_JOIN_SESSION_ERROR=%s' % type(errors[0]).__name__, flush=True)
