"""Firmware collection reports a missing build clearly instead of a cryptic crash."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('collect_firmware', ROOT/'scripts/collect_firmware.py')
collector = importlib.util.module_from_spec(spec); spec.loader.exec_module(collector)


class CollectFirmwareTests(unittest.TestCase):
    def test_missing_factory_image_is_reported_with_next_action(self):
        with tempfile.TemporaryDirectory() as name:
            with self.assertRaises(ValueError) as caught:
                collector.latest_factory(Path(name))
            self.assertIn('No factory image', str(caught.exception))
            self.assertIn('PlatformIO', str(caught.exception))

    def test_newest_factory_image_wins_regardless_of_name_order(self):
        with tempfile.TemporaryDirectory() as name:
            build = Path(name)
            old = build / 'fw_aaa.factory.bin'
            new = build / 'fw_zzz.factory.bin'
            old.write_bytes(b'old'); new.write_bytes(b'new')
            os.utime(old, (1000, 1000)); os.utime(new, (2000, 2000))
            self.assertEqual(collector.latest_factory(build), new)

    def test_record_json_manifest_is_no_longer_written(self):
        # The release builder recomputes every digest into firmware/manifest.json;
        # the per-board record.json was a second drifting copy no consumer read.
        source = (ROOT/'scripts/collect_firmware.py').read_text(encoding='utf-8')
        self.assertNotIn('record.json', source)


if __name__ == '__main__':
    unittest.main()
