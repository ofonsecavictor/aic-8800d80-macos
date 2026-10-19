import unittest

import service


class FakeBridge:
    def __init__(self, command):
        self.command = command

    def next_power_command(self):
        return self.command


class NativePowerMonitorTests(unittest.TestCase):
    def test_new_sequence_changes_power_once(self):
        requests = []

        class Controller:
            def handle(self, request):
                requests.append(request)
                return {'ok': True}

        controller = Controller()
        bridge = FakeBridge((14, False))
        sequence = service.apply_native_power_command(controller, bridge, None)
        self.assertEqual(sequence, 14)
        self.assertEqual(service.apply_native_power_command(controller, bridge,
                                                            sequence), 14)
        self.assertEqual(requests, [{'action': 'power', 'enabled': False}])

    def test_absent_command_preserves_sequence(self):
        self.assertEqual(service.apply_native_power_command(None,
                         FakeBridge(None), 19), 19)

    def test_refused_power_command_is_not_acknowledged(self):
        class Controller:
            def handle(self, request):
                return {'ok': False}

        with self.assertRaisesRegex(RuntimeError, 'recusado'):
            service.apply_native_power_command(Controller(), FakeBridge((7, True)), None)

    def test_already_matching_power_does_not_interrupt_wifi(self):
        controller = service.Controller()
        controller.config = lambda: {'enabled': True}
        controller.save = lambda _: self.fail('unnecessary save')
        controller.interrupt = lambda: self.fail('unnecessary interrupt')
        self.assertEqual(controller.handle({'action': 'power', 'enabled': True}),
                         {'ok': True})


if __name__ == '__main__':
    unittest.main()
