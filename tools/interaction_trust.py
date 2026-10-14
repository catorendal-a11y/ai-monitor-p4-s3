"""Explicit enrollment storage, encrypted with Windows current-user DPAPI. No network access."""
import base64
import ctypes
from ctypes import wintypes as w
import hashlib
import json
import os
from pathlib import Path
import secrets
from interaction_auth import TrustRecord
from permission_ipc import strict_json


def protect(data, entropy, decrypt=False):
    if os.name != 'nt': raise OSError('USB permission trust storage requires Windows')
    if not isinstance(data, bytes) or not 0 < len(data) <= 4096:
        raise ValueError('Invalid trust data size')
    if not isinstance(entropy, bytes) or len(entropy) != 32:
        raise ValueError('Invalid trust storage context')
    class Blob(ctypes.Structure):
        _fields_ = [('size', w.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    source_buffer = ctypes.create_string_buffer(data)
    entropy_buffer = ctypes.create_string_buffer(entropy)
    source = Blob(len(data), ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_ubyte)))
    extra = Blob(len(entropy), ctypes.cast(entropy_buffer, ctypes.POINTER(ctypes.c_ubyte)))
    result = Blob()
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.POINTER(Blob),
                         ctypes.c_void_p, ctypes.c_void_p, w.DWORD, ctypes.POINTER(Blob)]
    # UI_FORBIDDEN only: deliberately do not use LOCAL_MACHINE or prompt dialogs.
    if not function(ctypes.byref(source), None, ctypes.byref(extra), None, None, 1, ctypes.byref(result)):
        raise OSError('Current-user trust storage unavailable')
    try:
        if not result.data or not 0 < result.size <= 8192: raise ValueError('Invalid protected trust size')
        return ctypes.string_at(result.data, result.size)
    finally:
        if result.data:
            ctypes.memset(result.data, 0, result.size)
            kernel.LocalFree(ctypes.cast(result.data, ctypes.c_void_p))
        ctypes.memset(source_buffer, 0, len(source_buffer))


class TrustStore:
    def __init__(self, root):
        self.root = Path(root).resolve()
        tools = self.root / 'tools'
        if tools.is_symlink() or tools.resolve().parent != self.root or not tools.is_dir():
            raise ValueError('Invalid trust storage directory')
        self.path = tools / 'permission-trust.json'
        self.entropy = hashlib.sha256(b'AI Monitor USB trust v1\0' + str(self.root).casefold().encode()).digest()

    def load(self):
        if self.path.is_symlink(): raise ValueError('Invalid trust storage file')
        if not self.path.exists(): return None
        with self.path.open('rb') as source: raw = source.read(4097)
        envelope = strict_json(raw)
        if (not isinstance(envelope, dict) or set(envelope) != {'schema', 'encrypted'}
                or type(envelope['schema']) is not int or envelope['schema'] != 1
                or not isinstance(envelope['encrypted'], str)):
            raise ValueError('Invalid protected trust record')
        encrypted = base64.b64decode(envelope['encrypted'], validate=True)
        record = strict_json(protect(encrypted, self.entropy, decrypt=True))
        if (not isinstance(record, dict) or set(record) != {'schema', 'deviceId', 'key'}
                or type(record['schema']) is not int or record['schema'] != 1
                or not isinstance(record['key'], str) or len(record['key']) != 64):
            raise ValueError('Invalid enrolled device record')
        return TrustRecord(record['deviceId'], bytes.fromhex(record['key']))

    def save(self, record):
        if not isinstance(record, TrustRecord) or self.path.is_symlink():
            raise ValueError('Invalid enrolled device record')
        raw = json.dumps(dict(schema=1, deviceId=record.device_id, key=record.key.hex()), separators=(',', ':')).encode()
        encrypted = base64.b64encode(protect(raw, self.entropy)).decode('ascii')
        payload = json.dumps(dict(schema=1, encrypted=encrypted), separators=(',', ':')).encode()
        if len(payload) > 4096: raise ValueError('Protected trust record too large')
        temporary = self.path.with_name('permission-trust.' + secrets.token_hex(16) + '.tmp')
        created = False
        try:
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            created = True
            with os.fdopen(descriptor, 'wb') as output:
                output.write(payload); output.flush(); os.fsync(output.fileno())
            os.replace(temporary, self.path)
        finally:
            if created: temporary.unlink(missing_ok=True)

    def forget(self):
        if self.path.is_symlink(): raise ValueError('Invalid trust storage file')
        self.path.unlink(missing_ok=True)
