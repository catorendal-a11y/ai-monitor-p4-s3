"""External messages remain data: no process execution or file command dispatch."""
import io
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import aim_host as host
import codex_support as codex
from telemetry_bridge import ingest
from token_activity import TokenReporter

MARKER = "__import__('os').system('DO_NOT_EXECUTE_SYNTHETIC')"


class RetainedBuffer(io.BytesIO):
    def close(self): pass


class NoRemoteExecutionTests(unittest.TestCase):
    def panel(self, messages):
        serial = Mock(in_waiting=0)
        serial.write.side_effect = len
        with patch.object(host.serial, 'Serial', return_value=serial):
            panel = host.Panel('COM99')
        panel._rx = bytearray(b''.join(json.dumps(item).encode() + b'\n' for item in messages))
        return panel, serial

    def test_usb_cannot_dispatch_process_install_update_flash_or_file_commands(self):
        messages = [{'type': command, 'cmd': command, 'command': MARKER,
                     'url': 'https://attacker.invalid/script', 'path': '../../synthetic'}
                    for command in ('exec', 'reverse_shell', 'download', 'install', 'update',
                                    'setup_codex', 'flash', 'read_file', 'run')]
        messages += [{'type': 'ack', 'frameId': 7}]
        panel, serial = self.panel(messages)
        with patch.object(codex.subprocess, 'Popen') as spawn, \
                patch.object(codex.subprocess, 'run') as run, patch.object(host.os, 'system') as shell, \
                patch.object(host, 'open_provider_request') as network, patch.object(Path, 'write_text') as write:
            self.assertEqual(panel.wait_for('ack', frame_id=7), {'type': 'ack', 'frameId': 7})
        for action in (spawn, run, shell, network, write): action.assert_not_called()
        self.assertIsNone(panel.refresh_request_id)
        serial.write.assert_not_called()

    def test_extra_command_fields_in_refresh_only_queue_refresh(self):
        panel, serial = self.panel([{'type': 'refresh_request', 'requestId': 8,
                                     'command': MARKER, 'url': 'https://attacker.invalid/'}])
        with patch.object(codex.subprocess, 'Popen') as spawn, \
                patch.object(codex.subprocess, 'run') as run, patch.object(host.os, 'system') as shell, \
                patch.object(host, 'open_provider_request') as network:
            panel.collect_requests()
        for action in (spawn, run, shell, network): action.assert_not_called()
        self.assertEqual(panel.take_refresh_request(), 8)
        reply = json.loads(serial.write.call_args.args[0])
        self.assertEqual(reply['cmd'], 'refresh_status')
        self.assertNotIn(MARKER, str(reply))

    def test_api_command_fields_are_never_executed_or_forwarded_to_usb(self):
        for percent in (25, MARKER):
            response = Mock(); response.read.return_value = json.dumps({
                'success': True, 'execute': MARKER,
                'data': {'command': MARKER, 'limits': [{'type': 'CREDIT_LIMIT', 'unit': 3,
                                                       'percentage': percent, 'command': MARKER}]}}).encode()
            with patch.object(host, 'open_provider_request') as network, \
                    patch.object(codex.subprocess, 'Popen') as spawn, \
                    patch.object(codex.subprocess, 'run') as run, patch.object(host.os, 'system') as shell:
                network.return_value.__enter__.return_value = response
                rows, notice = host.fetch_zcode('synthetic-key')
                payload = host.frame_payload('zcode', 0, rows, notice)
            network.assert_called_once()
            for action in (spawn, run, shell): action.assert_not_called()
            self.assertNotIn(MARKER, payload)
            self.assertNotIn('synthetic-key', payload)
            self.assertEqual(rows is not None, percent == 25)

    def test_cli_execution_notifications_cannot_start_a_turn_or_command(self):
        result = {'rateLimits': {'limitId': 'codex', 'primary': {'usedPercent': 12,
                   'windowDurationMins': 300}}, 'execute': MARKER}
        incoming = [{'id': 1, 'result': {}}, {'method': 'exec/command', 'params': {'command': MARKER}},
                    {'method': 'turn/start', 'params': {'prompt': MARKER}}, {'id': 2, 'result': result}]
        process = Mock(pid=123456); process.stdin = RetainedBuffer()
        process.stdout = RetainedBuffer(b''.join(json.dumps(item).encode() + b'\n' for item in incoming))
        process.poll.side_effect = [None,None,0]
        with patch.object(host, 'codex_command', return_value=['official-client-fixture']), \
                patch.object(codex, 'start_child', return_value=process) as spawn, \
                patch.object(codex.subprocess, 'run') as run, patch.object(host.os, 'system') as shell, \
                patch('process_runtime.psutil.Process', return_value=Mock(children=Mock(return_value=[]))):
            rows, notice = host.fetch_codex()
        self.assertIsNone(notice); self.assertEqual(rows[0]['usedPercent'], 12)
        self.assertEqual(spawn.call_args.args[0], ['official-client-fixture', 'app-server'])
        spawn.assert_called_once(); run.assert_not_called(); shell.assert_not_called()
        outgoing = [json.loads(line) for line in process.stdin.getvalue().splitlines()]
        self.assertEqual([item['method'] for item in outgoing],
                         ['initialize', 'initialized', 'account/rateLimits/read'])
        self.assertNotIn(MARKER, str(outgoing))

    def test_telemetry_path_and_command_fields_only_produce_numeric_record(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(codex.subprocess, 'Popen') as spawn, \
                    patch.object(codex.subprocess, 'run') as run, patch.object(host.os, 'system') as shell:
                ingest('cursor', {'session_id': '../../synthetic', 'total_tokens': 25,
                                   'command': MARKER, 'path': '../../synthetic'}, root)
            for action in (spawn, run, shell): action.assert_not_called()
            paths = list(root.rglob('*.json')); self.assertEqual(len(paths), 1)
            self.assertEqual(paths[0].parent, root / 'cursor')
            record = json.loads(paths[0].read_text())
            self.assertEqual(set(record), {'total_tokens', 'received_at'})
            self.assertNotIn(MARKER, paths[0].read_text())

    def test_read_only_counter_database_cannot_load_an_extension(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'synthetic.sqlite'
            with closing(sqlite3.connect(path)) as database:
                database.execute("CREATE VIEW threads AS SELECT 'x' AS id, "
                                 "load_extension('/synthetic/blocked') AS tokens_used, 1 AS updated_at_ms")
                database.commit()
            self.assertIsNone(TokenReporter.read_counts('codex', path))
