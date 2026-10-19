import importlib.util
from pathlib import Path
import unittest


SPEC = importlib.util.spec_from_file_location(
    "airdrop_preflight", Path(__file__).resolve().parents[1] / "tools" / "airdrop_preflight.py"
)
preflight = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preflight)


class PreflightTests(unittest.TestCase):
    def test_current_transport_is_not_mistaken_for_airdrop(self):
        def run(*args):
            if args[0] == "/sbin/ifconfig":
                return "lo0 en0 utun40"
            if "IOUSB" in args:
                return '"idVendor" = 42652\n"idProduct" = 36225\n'
            return ""

        result = preflight.probe(run)
        self.assertEqual(result["aic_usb_stage"], "ready")
        self.assertFalse(result["awdl0_present"])
        self.assertFalse(result["airdrop_proven"])

    def test_awdl_interface_does_not_prove_transfer(self):
        def run(*args):
            if args[0] == "/sbin/ifconfig":
                return "lo0 en0 awdl0"
            if "IOUSB" in args:
                return '"idVendor" = 42652\n"idProduct" = 36225\n'
            return "IO80211Interface"

        result = preflight.probe(run)
        self.assertTrue(result["awdl0_present"])
        self.assertTrue(result["io80211_interface_present"])
        self.assertFalse(result["airdrop_proven"])

    def test_other_usb_device_does_not_count_as_aic(self):
        def run(*args):
            if "IOUSB" in args:
                return '"idVendor" = 1\n"idProduct" = 36225\n'
            return ""

        self.assertEqual(preflight.probe(run)["aic_usb_stage"], "not_found")


if __name__ == "__main__":
    unittest.main()
