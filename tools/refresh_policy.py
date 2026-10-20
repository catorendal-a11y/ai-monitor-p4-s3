"""When to poll provider quota next. Pure timing policy: no I/O, no provider or USB access.

The configured interval stays the ceiling. While you are using an AI and a quota window is
low, the number changes quickly and a value several minutes old misleads, so polling speeds up.
"""
import time

ACTIVE_SECONDS = 300   # token use this recently counts as working
LOW_PERCENT = 30       # same threshold the terminal colors amber
FAST_SECONDS = 60      # polite floor for the fast mode; the configured minimum is 15


def effective_interval(base, remaining, idle_seconds):
    """Seconds between provider polls for the current situation."""
    if idle_seconds is None or idle_seconds > ACTIVE_SECONDS:
        return base
    if remaining is None or remaining > LOW_PERCENT:
        return base
    return min(base, FAST_SECONDS)


def lowest_remaining(quota):
    """Lowest percent left over every window of every provider, or None when nothing is known."""
    values = [window['remaining'] for entry in (quota or {}).values() for window in entry.get('windows', ())]
    return min(values) if values else None


class AdaptiveRefresh:
    """Attached to the panel; wait_connected re-reads it so a wait can end early."""
    def __init__(self, base, health, tokens):
        self.base = base
        self.health = health
        self.tokens = tokens
        self.cycle_started = None

    def interval(self):
        last_use = self.tokens.last_use
        idle = None if last_use is None else time.monotonic() - last_use
        return effective_interval(self.base, lowest_remaining(self.health.data.get('quota')), idle)

    def deadline(self):
        """Absolute monotonic time of the next poll; unbounded while no cycle is running."""
        if self.cycle_started is None:
            return float('inf')
        return self.cycle_started + self.interval()
