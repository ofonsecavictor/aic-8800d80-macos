import unittest

from layouts import Connect, connect_request


class ConnectRequestTests(unittest.TestCase):
    def request_ies(self, frequency):
        request = Connect.from_buffer_copy(connect_request(
            0, bytes.fromhex('667ff0767e80'), 'Victor Fonseca 5', frequency))
        start = Connect.ies.offset
        raw = bytes(request)
        return raw[start:start + request.ie_len]

    def test_requests_vht80_operating_mode_on_5ghz(self):
        ies = self.request_ies(5200)
        self.assertEqual(ies[-3:], bytes.fromhex('c70102'))
        self.assertEqual(len(ies), 25)

    def test_does_not_add_vht_operating_mode_on_24ghz(self):
        ies = self.request_ies(2447)
        self.assertEqual(len(ies), 22)
        self.assertNotIn(bytes.fromhex('c70102'), ies)


if __name__ == '__main__':
    unittest.main()
