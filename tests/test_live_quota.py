"""Latest host quota reaches the terminal without history, using synthetic numbers only."""
from io import StringIO
from types import SimpleNamespace
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import host_status
import terminal_data as data


def rows():
    return [dict(title='Session', usedPercent=28.5, windowMinutes=300, resetSeconds=3600),
            dict(title='Week', usedPercent=70, windowMinutes=10080, resetSeconds=None)]


class HostQuotaStatusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); (self.root / 'tools').mkdir()
        self.status = host_status.HostStatus(self.root / 'tools')

    def test_quota_round_trips_as_remaining_numbers_with_reset_deadline(self):
        self.status.quota('codex', rows(), now=1000)
        saved = host_status.read_status(self.root, {os.getpid()})
        self.assertEqual(saved['quota']['codex'], {'at': 1000, 'windows': [
            {'title': 'Session', 'remaining': 71.5, 'window': 300, 'reset_at': 4600},
            {'title': 'Week', 'remaining': 30.0, 'window': 10080, 'reset_at': None}]})

    def test_titles_are_bounded_printable_text(self):
        self.status.quota('codex', [dict(rows()[0], title='Session\x1b[31m' + 'x' * 40)], now=1000)
        title = self.status.data['quota']['codex']['windows'][0]['title']
        self.assertLessEqual(len(title), host_status.MAX_QUOTA_TITLE)
        self.assertNotIn('\x1b', title)

    def test_invalid_rows_are_rejected_before_writing(self):
        for bad in (dict(rows()[0], usedPercent=float('nan')), dict(rows()[0], title=''),
                    dict(rows()[0], resetSeconds=-5), dict(rows()[0], windowMinutes='300')):
            with self.assertRaises(ValueError): self.status.quota('codex', [bad], now=1000)
        with self.assertRaises(ValueError): self.status.quota('unknown', rows(), now=1000)
        self.assertNotIn('quota', self.status.data)

    def test_tampered_quota_invalidates_the_status_file(self):
        self.status.quota('codex', rows(), now=1000)
        path = self.root / 'tools/aim_host.status.json'
        for change in (lambda q: q['codex']['windows'][0].update(remaining=150),
                       lambda q: q['codex']['windows'][0].update(extra=1),
                       lambda q: q.update(unknown=q['codex'])):
            saved = json.loads(path.read_text(encoding='utf-8')); change(saved['quota'])
            path.write_text(json.dumps(saved), encoding='utf-8')
            self.assertIsNone(host_status.read_status(self.root, {os.getpid()}))

    def test_deselected_providers_lose_their_quota(self):
        self.status.quota('codex', rows(), now=1000); self.status.quota('zcode', rows(), now=1000)
        self.status.provider('codex', 'ready')
        self.status.retain_providers(['zcode'])
        self.assertEqual(set(self.status.data['quota']), {'zcode'})
        self.assertNotIn('codex', self.status.data['providers'])


class TerminalLiveQuotaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.config = dict(providers=['codex', 'zcode'], board='guition-p4', port='COM6',
                           interval_s=240, token_poll_s=2, usage_history=False)

    def collect(self, health, running=True):
        with patch.object(data, 'local_config', return_value=self.config), \
             patch.object(data, 'owned_hosts', return_value=[SimpleNamespace(pid=1)] if running else []), \
             patch.object(data, 'read_status', return_value=health), \
             patch.object(data, 'live_agents', return_value=[]):
            return data.read_dashboard(self.temp.name, now=1200)

    def health(self, state='ready'):
        return {'state': 'connected', 'port': 'COM6', 'providers': {'codex': state},
                'quota': {'codex': {'at': 1000, 'windows': [
                    {'title': 'Session', 'remaining': 71.5, 'window': 300, 'reset_at': 4600},
                    {'title': 'Week', 'remaining': 30.0, 'window': 10080, 'reset_at': None}]}}}

    def test_live_quota_is_shown_without_history_and_most_constrained_window_wins(self):
        codex, zcode = self.collect(self.health())['providers']
        self.assertEqual(codex['source'], 'live')
        self.assertEqual(codex['remaining'], 30.0)
        self.assertEqual([w['title'] for w in codex['windows']], ['Session', 'Week'])
        self.assertEqual(codex['windows'][0]['window'], '5h')
        self.assertEqual(codex['windows'][0]['reset_in'], 3400)
        self.assertIn('updated 3m ago', codex['quota_note'])
        self.assertIsNone(zcode['remaining'])
        self.assertEqual(zcode['quota_note'], 'Waiting for the first provider update')

    def test_failed_provider_keeps_last_known_quota_labeled_as_such(self):
        codex = self.collect(self.health('unavailable'))['providers'][0]
        self.assertEqual(codex['remaining'], 30.0)
        self.assertIn('Last known', codex['quota_note'])
        self.assertIn('unavailable', codex['quota_note'])

    def test_stopped_host_explains_how_to_get_quota(self):
        codex = self.collect(None, running=False)['providers'][0]
        self.assertIsNone(codex['remaining'])
        self.assertEqual(codex['quota_note'], 'Start the host to read quota')

    def test_table_shows_every_window_with_reset_countdown(self):
        from rich.console import Console
        from terminal_presentation import provider_table
        stream = StringIO()
        Console(file=stream, width=120, color_system=None).print(provider_table(self.collect(self.health())['providers']))
        text = stream.getvalue()
        for expected in ('71.5% left', '30% left', 'Session / 5h', 'Week / 7d', 'Resets in 56m', 'Live / updated 3m ago'):
            self.assertIn(expected, text)


if __name__ == '__main__':
    unittest.main()
