"""Official Codex CLI onboarding and read-only account rate limits."""
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time
from process_runtime import start_child, stop_child
from host_security import allowed_executable, path_executable, powershell_executable
from project_version import HOST_VERSION, numeric_version

MAX_REPLY_BYTES = 65536


def codex_home():
    return Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex').expanduser()


def codex_command():
    candidates = [path_executable('codex.exe'), path_executable('codex')]
    install = os.environ.get('CODEX_INSTALL_DIR')
    if install: candidates += [str(Path(install) / ('codex.exe' if os.name == 'nt' else 'codex'))]
    if os.name == 'nt':
        local = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local'))
        candidates += [str(local / 'Programs/OpenAI/Codex/bin/codex.exe')]
        # Explorer-launched apps may inherit PATH from before CLI installation.
        # Search only known per-user install locations, never the working folder.
        native = local / 'OpenAI/Codex/bin'
        try:
            versions = sorted(native.glob('*/codex.exe'), key=lambda item: item.stat().st_mtime, reverse=True)[:32]
            candidates += [str(item) for item in versions]
        except OSError:
            pass
        roaming = Path(os.environ.get('APPDATA', Path.home() / 'AppData/Roaming'))
        candidates += [str(roaming / 'npm/codex.cmd')]
    else:
        candidates += [str(Path.home() / '.local/bin/codex')]
    for candidate in candidates:
        if not candidate or not allowed_executable(candidate): continue
        path = Path(candidate)
        if path.suffix.lower() in ('.cmd','.bat'):
            script = path.parent / 'node_modules/@openai/codex/bin/codex.js'
            node = path_executable('node.exe') or path_executable('node')
            if node and script.is_file(): return [node, str(script)]
            continue
        return [str(path)]
    return None


def install_command():
    if os.name == 'nt':
        return [powershell_executable(),'-NoProfile','-ExecutionPolicy','Bypass','-Command',
                'irm https://chatgpt.com/codex/install.ps1 | iex']
    import shlex
    shell, curl = path_executable('sh'), path_executable('curl')
    if not shell or not curl: raise RuntimeError('Official installation requires an installed shell and curl.')
    return [shell,'-c',shlex.quote(curl) + " --proto '=https' --proto-redir '=https' -fsSL https://chatgpt.com/codex/install.sh | " + shlex.quote(shell)]


def setup_codex(ask=input):
    command = codex_command()
    if not command:
        print('Codex CLI is missing. The official OpenAI installer prepares it for this account.')
        if ask('Install the official Codex CLI now? [y/N]: ').strip().lower() not in ('y','yes'):
            print('Skipped. Codex remains selected; use Provider integration help to finish setup.')
            return False
        if subprocess.run(install_command(), check=False).returncode:
            raise RuntimeError('Official Codex installation failed. Check the connection and retry setup.')
        command = codex_command()
        if not command: raise RuntimeError('Codex was not found after installation. Restart the menu and retry.')
    # Do not copy or echo CLI status output; credentials belong to the official client.
    try:
        status = subprocess.run(command + ['login','status'], stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15, check=False)
    except subprocess.TimeoutExpired:
        raise RuntimeError('Codex login status timed out. Open the official CLI and finish sign-in, then retry.') from None
    if status.returncode:
        print('Codex needs sign-in. Use your own ChatGPT account in the official browser/CLI flow.')
        if ask('Open official Codex sign-in now? [y/N]: ').strip().lower() not in ('y','yes'):
            print('Skipped. Codex remains selected; no other provider was enabled.')
            return False
        # Interactive, inherited console. Never read a password/token from the monitor UI.
        if subprocess.run(command + ['login'], check=False).returncode:
            raise RuntimeError('Codex sign-in did not finish. Retry through Provider integration help.')
    print('Codex CLI is prepared. Quota requires a ChatGPT-backed login; API-key-only mode has no plan quota here.')
    print('Existing account storage and global Codex settings were preserved.')
    return True


def read_rate_limits(command, timeout=20):
    return _read_app_server(command,'account/rateLimits/read',None,timeout)


def read_hook_status(command, cwd, timeout=10):
    """Read-only inventory; no thread/model requests or hook-trust/config writes."""
    path=Path(cwd)
    if not path.is_absolute():raise ValueError('Hook diagnostics require an absolute working directory')
    return _read_app_server(command,'hooks/list',{'cwds':[str(path)]},timeout)


def _read_app_server(command, method, params, timeout):
    if method not in ('account/rateLimits/read','hooks/list'):
        raise ValueError('Unsupported read-only Codex diagnostic')
    process = start_child(command + ['app-server'], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    replies = queue.Queue(maxsize=64)
    def read():
        try:
            while True:
                raw = process.stdout.readline(MAX_REPLY_BYTES + 1)
                if not raw: break
                if len(raw) > MAX_REPLY_BYTES: break
                try: message = json.loads(raw)
                except (ValueError, UnicodeError): continue
                if isinstance(message, dict):
                    try: replies.put_nowait(message)
                    except queue.Full: break
        except OSError:
            pass
        finally:
            try: replies.put_nowait(None)
            except queue.Full: pass
    worker = threading.Thread(target=read, daemon=True); worker.start()
    deadline = time.monotonic() + timeout
    def send(message):
        process.stdin.write(json.dumps(message).encode() + b'\n'); process.stdin.flush()
    def response(identifier):
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0: raise TimeoutError('Codex account request timed out')
            try: message = replies.get(timeout=remaining)
            except queue.Empty: raise TimeoutError('Codex account request timed out') from None
            if message is None: raise RuntimeError('Codex app-server stopped')
            if message.get('id') != identifier: continue
            if 'error' in message: raise RuntimeError('Codex account rate limits unavailable; check CLI login/version')
            if not isinstance(message.get('result'), dict): raise ValueError('Invalid Codex account result')
            return message['result']
    try:
        send({'method':'initialize','id':1,'params':{'clientInfo':{'name':'ai_monitor_p4','title':'LimitBuddy','version':numeric_version(HOST_VERSION)}}})
        response(1); send({'method':'initialized','params':{}})
        request={'method':method,'id':2}
        if params is not None:request['params']=params
        send(request)
        return response(2)
    finally:
        stop_child(process)
        worker.join(timeout=1)
        for stream in [process.stdin, process.stdout]:
            if stream:
                try: stream.close()
                except OSError: pass
