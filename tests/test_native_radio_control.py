import ctypes
import unittest
from subprocess import CompletedProcess
from unittest.mock import patch

from native_radio_control import (Command, NativeRadioPublisher, RadioState,
                                  decode_command, decode_leave_command, state_for, NOT_READY,
                                  ACTION_FRAME, ETHERNET_FRAME,
                                  frame_for_service_rx, latest_controller_service,
                                  native_interface_name,
                                  validate_frame, validate_frame_batch,
                                  FrameBatch, VERSION)
from native_scan_bridge import ScanRequest


class FakeIOKit:
    def __init__(self, status=0, command=None):
        self.status = status
        self.command = command
        self.calls = []

    def IOConnectCallStructMethod(self, connect, selector, source, size, output, output_size):
        self.calls.append((connect, selector, size,
                           ctypes.string_at(source, size) if source else None))
        if self.command is not None and output is not None:
            ctypes.memmove(output, ctypes.byref(self.command),
                           ctypes.sizeof(self.command))
            output_size._obj.value = ctypes.sizeof(self.command)
        return self.status

    def IOServiceClose(self, connect):
        self.calls.append(('close', connect))
        return 0


class FakeServiceIterator:
    def __init__(self, identifiers):
        self.identifiers = iter(identifiers)
        self.released = []

    def IOServiceGetMatchingServices(self, port, matching, iterator):
        assert (port, matching) == (0, 123)
        iterator._obj.value = 99
        return 0

    def IOIteratorNext(self, iterator):
        assert iterator == 99
        return next(self.identifiers, 0)

    def IORegistryEntryGetRegistryEntryID(self, service, entry_id):
        entry_id._obj.value = service
        return 0

    def IOObjectRelease(self, service):
        self.released.append(service)
        return 0


