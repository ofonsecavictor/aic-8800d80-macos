import unittest
from unittest.mock import Mock, patch

import wifi


class UsbRxPipelineTests(unittest.TestCase):
    def test_starts_bounded_parallel_bulk_read_pool(self):
        created=[]

        def thread(**kwargs):
            item=Mock()
            item.specification=kwargs
            created.append(item)
            return item

        target=Mock()
        with patch.object(wifi.threading,'Thread',side_effect=thread):
            readers=wifi.start_data_readers(target)

        self.assertEqual(len(readers),wifi.USB_DATA_READ_DEPTH)
        self.assertEqual(len(readers),16)
        self.assertEqual([item.specification['name'] for item in created],
                         ['AIC USB data RX %u'%index
                          for index in range(wifi.USB_DATA_READ_DEPTH)])
        self.assertTrue(all(item.specification['target'] is target
                            and item.specification['daemon'] for item in created))
        for item in created:item.start.assert_called_once_with()


if __name__=='__main__':
    unittest.main()
