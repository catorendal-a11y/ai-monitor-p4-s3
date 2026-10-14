"""Bounded inputs and explicit trust boundaries for the local companion."""
import json
import os
from pathlib import Path
import re
import ssl
import sys
import unicodedata
import urllib.error
import urllib.request

PROVIDER_ENDPOINTS = frozenset((
    'https://chatgpt.com/backend-api/wham/usage',
    'https://api.z.ai/api/monitor/usage/quota/limit',
))
PROJECT = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[1]


class RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never copy Authorization to another origin or an HTTP downgrade.
        raise urllib.error.HTTPError(req.full_url, code, 'Provider redirect blocked', headers, fp)


def open_provider_request(request):
    if request.full_url not in PROVIDER_ENDPOINTS:
        raise ValueError('Unsupported provider endpoint')
    context = ssl.create_default_context()
    opener = urllib.request.build_opener(RejectRedirects(), urllib.request.HTTPSHandler(context=context))
    return opener.open(request, timeout=20)


def allowed_executable(path):
    path = Path(path)
    if not path.is_absolute(): return False
    resolved = path.resolve()
    return resolved.parent != Path.cwd().resolve() and not resolved.is_relative_to(PROJECT) and path.is_file()


def path_executable(name):
    # Do not use the Windows implicit current-directory executable search.
    if os.name == 'nt':
        # npm also installs an extensionless POSIX shell shim. Windows cannot
        # execute it; selecting it hides a usable .cmd/native installation.
        suffixes = ('',) if Path(name).suffix.lower() in ('.exe', '.cmd', '.bat') else ('.exe', '.cmd', '.bat')
    else:
        suffixes = ('',)
    for item in os.environ.get('PATH', '').split(os.pathsep):
        directory = Path(item)
        if not item or not directory.is_absolute(): continue
        for suffix in suffixes:
            path = directory / (name + suffix)
            if allowed_executable(path) and (os.name == 'nt' or os.access(path, os.X_OK)):
                return str(path)
    return None


def powershell_executable():
    return str(Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe')


def serial_port(value):
    if not isinstance(value, str): raise ValueError('Invalid serial port')
    value = value.strip()
    if value == 'auto': return value
    if len(value) > 240 or not re.fullmatch(r'COM[1-9][0-9]*|/dev/[A-Za-z0-9._/-]+', value, re.I):
        raise ValueError('Use auto, a COM port or a /dev/ serial device')
    if any(part in ('', '.', '..') for part in value.split('/')[1:]):
        raise ValueError('Invalid serial device path')
    return value


def read_local_json(path, max_bytes=65536):
    with path.open('rb') as source:
        raw = source.read(max_bytes + 1)
    if len(raw) > max_bytes: raise ValueError('Local JSON exceeds size limit')
    try: return json.loads(raw.decode('utf-8-sig'))
    except RecursionError: raise ValueError('Local JSON nesting exceeds parser limit') from None


def safe_text(value, limit=512):
    return ''.join(character if not unicodedata.category(character).startswith('C') else ' '
                   for character in str(value)[:limit])