class NativeRadioControlTests(unittest.TestCase):
    def setUp(self):
        self.mac = bytes.fromhex('02aabbccddee')
        self.target = {'bssid': '02:11:22:33:44:55',
                       'frequency': 2437, 'rssi': -64,
                       'ssid': 'must-not-cross-bridge'}

    def test_state_has_no_ssid_or_credentials(self):
        state = state_for(True, self.target, self.mac)
        self.assertEqual(ctypes.sizeof(state), 36)
        self.assertEqual((state.version, state.powered, state.associated,
                          state.channel, state.rssi_dbm), (VERSION, 1, 1, 6, -64))
        self.assertEqual(bytes(state.mac), self.mac)
        self.assertEqual(bytes(state.bssid), bytes.fromhex('021122334455'))
        self.assertNotIn(b'must-not-cross-bridge', bytes(state))

    def test_hotplug_selects_newest_controller_and_releases_old_one(self):
        io = FakeServiceIterator([20, 40, 30])
        self.assertEqual(latest_controller_service(io, 123), 40)
        self.assertEqual(io.released, [20, 30, 99])

    def test_hotplug_discovers_interface_under_newest_usb_provider(self):
        registry = '''+-o AICNativeUSBProvider <class AICNativeUSBProvider, id 0x20>
  +-o AICAirPortController <class AICAirPortController, id 0x21>
    +-o en2 <class AICNativeEthernetInterface, id 0x22>
+-o AICNativeUSBProvider <class AICNativeUSBProvider, id 0x40>
  +-o AICAirPortController <class AICAirPortController, id 0x41>
    +-o en3 <class AICNativeEthernetInterface, id 0x42>
'''
        with patch('native_radio_control.subprocess.run', return_value=
                   CompletedProcess([], 0, registry, '')):
            self.assertEqual(native_interface_name(), 'en3')

    def test_powered_unassociated_and_off(self):
        self.assertEqual((state_for(True, None, self.mac).powered,
                          state_for(True, None, self.mac).associated), (1, 0))
        off = state_for(False, None, self.mac)
        self.assertEqual((off.powered, off.associated, off.channel), (0, 0, 0))

    def test_hotplug_waits_for_new_provider_instead_of_using_old_interface(self):
        old = '''+-o AICNativeUSBProvider <class AICNativeUSBProvider, id 0x20>
    +-o en2 <class AICNativeEthernetInterface, id 0x22>
'''
        new = '''+-o AICNativeUSBProvider <class AICNativeUSBProvider, id 0x40>
  +-o AICAirPortController <class AICAirPortController, id 0x41>
'''
        for registry in (old + new, new + old):
            with patch('native_radio_control.subprocess.run', return_value=
                       CompletedProcess([], 0, registry, '')):
                self.assertIsNone(native_interface_name())

    def test_rejects_inconsistent_or_untrusted_state(self):
        with self.assertRaises(ValueError):
            state_for(False, self.target, self.mac)
        with self.assertRaises(ValueError):
            state_for(True, self.target, b'\xff' * 6)
        with self.assertRaises(ValueError):
            state_for(True, self.target, b'\x00' * 6)
        with self.assertRaises(ValueError):
            state_for(True, {**self.target, 'rssi': -128}, self.mac)
        with self.assertRaises(ValueError):
            state_for(True, {**self.target, 'bssid': 'ff:ff:ff:ff:ff:ff'}, self.mac)

    def test_publish_uses_exact_selector_and_size(self):
        io = FakeIOKit()
        publisher = NativeRadioPublisher(io, 7)
        publisher.publish(True, self.target, self.mac)
        self.assertEqual(io.calls[0][:3], (7, 1, 36))
        self.assertEqual(RadioState.from_buffer_copy(io.calls[0][3]).associated, 1)

    def test_failed_bridge_is_disabled_without_retrying(self):
        io = FakeIOKit(status=1)
        publisher = NativeRadioPublisher(io, 7)
        publisher.safe_publish(True, self.target, self.mac)
        self.assertEqual(io.calls[-1], ('close', 7))
        publisher.safe_publish(True, self.target, self.mac)
        self.assertEqual(len(io.calls), 2)

    def test_reads_bounded_power_command(self):
        io = FakeIOKit(command=Command(VERSION, 1, 7, 0))
        self.assertEqual(NativeRadioPublisher(io, 7).next_power_command(),
                         (7, False))
        self.assertEqual(io.calls[0][:3], (7, 2, 0))

    def test_reads_one_shot_leave_command(self):
        io = FakeIOKit(command=Command(VERSION, 2, 9, 0))
        self.assertEqual(NativeRadioPublisher(io, 7).next_leave_command(), 9)
        self.assertEqual(io.calls[0][:3], (7, 11, 0))
        self.assertIsNone(NativeRadioPublisher(FakeIOKit(status=NOT_READY), 7)
                          .next_leave_command())
        with self.assertRaises(ValueError):
            decode_leave_command(Command(VERSION, 1, 9, 0))

    def test_scan_handoff_uses_bounded_selectors(self):
        request = ScanRequest()
        request.version = VERSION
        request.sequence = 9
        request.type = 1
        request.channelCount = 1
        request.selectedChannels[44 // 8] = 1 << (44 % 8)
        io = FakeIOKit(command=request)
        bridge = NativeRadioPublisher(io, 7)
        bridge.enable_scan_bridge()
        decoded = bridge.next_scan_request()
        self.assertEqual(decoded['frequencies'], (5220,))
        item = {'bssid': '02:11:22:33:44:55', 'frequency': 5220,
                'rssi': -57, '_beacon': {'interval': 100,
                                        'capability': 0x11, 'ies': b'\x00\x03AIC'}}
        bridge.submit_scan_result(9, item)
        bridge.complete_scan(9)
        self.assertEqual([call[1:3] for call in io.calls],
                         [(8, 0), (5, 0), (6, 3152), (7, 16)])

    def test_no_command_is_not_an_error(self):
        self.assertIsNone(NativeRadioPublisher(FakeIOKit(status=NOT_READY), 7)
                          .next_power_command())

    def test_rejects_invalid_command(self):
        for command in (Command(1, 1, 1, 1), Command(2, 3, 1, 1),
                        Command(2, 1, 0, 1), Command(2, 1, 1, 2)):
            with self.assertRaises(ValueError):
                decode_command(command)

    def test_typed_eth_and_action_frames(self):
        ethernet = frame_for_service_rx(ETHERNET_FRAME, bytes(14), 1, 0)
        self.assertEqual((ethernet.length, ethernet.kind), (14, ETHERNET_FRAME))
        action = bytearray(40)
        action[0] = 0xd0
        action[24] = 127
        received = frame_for_service_rx(ACTION_FRAME, bytes(action), 2, 255, 44)
        self.assertEqual((received.vif, received.channel), (255, 44))
        with self.assertRaises(ValueError):
            validate_frame(received, from_service=False)
        received.vif = 1
        validate_frame(received, from_service=False)
        received.data[24] = 3
        with self.assertRaises(ValueError):
            validate_frame(received, from_service=False)

    def test_rejects_invalid_native_frame(self):
        with self.assertRaises(ValueError):
            frame_for_service_rx(ETHERNET_FRAME, bytes(13), 1, 0)
        with self.assertRaises(ValueError):
            frame_for_service_rx(ACTION_FRAME, bytes(40), 1, 1, 44)
        with self.assertRaises(ValueError):
            frame_for_service_rx(ETHERNET_FRAME, bytes(14), 1, 1)
        frame = frame_for_service_rx(ETHERNET_FRAME, bytes(14), 1, 0)
        frame.data[14] = 1
        with self.assertRaises(ValueError):
            validate_frame(frame, from_service=True)

    def test_submits_bounded_received_frame(self):
        io = FakeIOKit()
        frame = frame_for_service_rx(ETHERNET_FRAME, bytes(14), 1, 0)
        NativeRadioPublisher(io, 7).submit_received_frame(frame)
        self.assertEqual(io.calls[0][:3], (7, 4, 1540))

    def test_reads_bounded_transmit_frame(self):
        action = bytearray(40)
        action[0] = 0xd0
        action[24] = 127
        frame = frame_for_service_rx(ACTION_FRAME, bytes(action), 1, 1, 44)
        io = FakeIOKit(command=frame)
        result = NativeRadioPublisher(io, 7).next_transmit_frame()
        self.assertEqual(bytes(result.data[:result.length]), bytes(action))
        self.assertEqual(io.calls[0][:3], (7, 3, 0))

    def test_transfers_received_frames_as_one_validated_batch(self):
        io = FakeIOKit()
        frames = [frame_for_service_rx(ETHERNET_FRAME, bytes(14), index + 1, 0)
                  for index in range(3)]
        NativeRadioPublisher(io, 7).submit_received_frames(frames)
        self.assertEqual(io.calls[0][:3], (7, 13, ctypes.sizeof(FrameBatch)))
        batch = FrameBatch.from_buffer_copy(io.calls[0][3])
        self.assertEqual((batch.version, batch.count), (VERSION, 3))
        validate_frame_batch(batch, from_service=True)

    def test_large_receive_burst_is_split_without_losing_frames(self):
        io = FakeIOKit()
        frames = [frame_for_service_rx(ETHERNET_FRAME, bytes(14), i + 1, 0)
                  for i in range(35)]
        NativeRadioPublisher(io, 7).submit_received_frames(frames)
        batches = [FrameBatch.from_buffer_copy(call[3]) for call in io.calls]
        self.assertEqual([batch.count for batch in batches], [16, 16, 3])
        self.assertEqual([batch.frames[i].sequence for batch in batches
                          for i in range(batch.count)], list(range(1, 36)))

    def test_transfers_ethernet_payloads_directly_as_validated_batches(self):
        io = FakeIOKit()
        payloads = [(bytes([index]) * 1514, index + 1) for index in range(17)]
        NativeRadioPublisher(io, 7).submit_received_ethernet(payloads)
        batches = [FrameBatch.from_buffer_copy(call[3]) for call in io.calls]
        self.assertEqual([batch.count for batch in batches], [16, 1])
        self.assertEqual(bytes(batches[0].frames[3].data), bytes([3]) * 1514)
        self.assertEqual(batches[1].frames[0].sequence, 17)
        for batch in batches:
            validate_frame_batch(batch, from_service=True)

    def test_rejects_invalid_direct_ethernet_payload(self):
        with self.assertRaises(ValueError):
            NativeRadioPublisher(FakeIOKit(), 7).submit_received_ethernet(
                [(bytes(13), 1)])

    def test_rejected_batch_keeps_native_single_frame_transport(self):
        io = FakeIOKit()
        publisher = NativeRadioPublisher(io, 7)
        frame = frame_for_service_rx(ETHERNET_FRAME, bytes(14), 1, 0)
        with patch.object(io, 'IOConnectCallStructMethod', return_value=0xe00002c2) as batch, \
                patch.object(publisher, 'next_transmit_frame', side_effect=[frame, None, None]):
            self.assertEqual(len(publisher.next_transmit_frames()), 1)
            self.assertEqual(publisher.next_transmit_frames(), ())
            batch.assert_called_once()
        with patch.object(io, 'IOConnectCallStructMethod', return_value=0xe00002c2) as batch, \
                patch.object(publisher, 'submit_received_frame') as single:
            publisher.submit_received_frames([frame])
            publisher.submit_received_frames([frame])
            batch.assert_called_once()
            self.assertEqual(single.call_count, 2)


if __name__ == '__main__':
    unittest.main()
