"""Opt-in local permission IPC adapter. Not started until authenticated USB is available."""
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import psutil
from permission_broker import Broker, TrustedContext
from permission_ipc import Listener, current_sid


def pipe_name(root):
    identity = str(Path(root).resolve()).casefold() + '|' + current_sid()
    return 'ai-monitor-permission-' + hashlib.sha256(identity.encode()).hexdigest()[:32]


def verified_helper(root, pid):
    if type(pid) is not int or not 0 < pid < 2**32:
        return False
    try:
        expected = (Path(root).resolve() / 'AI-Monitor-Permission.exe')
        return not expected.is_symlink() and Path(psutil.Process(pid).exe()).resolve() == expected
    except (OSError, psutil.Error):
        return False


class PermissionService:
    """No network listener, logs, hint persistence, automatic decisions or approval retries.

    A future serial-owner adapter supplies authenticated decisions via resolve(). This service
    cannot authenticate USB itself and remains unconnected to production host startup.
    """
    def __init__(self, root, context, clock=time.monotonic, broker=None):
        if not isinstance(context, TrustedContext) or not context.eligible():
            raise ValueError('An opted-in authenticated device session is required')
        self.root = Path(root).resolve()
        tools = self.root / 'tools'
        if tools.is_symlink() or tools.resolve().parent != self.root or not tools.is_dir():
            raise ValueError('Invalid permission runtime directory')
        self._clock = clock
        self._context = context
        self._endpoint_instance = context.host_instance
        if broker is not None and not isinstance(broker, Broker):
            raise ValueError('Invalid permission broker')
        # The host owner preserves its replay ledger across USB session/service replacement.
        self.broker = broker if broker is not None else Broker(clock)
        self.broker.update_context(context)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._response = None
        self._request = None
        self._thread = None
        self._listener = None

    def start(self):
        if self._thread is not None or self._stop.is_set():
            raise ValueError('Permission service cannot be restarted')
        # Verify the hosting process as well as the helper. Developer Python is deliberately
        # unsupported here; tests exercise the isolated connection handler with fixtures.
        expected = self.root / 'AI-Monitor-Console.exe'
        if expected.is_symlink() or Path(psutil.Process().exe()).resolve() != expected:
            raise ValueError('Permission service requires the installed host executable')
        self._listener = Listener(pipe_name(self.root))
        try:
            self._publish_endpoint()
            self._thread = threading.Thread(target=self._run, name='permission-ipc', daemon=True)
            self._thread.start()
        except BaseException:
            self._listener.close(); self._listener = None
            self._remove_endpoint()
            raise

    def update_context(self, context):
        with self._lock:
            self.broker.update_context(context)
            if context != self._context or not context.eligible():
                self._response = None
                self._request = None
                self._wake.set()
            self._context = context

    def resolve(self, request_id, nonce, revision, decision, context):
        with self._lock:
            if self._stop.is_set() or self._request is None:
                raise ValueError('No pending permission')
            try:
                self._response = self.broker.decide(request_id, nonce, revision, decision, context)
            except ValueError:
                self._request = None; self._response = None; self._wake.set()
                raise
            self._wake.set()

    def close(self):
        self._stop.set()
        with self._lock:
            self.broker.cancel(); self._response = None; self._request = None; self._wake.set()
        if self._thread:
            self._thread.join(3)
            if self._thread.is_alive():
                raise RuntimeError('Permission service did not stop')
        elif self._listener:
            self._listener.close()
        self._remove_endpoint()

    def _serve(self, channel):
        """Exactly one fixed request from a kernel-verified local helper process."""
        try:
            pid = channel.peer_pid(True)
            if not verified_helper(self.root, pid):
                return
            message = channel.receive(1)
            with self._lock:
                if self._stop.is_set():
                    return
                request = self.broker.submit(message)
                self._request = request; self._response = None; self._wake.clear()
            remaining = request.expires_at - self._clock()
            while remaining > 0 and not self._wake.wait(min(remaining, .1)):
                # The helper sends one request only. EOF or additional bytes cancel, and a
                # vanished helper must not leave an actionable request on the physical UI.
                if channel.connection.poll(0) or not verified_helper(self.root, pid):
                    return
                remaining = request.expires_at - self._clock()
            with self._lock:
                # Recheck immediately before writing; disconnect/opt-out/host-instance changes
                # after a device decision must cancel rather than deliver a delayed allow.
                if (not self._stop.is_set() and self._request == request and self._response
                        and self._context == request.context and self._context.eligible()
                        and self._clock() < request.expires_at
                        and channel.peer_pid(True) == pid and verified_helper(self.root, pid)):
                    channel.send(self._response)
        except (ValueError, OSError, TimeoutError, EOFError, RecursionError):
            pass  # Empty/closed response means the helper's normal Claude dialog fallback.
        finally:
            with self._lock:
                self.broker.cancel(); self._request = None; self._response = None
            channel.close()

    def _run(self):
        try:
            while not self._stop.is_set():
                listener = self._listener
                try:
                    channel = listener.accept(.25)
                except TimeoutError:
                    continue
                self._serve(channel)
                listener.close()
                if not self._stop.is_set():
                    self._listener = Listener(pipe_name(self.root))
        except (OSError, ValueError):
            self._stop.set()
        finally:
            if self._listener: self._listener.close()
            with self._lock:
                self.broker.cancel(); self._request = None; self._response = None
            self._remove_endpoint()

    def _publish_endpoint(self):
        path = self.root / 'tools/permission-endpoint.json'
        if path.is_symlink():
            raise ValueError('Invalid permission endpoint')
        temporary = path.with_name('permission-endpoint.' + self._context.host_instance + '.tmp')
        created = False
        try:
            # Exclusive creation prevents following a planted temporary symlink.
            with temporary.open('x', encoding='ascii') as output:
                created = True
                json.dump(dict(schema=1, pid=os.getpid(), instance=self._context.host_instance), output)
            os.replace(temporary, path)
        finally:
            if created: temporary.unlink(missing_ok=True)

    def _remove_endpoint(self):
        path = self.root / 'tools/permission-endpoint.json'
        try:
            from host_security import read_local_json
            if (not path.is_symlink() and read_local_json(path, 2048)
                    == dict(schema=1, pid=os.getpid(), instance=self._endpoint_instance)):
                path.unlink()
        except (ValueError, OSError):
            pass
