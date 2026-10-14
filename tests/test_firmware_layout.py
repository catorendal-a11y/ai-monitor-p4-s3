"""Factory boot failures can occur even after a successful write/hash check."""
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from board_profiles import BOARDS, get_board
from firmware_layout import validate_factory
import aim_control as control
from test_board_profiles import images


class FactoryLayoutTests(unittest.TestCase):
    def fixture(self, key='guition-p4'):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        record = images(root, key)
        (root/'firmware/manifest.json').write_text(json.dumps({'schema': 2, 'boards': {key: record}}))
        return root, record, root/'firmware'/key/'factory.bin'

    def replace_table(self, raw, entries):
        table = b''.join(struct.pack('<HBBII16sI', 0x50aa, kind, subtype, offset, size, b'fixture', 0)
                         for kind, subtype, offset, size in entries)
        table += b'\xeb\xeb' + b'\xff'*14 + hashlib.md5(table, usedforsecurity=False).digest()
        raw[0x8000:0x9000] = table.ljust(4096, b'\xff')

    def test_wrong_boot_flash_size_is_rejected_even_with_valid_manifest_hash(self):
        root, record, path = self.fixture()
        raw = bytearray(path.read_bytes()); raw[0x2003] = 0x2f; path.write_bytes(raw)
        record['files']['factory.bin']['sha256'] = hashlib.sha256(raw).hexdigest()
        (root/'firmware/manifest.json').write_text(json.dumps({'schema':2,'boards':{'guition-p4':record}}))
        with self.assertRaises(control.SetupError): control.flash_command('install', 'COM6', root)
        self.assertTrue(control.firmware_file('update', root).is_file())

    def test_partition_exceeding_physical_flash_is_rejected(self):
        root, _, path = self.fixture(); raw = bytearray(path.read_bytes())
        self.replace_table(raw, [(0,0,0x10000,0x1000000)])
        with self.assertRaisesRegex(ValueError, 'capacity'):
            validate_factory(raw, (root/'firmware/guition-p4/application.bin').read_bytes(), get_board('guition-p4'))

    def test_overlapping_partitions_are_rejected(self):
        root, _, path = self.fixture(); raw = bytearray(path.read_bytes())
        self.replace_table(raw, [(0,0,0x10000,0x640000), (1,2,0x20000,0x5000)])
        with self.assertRaisesRegex(ValueError, 'overlap'):
            validate_factory(raw, (root/'firmware/guition-p4/application.bin').read_bytes(), get_board('guition-p4'))

    def test_corrupt_partition_checksum_is_rejected(self):
        root, _, path = self.fixture(); raw = bytearray(path.read_bytes()); raw[0x803f] ^= 1
        with self.assertRaisesRegex(ValueError, 'checksum'):
            validate_factory(raw, (root/'firmware/guition-p4/application.bin').read_bytes(), get_board('guition-p4'))

    def test_application_larger_than_its_partition_is_rejected(self):
        root, _, path = self.fixture(); raw = bytearray(path.read_bytes())
        app = bytes(8192); raw[0x10000:] = app
        self.replace_table(raw, [(0,0,0x10000,4096)])
        with self.assertRaisesRegex(ValueError, 'fit'):
            validate_factory(raw, app, get_board('guition-p4'))

    def test_valid_factory_capacity_and_layout_for_both_boards(self):
        for key in BOARDS:
            with self.subTest(board=key):
                root, _, _ = self.fixture(key)
                self.assertTrue(control.firmware_file('install', root, key).is_file())

    def test_both_platformio_targets_set_the_image_header_flash_size(self):
        import configparser
        configuration = configparser.ConfigParser()
        configuration.read(Path(__file__).resolve().parents[1]/'platformio.ini')
        self.assertEqual(configuration['esp32_common']['board_upload.flash_size'], '16MB')
        self.assertEqual(configuration['env:esp32s3-waveshare-43-release']['board_upload.flash_size'], '16MB')


if __name__ == '__main__': unittest.main()
