"""Experimental IO80211 state/power bridge; never owns the USB device."""
import ctypes as c

from layouts import frequency_to_channel
from native_scan_bridge import (ScanRequest, completion as scan_completion,
                                decode_request as decode_scan_request,
                                encode_result as encode_scan_result)

VERSION = 2
NOT_FOUND = 0
NOT_READY = 0xe00002d8
SET_POWER = 1
ETHERNET_FRAME = 1
ACTION_FRAME = 2


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
    frame.data[:len(payload)] = payload
    validate_frame(frame, from_service=True)
    return frame


def decode_command(command):
    if (command.version != VERSION or command.operation != SET_POWER or
            not command.sequence or command.value not in (0, 1)):
        raise ValueError('Invalid AIC native command')
    return command.sequence, bool(command.value)


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


class NativeRadioPublisher:
    def __init__(self, library, connect):
        self.library = library
        self.connect = connect

    @classmethod
    def open_if_present(cls):
        io = c.CDLL('/System/Library/Frameworks/IOKit.framework/IOKit')
        io.IOServiceMatching.argtypes = [c.c_char_p]
        io.IOServiceMatching.restype = c.c_void_p
        io.IOServiceGetMatchingService.argtypes = [c.c_uint32, c.c_void_p]
        io.IOServiceGetMatchingService.restype = c.c_uint32
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
        service = io.IOServiceGetMatchingService(0, match)  # consumes match
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
                raise RuntimeError('AIC native control ABI mismatch: %08x' % status)
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

    def submit_received_frame(self, frame):
        if not self.connect:
            raise RuntimeError('AIC native control is closed')
        validate_frame(frame, from_service=True)
        status = self.library.IOConnectCallStructMethod(
            self.connect, 4, c.byref(frame), c.sizeof(frame), None, None)
        if status:
            raise RuntimeError('AIC native receive submit: %08x' % status)

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

    def enable_scan_bridge(self):
        if not self.connect:
            raise RuntimeError('AIC native control is closed')
        status = self.library.IOConnectCallStructMethod(
            self.connect, 8, None, 0, None, None)
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
