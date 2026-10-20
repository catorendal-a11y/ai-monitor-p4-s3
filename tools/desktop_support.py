"""Validated native-desktop actions; no model turns or network listener."""
from pathlib import Path
import os
import queue
import subprocess
import sys
import threading
import time

import aim_control as control
from board_profiles import get_board
from host_security import safe_text, serial_port
from provider_catalog import selected_providers
from host_status import validate_options, read_status


def clear_local_history(root: Path, emit=print) -> None:
    """Stop the owned writer before clearing; restore the prior host lifecycle."""
    from usage_history import clear_history
    was_running=bool(control.owned_hosts(root))
    control.stop_host(root,emit=emit)
    try:
        clear_history(root/'tools/activity')
    finally:
        if was_running: control.start_host(root,emit=emit)
    emit('Local history cleared. Collection settings were preserved.')


def load_settings(root: Path) -> dict:
    config = control.local_config(root)
    validate_options(config)
    if type(config['interval_s']) is not int or not 15 <= config['interval_s'] <= 240:
        raise control.SetupError('Invalid refresh interval in local configuration.')
    control.host.credential(config['zai_key'], optional=True)
    return config


def reset_invalid_settings(root: Path, emit=print) -> None:
    """Explicit recovery only: keep the original private bytes in a local backup."""
    try:
        load_settings(root)
    except (ValueError, OSError):
        pass
    else:
        raise control.SetupError('Settings are valid; recovery is unnecessary.')
    source = root / 'tools/aim_host.json'
    with source.open('rb') as stream:
        raw = stream.read(65537)
    if len(raw) > 65536: raise control.SetupError('Configuration is too large for safe recovery. Repair it locally.')
    backup = source.with_name('aim_host.invalid-' + str(time.time_ns()) + '.json')
    from private_files import write_bytes
    write_bytes(backup,raw)
    control.stop_host(root, emit=emit)
    control.save_config(dict(control.host.DEFAULT_CONFIG), root)


def save_settings(root: Path, board: str, providers: list[str], port: str,
                  interval: int, key: str = '', clear_key: bool = False, options=None) -> dict:
    get_board(board)
    config = load_settings(root)
    choices = selected_providers({'providers': providers})
    if not choices:
        raise control.SetupError('Choose at least one AI provider before saving.')
    port = serial_port(port)
    if type(interval) is not int or not 15 <= interval <= 240:
        raise control.SetupError('Quota refresh must be between 15 and 240 seconds.')
    if type(clear_key) is not bool or not isinstance(key, str):
        raise control.SetupError('Invalid key settings. Nothing was saved.')
    updated = dict(config, board=board, providers=choices, port=port,
                   interval_s=interval, zai_provider='zcode')
    if options is not None:
        from host_status import OPTIONS, FLAGS
        if not isinstance(options, dict) or set(options) - (set(OPTIONS) | set(FLAGS)):
            raise control.SetupError('Unknown host preference. Nothing was saved.')
        updated.update(options)
    validate_options(updated)
    if clear_key:
        updated['zai_key'] = ''
    elif key.strip():
        try:
            updated['zai_key'] = control.host.credential(key)
        except ValueError:
            raise control.SetupError('Use a single printable API key. Nothing was saved.') from None
    control.save_config(updated, root)
    return updated


def connection_summary(root: Path, processes) -> str:
    if not processes: return 'HOST STOPPED'
    status = read_status(root, {process.pid for process in processes})
    if not status: return 'HOST RUNNING • USB STATUS UNCONFIRMED'
    state = status['state']
    port = safe_text(status.get('port', ''), 64)
    return {'starting': 'HOST STARTING', 'waiting_usb': 'WAITING FOR USB SELECTION',
            'connecting': f'CONNECTING • {port}', 'connected': f'USB CONNECTED • {port}',
            'reconnecting': f'USB RECONNECTING • {port}', 'stopped': 'HOST STOPPING',
            'error': 'HOST ERROR • CHECK LOG'}[state]


def _wait_for_boot(read_identity):
    """Opening serial can reboot a board; retry only bounded identity timeouts."""
    for attempt in range(3):
        try:
            return read_identity()
        except TimeoutError:
            if attempt == 2:
                raise
            time.sleep(0.25)


