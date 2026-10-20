import importlib.util
import json
import math
import tempfile
import unittest
import subprocess
import sys
import threading
from pathlib import Path
from unittest.mock import Mock, patch
from datetime import datetime, timedelta

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
spec = importlib.util.spec_from_file_location("aim_host", ROOT / "tools" / "aim_host.py")
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)


class PortSelectionTests(unittest.TestCase):
    def test_multiple_boards_require_explicit_port(self):
        ports = [Mock(device="COM4", vid=0x303A), Mock(device="COM6", vid=0x303A)]
        with patch.object(host.list_ports, "comports", return_value=ports), patch.object(host, "LOG") as log:
            self.assertIsNone(host.find_port("auto"))
            self.assertIn("explicit port", log.call_args.args[0])
            self.assertEqual(host.find_port("COM6"), "COM6")

    def test_single_board_ignores_other_usb_devices_and_duplicates(self):
        ports = [Mock(device="COM4", vid=0x1234), Mock(device="COM6", vid=0x303A), Mock(device="COM6", vid=0x303A)]
        with patch.object(host.list_ports, "comports", return_value=ports):
            self.assertEqual(host.find_port("auto"), "COM6")
        with patch.object(host.list_ports, "comports", return_value=[]):
            self.assertIsNone(host.find_port("auto"))


class FakeSerial:
    def __init__(self, chunks=()):
        self.chunks = list(chunks)
        self.written = bytearray()
        self.closed = False

    def read(self, count):
        return self.chunks.pop(0) if self.chunks else b""

    @property
    def in_waiting(self):
        return sum(len(chunk) for chunk in self.chunks)

    def write(self, data):
        self.written.extend(data)
        return len(data)

    def close(self):
        self.closed = True


def panel_with(serial):
    with patch.object(host.serial, "Serial", return_value=serial):
        return host.Panel("COM_TEST")


