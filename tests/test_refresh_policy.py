"""Quota polling follows activity: fast while you use an AI with a low quota, slow when idle."""
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import aim_host as host
import refresh_policy
from refresh_policy import AdaptiveRefresh, effective_interval, lowest_remaining

LOW = refresh_policy.LOW_PERCENT
FAST = refresh_policy.FAST_SECONDS
ACTIVE = refresh_policy.ACTIVE_SECONDS


def quota(*remaining, provider='codex'):
    return {provider: {'at': 1, 'windows': [{'title': 'W', 'remaining': value, 'window': 300, 'reset_at': None}
                                            for value in remaining]}}


class EffectiveIntervalTests(unittest.TestCase):
    def test_idle_or_unknown_activity_keeps_the_configured_interval(self):
        for idle in (None, ACTIVE + 1, 10_000):
            self.assertEqual(effective_interval(240, LOW - 5, idle), 240)

    def test_activity_with_a_comfortable_quota_keeps_the_configured_interval(self):
        self.assertEqual(effective_interval(240, LOW + 1, 5), 240)
        self.assertEqual(effective_interval(240, None, 5), 240)

    def test_activity_with_a_low_quota_polls_faster(self):
        self.assertEqual(effective_interval(240, LOW, 5), FAST)
        self.assertEqual(effective_interval(240, 0, ACTIVE), FAST)

    def test_a_shorter_configured_interval_is_never_lengthened(self):
        self.assertEqual(effective_interval(30, 0, 5), 30)
        self.assertEqual(effective_interval(15, 0, 5), 15)


class LowestRemainingTests(unittest.TestCase):
    def test_lowest_window_across_providers_decides(self):
        data = {**quota(80, 40), **quota(55, 12, provider='zcode')}
        self.assertEqual(lowest_remaining(data), 12)

    def test_no_data_is_unknown_rather_than_zero(self):
        for empty in (None, {}, {'codex': {'at': 1, 'windows': []}}):
            self.assertIsNone(lowest_remaining(empty))


class FakeTokens:
    last_use = None


class AdaptiveRefreshTests(unittest.TestCase):
    def setUp(self):
        self.now = 1000.0
        patcher = patch.object(refresh_policy.time, 'monotonic', side_effect=lambda: self.now)
        patcher.start(); self.addCleanup(patcher.stop)
        self.tokens = FakeTokens(); self.health = Mock(); self.health.data = {}
        self.policy = AdaptiveRefresh(240, self.health, self.tokens)

    def test_interval_reads_live_quota_and_recent_use(self):
        self.health.data['quota'] = quota(10)
        self.assertEqual(self.policy.interval(), 240)            # never used
        self.tokens.last_use = self.now - 20
        self.assertEqual(self.policy.interval(), FAST)           # working with a low quota
        self.now += ACTIVE + 1
        self.assertEqual(self.policy.interval(), 240)            # activity went quiet

    def test_deadline_is_measured_from_the_start_of_the_cycle(self):
        self.assertEqual(self.policy.deadline(), float('inf'))   # no cycle running
        self.policy.cycle_started = 900.0
        self.assertEqual(self.policy.deadline(), 900.0 + 240)

    def test_base_follows_a_saved_configuration_change(self):
        self.policy.base = 120
        self.assertEqual(self.policy.interval(), 120)


class WaitShorteningTests(unittest.TestCase):
    """wait_connected re-checks while waiting: work that starts mid-wait must not wait out 4 minutes."""
    def setUp(self):
        self.clock = {'now': 100.0}
        for module in (host.time, refresh_policy.time):
            patcher = patch.object(module, 'monotonic', side_effect=lambda: self.clock['now'])
            patcher.start(); self.addCleanup(patcher.stop)
        self.tokens = FakeTokens(); self.health = Mock()
        self.health.data = {'quota': quota(10)}
        self.panel = Mock(); self.panel.refresh_request_id = None
        self.panel.refresh_policy = AdaptiveRefresh(240, self.health, self.tokens)

    def sleep(self, seconds):
        self.clock['now'] += seconds
        if self.clock['now'] >= self.activity_at:
            self.tokens.last_use = self.clock['now'] - 1

    def run_wait(self, seconds, minimum_wait=0, activity_at=float('inf')):
        self.activity_at = activity_at
        with patch.object(host.time, 'sleep', side_effect=self.sleep):
            host.wait_connected(self.panel, seconds, minimum_wait=minimum_wait)
        return self.clock['now']

    def test_wait_ends_early_when_use_starts_with_a_low_quota(self):
        self.panel.refresh_policy.cycle_started = 100.0
        end = self.run_wait(240, minimum_wait=15, activity_at=130)
        self.assertEqual(end, 100.0 + FAST)

    def test_idle_wait_runs_the_full_interval(self):
        self.panel.refresh_policy.cycle_started = 100.0
        self.assertEqual(self.run_wait(240, minimum_wait=15), 340.0)

    def test_the_polling_cooldown_still_applies(self):
        self.panel.refresh_policy.cycle_started = 0.0            # fast deadline already in the past
        self.tokens.last_use = 99.0
        self.assertEqual(self.run_wait(240, minimum_wait=15), 115.0)

    def test_a_panel_without_a_policy_behaves_as_before(self):
        self.panel.refresh_policy = None
        self.assertEqual(self.run_wait(25), 125.0)


if __name__ == '__main__':
    unittest.main()
