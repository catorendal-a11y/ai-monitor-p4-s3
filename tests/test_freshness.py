import os, re, sys, tempfile, threading, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import aim_host as host


class FreshnessTests(unittest.TestCase):
    def test_panel_stale_limit_leaves_margin_over_slowest_host_cycle(self):
        header = (ROOT / 'src/ai_monitor/ai_monitor.h').read_text()
        stale_ms = int(re.search(r'kQuotaStaleMs\s*=\s*(\d+)u?;', header).group(1))
        slowest = host.MAX_INTERVAL_SECONDS + host.CYCLE_DEADLINE_SECONDS
        self.assertGreaterEqual(stale_ms // 1000 - slowest, 10)

    def test_ui_sources_do_not_repeat_the_stale_literal(self):
        for path in list((ROOT / 'src').glob('*.cpp')) + list((ROOT / 'src/ui').glob('*.h')):
            if path.name in ('nova_assets.cpp', 'usage_history.h'):
                continue  # generated assets; history bucket width is a different quantity
            self.assertNotIn('300000', path.read_text(errors='ignore'), path.name)

    def test_log_is_created_private_and_survives_concurrent_writers(self):
        with tempfile.TemporaryDirectory() as folder:
            original = host.LOG_PATH
            host.LOG_PATH = Path(folder) / 'aim_host.log'
            try:
                workers = [threading.Thread(target=lambda n=n: [host.LOG(f'w{n}') for _ in range(50)]) for n in range(4)]
                [w.start() for w in workers]; [w.join() for w in workers]
                lines = host.LOG_PATH.read_text().splitlines()
                self.assertEqual(len(lines), 200)
                if os.name != 'nt':
                    self.assertEqual(host.LOG_PATH.stat().st_mode & 0o777, 0o600)
            finally:
                host.LOG_PATH = original


if __name__ == '__main__':
    unittest.main()
