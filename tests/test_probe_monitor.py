from pathlib import Path
import queue
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import probe_monitor
from test_probe_roc import FakeWifi


def record(frame):
    header = bytearray(60)
    header[:2] = len(frame).to_bytes(2, 'little')
    return bytes(header) + frame


class MonitorWifi(FakeWifi):
    def __init__(self, response=None):
        super().__init__()
        self.rx = queue.Queue()
        self.monitor_response = response

    def request(self, message, payload=b'', confirmation=None):
        if message == 0x1412:
            self.calls.append((message, payload))
            return (b'\x01\x00' + payload[:10]
                    if self.monitor_response is None else self.monitor_response)
        return super().request(message, payload, confirmation)


def clock():
    value = [0]

    def tick():
        value[0] += 0.5
        return value[0]

    return tick


class MonitorProbeTests(unittest.TestCase):
    def test_passive_beacon_counts_and_cleanup(self):
        device = MonitorWifi()
        device.rx.put(record(b'\x80\x00' + bytes(22)))
        result = probe_monitor.probe(device, now=clock())
        self.assertEqual(result['usb_batches'], 1)
        self.assertEqual(result['beacons'], 1)
        self.assertEqual(result['bounded_records'], 1)
        self.assertFalse(result['airdrop_proven'])
        self.assertEqual([payload for msg, payload in device.calls if msg == 8], [b'\x00'])
        self.assertEqual(device.calls[-1][0], 0)
        self.assertNotIn('mac', result)

    def test_unset_monitor_channel_cleans_up(self):
        device = MonitorWifi(response=b'\xff' + bytes(11))
        with self.assertRaisesRegex(ValueError, 'not configured'):
            probe_monitor.probe(device, now=clock())
        self.assertEqual([payload for msg, payload in device.calls if msg == 8], [b'\x00'])
        self.assertEqual(device.calls[-1][0], 0)


if __name__ == '__main__':
    unittest.main()