def check_connection(root: Path, emit) -> None:
    """Read device identity; no flash, quota requests or settings mutation."""
    config = load_settings(root)
    board = get_board(config['board'])
    processes = control.owned_hosts(root)
    if processes:
        status = read_status(root, {process.pid for process in processes})
        if (status and status['state'] == 'connected' and status.get('board') == board.id
                and config['port'] in ('auto', status['port'])):
            emit('The host has a verified USB connection on ' + status['port'] + '.')
            return
        raise control.SetupError('The host is running but USB is not confirmed. Stop host before checking the display; then select its port and retry.')
    port = control.host.find_port(config['port'], board.id)
    if not port: raise control.SetupError('Choose an explicit display port in Setup, save settings and retry. Use a USB data cable.')
    panel = None
    try:
        panel = control.host.Panel(port)
        time.sleep(0.5)
        def read_identity():
            panel.send_line('{"cmd":"get_info"}')
            return panel.wait_for('info')
        info = _wait_for_boot(read_identity)
        from board_profiles import matches_info
        if not matches_info(board, info):
            raise control.SetupError('This port does not report the selected LimitBuddy board. Check the port and board; a new factory display needs firmware installation.')
        emit('Verified LimitBuddy display: ' + board.name + ' on ' + port + '. No firmware or settings were changed.')
    except (TimeoutError, OSError, RuntimeError, control.host.serial.SerialException):
        raise control.SetupError('The display did not respond. Check its USB data port/cable, close other serial tools, or install firmware on a new board.') from None
    finally:
        if panel is not None: panel.close()


def recent_log(root: Path, secrets: tuple[str, ...] = ()) -> str:
    path = root / 'tools/aim_host.log'
    try:
        with path.open('rb') as stream:
            stream.seek(0, 2)
            length = stream.tell()
            stream.seek(max(0, length - 12000))
            text = stream.read(12000).decode('utf-8', errors='replace')
    except OSError:
        return ''
    for secret in secrets:
        if secret:
            text = text.replace(secret, '[REDACTED]')
    if length > 12000:
        text = text.partition('\n')[2]
    return '\n'.join(safe_text(line) for line in text.splitlines()[-100:])


def integration_command(root: Path, codex_only=False) -> list[str]:
    option = '--setup-codex' if codex_only else '--integrations'
    if getattr(sys, 'frozen', False):
        helper = root / 'AI-Monitor-Console.exe'
        if not helper.is_file():
            raise control.SetupError('Console helper missing. Extract the complete Windows package.')
        return [str(helper), option]
    return [sys.executable, str(root / 'tools/aim_control.py'), option]


def open_integrations(root: Path, codex_only=False) -> None:
    if os.name != 'nt':
        raise control.SetupError('Use tools/aim_control.py in a terminal for provider setup on this platform.')
    environment = dict(os.environ)
    environment['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    subprocess.Popen(integration_command(root, codex_only), cwd=root, env=environment,
                     creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0)


def prepare_flash(root: Path, board_id: str, kind: str) -> tuple[str, list[str]]:
    config = load_settings(root)
    if config.get('board') != board_id:
        raise control.SetupError('Save the selected board before preparing firmware.')
    board = get_board(board_id)
    port = control.host.find_port(config['port'], board.id)
    if not port:
        raise control.SetupError('No unambiguous USB port. Choose an explicit port and save settings.')
    return port, control.flash_command(kind, port, root, board.id)


