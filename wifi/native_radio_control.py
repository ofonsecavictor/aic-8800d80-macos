"""Experimental IO80211 state/power bridge; never owns the USB device."""
import ctypes as c
import re
import subprocess

from layouts import frequency_to_channel
from native_scan_bridge import (ScanRequest, completion as scan_completion,
                                decode_request as decode_scan_request,
                                encode_result as encode_scan_result)
from native_join_bridge import (JoinRequest, decode_join_request,
                                join_completion)

VERSION = 6
NOT_FOUND = 0
NOT_READY = 0xe00002d8
SET_POWER = 1
LEAVE_NETWORK = 2
ETHERNET_FRAME = 1
ACTION_FRAME = 2


class AWDLState(c.Structure):
    _fields_ = [('version', c.c_uint32), ('sequence', c.c_uint32),
                ('enabled', c.c_uint32), ('channel', c.c_uint32),
                ('mac', c.c_uint8 * 6), ('reserved', c.c_uint8 * 2)]


assert c.sizeof(AWDLState) == 24


class NativeScanNotReady(RuntimeError):
    pass


class RadioState(c.Structure):
    _fields_ = [('version', c.c_uint32), ('powered', c.c_uint32),
                ('associated', c.c_uint32), ('channel', c.c_uint32),
                ('rssi_dbm', c.c_int32), ('mac', c.c_uint8 * 6),
                ('bssid', c.c_uint8 * 6), ('reserved', c.c_uint32)]


assert c.sizeof(RadioState) == 36


class Command(c.Structure):
    _fields_ = [('version', c.c_uint32), ('operation', c.c_uint32),
                ('sequence', c.c_uint32), ('value', c.c_uint32)]


assert c.sizeof(Command) == 16


class Frame(c.Structure):
    _fields_ = [('version', c.c_uint32), ('kind', c.c_uint32),
                ('sequence', c.c_uint32), ('vif', c.c_uint32),
                ('channel', c.c_uint32), ('length', c.c_uint32),
                ('data', c.c_uint8 * 1514), ('reserved', c.c_uint8 * 2)]


assert c.sizeof(Frame) == 1540


FRAME_BATCH_CAPACITY = 16


class FrameBatch(c.Structure):
    _fields_ = [('version', c.c_uint32), ('count', c.c_uint32),
                ('frames', Frame * FRAME_BATCH_CAPACITY)]


assert c.sizeof(FrameBatch) == 24648


def validate_frame(frame, from_service):
    if (frame.version != VERSION or not frame.sequence or
            any(frame.reserved) or
            (frame.vif > 3 and not (from_service and frame.vif == 255))):
        raise ValueError('Invalid AIC native frame header')
    if frame.length > 1514 or any(frame.data[frame.length:]):
        raise ValueError('Invalid AIC native frame padding')
    if frame.kind == ETHERNET_FRAME:
        if frame.vif != 0 or frame.channel != 0 or not 14 <= frame.length <= 1514:
            raise ValueError('Invalid AIC Ethernet frame')
    elif frame.kind == ACTION_FRAME:
        if not 1 <= frame.channel <= 196 or not 25 <= frame.length <= 512:
            raise ValueError('Invalid AIC action frame')
        control = frame.data[0] | frame.data[1] << 8
        if (control & 0xff) != 0xd0 or (control & 0x4000):
            raise ValueError('Protected or non-action 802.11 frame')
        if not from_service and frame.data[24] not in (4, 127):
            raise ValueError('Unsupported action category for TX')
    else:
        raise ValueError('Invalid AIC frame kind')


def validate_frame_batch(batch, from_service):
    if (batch.version != VERSION or not 1 <= batch.count <= FRAME_BATCH_CAPACITY):
        raise ValueError('Invalid AIC frame batch header')
    for index in range(batch.count):
        validate_frame(batch.frames[index], from_service)
    for index in range(batch.count, FRAME_BATCH_CAPACITY):
        frame = batch.frames[index]
        if any((frame.version, frame.kind, frame.sequence, frame.vif,
                frame.channel, frame.length)):
            raise ValueError('Invalid AIC frame batch padding')


