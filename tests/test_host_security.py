"""Synthetic trust-boundary regressions; never use account credentials."""
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import urllib.error
import urllib.request
from urllib.response import addinfourl
from email.message import Message

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import host_security as security
import aim_host as host
import aim_control as control


class SecurityTests(unittest.TestCase):
    def test_real_opener_stops_redirect_before_a_second_http_request(self):
        requests = []
        class FakeHTTPS(urllib.request.HTTPSHandler):
            def https_open(self, request):
                requests.append((request.full_url, request.get_header('Authorization')))
                headers = Message(); headers['Location'] = 'https://attacker.invalid/steal'
                response = addinfourl(io.BytesIO(), headers, request.full_url, 302)
                response.msg = 'Found'
                return response
        with patch.object(security.urllib.request, 'HTTPSHandler', FakeHTTPS):
            request = urllib.request.Request('https://api.z.ai/api/monitor/usage/quota/limit',
                                             headers={'Authorization': 'synthetic-secret'})
            with self.assertRaises(urllib.error.HTTPError): security.open_provider_request(request)
        self.assertEqual(requests, [(request.full_url, 'synthetic-secret')])

    def test_redirects_never_create_a_second_request_with_credentials(self):
        request = urllib.request.Request('https://api.z.ai/api/monitor/usage/quota/limit',
                                         headers={'Authorization': 'synthetic-secret'})
        handler = security.RejectRedirects()
        for status in (301, 302, 303, 307, 308):
            for target in ('https://attacker.invalid/', 'http://api.z.ai/', request.full_url):
                with self.subTest(status=status, target=target), self.assertRaises(urllib.error.HTTPError) as caught:
                    handler.redirect_request(request, io.BytesIO(), status, 'redirect', {}, target)
                self.assertNotIn('synthetic-secret', str(caught.exception))
                self.assertNotIn('attacker.invalid', str(caught.exception))

    def test_only_fixed_https_provider_endpoints_reach_network(self):
        for target in ('http://api.z.ai/', 'https://attacker.invalid/',
                       'https://api.z.ai@attacker.invalid/', 'file:///etc/passwd',
                       'https://api.z.ai/api/monitor/usage/quota/limit?redirect=evil'):
            with patch.object(security.urllib.request, 'build_opener') as build:
                with self.assertRaises(ValueError): security.open_provider_request(urllib.request.Request(target))
            build.assert_not_called()
        with patch.object(security.urllib.request, 'build_opener') as build:
            request = urllib.request.Request('https://api.z.ai/api/monitor/usage/quota/limit')
            security.open_provider_request(request)
        handlers = build.call_args.args
        self.assertTrue(any(isinstance(item, security.RejectRedirects) for item in handlers))
        context = next(item for item in handlers if isinstance(item, urllib.request.HTTPSHandler))._context
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, security.ssl.CERT_REQUIRED)

    def test_relative_and_current_directory_programs_are_not_discovered(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); safe = root / 'installed'; safe.mkdir()
            name = 'synthetic-client.exe' if os.name == 'nt' else 'synthetic-client'
            (root / name).write_text('fake'); (safe / name).write_text('fake')
            (safe / name).chmod(0o700)
            with patch.object(security.Path, 'cwd', return_value=root), \
                    patch.dict(os.environ, {'PATH': os.pathsep.join(('', '.', str(root), str(safe)))}):
                self.assertEqual(security.path_executable(name), str(safe / name))

    def test_serial_paths_cannot_be_network_urls_or_escape_dev(self):
        for value in ('socket://attacker.invalid:22', '/dev/../../etc/passwd',
                      '/tmp/file', 'COM6\x1b[2J', '\\\\attacker\\share', '', 'COM0'):
            with self.subTest(value=value), self.assertRaises(ValueError): security.serial_port(value)
        for value in ('auto', 'COM6', '/dev/ttyACM0', '/dev/serial/by-id/device-123'):
            self.assertEqual(security.serial_port(value), value)

    def test_large_local_configuration_is_rejected_and_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / 'tools').mkdir()
            path = root / 'tools/aim_host.json'; raw = b' ' * 65537; path.write_bytes(raw)
            with self.assertRaises(control.SetupError): control.local_config(root)
            with patch.object(host, 'CONFIG_PATH', path), self.assertRaises(ValueError): host.load_config()
            self.assertEqual(path.read_bytes(), raw)

    def test_log_text_cannot_inject_terminal_escape_or_extra_records(self):
        result = security.safe_text('message\x1b[2J\r\nFAKE\x00\u202eevil')
        self.assertNotIn('\x1b', result); self.assertNotIn('\n', result)
        self.assertNotIn('\r', result); self.assertNotIn('\u202e', result)
        self.assertLessEqual(len(security.safe_text('x' * 10000)), 512)

    def test_serial_error_details_are_not_exported_into_host_exception(self):
        panel = host.Panel.__new__(host.Panel)
        panel._rx = bytearray(json.dumps({'type': 'error', 'message': 'private\u001b[2J'}).encode() + b'\n')
        with self.assertRaises(RuntimeError) as caught: panel.wait_for('info')
        self.assertEqual(str(caught.exception), 'Panel rejected request')
