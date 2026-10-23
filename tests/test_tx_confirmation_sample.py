import threading
import unittest

from wifi import Wifi


class FakeLib:
    def __init__(self):
        self.sync_writes = 0
        self.async_writes = 0
        self.batch_writes = 0

    def wifi_write_data(self, _handle, _frame, _length):
        self.sync_writes += 1
        return 0

    def wifi_write_data_async(self, _handle, _frame, _length):
        self.async_writes += 1
        return 0

    def wifi_write_data_batch_async(self, _handle, _frame, _length):
        self.batch_writes += 1
        return 0


class TxConfirmationSampleTests(unittest.TestCase):
    def setUp(self):
        self.wifi = Wifi.__new__(Wifi)
        self.wifi.lib = FakeLib()
        self.wifi.handle = object()
        self.wifi.tx_sequence = 0
        self.wifi.tx_confirmations = {}
        self.wifi.tx_sample_pending = set()
        self.wifi.tx_sample_results = {}
        self.wifi.tx_condition = threading.Condition()
        self.wifi.tx_aggregation = True
        self.wifi.tx_diagnostics = {
            'data_submitted': 0, 'sample_requested': 0,
            'sample_confirmed': 0, 'sample_acked': 0,
            'sample_nacked': 0, 'usb_bytes_submitted': 0,
            'ethernet_bytes_submitted': 0,
            'submit_ns_total': 0, 'submit_ns_max': 0,
            'aggregate_transfers': 0, 'aggregate_frames': 0,
            'aggregate_fallbacks': 0}
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
        self.assertEqual(self.wifi.lib.async_writes, 1)
        self.assertEqual(self.wifi.lib.sync_writes, 0)

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

    def test_confirmed_frames_keep_the_synchronous_path(self):
        self.wifi.tx_confirmations[0] = 9
        self.assertTrue(self.wifi.data_write(self.frame, 0, 0))
        self.assertEqual(self.wifi.lib.sync_writes, 1)
        self.assertEqual(self.wifi.lib.async_writes, 0)

    def test_batch_path_groups_ten_frames_per_usb_transfer(self):
        self.assertEqual(self.wifi.data_write_batch((self.frame,) * 16, 0, 0), 16)
        self.assertEqual(self.wifi.lib.batch_writes, 2)
        self.assertEqual(self.wifi.tx_diagnostics['data_submitted'], 16)
        self.assertEqual(self.wifi.tx_diagnostics['aggregate_frames'], 16)


if __name__ == '__main__':
    unittest.main()