def run_firmware_command(command, root, environment, emit, timeout_s=600, idle_s=120):
    """Bound the child lifetime, including a blocked stdout pipe. Never free the UI early."""
    lines = queue.Queue(maxsize=128)
    completed = threading.Event()
    process = subprocess.Popen(command, cwd=root, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, errors='replace', env=environment,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    def read_output():
        try:
            for line in iter(lambda: process.stdout.readline(512), ''):
                try: lines.put_nowait(safe_text(line).rstrip())
                except queue.Full: pass  # Bounded diagnostics; never stall the actual flasher.
        except (OSError, ValueError):
            pass
        finally: completed.set()
    reader = threading.Thread(target=read_output, daemon=True)
    reader.start()
    started = last_output = time.monotonic()
    try:
        while True:
            now = time.monotonic()
            if now - started >= timeout_s or now - last_output >= idle_s:
                raise control.SetupError('Firmware tool timed out and was stopped. The write may be incomplete. '
                    'Keep the display powered and check USB. If LimitBuddy still boots, retry the update. '
                    'If it no longer boots, use First installation; this resets display settings. PC provider settings are kept.')
            try:
                line = lines.get(timeout=0.05)
                last_output = time.monotonic()
                emit(line)
            except queue.Empty: pass
            if completed.is_set() and lines.empty() and process.poll() is not None: break
        if process.wait(timeout=3) != 0:
            raise control.SetupError('Firmware tool failed. Check the USB port and device connection.')
    finally:
        # PyInstaller can have a bootloader and a child. Scope cleanup to this
        # exact process tree, wait for exit, and only then let the action finish.
        children = []
        if process.poll() is None:
            try: children = control.psutil.Process(process.pid).children(recursive=True)
            except control.psutil.Error: pass
            for child in children:
                try: child.terminate()
                except control.psutil.Error: pass
            process.terminate()
            try: process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=3)
        _, alive = control.psutil.wait_procs(children, timeout=3)
        for child in alive:
            try: child.kill()
            except control.psutil.NoSuchProcess: pass
        _, alive = control.psutil.wait_procs(alive, timeout=3)
        if alive:
            raise control.SetupError('Firmware tool cleanup could not be confirmed. Close the flasher before retrying.')
        reader.join(timeout=1)
        if completed.is_set(): process.stdout.close()


def verify_firmware_boot(board_id: str, port: str) -> None:
    """Confirm the selected board boots; never retry a write or search other ports."""
    for attempt in range(3):
        panel = None
        try:
            panel = control.host.Panel(port)
            panel.expected_board = get_board(board_id)
            time.sleep(0.5)
            _wait_for_boot(panel.heartbeat)
            return
        except (TimeoutError, OSError, control.host.serial.SerialException):
            if attempt == 2:
                raise control.SetupError('Firmware was written, but startup could not be confirmed. '
                    'Keep the display powered, reconnect USB, and use Check connection. '
                    'No additional write was attempted.') from None
            time.sleep(0.5)
        except RuntimeError:
            raise control.SetupError('Firmware was written, but the connected display identity does not match. '
                'Check the selected board and USB port. No additional write was attempted.') from None
        finally:
            if panel is not None:
                panel.close()


def write_firmware(root: Path, board_id: str, kind: str, port: str, emit) -> None:
    # Revalidate the current files and configuration after the dialog, before
    # stopping the host or invoking any tool. Do not trust a prepared command.
    current_port, command = prepare_flash(root, board_id, kind)
    if current_port != port:
        raise control.SetupError('USB selection changed. Prepare firmware again.')
    control.stop_host(root, emit=emit)
    if kind == 'update':
        # Application-only updates require this project's existing layout.
        panel = None
        try:
            panel = control.host.Panel(port)
            panel.expected_board = get_board(board_id)
            time.sleep(0.5)
            _wait_for_boot(panel.heartbeat)
        except (RuntimeError, TimeoutError, OSError, control.host.serial.SerialException):
            raise control.SetupError('Existing LimitBuddy identity could not be verified. '
                'Check the board/port. A factory demo or another project requires First installation. '
                'The host is stopped; no firmware was written.') from None
        finally:
            if panel is not None:
                panel.close()
    environment = dict(os.environ)
    environment['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    run_firmware_command(command, root, environment, emit)
    emit('Firmware written. Checking display startup...')
    verify_firmware_boot(board_id, port)
    emit('Firmware written and display startup verified. You can start the host.')


def check_flasher_runtime(root: Path) -> bool:
    """Read image metadata using the exact child EXE, without opening USB."""
    environment = dict(os.environ); environment['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    try:
        for board in control.BOARDS.values():
            image = control.firmware_file('update', root, board.id)
            result = subprocess.run([str(root/'firmware-flasher.exe'), '--chip', board.chip, 'image-info', str(image)],
                cwd=root, env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                timeout=30, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            if result.returncode:
                return False
    except (control.SetupError, OSError, subprocess.TimeoutExpired):
        return False
    return True
