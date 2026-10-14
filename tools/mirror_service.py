"""Fixed-path capture mailbox. No caller paths, network, commands or touch control."""
import base64
import json
import math
from functools import lru_cache
import os
from pathlib import Path
import re
import secrets
import tempfile
import time
from host_security import read_local_json
from usb_mirror import UsbMirrorClient, BYTES


@lru_cache(maxsize=16)
def directory(root):
    path = Path(root) / 'tools' / 'screen-capture'
    if path.is_symlink() or path.parent.is_symlink(): raise ValueError('Invalid capture directory')
    path.mkdir(mode=0o700, exist_ok=True)
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes as w
        from permission_ipc import current_sid
        advapi = ctypes.WinDLL('advapi32', use_last_error=True)
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        descriptor = ctypes.c_void_p()
        advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [w.LPCWSTR, w.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p]
        advapi.SetFileSecurityW.argtypes = [w.LPCWSTR, w.DWORD, ctypes.c_void_p]
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        sddl = 'D:P(A;OICI;FA;;;' + current_sid() + ')'
        if not advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, ctypes.byref(descriptor), None): raise ctypes.WinError(ctypes.get_last_error())
        try:
            if not advapi.SetFileSecurityW(str(path), 0x80000004, descriptor): raise ctypes.WinError(ctypes.get_last_error())
        finally: kernel.LocalFree(descriptor)
    else: os.chmod(path, 0o700)
    return path


def write(path, value):
    if path.is_symlink() or path.parent.is_symlink(): raise ValueError('Invalid capture file')
    descriptor, name = tempfile.mkstemp(prefix='.capture-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='ascii') as stream:
            json.dump(value, stream, separators=(',', ':'), allow_nan=False)
        os.replace(name, path)
    finally:
        if os.path.exists(name): os.unlink(name)


def request(root):
    path = directory(root)
    nonce = secrets.token_hex(16)
    (path / 'response.json').unlink(missing_ok=True)
    write(path / 'request.json', dict(nonce=nonce, operation='capture', at=time.time()))
    return nonce


def cancel(root, nonce):
    try: path = directory(root)
    except (OSError, ValueError): return
    try:
        if read_local_json(path / 'request.json', 512).get('nonce') == nonce:
            (path / 'request.json').unlink(missing_ok=True)
    except (OSError, ValueError, AttributeError): pass
    try:
        response = path / 'response.json'
        if not response.is_symlink() and read_local_json(response, 1030000).get('nonce') == nonce:
            response.unlink(missing_ok=True)
    except (OSError, ValueError, AttributeError): pass


def receive(root, nonce):
    path = directory(root) / 'response.json'
    if not path.exists(): return None
    if path.is_symlink() or path.parent.is_symlink(): raise ValueError('Invalid capture file')
    data = read_local_json(path, 1030000)
    path.unlink(missing_ok=True)
    if (not isinstance(data, dict) or data.get('nonce') != nonce or
        set(data) not in ({'nonce', 'at', 'pixels'}, {'nonce', 'at', 'error'})): raise ValueError('Capture response changed')
    if data.get('error'): raise RuntimeError('Device capture unavailable. Connect the host and try again.')
    stamp = data.get('at')
    if type(stamp) not in (int, float) or not math.isfinite(stamp) or not 0 <= time.time() - stamp <= 60:
        raise ValueError('Stale capture response')
    try: pixels = base64.b64decode(data['pixels'], validate=True)
    except (ValueError, KeyError, TypeError): raise ValueError('Invalid capture pixels') from None
    if len(pixels) != BYTES: raise ValueError('Incomplete capture image')
    return pixels, stamp


class MirrorService:
    def __init__(self, root):
        self.root = root
        self.path = Path(root) / 'tools' / 'screen-capture'
        self.busy = False
        self.client = None
        self.nonce = None
        self.handled = None
        self.last_cleanup = 0

    def _current(self):
        path = self.path / 'request.json'
        if path.is_symlink() or path.parent.is_symlink(): raise ValueError('Invalid capture file')
        data = read_local_json(path, 512)
        if (not isinstance(data, dict) or set(data) != {'nonce', 'operation', 'at'} or
            not isinstance(data['nonce'], str) or not re.fullmatch('[0-9a-f]{32}', data['nonce']) or
            data['operation'] != 'capture' or type(data['at']) not in (int, float) or
            not math.isfinite(data['at']) or not 0 <= time.time() - data['at'] <= 110): raise ValueError('Invalid capture request')
        return data['nonce']

    def pump(self, panel):
        if self.busy: return
        self.busy = True
        try: self._pump(panel)
        finally: self.busy = False

    def _publish(self, value):
        try: write(self.path / "response.json", value)
        except (OSError, ValueError): pass  # Optional capture storage never breaks monitoring.

    def _expire_response(self):
        now = time.monotonic()
        if now - self.last_cleanup < 5: return
        self.last_cleanup = now
        response = self.path / 'response.json'
        try:
            if response.is_symlink() or response.parent.is_symlink(): return
            # Stat-only retention avoids re-reading a megabyte every host tick.
            if now and time.time() - response.stat().st_mtime > 60:
                response.unlink(missing_ok=True)
        except OSError: pass

    def _pump(self, panel):
        self._expire_response()
        try: nonce = self._current()
        except (OSError, ValueError): nonce = None
        if self.client and nonce != self.nonce:
            self.client.cancel(); self.client = None
        if nonce is None or nonce == self.handled: return
        if self.client is None:
            self.nonce = nonce
            capability = getattr(panel, "info", {}).get("mirrorProtocol")
            if type(capability) is not int or capability != 1:
                self._publish(dict(nonce=nonce, at=time.time(), error="unavailable"))
                self.handled = nonce
                return
            self.client = UsbMirrorClient(panel, nonce)
        deadline = time.monotonic() + .2
        try:
            for _ in range(32):
                if self.client.step():
                    self._publish(dict(nonce=nonce, at=self.client.captured_at,
                        pixels=base64.b64encode(self.client.pixels).decode('ascii')))
                    self.handled = nonce; self.client = None
                    return
                if self.client.waiting or time.monotonic() >= deadline: return
        except (TimeoutError, ValueError, RuntimeError):
            self.client.cancel(); self.client = None; self.handled = nonce
            self._publish(dict(nonce=nonce, at=time.time(), error='unavailable'))

    def close(self):
        # The caller closes the serial connection; no writes after shutdown.
        if self.client: self.client.pixels.clear()
        self.client = None
        if self.nonce: cancel(self.root, self.nonce)
