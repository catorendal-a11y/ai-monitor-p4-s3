"""Authenticated permission adapter for the existing Panel serial owner. Never opens a port."""
import json
import time
from interaction_auth import SessionHost, number
from permission_broker import TrustedContext


class UsbPermissionClient:
    def __init__(self, panel, trust, instance, opted_in=False, service_factory=None, clock=time.monotonic):
        if opted_in is not True:
            raise ValueError('Physical USB permissions require explicit opt-in')
        self.panel = panel; self.trust = trust; self.instance = instance; self.clock = clock
        self.service_factory = service_factory; self.service = None; self.auth = None
        self._request = None; self._waiting = False; self._last_heartbeat = 0
        self.shutdown_complete = True

    def open(self):
        self.close()
        if not self.shutdown_complete:
            raise RuntimeError('Previous permission service did not stop')
        info = self.panel.info
        if (not isinstance(info, dict) or type(info.get('interactionProtocol')) is not int
                or info['interactionProtocol'] != 1 or not number(info.get('bootId'))):
            raise ValueError('Display does not support authenticated USB interactions')
        self.auth = SessionHost(self.trust, self.instance, info['bootId'], self.clock)
        try:
            self._write(self.auth.hello())
            command = self.auth.challenge(self.panel.wait_for('interaction_challenge', seconds=1))
            self._write(command)
            self.auth.ready(self.panel.wait_for('interaction_ready', seconds=1))
            self._last_heartbeat = self.clock()
            if self.service_factory:
                self.service = self.service_factory(self.context())
                self.service.start()
        except (ValueError, OSError, TimeoutError, RuntimeError):
            self.close(); raise

    def context(self):
        alive = self.auth is not None and self.auth.alive()
        return TrustedContext(opted_in=True, connected=alive, host_instance=self.instance,
                              device_id=self.trust.device_id, session_id=self.auth.session if alive else '',
                              authenticated=alive)

    def pump(self):
        """Serial-owner calls frequently while waiting/polling; no provider or model operation."""
        if self.auth is None: return
        try:
            context = self.context()
            if not context.eligible():
                self.close(); return
            if self.service:
                self.service.update_context(context)
                request = self.service.broker.current()
                if self._request and (request is None or request != self._request):
                    previous = self._request
                    self._exchange(dict(kind='cancel', requestId=previous.request_id,
                                        nonce=previous.nonce, revision=previous.revision), 'cancelled')
                    self._request = None
                if request and self._request is None:
                    remaining = min(25000, int((request.expires_at - self.clock()) * 1000))
                    if remaining <= 0 or request.context != context:
                        self.service.broker.cancel(); return
                    self._request = request
                    received = self._exchange(dict(kind='request', requestId=request.request_id,
                        nonce=request.nonce, revision=request.revision, tool=request.tool, hint=request.hint,
                        expiresInMs=remaining), 'received')
                    if (set(received) != {'kind', 'requestId', 'nonce', 'revision'}
                            or received['requestId'] != request.request_id or received['nonce'] != request.nonce
                            or type(received['revision']) is not int or received['revision'] != request.revision):
                        raise ValueError('Uncorrelated device receipt')
            if self.clock() - self._last_heartbeat >= 1:
                reply = self._exchange({'kind': 'heartbeat'}, 'heartbeat')
                if reply != {'kind': 'heartbeat'}: raise ValueError('Invalid interaction heartbeat')
                self._last_heartbeat = self.clock()
        except (ValueError, OSError, TimeoutError, RuntimeError):
            # Do not retry any old request/decision. The helper retains its normal PC fallback.
            self.close()

    def handle_event(self, message):
        if not isinstance(message, dict) or message.get('type') != 'interaction_packet': return False
        if self._waiting: return False  # The synchronous exchange verifies/dispatches every packet.
        if self.auth is None: return True  # Discard old packets without establishing authority.
        try:
            self._body(self.auth.decode(message))
        except (ValueError, OSError, RuntimeError):
            self.close()
        return True

    def _body(self, body):
        request = self._request
        if (not self.service or not request or set(body) != {'kind', 'requestId', 'nonce', 'revision', 'decision'}
                or body.get('kind') != 'decision' or body['requestId'] != request.request_id
                or body['nonce'] != request.nonce or type(body['revision']) is not int
                or body['revision'] != request.revision or body['decision'] not in ('allow', 'deny')):
            raise ValueError('Uncorrelated physical decision')
        context = self.context()
        if not context.eligible() or request.context != context or self.clock() >= request.expires_at:
            raise ValueError('Physical decision expired')
        self.service.resolve(body['requestId'], body['nonce'], body['revision'], body['decision'], context)

    def _exchange(self, body, kind):
        if self.auth is None: raise ValueError('Interaction session unavailable')
        self._waiting = True
        try:
            self._write(self.auth.encode(body))
            deadline = self.clock() + 2
            while self.clock() < deadline:
                message = self.panel.wait_for('interaction_packet', seconds=deadline - self.clock())
                reply = self.auth.decode(message)
                if reply.get('kind') == kind: return reply
                self._body(reply)  # An earned decision can arrive while a heartbeat is awaited.
            raise TimeoutError('Interaction response expired')
        finally:
            self._waiting = False

    def _write(self, message):
        raw = json.dumps(message, ensure_ascii=True, separators=(',', ':'), allow_nan=False)
        if len(raw) > 4095: raise ValueError('Interaction frame too large')
        self.panel.send_line(raw)

    def close(self):
        self._request = None
        if self.auth:
            # One authenticated best-effort close, without waiting or retrying. If the USB
            # link is already broken the device's authenticated lease still cancels it.
            # Never interleave a shutdown command inside an in-flight exchange.
            if not self._waiting and self.auth.alive():
                try: self._write(self.auth.encode({'kind': 'close'}))
                except (ValueError, OSError, TimeoutError, RuntimeError): pass
            self.auth.close()
        self.auth = None
        service, self.service = self.service, None
        if service:
            try:
                try: service.update_context(TrustedContext())
                finally: service.close()
            except (ValueError, OSError, RuntimeError):
                # Keep normal USB monitoring alive, but prevent creating a replacement service.
                self.shutdown_complete = False