class PanelTests(unittest.TestCase):
    def test_short_reply_reads_first_byte_then_available_without_fill_timeout(self):
        class BurstSerial(FakeSerial):
            def __init__(self):
                super().__init__()
                self.pending = bytearray(b'{"type":"refresh_request","requestId":7}\n{"type":"ack","frameId":101}\n')
                self.calls = []
                self.fill_timeouts = 0
                self.first = True
            @property
            def in_waiting(self):
                # Simulate arriving first byte, then partial bursts while preserving JSON.
                if self.first: return 0
                return min(13, len(self.pending))
            def read(self, count):
                self.calls.append(count)
                available = 1 if self.first else min(13, len(self.pending))
                self.first = False
                if count > available: self.fill_timeouts += 1
                result = bytes(self.pending[:min(count, available)])
                del self.pending[:len(result)]
                return result
        serial = BurstSerial(); panel = panel_with(serial)
        self.assertEqual(panel.wait_for('ack', frame_id=101)['frameId'], 101)
        self.assertEqual(serial.calls[0], 1)
        self.assertEqual(serial.fill_timeouts, 0)
        self.assertTrue(all(count <= 13 for count in serial.calls))
        self.assertEqual(panel.take_refresh_request(), 7)

    def test_wait_reply_serial_error_keeps_reconnect_signal(self):
        serial = FakeSerial()
        with patch.object(serial, 'read', side_effect=host.serial.SerialException('disconnected')):
            with self.assertRaises(host.serial.SerialException): panel_with(serial).wait_for('ack')

    def test_activity_signals_are_negotiated_with_firmware(self):
        serial = FakeSerial([b'{"type":"info","hostActivity":true}\n'])
        panel = panel_with(serial)
        panel.activity("fetching", "Fetching provider data")
        self.assertEqual(serial.written, b"")
        panel.heartbeat()
        panel.activity("fetching", "Fetching provider data")
        self.assertIn(b'"cmd": "host_activity"', bytes(serial.written))

    def test_legacy_firmware_does_not_receive_activity_commands(self):
        serial = FakeSerial([b'{"type":"info","display":"jc4880p433","panelId":"esp32p4-mipi-dsi"}\n'])
        panel = panel_with(serial)
        panel.heartbeat()
        before = bytes(serial.written)
        panel.activity("updated", "Latest quota received")
        self.assertEqual(bytes(serial.written), before)

    def test_manual_refresh_reports_result_after_provider_ack(self):
        for success in (True, False):
            with self.subTest(success=success):
                panel = Mock()
                panel.take_refresh_request.return_value = 7
                def poll(*args):
                    panel.last_poll_success = success
                    return 101
                with patch.object(host, "find_port", return_value="COM_TEST"), \
                        patch.object(host, "connect_panel", return_value=panel), \
                        patch.object(host, "poll_cycle", side_effect=poll), \
                        patch.object(host, "wait_connected", side_effect=KeyboardInterrupt), \
                        patch.object(host, "LOG"):
                    with self.assertRaises(KeyboardInterrupt):
                        host._run_loop(host.DEFAULT_CONFIG, 240, "", ["codex"])
                self.assertEqual([call.args[1] for call in panel.refresh_status.call_args_list],
                                 ["updating", "complete" if success else "failed"])
                panel.close.assert_called_once()

    def test_refresh_requests_need_valid_integer_ids(self):
        serial = FakeSerial()
        panel = panel_with(serial)
        for value in (0, -1, True, "7", 4294967296):
            self.assertFalse(panel.handle_event({"type": "refresh_request", "requestId": value}))
        self.assertEqual(serial.written, b"")
        self.assertIsNone(panel.take_refresh_request())

    def test_frame_transmits_countdown_only_for_unambiguous_timestamp(self):
        with patch.object(host.time, "time", return_value=1000):
            payload = json.loads(host.frame_payload("codex", 0, [
                {"usedPercent": 25, "resetsAt": host.now_iso_epoch(3400)},
                {"usedPercent": 50, "resetsAt": "23:45"}]))
        rows = payload["data"][0]["usage"]["rows"]
        self.assertEqual(rows[0]["resetSeconds"], 2400)
        self.assertNotIn("resetSeconds", rows[1])
        self.assertEqual(rows[0]["usedPercent"], 75)

    def test_refresh_event_is_preserved_while_waiting_for_ack(self):
        serial = FakeSerial([b'{"type":"refresh_request","requestId":7}\n'
                             b'{"type":"ack","frameId":101}\n'])
        panel = panel_with(serial)
        panel.wait_for("ack", frame_id=101)
        self.assertEqual(panel.take_refresh_request(), 7)

    def test_manual_refresh_interrupts_wait_after_cooldown(self):
        clock = {"now": 100.0}
        panel = Mock()
        panel.refresh_request_id = 7
        with patch.object(host.time, "monotonic", side_effect=lambda: clock["now"]), \
                patch.object(host.time, "sleep", side_effect=lambda seconds: clock.update(now=clock["now"] + seconds)):
            host.wait_connected(panel, 240, minimum_wait=15)
        self.assertEqual(clock["now"], 115)

    def test_heartbeat_detects_reboot(self):
        serial = FakeSerial([b'{"type":"info","bootId":2}\n'])
        panel = panel_with(serial)
        panel.boot_id = 1
        with self.assertRaises(ConnectionResetError):
            panel.heartbeat()

    def test_wait_checks_usb_without_calling_provider_api(self):
        clock = {"now": 100.0}
        panel = Mock()
        def advance(seconds):
            clock["now"] += seconds
        with patch.object(host.time, "monotonic", side_effect=lambda: clock["now"]), \
                patch.object(host.time, "sleep", side_effect=advance), \
                patch.object(host, "fetch_codex") as fetch:
            host.wait_connected(panel, 25)
        self.assertEqual(panel.heartbeat.call_count, 2)
        self.assertEqual(clock["now"], 125)
        fetch.assert_not_called()

    def test_close_releases_port(self):
        serial = FakeSerial()
        panel_with(serial).close()
        self.assertTrue(serial.closed)

    def test_split_reply_logs_whitespace_and_unrelated_ack(self):
        serial = FakeSerial([
            b'[E] boot log\n{"type": "ack", "frameId": 10}\n{"ty',
            b'pe": "ack", "frameId": 11}\r\n',
        ])
        reply = panel_with(serial).wait_for("ack", frame_id=11)
        self.assertEqual(reply["frameId"], 11)

    def test_matching_error_is_failure_even_with_other_ack(self):
        serial = FakeSerial([
            b'{"type":"ack","frameId":10}\n'
            b'{"type":"error","frameId":11,"message":"bad frame"}\n'
        ])
        with self.assertRaisesRegex(RuntimeError, "Panel rejected request"):
            panel_with(serial).wait_for("ack", frame_id=11)

    def test_silent_device_times_out(self):
        with self.assertRaises(TimeoutError):
            panel_with(FakeSerial()).wait_for("info", seconds=0)

    def test_oversize_payload_is_rejected_before_writing(self):
        serial = FakeSerial()
        with self.assertRaises(ValueError):
            panel_with(serial).send_frame("x" * 4096, 1)
        self.assertEqual(serial.written, b"")

    def test_frame_length_counts_utf8_bytes(self):
        serial = FakeSerial()
        panel_with(serial).send_frame("ø", 3)
        self.assertEqual(serial.written, b"AIM1 2 3\n\xc3\xb8\n")

    def test_failed_handshake_closes_port(self):
        serial = FakeSerial([b'{"type":"info","display":"jc4880p433","panelId":"esp32p4-mipi-dsi"}\n'])
        with patch.object(host.serial, "Serial", return_value=serial), patch.object(host.time, "sleep"):
            with self.assertRaises(TimeoutError):
                host.connect_panel("COM_TEST", ["codex"])
        self.assertTrue(serial.closed)

    def test_handshake_configures_views_before_returning(self):
        serial = FakeSerial([
            b'{"type":"info","display":"jc4880p433","panelId":"esp32p4-mipi-dsi"}\n',
            b'{"type":"ok","cmd":"set_views"}\n',
        ])
        with patch.object(host.serial, "Serial", return_value=serial), patch.object(host.time, "sleep"):
            panel = host.connect_panel("COM_TEST", ["codex"])
        self.assertEqual(panel.name, "COM_TEST")
        commands = [json.loads(line) for line in serial.written.splitlines()]
        self.assertEqual([cmd["cmd"] for cmd in commands], ["get_info", "set_views"])