def frame_for_service_rx(kind, payload, sequence, vif, channel=0):
    if not isinstance(payload, bytes) or len(payload) > 1514:
        raise ValueError('Invalid AIC native frame payload')
    frame = Frame()
    frame.version = VERSION
    frame.kind = kind
    frame.sequence = sequence
    frame.vif = vif
    frame.channel = channel
    frame.length = len(payload)
    # ctypes array slice assignment converts every byte through Python.  On
    # full-size Ethernet ingress that consumed most of one CPU core.  The
    # freshly zeroed structure already provides the required zero padding, so
    # copy the validated bytes directly into its fixed-size payload field.
    if payload:
        c.memmove(c.addressof(frame) + Frame.data.offset, payload, len(payload))
    validate_frame(frame, from_service=True)
    return frame


def decode_command(command):
    if (command.version != VERSION or command.operation != SET_POWER or
            not command.sequence or command.value not in (0, 1)):
        raise ValueError('Invalid AIC native command')
    return command.sequence, bool(command.value)


def decode_leave_command(command):
    if (command.version != VERSION or command.operation != LEAVE_NETWORK or
            not command.sequence or command.value != 0):
        raise ValueError('Invalid AIC native leave command')
    return command.sequence


def decode_awdl_state(state):
    mac = bytes(state.mac)
    if (state.version != VERSION or not state.sequence or
            state.enabled not in (0, 1) or not 0 <= state.channel <= 196 or
            any(state.reserved) or len(mac) != 6 or mac[0] & 1 or
            not any(mac) or (state.enabled and state.channel == 0)):
        raise ValueError('Invalid AIC AWDL state')
    return {'sequence': state.sequence, 'enabled': bool(state.enabled),
            'channel': state.channel, 'mac': mac}


def state_for(powered, target, mac):
    """Only authenticated association data may set associated=1."""
    if len(mac) != 6 or mac[0] & 1 or not any(mac):
        raise ValueError('Invalid AIC station MAC')
    if target is not None and not powered:
        raise ValueError('Association requires powered radio')
    state = RadioState()
    state.version = VERSION
    state.powered = int(bool(powered))
    state.mac[:] = mac
    if target is not None:
        bssid = bytes.fromhex(target['bssid'].replace(':', ''))
        channel = frequency_to_channel(target['frequency'])
        rssi = target['rssi']
        if len(bssid) != 6 or bssid[0] & 1 or not any(bssid):
            raise ValueError('Invalid AIC BSSID')
        if not isinstance(channel, int) or not 1 <= channel <= 196:
            raise ValueError('Invalid AIC channel')
        if not isinstance(rssi, int) or not -127 <= rssi <= 0:
            raise ValueError('Invalid AIC RSSI')
        state.associated = 1
        state.channel = channel
        state.rssi_dbm = rssi
        state.bssid[:] = bssid
    return state


def latest_controller_service(io, matching):
    """Retain the newest live USB controller, not a detached hot-plug ghost."""
    iterator = c.c_uint32()
    status = io.IOServiceGetMatchingServices(0, matching, c.byref(iterator))
    if status:
        raise RuntimeError('AIC native controller enumeration: %08x' % status)
    selected = 0
    selected_id = -1
    try:
        while True:
            service = io.IOIteratorNext(iterator.value)
            if not service:
                break
            entry_id = c.c_uint64()
            status = io.IORegistryEntryGetRegistryEntryID(service,
                                                          c.byref(entry_id))
            if status:
                io.IOObjectRelease(service)
                continue
            if entry_id.value > selected_id:
                if selected:
                    io.IOObjectRelease(selected)
                selected = service
                selected_id = entry_id.value
            else:
                io.IOObjectRelease(service)
        return selected
    except BaseException:
        if selected:
            io.IOObjectRelease(selected)
        raise
    finally:
        if iterator.value:
            io.IOObjectRelease(iterator.value)


def native_interface_name():
    """Find the BSD interface under the newest AIC USB provider."""
    result = subprocess.run(
        ['/usr/sbin/ioreg', '-r', '-c', 'AICNativeUSBProvider', '-w0'],
        text=True, capture_output=True, timeout=4)
    if result.returncode:
        return None
    provider_id = None
    newest_provider_id = None
    interfaces = []
    for line in result.stdout.splitlines():
        provider = re.search(
            r'^\+-o AICNativeUSBProvider\s+<class [^,]+, id 0x([0-9a-fA-F]+)',
            line)
        if provider:
            provider_id = int(provider.group(1), 16)
            newest_provider_id = max(newest_provider_id or 0, provider_id)
        interface = re.search(
            r'\+-o (en([0-9]+))\s+<class AICNativeEthernetInterface,', line)
        if interface and provider_id is not None:
            interfaces.append((provider_id, int(interface.group(2)),
                               interface.group(1)))
    # During hotplug the new provider can exist before its BSD interface.
    # Never power the old provider's stale enX while waiting for the new one.
    current = [item for item in interfaces if item[0] == newest_provider_id]
    return max(current)[2] if current else None


