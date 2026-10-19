import unittest
from unittest.mock import patch

import iptest


class LeaseCallbackTests(unittest.TestCase):
    def test_failed_callback_still_releases_diagnostic_lease(self):
        mac = bytes.fromhex('001122334455')
        server_mac = bytes.fromhex('021122334455')
        address = bytes((192, 168, 1, 100))
        server = bytes((192, 168, 1, 1))
        offer = {'kind': 2, 'address': address, 'server': server,
                 'server_mac': server_mac}
        ack = {**offer, 'kind': 5, 'routers': server}
        responses = iter(([b'offer'], [b'ack'], [b'arp']))
        sent = []
        observed = []

        def on_lease(lease, result, send, receive, service_eapol):
            observed.append((lease['address'], result['gateway_arp_reply']))
            raise RuntimeError('probe failed')

        with patch.object(iptest, 'parse_dhcp',
                          side_effect=lambda frame, *_: offer if frame == b'offer' else
                          ack if frame == b'ack' else None), \
             patch.object(iptest, 'arp_reply', return_value=server_mac):
            with self.assertRaisesRegex(RuntimeError, 'probe failed'):
                iptest.test_link(sent.append, lambda: next(responses, []), mac,
                                 lambda frame: None, on_lease=on_lease)
        self.assertEqual(observed, [(address, True)])
        self.assertEqual(len(sent), 4)  # discover, request, ARP, DHCP release
        self.assertIn(bytes.fromhex('350107'), sent[-1])  # DHCP message type 7


if __name__ == '__main__':
    unittest.main()
