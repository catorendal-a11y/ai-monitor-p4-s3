"""Explicit desktop enrollment action. Scoped host pause, one serial owner, no AI hooks."""
import threading
import time
from pathlib import Path
import aim_control as control
from board_profiles import get_board
from host_security import serial_port
from interaction_trust import TrustStore
from usb_enrollment import UsbEnrollmentClient


class ComparisonPrompt:
    def __init__(self, code):
        self.code = code; self._event = threading.Event(); self._lock = threading.Lock(); self._accepted = False
    def decide(self, accepted):
        with self._lock:
            if self._event.is_set(): return
            self._accepted = accepted is True; self._event.set()
    def signal(self, seconds): return self._event.wait(seconds)
    @property
    def cancelled(self): return self._event.is_set() and not self._accepted
    def wait(self, seconds):
        ready = self._event.wait(seconds)
        with self._lock:
            if not ready:
                self._accepted = False; self._event.set()
            return ready and self._accepted


def connect_device(root, present, emit=print):
    root = Path(root).resolve(); config = control.local_config(root)
    board = get_board(config['board']); port = config.get('port')
    if not serial_port(port) or port.upper() == 'AUTO':
        raise control.SetupError('Choose an explicit USB port before connecting this PC')
    restore = bool(control.owned_hosts(root)); panel = client = prompt = None
    try:
        control.stop_host(root, emit=emit)
        if control.owned_hosts(root): raise control.SetupError('Existing host did not stop; connection cancelled')
        panel = control.host.Panel(port); panel.expected_board = board
        time.sleep(.3); panel.heartbeat()
        client = UsbEnrollmentClient(panel, TrustStore(root)); code = client.begin()
        prompt = ComparisonPrompt(code); present(prompt)
        deadline = time.monotonic() + 45
        while not prompt.signal(0):
            if time.monotonic() >= deadline:
                prompt.decide(False);break
            client.keep_alive()  # Same serial owner; no model/provider request while dialog is open.
            prompt.signal(min(.5, max(0., deadline - time.monotonic())))
        if not prompt.wait(45):
            raise control.SetupError('Code comparison cancelled or timed out; permissions remain disabled')
        client.finish(True)
        emit('PC/display connection verified and stored locally. AI permission control remains disabled.')
    except (ValueError, OSError, TimeoutError, RuntimeError) as error:
        # Only fixed user-facing errors; never log an input frame, key or trust record.
        raise control.SetupError(str(error)) from None
    finally:
        if prompt: prompt.decide(False)
        try:
            if client: client.close()
        finally:
            if panel: panel.close()
            if restore: control.start_host(root, emit=emit)
