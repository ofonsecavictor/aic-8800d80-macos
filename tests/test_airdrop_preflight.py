import importlib.util
from pathlib import Path
from unittest.mock import patch
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
            if "IO80211SkywalkInterface" in args:
                return '"IO80211InterfaceRole" = "Infrastructure"\n'
            if "AICInfraInterface" in args:
                return ('"IOClass" = "AICInfraInterface"\n'
                        '"IOInterfaceName" = "en2"\n')
            return ""

        result = preflight.probe(run, capabilities={})
        self.assertEqual(result["aic_usb_stage"], "ready")
        self.assertFalse(result["awdl0_present"])
        self.assertTrue(result["io80211_interface_present"])
        self.assertTrue(result["aic_native_interface_present"])
        self.assertFalse(result["airdrop_proven"])
        self.assertEqual(result["next_gate"],
                         "Create and validate an AIC-backed AWDL virtual interface.")

    def test_awdl_interface_does_not_prove_transfer(self):
        def run(*args):
            if args[0] == "/sbin/ifconfig":
                return "lo0 en0 awdl0"
            if "IOUSB" in args:
                return '"idVendor" = 42652\n"idProduct" = 36225\n'
            if "IO80211SkywalkInterface" in args:
                return '"IO80211InterfaceRole" = "Infrastructure"\n'
            if "AICInfraInterface" in args:
                return ('"IOClass" = "AICInfraInterface"\n'
                        '"IOInterfaceName" = "en2"\n')
            return ""

        result = preflight.probe(run, capabilities={})
        self.assertTrue(result["awdl0_present"])
        self.assertTrue(result["io80211_interface_present"])
        self.assertTrue(result["aic_native_interface_present"])
        self.assertFalse(result["airdrop_proven"])
        self.assertEqual(result["next_gate"],
                         "Validate AIC ownership and bidirectional AWDL/AirDrop traffic.")

    def test_other_usb_device_does_not_count_as_aic(self):
        def run(*args):
            if "IOUSB" in args:
                return '"idVendor" = 1\n"idProduct" = 36225\n'
            return ""

        self.assertEqual(preflight.probe(run, capabilities={})["aic_usb_stage"], "not_found")

    def test_legacy_native_check_does_not_hide_missing_aic_interface(self):
        def run(*args):
            if args[0] == "/sbin/ifconfig":
                return "lo0 en0"
            if "IOUSB" in args:
                return '"idVendor" = 42652\n"idProduct" = 36225\n'
            if "IO80211SkywalkInterface" in args:
                return '"IO80211InterfaceRole" = "Infrastructure"\n'
            return ""

        result = preflight.probe(run, capabilities={})
        self.assertTrue(result["io80211_interface_present"])
        self.assertFalse(result["aic_native_interface_present"])
        self.assertEqual(result["next_gate"],
                         "Implement and validate an AIC-backed native Wi-Fi interface.")

    def test_capability_report_excludes_identifiers(self):
        import service

        info = {
            'lmac_version': '06090101', 'features': '00000001',
            'max_stations': 2, 'max_interfaces': 2,
            'mac': '11:22:33:44:55:66', 'location': 'deadbeef',
        }
        with patch.object(service, 'write_report') as write:
            service.publish_capabilities(info)
        payload = write.call_args.args[1]
        self.assertEqual(set(payload), {
            'lmac_version', 'features', 'max_stations', 'max_interfaces'
        })
        self.assertNotIn('mac', payload)

    def test_missing_capabilities_do_not_interrupt_wifi(self):
        import service

        with patch.object(service, 'write_report') as write:
            service.publish_capabilities(None)
        write.assert_not_called()

        with patch.object(service, 'write_report', side_effect=OSError('read-only')):
            service.publish_capabilities({
                'lmac_version': '06090101', 'features': '00000001',
                'max_stations': 2, 'max_interfaces': 2,
            })


if __name__ == "__main__":
    unittest.main()
