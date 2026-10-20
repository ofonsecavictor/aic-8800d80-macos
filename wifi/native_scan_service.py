"""Research-only native scan session using the existing AIC FullMAC USB owner.

Not installed or started by the stable service. The Wifi session lock prevents
simultaneous ownership with the UTUN implementation. No connection, DHCP, or
AirDrop path is supplied by this module.
"""

import threading
import time

from native_radio_control import NativeScanNotReady
from native_scan_bridge import matches_request


SCAN_FAILED = 0xe00002bc
SCAN_ABORTED = 0xe00002eb


class NativeScanSession:
    def __init__(self, wifi, bridge, stop=None):
        self.wifi = wifi
        self.bridge = bridge
        self.stop = stop if stop is not None else threading.Event()
        self.wifi.native_stop = self.stop
        self.last_sequence = None

    def prepare(self, timeout=10):
        info = self.wifi.identity()
        if info['lmac_version'] != '06090101':
            raise RuntimeError('Untested AIC firmware revision')
        self.wifi.initialize_radio()
        self.bridge.publish(True, None, self.wifi.mac)
        deadline = time.monotonic() + timeout
        while not self.stop.is_set():
            try:
                self.bridge.enable_scan_bridge()
                return
            except NativeScanNotReady:
                if time.monotonic() >= deadline:
                    raise RuntimeError('Native AIC interface registration timed out') from None
                self.stop.wait(.1)
        raise KeyboardInterrupt

    def execute(self, request):
        sequence = request['sequence']
        if sequence == self.last_sequence:
            raise RuntimeError('Repeated native AIC scan sequence')
        previous_beacon = self.wifi.scan_observer
        previous_control = self.wifi.control_observer
        completion_attempted = False

        def beacon(item):
            if matches_request(request, item):
                try:
                    self.bridge.submit_scan_result(sequence, item)
                except ValueError:
                    # A malformed beacon is omitted, never sent to the kernel.
                    pass

        def control(message, body):
            nonlocal completion_attempted
            if message == 0x1001:
                completion_attempted = True
                self.bridge.complete_scan(sequence, 0 if body[:1] == b'\x00'
                                          else SCAN_FAILED)

        self.wifi.scan_observer = beacon
        self.wifi.control_observer = control
        try:
            self.wifi.scan(scan_frequencies=request['frequencies'],
                           publish_results=False)
            if not completion_attempted:
                raise RuntimeError('AIC scan ended without firmware completion')
            self.last_sequence = sequence
        except BaseException as error:
            if not completion_attempted:
                try:
                    self.bridge.complete_scan(sequence,
                                              SCAN_ABORTED if isinstance(error, KeyboardInterrupt)
                                              else SCAN_FAILED)
                except RuntimeError:
                    pass  # Kernel timeout or teardown is already authoritative.
            raise
        finally:
            self.wifi.scan_observer = previous_beacon
            self.wifi.control_observer = previous_control

    def run(self):
        try:
            self.prepare()
            while not self.stop.is_set():
                request = self.bridge.next_scan_request()
                if request is None:
                    self.stop.wait(.05)
                    continue
                self.execute(request)
        finally:
            try:
                self.bridge.publish(False, None, self.wifi.mac)
            except (AttributeError, RuntimeError, ValueError):
                pass
            self.bridge.close()
            self.wifi.close()
