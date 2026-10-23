import queue
import unittest
from unittest.mock import patch

from wifi import Wifi


class ProbeCleanupTests(unittest.TestCase):
    def make_wifi(self):
        wifi = Wifi.__new__(Wifi)
        wifi.rx = queue.Queue()
        return wifi

    def target(self):
        return {'ssid': 'Example', 'bssid': '02:11:22:33:44:55',
                'frequency': 5200, 'rsn': ''}

    def test_cleanup_timeout_preserves_primary_join_error(self):
        wifi = self.make_wifi()

        def request(message, _payload):
            if message == 0x1800:
                raise RuntimeError('primary join failure')
            raise RuntimeError('USB write 1803: e0004051')

        wifi.request = request
        with patch('wifi.validate_rsn'), patch('wifi.connect_request', return_value=b''):
            with self.assertRaisesRegex(RuntimeError, 'primary join failure'):
                wifi.probe(0, self.target())

    def test_cleanup_timeout_still_reported_without_primary_error(self):
        wifi = self.make_wifi()
        wifi.events = []
        wifi.kernel_poll = None
        wifi.write_auth_report = False
        wifi.read = lambda: [(0x1802, bytes(12))]
        wifi.data_read = lambda: b'frame'
        wifi.authenticate = lambda *_args: {}

        def request(message, _payload):
            if message == 0x1800:
                return b'\x00'
            raise RuntimeError('USB write 1803: e0004051')

        wifi.request = request
        with patch('wifi.validate_rsn'), \
                patch('wifi.connect_request', return_value=b''), \
                patch('wifi.ethernet_frames', return_value=[bytes(12) + b'\x88\x8e']), \
                patch('wifi.parse_key', return_value=(0x8a, 0, None, None)):
            with self.assertRaisesRegex(RuntimeError, 'USB write 1803: e0004051'):
                wifi.probe(0, self.target(), b'key')


if __name__ == '__main__':
    unittest.main()
