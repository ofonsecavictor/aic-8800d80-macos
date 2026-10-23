import ctypes
import unittest

from layouts import (HTCapability, HECapability, MEChannelConfig, MEConfig,
                     VHTCapability, me_channel_config_request,
                     me_config_request)


class MEConfigTests(unittest.TestCase):
    def test_firmware_abi_layout(self):
        self.assertEqual(ctypes.sizeof(HTCapability), 32)
        self.assertEqual(ctypes.sizeof(VHTCapability), 12)
        self.assertEqual(ctypes.sizeof(HECapability), 56)
        self.assertEqual(ctypes.sizeof(MEConfig), 112)
        self.assertEqual(MEConfig.vht.offset, 32)
        self.assertEqual(MEConfig.he.offset, 44)
        self.assertEqual(MEConfig.tx_lifetime.offset, 100)
        self.assertEqual(MEConfig.max_bandwidth.offset, 102)

    def test_d80_vht80_one_stream_capabilities(self):
        raw = me_config_request()
        req = MEConfig.from_buffer_copy(raw)
        self.assertEqual(len(raw), 112)
        self.assertEqual(req.ht.info, 0x0963)
        self.assertEqual(req.ht.ampdu, 0x1f)
        self.assertEqual(bytes(req.ht.mcs),
                         bytes.fromhex('ff000000010000000000960001000000'))
        self.assertEqual(req.vht.info, 0x03987131)
        self.assertEqual((req.vht.rx_mcs_map, req.vht.tx_mcs_map),
                         (0xfffe, 0xfffe))
        self.assertEqual((req.vht.rx_highest, req.vht.tx_highest), (390, 390))
        self.assertEqual(req.tx_lifetime, 1000)
        self.assertEqual(req.max_bandwidth, 2)
        self.assertTrue(req.ht_supported)
        self.assertTrue(req.vht_supported)
        self.assertFalse(req.he_supported)
        self.assertFalse(req.he_ul_enabled)
        self.assertFalse(req.power_save)
        self.assertTrue(req.antenna_diversity)
        self.assertFalse(req.dynamic_power_save)
        self.assertEqual(bytes(req.he), bytes(56))

    def test_d81_he80_one_stream_capabilities(self):
        req = MEConfig.from_buffer_copy(me_config_request(enable_he=True))
        self.assertTrue(req.he_supported)
        self.assertFalse(req.he_ul_enabled)
        self.assertEqual(bytes(req.he.mac), bytes.fromhex('000002000000'))
        self.assertEqual(bytes(req.he.phy),
                         bytes.fromhex('06e02b580dc0cf00023000'))
        self.assertEqual((req.he.mcs.rx_mcs_80, req.he.mcs.tx_mcs_80),
                         (0xfffe, 0xfffe))
        self.assertEqual((req.he.mcs.rx_mcs_160, req.he.mcs.tx_mcs_160,
                          req.he.mcs.rx_mcs_80p80, req.he.mcs.tx_mcs_80p80),
                         (0xffff, 0xffff, 0xffff, 0xffff))
        self.assertEqual(bytes(req.he.ppe[:4]), bytes.fromhex('381cc701'))
        self.assertEqual(bytes(req.he.ppe[4:]), bytes(21))

    def test_brazilian_regulatory_channel_table(self):
        raw = me_channel_config_request()
        req = MEChannelConfig.from_buffer_copy(raw)
        self.assertEqual(len(raw), 254)
        self.assertEqual((req.count_2g, req.count_5g), (14, 25))
        self.assertEqual(req.channels_2g[0].frequency, 2412)
        self.assertEqual(req.channels_2g[12].frequency, 2472)
        self.assertEqual((req.channels_2g[13].frequency,
                          req.channels_2g[13].flags), (2484, 2))
        self.assertEqual(req.channels_5g[0].frequency, 5180)
        dfs = next(channel for channel in req.channels_5g
                   if channel.frequency == 5260)
        self.assertEqual(dfs.flags, 5)


if __name__ == '__main__':
    unittest.main()
