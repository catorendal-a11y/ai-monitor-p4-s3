"""Serial-owner lifecycle for explicit USB permissions; no automatic activation or port open."""
from pathlib import Path
import secrets
import time
from interaction_auth import TrustRecord
from interaction_trust import TrustStore
from permission_broker import Broker, TrustedContext
from permission_service import PermissionService
from usb_interaction import UsbPermissionClient


class PermissionRuntime:
    """A local validation gate is required in addition to the user's opt-in.

    No wire/config field can replace that gate. Production startup must not instantiate an
    enabled runtime until physical enrollment and final device/UI gates have been validated.
    All methods run on the existing serial owner; only PermissionService owns an IPC thread.
    """
    def __init__(self, root, validation_gate, clock=time.monotonic):
        if not callable(validation_gate):
            raise ValueError('A local permission validation gate is required')
        self.root = Path(root).resolve()
        self.validation_gate = validation_gate
        self.clock = clock
        self.instance = secrets.token_hex(16)
        self.broker = Broker(clock)
        self.client = None
        self.panel = None
        self._attempted_panel = None
        self.opted_in = False
        self._shutdown_failed = False
        self.state = 'disabled'

    def configure(self, opted_in):
        if type(opted_in) is not bool:
            raise ValueError('USB permission opt-in must be true or false')
        if opted_in != self.opted_in:
            self.close()
            self._attempted_panel = None
        self.opted_in = opted_in
        if not opted_in:
            self.state = 'disabled'

    def attach(self, panel):
        if self._shutdown_failed:
            self.state = 'unavailable'
            return False
        if not self.opted_in or self.validation_gate() is not True:
            self.close()
            self.state = 'disabled'
            return False
        if panel is self.panel and self.client is not None:
            return True
        self.close()
        if self._shutdown_failed:
            self.state = 'unavailable'
            return False
        # No automatic retry within the same connection after an ambiguous failure.
        if panel is None or panel is self._attempted_panel:
            return False
        self._attempted_panel = panel
        candidate = None
        try:
            record = TrustStore(self.root).load()
            if not isinstance(record, TrustRecord):
                self.state = 'not_enrolled'
                return False
            candidate = UsbPermissionClient(panel, record, self.instance, opted_in=True,
                service_factory=lambda context: PermissionService(
                    self.root, context, self.clock, broker=self.broker), clock=self.clock)
            candidate.open()
            self.client = candidate
            self.panel = panel
            self.state = 'connected'
            return True
        except (ValueError, OSError, TimeoutError, RuntimeError):
            if candidate is not None:
                self._retire(candidate)
            self.state = 'unavailable'
            return False  # No keys, arguments or exception strings enter logs/status.

    def pump(self):
        if not self.opted_in or self.validation_gate() is not True:
            self.close()
            return
        if self.client is None:
            return
        self.client.pump()
        if self.client.auth is None:
            self.close()

    def handle_event(self, message):
        if not isinstance(message, dict) or message.get('type') != 'interaction_packet':
            return False
        if self.client is not None:
            consumed = self.client.handle_event(message)
            if self.client.auth is None:
                self.close()
            return consumed  # A synchronous authenticated exchange must receive its own packet.
        return True  # Old packets can neither establish trust nor leak into normal replies.

    def close(self):
        candidate, self.client = self.client, None
        self.panel = None
        if candidate is not None:
            self._retire(candidate)
        # Cancel pending authority but retain the consumed ID/nonce ledger for this host instance.
        self.broker.update_context(TrustedContext())
        self.state = 'disabled' if not self.opted_in else 'unavailable'

    def _retire(self, candidate):
        try: candidate.close()
        except (ValueError, OSError, TimeoutError, RuntimeError): self._shutdown_failed = True
        if getattr(candidate, 'shutdown_complete', True) is False:
            self._shutdown_failed = True
