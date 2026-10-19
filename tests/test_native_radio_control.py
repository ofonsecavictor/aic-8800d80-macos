import ctypes
import unittest

from native_radio_control import NativeRadioPublisher, RadioState, state_for


class FakeIOKit:
    def __init__(self, status=0):
        self.status = status
        self.calls = []

    def IOConnectCallStructMethod(self, connect, selector, source, size, output, output_size):
        self.calls.append((connect, selector, size,
                           ctypes.string_at(source, size)))
        return self.status

    def IOServiceClose(self, connect):
        self.calls.append(('close', connect))
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
                          state.channel, state.rssi_dbm), (1, 1, 1, 6, -64))
        self.assertEqual(bytes(state.mac), self.mac)
        self.assertEqual(bytes(state.bssid), bytes.fromhex('021122334455'))
        self.assertNotIn(b'must-not-cross-bridge', bytes(state))

    def test_powered_unassociated_and_off(self):
        self.assertEqual((state_for(True, None, self.mac).powered,
                          state_for(True, None, self.mac).associated), (1, 0))
        off = state_for(False, None, self.mac)
        self.assertEqual((off.powered, off.associated, off.channel), (0, 0, 0))

    def test_rejects_inconsistent_or_untrusted_state(self):
        with self.assertRaises(ValueError):
            state_for(False, self.target, self.mac)
        with self.assertRaises(ValueError):
            state_for(True, self.target, b'\xff' * 6)
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


if __name__ == '__main__':
    unittest.main()
