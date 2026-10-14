"""Bounded permission authority; no transport, provider, persistence or automatic decisions."""
from dataclasses import dataclass, replace
import re
import threading
import time


def _hex(value, length):
    return isinstance(value, str) and re.fullmatch(r'[0-9a-f]{%d}' % length, value) is not None


@dataclass(frozen=True)
class TrustedContext:
    """Created only by local enrollment/connection code, never from a wire object."""
    opted_in: bool = False
    connected: bool = False
    host_instance: str = ''
    device_id: str = ''
    session_id: str = ''
    authenticated: bool = False

    def eligible(self):
        return (self.opted_in is True and self.connected is True and self.authenticated is True
                and _hex(self.host_instance, 32) and _hex(self.device_id, 32)
                and _hex(self.session_id, 64))


@dataclass(frozen=True)
class Request:
    request_id: str
    nonce: str
    revision: int
    tool: str
    hint: str
    expires_at: float
    context: TrustedContext


def validate_request(message, context, now):
    fields = {'schema', 'instance', 'requestId', 'nonce', 'revision', 'tool', 'hint', 'expiresInMs'}
    if (not isinstance(message, dict) or set(message) != fields
            or type(message['schema']) is not int or message['schema'] != 1
            or message['instance'] != context.host_instance
            or not _hex(message['requestId'], 32) or not _hex(message['nonce'], 64)
            or type(message['revision']) is not int or message['revision'] != 1
            or not isinstance(message['tool'], str)
            or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', message['tool'])
            or not isinstance(message['hint'], str) or not 1 <= len(message['hint']) <= 320
            or any(not 32 <= ord(c) <= 126 for c in message['hint'])
            or type(message['expiresInMs']) is not int or not 1 <= message['expiresInMs'] <= 25000):
        raise ValueError('Invalid permission request')
    return Request(message['requestId'], message['nonce'], message['revision'], message['tool'],
                   message['hint'], now + message['expiresInMs'] / 1000, context)


class Broker:
    """One pending request, exact session matching, one response, fail closed on any change.

    Adapters must authenticate the IPC peer and USB decision before calling submit/decide.
    No JSON flag establishes trust. A full replay ledger disables this host instance rather
    than evicting old identities that could then be approved again. Restart creates a new
    host instance. Tool arguments exist only while pending, never in the consumed ledger.
    """
    def __init__(self, clock=time.monotonic, ledger_limit=1024):
        if type(ledger_limit) is not int or not 1 <= ledger_limit <= 4096:
            raise ValueError('Invalid permission ledger bound')
        self._clock = clock
        self._limit = ledger_limit
        self._lock = threading.Lock()
        self._context = TrustedContext()
        self._pending = None
        self._consumed_ids = set()
        self._consumed_nonces = set()

    def update_context(self, context):
        if not isinstance(context, TrustedContext):
            raise ValueError('Permission context must be locally constructed')
        with self._lock:
            if context != self._context or not context.eligible():
                self._pending = None
            self._context = context

    def submit(self, message):
        with self._lock:
            self._expire()
            if not self._context.eligible() or self._pending is not None:
                raise ValueError('Permission channel unavailable or busy')
            request = validate_request(message, self._context, self._clock())
            if (request.request_id in self._consumed_ids or request.nonce in self._consumed_nonces
                    or len(self._consumed_ids) >= self._limit):
                raise ValueError('Permission request already consumed or ledger full')
            # Reserve upon receipt, including requests later cancelled or ambiguously sent.
            self._consumed_ids.add(request.request_id)
            self._consumed_nonces.add(request.nonce)
            self._pending = request
            return replace(request)

    def current(self):
        with self._lock:
            self._expire()
            return replace(self._pending) if self._pending else None

    def cancel(self):
        with self._lock:
            self._pending = None

    def decide(self, request_id, nonce, revision, decision, context):
        """Final host gate. Call only with an authenticated device decision, never IPC input."""
        with self._lock:
            self._expire()
            request = self._pending
            self._pending = None  # Consume on failure too; never retry an ambiguous approval.
            if (request is None or context != self._context or context != request.context
                    or not context.eligible() or request_id != request.request_id
                    or nonce != request.nonce or type(revision) is not int
                    or revision != request.revision or decision not in ('allow', 'deny')):
                raise ValueError('Stale or uncorrelated permission decision')
            return dict(schema=1, instance=context.host_instance, requestId=request.request_id,
                        nonce=request.nonce, revision=request.revision, decision=decision)

    def _expire(self):
        if self._pending and (self._clock() >= self._pending.expires_at
                              or not self._context.eligible()):
            self._pending = None
