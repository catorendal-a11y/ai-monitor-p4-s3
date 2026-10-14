import contextlib
import hashlib
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import aim_control as control
import aim_host as host
from test_aim_host import FakeSerial
from board_profiles import BOARDS, configured_board, get_board, matches_info


def images(root, board_id):
    board = get_board(board_id)
    folder = root / 'firmware' / board_id; folder.mkdir(parents=True)
    header = bytearray(24); header[0] = 0xe9; header[3] = 0x4f
    struct.pack_into('<H', header, 12, board.image_chip_id)
    app = bytes(header) + b'synthetic-application'
    factory = bytearray(b'\xff' * (0x10000 + len(app)))
    factory[board.bootloader_offset:board.bootloader_offset+24] = header
    factory[0x10000:] = app
    entry = struct.pack('<HBBII16sI', 0x50aa, 0, 0, 0x10000, 0x640000, b'app0', 0)
    factory[0x8000:0x8040] = entry + b'\xeb\xeb' + b'\xff' * 14 + hashlib.md5(entry, usedforsecurity=False).digest()
    records = {}
    for name, data, offset in [('application.bin', app, 0x10000), ('factory.bin', factory, 0)]:
        (folder / name).write_bytes(data)
        records[name] = {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data), 'offset': offset}
    return {'board': board.name, 'chip': board.chip, 'experimental': board.experimental, 'files': records}


class BoardTests(unittest.TestCase):
    def test_wrong_board_handshake_closes_port_before_sending_views(self):
        serial = FakeSerial([b'{"type":"info","boardId":"guition-p4","chip":"esp32p4"}\n'])
        with patch.object(host.serial, 'Serial', return_value=serial), patch.object(host.time, 'sleep'):
            with self.assertRaises(RuntimeError): host.connect_panel('COM_TEST', ['codex'], 'waveshare-s3-43')
        self.assertTrue(serial.closed)
        self.assertNotIn(b'set_views', serial.written)

    def test_s3_handshake_and_uart_port_detection_use_the_selected_board(self):
        serial = FakeSerial([b'{"type":"info","boardId":"waveshare-s3-43","chip":"esp32s3"}\n',
                             b'{"type":"ok","cmd":"set_views"}\n'])
        with patch.object(host.serial, 'Serial', return_value=serial), patch.object(host.time, 'sleep'):
            panel = host.connect_panel('COM_TEST', ['codex'], 'waveshare-s3-43')
        self.assertEqual(panel.info['chip'], 'esp32s3')
        ports = [Mock(device='COM6', vid=0x303a), Mock(device='COM7', vid=0x1a86)]
        with patch.object(host.list_ports, 'comports', return_value=ports):
            self.assertEqual(host.find_port('auto', 'guition-p4'), 'COM6')
            self.assertEqual(host.find_port('auto', 'waveshare-s3-43'), 'COM7')

    def test_start_without_hardware_choice_never_stops_existing_host(self):
        with patch.object(control.host, 'load_config', return_value={'providers':['codex'], 'board':''}), \
                patch.object(control, 'stop_host') as stop:
            with self.assertRaises(control.SetupError): control.start_host()
        stop.assert_not_called()

    def test_fresh_board_selection_is_explicit_and_legacy_configuration_remains_p4(self):
        self.assertEqual(configured_board({}, legacy=False), '')
        self.assertEqual(configured_board({}), 'guition-p4')
        with contextlib.redirect_stdout(io.StringIO()):
            replies = iter(['', '3', '2'])
            self.assertEqual(control.choose_board('', lambda _: next(replies)), 'waveshare-s3-43')
        for value in ('https://attacker.invalid/', ['guition-p4'], True, 'esp32s3;command'):
            with self.assertRaises(ValueError): configured_board({'board': value})

    def test_device_identity_cannot_switch_the_selected_hardware_target(self):
        p4, s3 = BOARDS.values()
        self.assertTrue(matches_info(p4, {'display':'jc4880p433','panelId':'esp32p4-mipi-dsi'}))
        self.assertFalse(matches_info(s3, {'display':'jc4880p433','panelId':'esp32p4-mipi-dsi'}))
        self.assertFalse(matches_info(s3, {'boardId':s3.id,'chip':p4.chip}))
        self.assertTrue(matches_info(s3, {'boardId':s3.id,'chip':s3.chip}))

    def test_both_flash_commands_use_only_the_selected_manifest_and_chip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = {'schema':2,'version':'v1.13.0','boards':{key:images(root,key) for key in BOARDS}}
            (root/'firmware/manifest.json').write_text(json.dumps(manifest))
            for key, board in BOARDS.items():
                for kind, filename, offset in [('install','factory.bin','0x0'),('update','application.bin','0x10000')]:
                    command = control.flash_command(kind, 'COM6', root, board_id=key)
                    self.assertEqual(command[command.index('--chip')+1], board.chip)
                    self.assertEqual(command[command.index('--after')+1],
                        'watchdog-reset' if key=='guition-p4' else 'hard-reset')
                    self.assertEqual(command[-2], offset)
                    self.assertEqual(Path(command[-1]),root/'firmware'/key/filename)

    def test_wrong_image_chip_is_rejected_even_with_a_matching_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); record = images(root, 'waveshare-s3-43')
            path = root/'firmware/waveshare-s3-43/application.bin'
            data = bytearray(path.read_bytes()); struct.pack_into('<H',data,12,18); path.write_bytes(data)
            record['files']['application.bin']['sha256'] = hashlib.sha256(data).hexdigest()
            (root/'firmware/manifest.json').write_text(json.dumps({'schema':2,'boards':{'waveshare-s3-43':record}}))
            with self.assertRaises(control.SetupError): control.flash_command('update','COM6',root,board_id='waveshare-s3-43')

    def test_factory_image_must_contain_the_matching_application(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); record = images(root, 'waveshare-s3-43')
            path = root/'firmware/waveshare-s3-43/factory.bin'
            data = bytearray(path.read_bytes()); data[-1] ^= 1; path.write_bytes(data)
            record['files']['factory.bin']['sha256'] = hashlib.sha256(data).hexdigest()
            (root/'firmware/manifest.json').write_text(json.dumps({'schema':2,'boards':{'waveshare-s3-43':record}}))
            with self.assertRaises(control.SetupError): control.flash_command('install','COM6',root,board_id='waveshare-s3-43')

    def test_manifest_cannot_redirect_a_firmware_file_or_override_flash_offsets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); record = images(root,'guition-p4')
            record['files']['application.bin']['offset'] = 0
            (root/'firmware/manifest.json').write_text(json.dumps({'schema':2,'boards':{'guition-p4':record}}))
            with self.assertRaises(control.SetupError): control.flash_command('update','COM6',root,board_id='guition-p4')
