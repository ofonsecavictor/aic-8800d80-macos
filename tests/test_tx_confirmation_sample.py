import unittest

from wifi import Wifi


class FakeLib:
    def wifi_write_data(self, _handle, _frame, _length):
        return 0


class TxConfirmationSampleTests(unittest.TestCase):
    def setUp(self):
        self.wifi = Wifi.__new__(Wifi)
        self.wifi.lib = FakeLib()
        self.wifi.handle = object()
        self.wifi.tx_sequence = 0
        self.wifi.tx_confirmations = {}
        self.wifi.tx_sample_pending = set()
        self.wifi.tx_diagnostics = {
            'data_submitted': 0, 'sample_requested': 0,
            'sample_confirmed': 0, 'sample_acked': 0,
            'sample_nacked': 0}
        self.frame = bytes.fromhex('0211223344550211223344660800') + b'x'

    def test_sampled_confirmation_is_counted_without_blocking(self):
        self.assertTrue(self.wifi.data_write(
            self.frame, 0, 0, require_confirmation=False,
            sample_confirmation=True))
        self.assertEqual(self.wifi.tx_sample_pending, {0})
        self.wifi.record_tx_confirmation(9, 0)
        self.assertEqual(self.wifi.tx_diagnostics['sample_acked'], 1)
        self.assertEqual(self.wifi.tx_diagnostics['sample_confirmed'], 1)
        self.assertEqual(self.wifi.tx_sample_pending, set())
        self.assertEqual(self.wifi.tx_confirmations, {})

    def test_negative_sample_is_separate_from_synchronous_confirmation(self):
        self.wifi.data_write(self.frame, 0, 0, require_confirmation=False,
                             sample_confirmation=True)
        self.wifi.record_tx_confirmation(1, 0)
        self.wifi.record_tx_confirmation(9, 3)
        self.assertEqual(self.wifi.tx_diagnostics['sample_nacked'], 1)
        self.assertEqual(self.wifi.tx_confirmations, {3: 9})

    def test_unconfirmed_data_does_not_request_status(self):
        self.wifi.data_write(self.frame, 0, 0, require_confirmation=False)
        self.assertEqual(self.wifi.tx_diagnostics['data_submitted'], 1)
        self.assertEqual(self.wifi.tx_diagnostics['sample_requested'], 0)
        self.assertEqual(self.wifi.tx_sample_pending, set())


if __name__ == '__main__':
    unittest.main()