class NativeRadioPublisher:
    def __init__(self, library, connect):
        self.library = library
        self.connect = connect

    @classmethod
    def open_if_present(cls):
        io = c.CDLL('/System/Library/Frameworks/IOKit.framework/IOKit')
        io.IOServiceMatching.argtypes = [c.c_char_p]
        io.IOServiceMatching.restype = c.c_void_p
        io.IOServiceGetMatchingServices.argtypes = [c.c_uint32, c.c_void_p,
                                                    c.POINTER(c.c_uint32)]
        io.IOServiceGetMatchingServices.restype = c.c_uint32
        io.IOIteratorNext.argtypes = [c.c_uint32]
        io.IOIteratorNext.restype = c.c_uint32
        io.IORegistryEntryGetRegistryEntryID.argtypes = [c.c_uint32,
                                                         c.POINTER(c.c_uint64)]
        io.IORegistryEntryGetRegistryEntryID.restype = c.c_uint32
        io.IOServiceOpen.argtypes = [c.c_uint32, c.c_uint32, c.c_uint32,
                                     c.POINTER(c.c_uint32)]
        io.IOServiceOpen.restype = c.c_uint32
        io.IOObjectRelease.argtypes = [c.c_uint32]
        io.IOServiceClose.argtypes = [c.c_uint32]
        io.IOConnectCallScalarMethod.argtypes = [
            c.c_uint32, c.c_uint32, c.POINTER(c.c_uint64), c.c_uint32,
            c.POINTER(c.c_uint64), c.POINTER(c.c_uint32)]
        io.IOConnectCallScalarMethod.restype = c.c_uint32
        io.IOConnectCallStructMethod.argtypes = [
            c.c_uint32, c.c_uint32, c.c_void_p, c.c_size_t,
            c.c_void_p, c.POINTER(c.c_size_t)]
        io.IOConnectCallStructMethod.restype = c.c_uint32

        match = io.IOServiceMatching(b'AICAirPortController')
        if not match:
            raise RuntimeError('IOServiceMatching failed for AIC controller')
        service = latest_controller_service(io, match)  # consumes match
        if service == NOT_FOUND:
            return None
        try:
            libsystem = c.CDLL('/usr/lib/libSystem.B.dylib')
            task = c.c_uint32.in_dll(libsystem, 'mach_task_self_').value
            connect = c.c_uint32()
            status = io.IOServiceOpen(service, task, 0, c.byref(connect))
            if status:
                raise RuntimeError('AIC native control open: %08x' % status)
        finally:
            io.IOObjectRelease(service)
        publisher = cls(io, connect.value)
        try:
            output = (c.c_uint64 * 1)()
            count = c.c_uint32(1)
            status = io.IOConnectCallScalarMethod(connect.value, 0, None, 0,
                                                  output, c.byref(count))
            if status or count.value != 1 or output[0] != VERSION:
                raise RuntimeError(
                    'AIC native control ABI mismatch: status=%08x expected=%u actual=%u count=%u'
                    % (status, VERSION, output[0], count.value))
            return publisher
        except Exception:
            publisher.close()
            raise

    def publish(self, powered, target, mac):
        state = state_for(powered, target, mac)
        status = self.library.IOConnectCallStructMethod(
            self.connect, 1, c.byref(state), c.sizeof(state), None, None)
        if status:
            raise RuntimeError('AIC native state publish: %08x' % status)

    def next_power_command(self):
        if not self.connect:
            return None
        command = Command()
        size = c.c_size_t(c.sizeof(command))
        status = self.library.IOConnectCallStructMethod(
            self.connect, 2, None, 0, c.byref(command), c.byref(size))
        if status == NOT_READY:
            return None
        if status or size.value != c.sizeof(command):
            raise RuntimeError('AIC native command read: %08x' % status)
        return decode_command(command)

    def next_leave_command(self):
        if not self.connect:
            return None
        command = Command()
        size = c.c_size_t(c.sizeof(command))
        status = self.library.IOConnectCallStructMethod(
            self.connect, 11, None, 0, c.byref(command), c.byref(size))
        if status == NOT_READY:
            return None
        if status or size.value != c.sizeof(command):
            raise RuntimeError('AIC native leave read: %08x' % status)
        return decode_leave_command(command)

    def next_awdl_state(self):
        if not self.connect:
            return None
        state = AWDLState()
        size = c.c_size_t(c.sizeof(state))
        status = self.library.IOConnectCallStructMethod(
            self.connect, 14, None, 0, c.byref(state), c.byref(size))
        if status == NOT_READY:
            return None
        if status or size.value != c.sizeof(state):
            raise RuntimeError('AIC native AWDL state read: %08x' % status)
        return decode_awdl_state(state)

    def submit_received_frame(self, frame):
        if not self.connect:
            raise RuntimeError('AIC native control is closed')
        validate_frame(frame, from_service=True)
        status = self.library.IOConnectCallStructMethod(
            self.connect, 4, c.byref(frame), c.sizeof(frame), None, None)
        if status:
            raise RuntimeError('AIC native receive submit: %08x' % status)

    def submit_received_frames(self, frames):
        frames = tuple(frames)
        if not frames:
            return
        if len(frames) > FRAME_BATCH_CAPACITY:
            for start in range(0, len(frames), FRAME_BATCH_CAPACITY):
                self.submit_received_frames(frames[start:start + FRAME_BATCH_CAPACITY])
            return
        if not self.connect:
            raise RuntimeError('AIC native control is closed')
        if getattr(self, '_rx_single_frames', False):
            for frame in frames:
                self.submit_received_frame(frame)
            return
        batch = FrameBatch()
        batch.version = VERSION
        batch.count = len(frames)
        for index, frame in enumerate(frames):
            validate_frame(frame, from_service=True)
            batch.frames[index] = frame
        validate_frame_batch(batch, from_service=True)
        status = self.library.IOConnectCallStructMethod(
            self.connect, 13, c.byref(batch), c.sizeof(batch), None, None)
        if status in (0xe00002c2, 0xe00002c7):
            self._rx_single_frames = True
            for frame in frames:
                self.submit_received_frame(frame)
            return
        if status:
            raise RuntimeError('AIC native receive batch submit: %08x' % status)

    def submit_received_ethernet(self, packets):
        """Submit trusted, normalized Ethernet bytes without a duplicate Frame copy."""
        packets = tuple(packets)
        if not packets:
            return
        if len(packets) > FRAME_BATCH_CAPACITY:
            for start in range(0, len(packets), FRAME_BATCH_CAPACITY):
                self.submit_received_ethernet(
                    packets[start:start + FRAME_BATCH_CAPACITY])
            return
        if not self.connect:
            raise RuntimeError('AIC native control is closed')
        if getattr(self, '_rx_single_frames', False):
            for payload, sequence in packets:
                self.submit_received_frame(frame_for_service_rx(
                    ETHERNET_FRAME, payload, sequence, 0))
            return
        batch = FrameBatch()
        batch.version = VERSION
        batch.count = len(packets)
        for index, (payload, sequence) in enumerate(packets):
            if (not isinstance(payload, bytes) or not 14 <= len(payload) <= 1514 or
                    not isinstance(sequence, int) or not 1 <= sequence <= 0xffffffff):
                raise ValueError('Invalid AIC Ethernet ingress packet')
            frame = batch.frames[index]
            frame.version = VERSION
            frame.kind = ETHERNET_FRAME
            frame.sequence = sequence
            frame.length = len(payload)
            c.memmove(c.addressof(batch) + FrameBatch.frames.offset +
                      index * c.sizeof(Frame) + Frame.data.offset,
                      payload, len(payload))
        validate_frame_batch(batch, from_service=True)
        status = self.library.IOConnectCallStructMethod(
            self.connect, 13, c.byref(batch), c.sizeof(batch), None, None)
        if status in (0xe00002c2, 0xe00002c7):
            self._rx_single_frames = True
            for payload, sequence in packets:
                self.submit_received_frame(frame_for_service_rx(
                    ETHERNET_FRAME, payload, sequence, 0))
            return
        if status:
            raise RuntimeError('AIC native receive batch submit: %08x' % status)

    def next_transmit_frame(self):
        if not self.connect:
            return None
        frame = Frame()
        size = c.c_size_t(c.sizeof(frame))
        status = self.library.IOConnectCallStructMethod(
            self.connect, 3, None, 0, c.byref(frame), c.byref(size))
        if status == NOT_READY:
            return None
        if status or size.value != c.sizeof(frame):
            raise RuntimeError('AIC native transmit read: %08x' % status)
        validate_frame(frame, from_service=False)
        return frame

    def next_transmit_frames(self):
        if not self.connect:
            return ()
        if getattr(self, '_tx_single_frames', False):
            frames = []
            for _ in range(FRAME_BATCH_CAPACITY):
                frame = self.next_transmit_frame()
                if frame is None:
                    break
                frames.append(frame)
            return tuple(frames)
        batch = FrameBatch()
        size = c.c_size_t(c.sizeof(batch))
        status = self.library.IOConnectCallStructMethod(
            self.connect, 12, None, 0, c.byref(batch), c.byref(size))
        if status in (0xe00002c2, 0xe00002c7):
            self._tx_single_frames = True
            return self.next_transmit_frames()
        if status == NOT_READY:
            return ()
        if status or size.value != c.sizeof(batch):
            raise RuntimeError('AIC native transmit batch read: %08x' % status)
        validate_frame_batch(batch, from_service=False)
        return tuple(batch.frames[index] for index in range(batch.count))

    def enable_scan_bridge(self):
        if not self.connect:
            raise RuntimeError('AIC native control is closed')
        status = self.library.IOConnectCallStructMethod(
            self.connect, 8, None, 0, None, None)
        if status == NOT_READY:
            raise NativeScanNotReady('AIC native scan interface not ready')
        if status:
            raise RuntimeError('AIC native scan enable: %08x' % status)

    def next_scan_request(self):
        if not self.connect:
            return None
        request = ScanRequest()
        size = c.c_size_t(c.sizeof(request))
        status = self.library.IOConnectCallStructMethod(
            self.connect, 5, None, 0, c.byref(request), c.byref(size))
        if status == NOT_READY:
            return None
        if status or size.value != c.sizeof(request):
            raise RuntimeError('AIC native scan read: %08x' % status)
        return decode_scan_request(request)

    def submit_scan_result(self, sequence, item):
        if not self.connect:
            raise RuntimeError('AIC native control is closed')
        result = encode_scan_result(sequence, item)
        status = self.library.IOConnectCallStructMethod(
            self.connect, 6, c.byref(result), c.sizeof(result), None, None)
        if status:
            raise RuntimeError('AIC native scan result: %08x' % status)

    def complete_scan(self, sequence, status_code=0):
        if not self.connect:
            raise RuntimeError('AIC native control is closed')
        result = scan_completion(sequence, status_code)
        status = self.library.IOConnectCallStructMethod(
            self.connect, 7, c.byref(result), c.sizeof(result), None, None)
        if status:
            raise RuntimeError('AIC native scan complete: %08x' % status)

    def next_join_request(self):
        if not self.connect:
            return None
        request = JoinRequest()
        size = c.c_size_t(c.sizeof(request))
        status = self.library.IOConnectCallStructMethod(
            self.connect, 9, None, 0, c.byref(request), c.byref(size))
        if status == NOT_READY:
            return None
        if status or size.value != c.sizeof(request):
            c.memset(c.addressof(request), 0, c.sizeof(request))
            raise RuntimeError('AIC native join read: %08x' % status)
        return decode_join_request(request)

    def complete_join(self, sequence, status_code=0):
        if not self.connect:
            raise RuntimeError('AIC native control is closed')
        completion = join_completion(sequence, status_code)
        status = self.library.IOConnectCallStructMethod(
            self.connect, 10, c.byref(completion), c.sizeof(completion),
            None, None)
        if status:
            raise RuntimeError('AIC native join complete: %08x' % status)

    def safe_publish(self, powered, target, mac):
        if not self.connect:
            return
        try:
            self.publish(powered, target, mac)
        except (KeyError, TypeError, ValueError, RuntimeError) as error:
            print('AIC: ponte de estado nativo desativada: ' + str(error), flush=True)
            self.close()

    def close(self):
        if self.connect:
            self.library.IOServiceClose(self.connect)
            self.connect = 0