class PayloadTests(unittest.TestCase):
    def test_reset_countdown_keeps_absolute_time(self):
        reset = "2026-10-08T12:30:00Z"
        epoch = datetime.fromisoformat(reset.replace("Z", "+00:00")).timestamp() - 2400
        self.assertEqual(host.reset_seconds(reset, epoch_now=epoch), 2400)
        self.assertIsNone(host.reset_seconds("Tomorrow", epoch_now=0))

    def test_remaining_percent_and_notice_state(self):
        usage = json.loads(host.frame_payload("codex", 0, [{"usedPercent": 25}]))["data"][0]
        self.assertEqual(usage["usage"]["rows"][0]["usedPercent"], 75)
        notice = json.loads(host.frame_payload("codex", 0, None, "Unavailable"))["data"][0]
        self.assertFalse(notice["fetching"])

    def test_over_quota_is_zero_remaining(self):
        usage = json.loads(host.frame_payload("codex", 0, [{"usedPercent": 140}]))["data"][0]
        self.assertEqual(usage["usage"]["rows"][0]["usedPercent"], 0)

    def test_nonfinite_usage_is_rejected(self):
        for value in (math.nan, math.inf):
            with self.subTest(value=value), self.assertRaises(ValueError):
                host.frame_payload("codex", 0, [{"usedPercent": value}])

    def test_current_timezone_offset_is_used(self):
        envelope = json.loads(host.frame_payload("codex", 0, [{"usedPercent": 25}]))
        offset = host.datetime.now().astimezone().utcoffset()
        self.assertEqual(envelope["tzOffsetMinutes"], int(offset.total_seconds() // 60))

    def test_winter_offset_does_not_add_summer_time(self):
        clock = Mock()
        clock.astimezone.return_value = clock
        clock.utcoffset.return_value = timedelta(hours=1)
        clock.strftime.return_value = "2026-01-15T12:00:00Z"
        clock.second = 0
        with patch.object(host, "datetime") as dates, patch.object(host.time, "daylight", 1), \
                patch.object(host.time, "timezone", -3600):
            dates.now.return_value = clock
            envelope = json.loads(host.frame_payload("codex", 0, [{"usedPercent": 25}]))
        self.assertEqual(envelope["tzOffsetMinutes"], 60)

    def test_resets_use_local_time_and_long_windows_keep_date(self):
        iso = "2026-12-01T20:30:00Z"
        local = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone()
        self.assertEqual(host.reset_display(iso, 300), local.strftime("%H:%M"))
        self.assertEqual(host.reset_display(iso, 10080), local.strftime("%d %b %H:%M"))


class LoopTests(unittest.TestCase):
    def setUp(self):
        # Loop fixtures stay in-process and synthetic; production quota uses
        # the independently tested bounded subprocess below.
        worker = patch.object(host.FetchPool, 'fetch', side_effect=lambda provider, key, _panel:
                             host.fetch_codex() if provider == 'codex' else host.fetch_zcode(key))
        worker.start(); self.addCleanup(worker.stop)
    def test_poll_interval_includes_fetch_duration(self):
        panel = Mock()
        with patch.object(host, "find_port", return_value="COM_TEST"), \
                patch.object(host, "connect_panel", return_value=panel), \
                patch.object(host, "poll_cycle", return_value=101), \
                patch.object(host, "time", wraps=host.time) as clock, \
                patch.object(host, "wait_connected", side_effect=KeyboardInterrupt) as wait, \
                patch.object(host, "LOG"):
            clock.monotonic.side_effect=[100,140,140]
            with self.assertRaises(KeyboardInterrupt):
                host._run_loop(host.DEFAULT_CONFIG, 240, "", ["codex"])
        wait.assert_called_once_with(panel, 200, minimum_wait=0)
        # The panel carries the activity-aware policy, anchored to the start of this poll cycle.
        self.assertIsInstance(panel.refresh_policy, host.AdaptiveRefresh)
        self.assertEqual((panel.refresh_policy.base, panel.refresh_policy.cycle_started), (240, 100))
        panel.close.assert_called_once()

    def test_codex_is_sent_before_waiting_for_zai(self):
        events = []
        rows = [{"usedPercent": 25}]
        panel = Mock()
        panel.wait_for.side_effect = lambda *args, **kwargs: events.append("ack")
        with patch.object(host, "fetch_codex", side_effect=lambda: (events.append("codex") or (rows, None))), \
                patch.object(host, "fetch_zcode", side_effect=lambda key: (events.append("zai") or (rows, None))), \
                patch.object(host, "LOG"):
            host.poll_cycle(host.DEFAULT_CONFIG, "test-key", ["codex", "zcode"], 100, panel)
        self.assertEqual(events, ["codex", "ack", "zai", "ack"])

    def test_keyboard_interrupt_during_fetch_releases_port(self):
        serial = FakeSerial()
        panel = panel_with(serial)
        with patch.object(host, "find_port", return_value="COM_TEST"), \
                patch.object(host, "connect_panel", return_value=panel), \
                patch.object(host, "fetch_codex", side_effect=KeyboardInterrupt), \
                patch.object(host, "LOG"):
            with self.assertRaises(KeyboardInterrupt):
                host._run_loop(host.DEFAULT_CONFIG, 60, "", ["codex"])
        self.assertTrue(serial.closed)

    def test_missing_ack_closes_link_and_performs_fresh_handshake(self):
        first, second = Mock(), Mock()
        first.wait_for.side_effect = TimeoutError("missing ACK")
        rows = [{"usedPercent": 25}]
        with patch.object(host, "find_port", return_value="COM_TEST"), \
                patch.object(host, "connect_panel", side_effect=[first, second]) as connect, \
                patch.object(host, "fetch_codex", side_effect=[(rows, None), KeyboardInterrupt]), \
                patch.object(host, "wait_for_config") as sleep, patch.object(host, "LOG"):
            with self.assertRaises(KeyboardInterrupt):
                host._run_loop(host.DEFAULT_CONFIG, 60, "", ["codex"])
        self.assertEqual(connect.call_count, 2)
        first.close.assert_called_once()
        second.close.assert_called_once()
        self.assertEqual(sleep.call_args.args[1], 5)

    def test_post_handshake_failure_closes_port_before_reconnect_wait(self):
        panel = Mock(info={'hardwareDiagnostics': True})
        panel.send_line.side_effect = OSError('Synthetic disconnected USB')
        closed_before_wait = []
        def reconnect_wait(*args):
            closed_before_wait.append(panel.close.called)
            raise KeyboardInterrupt()
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(host, 'HERE', Path(folder)), \
                patch.object(host, 'find_port', return_value='COM_TEST'), \
                patch.object(host, 'connect_panel', return_value=panel), \
                patch.object(host, 'wait_for_config', side_effect=reconnect_wait), \
                patch.object(host, 'poll_cycle') as poll, patch.object(host, 'LOG'):
            with self.assertRaises(KeyboardInterrupt):
                host._run_loop(host.DEFAULT_CONFIG, 60, '', ['codex'])
        self.assertEqual(closed_before_wait, [True])
        panel.close.assert_called_once()
        poll.assert_not_called()

    def test_provider_error_is_sent_as_notice_and_receives_ack(self):
        serial = FakeSerial([b'{"type":"ack","frameId":101}\n'])
        with patch.object(host, "fetch_codex", return_value=(None, "Unavailable")), \
                patch.object(host, "LOG"):
            self.assertEqual(host.poll_cycle(host.DEFAULT_CONFIG, "", ["codex"], 100,
                                             panel_with(serial)), 101)
        header, payload = bytes(serial.written).split(b"\n", 1)
        self.assertTrue(header.startswith(b"AIM1 "))
        self.assertEqual(json.loads(payload)["data"][0]["notice"], "Unavailable")


class RetryTests(unittest.TestCase):
    def test_backoff_is_per_provider_and_success_resets_it(self):
        clock = {"now": 100.0}
        retries = host.ProviderRetries(15)
        with patch.object(host.time, "monotonic", side_effect=lambda: clock["now"]):
            retries.failed("codex", "Unavailable")
            self.assertEqual(retries.remaining("codex"), 15)
            self.assertEqual(retries.remaining("zcode"), 0)
            clock["now"] += 15
            retries.failed("codex", "Unavailable")
            self.assertEqual(retries.remaining("codex"), 30)
            for _ in range(12):
                retries.failed("codex", "Unavailable")
            self.assertEqual(retries.remaining("codex"), 3600)
            retries.succeeded("codex")
            retries.failed("codex", "Unavailable")
            self.assertEqual(retries.remaining("codex"), 15)

    def test_retry_after_accepts_seconds_and_http_date(self):
        with patch.object(host.time, "time", return_value=0):
            self.assertEqual(host.retry_after_seconds({"Retry-After": "90"}), 90)
            self.assertEqual(host.retry_after_seconds({"Retry-After": "Thu, 01 Jan 1970 00:02:00 GMT"}), 120)
        for value in ("bad", "-1", "Thu, 99 Jan 1970 00:00:00 GMT"):
            self.assertEqual(host.retry_after_seconds({"Retry-After": value}), 0)
        with patch.object(host.time, "monotonic", return_value=100):
            retries = host.ProviderRetries(15)
            retries.failed("codex", host.ProviderNotice("Rate limited", 90))
            self.assertEqual(retries.remaining("codex"), 90)

    def test_deferred_provider_is_not_fetched_and_other_provider_continues(self):
        serial = FakeSerial([b'{"type":"ack","frameId":101}\n', b'{"type":"ack","frameId":102}\n'])
        panel = panel_with(serial)
        panel.retries = host.ProviderRetries(15)
        with patch.object(host.time, "monotonic", return_value=100), patch.object(host, "LOG"):
            panel.retries.failed("codex", host.ProviderNotice("Rate limited", 90))
            with patch.object(host, "fetch_codex") as codex, \
                    patch.object(host, "fetch_zcode", return_value=([{"usedPercent": 25}], None)) as zcode:
                host.poll_cycle(host.DEFAULT_CONFIG, "test-key", ["codex", "zcode"], 100, panel)
            codex.assert_not_called()
            zcode.assert_called_once_with("test-key")
            self.assertFalse(panel.last_poll_success)
            self.assertEqual(panel.retries.remaining("codex"), 90)  # skipping does not extend the cooldown
        self.assertIn(b"retry in 90 s", bytes(serial.written))


class ResponsiveFetchTests(unittest.TestCase):
    def test_request_in_automatic_poll_completes_in_the_same_cycle(self):
        serial = FakeSerial()
        panel = panel_with(serial)
        ack_count = {"value": 0}
        def ack(*args, **kwargs):
            ack_count["value"] += 1
            if ack_count["value"] == 1:
                panel.handle_event({"type": "refresh_request", "requestId": 7})
        with patch.object(host, "find_port", return_value="COM_TEST"), \
                patch.object(host, "connect_panel", return_value=panel), \
                patch.object(host, "fetch_codex", return_value=([{"usedPercent": 25}], None)) as codex, \
                patch.object(host, "fetch_zcode", return_value=([{"usedPercent": 25}], None)) as zcode, \
                patch.object(host.FetchPool, 'fetch', side_effect=lambda provider, key, _panel:
                             host.fetch_codex() if provider == 'codex' else host.fetch_zcode(key)), \
                patch.object(panel, "wait_for", side_effect=ack), \
                patch.object(host, "wait_connected", side_effect=KeyboardInterrupt), patch.object(host, "LOG"):
            with self.assertRaises(KeyboardInterrupt):
                host._run_loop(host.DEFAULT_CONFIG, 240, "test-key", ["codex", "zcode"])
        codex.assert_called_once()
        zcode.assert_called_once_with("test-key")
        statuses = []
        for line in bytes(serial.written).splitlines():
            try:
                value = json.loads(line)
            except ValueError:
                continue
            if value.get("cmd") == "refresh_status":
                statuses.append((value["requestId"], value["state"]))
        self.assertEqual(statuses, [(7, "updating"), (7, "complete")])
        self.assertTrue(serial.closed)

    def test_request_during_fetch_joins_current_cycle_without_another_poll(self):
        serial = FakeSerial([b'{"type":"refresh_request","requestId":7}\n'])
        panel = panel_with(serial)
        panel.cycle_active = True
        pool = host.FetchPool()
        code = "import sys,time; sys.stdin.read(); time.sleep(.35); print('{\"rows\":[{\"usedPercent\":25}],\"notice\":null,\"retry_after\":0}')"
        try:
            with patch.object(pool, 'command', return_value=[sys.executable, '-u', '-c', code]):
                rows, notice = pool.fetch("codex", '', panel)
            self.assertIsNone(notice)
            self.assertEqual(rows[0]["usedPercent"], 25)
            self.assertEqual(panel.active_refresh_id, 7)
            self.assertIsNone(panel.take_refresh_request())
            self.assertIn(b'"state": "updating"', bytes(serial.written))
        finally:
            pool.close()

    def test_heartbeat_continues_and_api_wait_has_deadline(self):
        pool, panel = host.FetchPool(), Mock()
        pool.request_seconds = .35
        command = [sys.executable, '-u', '-c', 'import sys,time; sys.stdin.read(); time.sleep(60)']
        with patch.object(pool, 'command', return_value=command), patch.object(host, 'HEARTBEAT_SECONDS', .05), \
                patch.object(host.subprocess, 'Popen', wraps=subprocess.Popen) as spawn:
            rows, notice = pool.fetch('codex', '', panel)
        self.assertIsNone(rows); self.assertIn('timed out', notice)
        self.assertGreater(panel.heartbeat.call_count, 0)
        self.assertGreater(panel.collect_requests.call_count, 0)
        self.assertIsNone(pool.process)
        self.assertTrue(spawn.called)
        # A subsequent request can recover; there is no stuck future.
        code = "print('{\"rows\":[{\"usedPercent\":25}],\"notice\":null,\"retry_after\":0}')"
        pool.request_seconds = 3
        with patch.object(pool, 'command', return_value=[sys.executable, '-u', '-c', code]):
            rows, notice = pool.fetch('codex', '', panel)
        self.assertIsNone(notice); self.assertEqual(rows[0]['usedPercent'], 25)

    def test_unexpected_worker_exception_never_echoes_secret(self):
        pool = host.FetchPool()
        command = [sys.executable, '-u', '-c', "import sys; sys.stdin.read(); print('private-key')"]
        with patch.object(pool, 'command', return_value=command):
            rows, notice = pool.fetch("codex", '', Mock())
        self.assertIsNone(rows)
        self.assertNotIn("private-key", notice)
        pool.close()

    def test_second_provider_cannot_exceed_total_cycle_budget(self):
        pool, panel = host.FetchPool(), Mock(cycle_deadline=host.time.monotonic()-1)
        with patch.object(host.subprocess, 'Popen') as spawn:
            rows, notice = pool.fetch("zcode", '', panel)
        self.assertIsNone(rows)
        self.assertIn("timed out", notice)
        spawn.assert_not_called()
        pool.close()

    def test_worker_that_never_reads_stdin_cannot_block_a_long_credential(self):
        pool = host.FetchPool(); pool.request_seconds = .35
        command = [sys.executable, '-u', '-c', 'import time; time.sleep(60)']
        with patch.object(pool, 'command', return_value=command):
            started = host.time.monotonic()
            rows, notice = pool.fetch('zcode', 'synthetic-'+'x'*20000, Mock())
        self.assertIsNone(rows); self.assertIn('timed out', notice)
        self.assertLess(host.time.monotonic()-started, 2)
        self.assertIsNone(pool.process)

    def test_timeout_reaps_launched_worker_descendants_and_hides_key_arguments(self):
        import psutil
        with tempfile.TemporaryDirectory() as directory:
            pid_file = Path(directory)/'synthetic-child.pid'
            code = ("import subprocess,sys,time,pathlib; sys.stdin.read(); "
                    "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
                    "pathlib.Path(sys.argv[1]).write_text(str(child.pid)); time.sleep(60)")
            pool = host.FetchPool(); pool.request_seconds = 1
            command = [sys.executable, '-u', '-c', code, str(pid_file)]
            with patch.object(pool, 'command', return_value=command), \
                    patch.object(host.subprocess, 'Popen', wraps=subprocess.Popen) as spawn:
                rows, notice = pool.fetch('zcode', 'synthetic-private-key', Mock())
            self.assertIsNone(rows); self.assertIn('timed out', notice)
            self.assertNotIn('synthetic-private-key', str(spawn.call_args))
            self.assertTrue(pid_file.is_file())
            self.assertFalse(psutil.pid_exists(int(pid_file.read_text())))
            self.assertIsNone(pool.process)

    def test_small_positive_remaining_is_not_rounded_to_zero_by_host(self):
        usage = json.loads(host.frame_payload("codex", 0, [{"usedPercent": 99.96}]))["data"][0]
        remaining = usage["usage"]["rows"][0]["usedPercent"]
        self.assertGreater(remaining, 0)
        self.assertAlmostEqual(remaining, 0.04)


class ConfigReloadTests(unittest.TestCase):
    def test_changed_key_invalidates_the_previous_quota_success(self):
        previous = dict(host.DEFAULT_CONFIG, board='guition-p4', providers=['zcode'],
                        port='COM_TEST', zai_key='synthetic-old-key')
        changed = dict(previous, zai_key='synthetic-new-key')
        health = Mock(data={'providers':{'zcode':'ready'}})
        watcher = Mock(); watcher.take.return_value = changed
        panel = Mock()
        observed = []
        def poll(*_args):
            observed.append(dict(health.data['providers']))
            raise KeyboardInterrupt
        with patch.object(host, 'HostStatus', return_value=health), \
                patch.object(host, 'ConfigWatcher', return_value=watcher), \
                patch.object(host, 'find_port', return_value='COM_TEST'), \
                patch.object(host, 'connect_panel', return_value=panel), \
                patch.object(host, 'poll_cycle', side_effect=poll), patch.object(host, 'LOG'):
            with self.assertRaises(KeyboardInterrupt): host._run_loop(previous, 240, previous['zai_key'], ['zcode'])
        self.assertEqual(observed, [{}])
    def test_valid_edit_is_loaded_and_invalid_edit_keeps_last_configuration(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(host.os.environ, {}, clear=True):
            path = Path(directory) / "aim_host.json"
            path.write_text('{"interval_s":240}', encoding="utf-8")
            with patch.object(host, "CONFIG_PATH", path), patch.object(host, "LOG") as log:
                watcher = host.ConfigWatcher()
                stamp = path.stat().st_mtime_ns
                path.write_text('{"interval_s":60,"zai_key":"test-key"}', encoding="utf-8")
                host.os.utime(path, ns=(stamp + 10000000, stamp + 10000000))
                watcher.check()
                valid = watcher.take()
                self.assertEqual(valid["interval_s"], 60)
                self.assertEqual(valid["zai_key"], "test-key")
                path.write_text(json.dumps({"zai_key": "private-key\ninvalid"}), encoding="utf-8")
                host.os.utime(path, ns=(stamp + 20000000, stamp + 20000000))
                watcher.check()
                self.assertIsNone(watcher.take())
                self.assertNotIn("private-key", str(log.call_args))
                calls = log.call_count
                watcher.check()
                self.assertEqual(log.call_count, calls)

    def test_new_configuration_changes_interval_and_view_set(self):
        panel, watcher = Mock(), Mock()
        changed = dict(host.DEFAULT_CONFIG, board='waveshare-s3-43', providers=['codex', 'zcode'], interval_s=60, zai_key="test-key", port="COM_TEST")
        watcher.take.side_effect = [changed]
        with patch.object(host, "ConfigWatcher", return_value=watcher), \
                patch.object(host, "find_port", return_value="COM_TEST") as find, \
                patch.object(host, "connect_panel", return_value=panel) as connect, \
                patch.object(host, "poll_cycle", return_value=102) as poll, \
                patch.object(host, "wait_connected", side_effect=KeyboardInterrupt) as wait, patch.object(host, "LOG"):
            with self.assertRaises(KeyboardInterrupt):
                host._run_loop(host.DEFAULT_CONFIG, 240, "", ["codex"])
        find.assert_called_once_with("COM_TEST", 'waveshare-s3-43')
        connect.assert_called_once_with("COM_TEST", ["codex", "zcode"], 'waveshare-s3-43')
        self.assertEqual(poll.call_args.args[:3], (changed, "test-key", ["codex", "zcode"]))
        self.assertLessEqual(wait.call_args.args[1], 60)
        panel.close.assert_called_once()


class ConfigTests(unittest.TestCase):
    def test_multiline_key_is_rejected_without_echoing_it(self):
        secret = "private-key\nInjected: value"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "aim_host.json"
            path.write_text(json.dumps({"zai_key": secret}), encoding="utf-8")
            with patch.object(host, "CONFIG_PATH", path), patch.dict(host.os.environ, {}, clear=True):
                with self.assertRaises(ValueError) as error:
                    host.load_config()
        self.assertNotIn("private-key", str(error.exception))

    def test_existing_config_is_not_rewritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "aim_host.json"
            original = '{"interval_s": 60}\n'
            path.write_text(original, encoding="utf-8")
            with patch.object(host, "CONFIG_PATH", path):
                self.assertEqual(host.load_config()["interval_s"], 60)
            self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_invalid_config_fails_with_clear_message(self):
        for value in ({"interval_s": "bad"}, {"zai_provider": "codex"}, [], {"port": 12}):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "aim_host.json"
                path.write_text(json.dumps(value), encoding="utf-8")
                with patch.object(host, "CONFIG_PATH", path), self.assertRaises(ValueError):
                    host.load_config()


class ProviderTests(unittest.TestCase):
    def test_zcode_keeps_model_week_and_monthly_mcp_separate(self):
        context = self.response({"success": True, "data": {"limits": [
            {"type": "CREDIT_LIMIT", "unit": 3, "number": 5, "percentage": 25},
            {"type": "CREDIT_LIMIT", "unit": 6, "number": 1, "percentage": 60},
            {"type": "TIME_LIMIT", "percentage": 12, "currentValue": 12, "usage": 100},
        ]}})
        with patch.object(host, "open_provider_request", return_value=context):
            rows, notice = host.fetch_zcode("test-key")
        self.assertIsNone(notice)
        self.assertEqual([(row["title"], row["windowMinutes"]) for row in rows],
                         [("Session", 300), ("Week", 10080), ("Monthly MCP", 43200)])
        self.assertEqual([row["usedPercent"] for row in rows], [25, 60, 12])

    def test_zcode_monthly_counts_require_a_real_positive_limit(self):
        for limit, expected in ((100, 12), (0, None), (True, None)):
            with self.subTest(limit=limit):
                context = self.response({"success": True, "data": {"limits": [
                    {"type": "TIME_LIMIT", "currentValue": 12, "usage": limit}]}})
                with patch.object(host, "open_provider_request", return_value=context):
                    rows, notice = host.fetch_zcode("test-key")
                if expected is None:
                    self.assertIsNone(rows)
                    self.assertTrue(notice)
                else:
                    self.assertIsNone(notice)
                    self.assertEqual(rows[0]["usedPercent"], expected)

    def setUp(self):
        legacy = patch.object(host, 'codex_command', return_value=None)
        legacy.start(); self.addCleanup(legacy.stop)
    def test_explicit_rejection_does_not_accept_success_code(self):
        context = self.response({"success": False, "code": 200, "data": {"limits": [
            {"type": "CREDIT_LIMIT", "unit": 3, "percentage": 25}]}})
        with patch.object(host, "open_provider_request", return_value=context):
            rows, notice = host.fetch_zcode("test-key")
        self.assertIsNone(rows)
        self.assertTrue(notice)

    def test_missing_duration_is_unknown_and_daily_secondary_is_not_called_week(self):
        context = self.response({"rate_limit": {"primary_window": {"used_percent": 12},
            "secondary_window": {"used_percent": 25, "limit_window_seconds": 86400}}})
        with patch.object(host, 'read_local_json', return_value={'tokens': {'access_token': 'test-token'}}), \
                patch.object(host, "open_provider_request", return_value=context):
            rows, notice = host.fetch_codex()
        self.assertIsNone(notice)
        self.assertEqual(rows[0]["windowMinutes"], 0)
        self.assertEqual(rows[1]["windowMinutes"], 1440)
        self.assertEqual(rows[1]["title"], "Secondary")

    def test_oversized_codex_auth_is_rejected_before_network(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'auth.json'
            path.write_bytes(b'x' * 65537)
            with patch.object(host, 'CODEX_AUTH', path), patch.object(host, 'open_provider_request') as request:
                rows, notice = host.fetch_codex()
            self.assertIsNone(rows); self.assertTrue(notice)
            request.assert_not_called()

    def test_invalid_key_never_reaches_network(self):
        with patch.object(host, "open_provider_request") as request:
            rows, notice = host.fetch_zcode("private-key\nInjected: header")
        request.assert_not_called()
        self.assertIsNone(rows)
        self.assertNotIn("private-key", notice)

    def test_key_format_error_identifies_source_without_echoing_value(self):
        bad = 'fixture-private-key\ninvalid'
        with patch.dict(host.os.environ, {'ZAI_API_KEY': bad}):
            with self.assertRaisesRegex(ValueError, 'ZAI_API_KEY environment variable') as error:
                host.zcode_key({'zai_key': 'fixture-valid'})
            self.assertNotIn('fixture-private-key', str(error.exception))
        with patch.dict(host.os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, 'saved zai_key') as error:
                host.zcode_key({'zai_key': bad})
            self.assertNotIn('fixture-private-key', str(error.exception))
        with patch.dict(host.os.environ, {'ZAI_API_KEY': ''}):
            self.assertEqual(host.zcode_key({'zai_key': 'fixture-valid'}), '')

    def response(self, data):
        response = Mock()
        response.read.return_value = json.dumps(data).encode()
        context = Mock()
        context.__enter__ = Mock(return_value=response)
        context.__exit__ = Mock(return_value=False)
        return context

    def test_exception_messages_do_not_expose_credentials(self):
        with patch.object(host, "open_provider_request", side_effect=ValueError("Invalid header: private-key")):
            rows, notice = host.fetch_zcode("test-key")
        self.assertIsNone(rows)
        self.assertNotIn("private-key", notice)

    def test_unknown_window_is_not_falsely_labelled_as_five_hours(self):
        context = self.response({"success": True, "data": {"limits": [
            {"type": "CREDIT_LIMIT", "unit": 99, "percentage": 25}]}})
        with patch.object(host, "open_provider_request", return_value=context):
            rows, notice = host.fetch_zcode("test-key")
        self.assertIsNone(notice)
        self.assertEqual(rows[0]["title"], "Quota")
        self.assertEqual(rows[0]["windowMinutes"], 0)

    def test_large_response_is_rejected_with_bounded_read(self):
        response = Mock()
        response.read.return_value = b"x" * 65537
        with self.assertRaises(ValueError):
            host.read_json_response(response)
        response.read.assert_called_once_with(65537)

    def test_response_must_be_json_object(self):
        response = Mock()
        response.read.return_value = b"[]"
        with self.assertRaises(ValueError):
            host.read_json_response(response)

    def test_rejection_message_from_server_is_not_forwarded_verbatim(self):
        context = self.response({"success": False, "code": 401, "msg": "private-key"})
        with patch.object(host, "open_provider_request", return_value=context):
            rows, notice = host.fetch_zcode("test-key")
        self.assertIsNone(rows)
        self.assertNotIn("private-key", notice)

    def test_zai_numeric_string_reset_matches_numeric_timestamp(self):
        value = 1791399600000
        self.assertEqual(host.zai_reset_iso(str(value)), host.zai_reset_iso(value))
        self.assertTrue(host.zai_reset_iso(value).endswith("Z"))

    def test_missing_codex_percentage_is_not_reported_as_unused_quota(self):
        response = Mock()
        response.read.return_value = json.dumps({"rate_limit": {"primary_window": {"reset_at": 1}}}).encode()
        context = Mock()
        context.__enter__ = Mock(return_value=response)
        context.__exit__ = Mock(return_value=False)
        auth = Mock()
        auth.read_text.return_value = '{"tokens":{"access_token":"test-token"}}'
        with patch.object(host, "CODEX_AUTH", auth), patch.object(host, "open_provider_request", return_value=context):
            rows, notice = host.fetch_codex()
        self.assertIsNone(rows)
        self.assertTrue(notice)

    def test_missing_zai_percentage_is_not_reported_as_unused_quota(self):
        response = Mock()
        response.read.return_value = json.dumps({"success": True, "data": {"limits": [
            {"type": "CREDIT_LIMIT", "unit": 3}]}}).encode()
        context = Mock()
        context.__enter__ = Mock(return_value=response)
        context.__exit__ = Mock(return_value=False)
        with patch.object(host, "open_provider_request", return_value=context):
            rows, notice = host.fetch_zcode("test-key")
        self.assertIsNone(rows)
        self.assertTrue(notice)


class HostLifecycleTests(unittest.TestCase):
    def test_only_one_process_can_hold_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            lock = Path(directory) / "aim_host.lock"
            with patch.object(host, "LOCK_PATH", lock):
                self.assertTrue(host.acquire_lock())
                try:
                    code = (f"import sys; sys.path.insert(0, {str(ROOT / 'tools')!r}); "
                            f"import aim_host; from pathlib import Path; aim_host.LOCK_PATH=Path({str(lock)!r}); "
                            "sys.exit(1 if aim_host.acquire_lock() else 0)")
                    other = subprocess.run([sys.executable, "-c", code], capture_output=True, timeout=10)
                    self.assertEqual(other.returncode, 0)
                finally:
                    host.release_lock()
                self.assertTrue(host.acquire_lock())
                host.release_lock()

    def test_configuration_error_releases_lock(self):
        with patch.object(host, "acquire_lock", return_value=True), \
                patch.object(host, "release_lock") as release, \
                patch.object(host, "load_config", side_effect=ValueError("bad config")), \
                patch.object(host, "LOG"):
            self.assertEqual(host.main(), 1)
        release.assert_called_once()


if __name__ == "__main__":
    unittest.main()
