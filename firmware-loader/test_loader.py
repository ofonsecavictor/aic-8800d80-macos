import importlib.util, pathlib, struct, unittest
import contextlib,io
from unittest.mock import Mock,patch
path=pathlib.Path(__file__).with_name('loader.py')
spec=importlib.util.spec_from_file_location('aic_loader',path)
loader=importlib.util.module_from_spec(spec);spec.loader.exec_module(loader)
class PatchTableTests(unittest.TestCase):
    def test_watch_retries_interface_open_but_not_failed_firmware_write(self):
        lib=Mock();lib.aic_loader_id.return_value=42
        device=Mock();device.read.return_value=0xf3078820
        with patch('sys.argv',['loader.py','--watch','--firmware-dir','unused']),patch.object(loader,'prepare',return_value=({},[])),patch.object(loader.ctypes,'CDLL',return_value=lib),patch.object(loader,'Device',side_effect=[loader.DeviceNotReady('not ready'),device]) as opened,patch.object(loader,'load',side_effect=RuntimeError('simulated upload failure')) as loaded,patch.object(loader.time,'sleep',side_effect=[None,None,KeyboardInterrupt]),contextlib.redirect_stdout(io.StringIO()) as output,contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(KeyboardInterrupt):loader.main()
        self.assertEqual(opened.call_count,2)
        self.assertEqual(loaded.call_count,1)
        device.close.assert_called_once()
        self.assertIn('retrying in 3 seconds',output.getvalue())
        self.assertIn('Stopped for this USB session',output.getvalue())
    def table(self):
        return b'AICBT_PT_TAG'.ljust(16,b'\0')+b'INFO'.ljust(16,b'\0')+struct.pack('<II',0,6)+struct.pack('<12I',*range(12))
    def test_truncated_input_rejected(self):
        b=self.table()
        for n in range(len(b)):
            with self.assertRaises(ValueError):loader.parse_table(b[:n])
    def test_excessive_count_rejected(self):
        b=bytearray(self.table());struct.pack_into('<I',b,36,0xffffffff)
        with self.assertRaises(ValueError):loader.parse_table(bytes(b))
    def test_unknown_type_rejected(self):
        b=bytearray(self.table());struct.pack_into('<I',b,32,1000)
        with self.assertRaises(ValueError):loader.parse_table(bytes(b))
    def test_supported_info_entry(self):
        entries=loader.parse_table(self.table());self.assertEqual(entries[0][1],0);self.assertEqual(entries[0][2],list(range(12)))
if __name__=='__main__':unittest.main()
