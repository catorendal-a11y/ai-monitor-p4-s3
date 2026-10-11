"""First-run setup and host controls. Also the portable Windows entry point."""
import argparse
import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
import time

import psutil
from serial.tools import list_ports
import aim_host as host
from provider_catalog import PROVIDERS, selected_providers
from codex_support import setup_codex, codex_command
from host_security import read_local_json, safe_text, serial_port, powershell_executable
from board_profiles import BOARDS, get_board, configured_board
from host_status import validate_options


class SetupError(ValueError):
    """A safe, actionable error message for the setup menu."""


ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]


def local_config(root=ROOT):
    path = root / "tools/aim_host.json"
    if not path.exists():
        return dict(host.DEFAULT_CONFIG)
    try:
        config = read_local_json(path)
    except (ValueError, OSError):
        raise SetupError("Local configuration is unreadable. Repair tools/aim_host.json before setup.") from None
    if not isinstance(config, dict):
        raise SetupError("Local configuration must be a JSON object.")
    output = dict(host.DEFAULT_CONFIG, **config)
    output['board'] = configured_board(config)
    try: output['port'] = serial_port(output['port'])
    except ValueError: raise SetupError('Invalid local USB port; use auto, COM or a /dev/ serial device.') from None
    output['providers'] = selected_providers(config, legacy=True)
    return output


def save_config(config, root=ROOT):
    directory = root / "tools"
    directory.mkdir(exist_ok=True)
    path = directory / "aim_host.json"
    descriptor, temporary = tempfile.mkstemp(prefix=".aim-config-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(config, output, indent=2)
            output.write("\n")
        for attempt in range(4):
            try:
                os.replace(temporary, path)
                break
            except PermissionError as error:
                # Windows scanners can briefly hold the existing config open.
                # Retain atomic replacement; never relax file permissions.
                if getattr(error, 'winerror', None) not in (5, 32) or attempt == 3:
                    raise
                time.sleep(0.025 * (2 ** attempt))
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def choose_port(current="auto", ask=input):
    ports = sorted(list_ports.comports(), key=lambda port: port.device)
    print("\nConnect the display using its USB data port.")
    for index, port in enumerate(ports, 1):
        print(f"  {index}. {safe_text(port.device)} - {safe_text(port.description)}")
    if not ports:
        print("No serial ports found. Check the cable; you can configure again later.")
    print(f"Enter a listed number, a port name, or auto. Enter keeps {current}.")
    while True:
        answer = ask("USB port: ").strip()
        if not answer:
            return current
        if answer.isdecimal():
            index = int(answer) - 1
            if 0 <= index < len(ports):
                return ports[index].device
        else:
            try: return serial_port(answer)
            except ValueError: pass
        print("Choose a listed number, COM port, /dev/... port or auto.")


def choose_providers(current, ask=input):
    keys = list(PROVIDERS)
    print('\nChoose the AI tools you want to monitor (no first-run default):')
    for index, key in enumerate(keys, 1):
        name, _, support = PROVIDERS[key]
        print(f'  {index}. {name} - {support}')
    if current:
        print('Enter keeps: ' + ', '.join(PROVIDERS[key][0] for key in current))
    while True:
        answer = ask('Provider numbers, separated by commas: ').strip()
        if not answer and current: return list(current)
        choices = [part.strip() for part in answer.split(',')]
        if choices and all(part.isdecimal() and 1 <= int(part) <= len(keys) for part in choices):
            selected = [keys[int(part) - 1] for part in choices]
            if len(set(selected)) == len(selected): return selected
        print('Select at least one provider explicitly; duplicates are not allowed.')


def choose_board(current='', ask=input):
    print('\nChoose your display board:')
    choices = list(BOARDS)
    for index, identifier in enumerate(choices, 1):
        board = BOARDS[identifier]
        print(f'  {index}. {board.name}' + (' (EXPERIMENTAL - not physically verified)' if board.experimental else ''))
    if current:
        print('Enter keeps: ' + get_board(current).name)
    while True:
        answer = ask('Board number: ').strip()
        if not answer and current: return current
        if answer.isdecimal() and 1 <= int(answer) <= len(choices): return choices[int(answer)-1]
        print('Select a supported board explicitly.')


def configure(root=ROOT, ask=input, read_secret=getpass.getpass):
    config = local_config(root)
    config['board'] = choose_board(config.get('board', ''), ask)
    board = get_board(config['board'])
    if board.experimental:
        print('S3: use the USB TO UART connector for flashing AND host data. Native USB is not this transport.')
        print('Brightness is visual dimming; the physical backlight supports on/off. RGB/touch need hardware verification.')
    config['providers'] = choose_providers(config['providers'], ask)
    config["port"] = choose_port(config["port"], ask)
    if 'codex' in config['providers']:
        print('Codex uses the existing CLI login; no key needs to be pasted.')
    key = ''
    if 'zcode' in config['providers']:
        print('ZCode quota key is optional. Enter keeps it; clear removes it. Input is hidden.')
        key = read_secret('Optional Z.AI key: ').strip()
    if key == "clear":
        config["zai_key"] = ""
    elif key:
        try:
            config["zai_key"] = host.credential(key)
        except ValueError:
            raise SetupError("The key must be a single printable token. No settings were changed.") from None
    config["zai_provider"] = "zcode"
    save_config(config, root)
    print("Saved tools/aim_host.json. Existing settings were preserved.")
    if 'codex' in config['providers']:
        try: setup_codex(ask)
        except RuntimeError as error: raise SetupError(str(error)) from None
    print("Use Start host next, or Install firmware if this is a new display.")


def owned_hosts(root=ROOT):
    expected = {(root / "tools/aim_host.py").resolve(), (root / "tools/aim_control.py").resolve()}
    portable = {(root / name).resolve() for name in ('AI-Monitor.exe', 'AI-Monitor-Console.exe')}
    found = []
    for process in psutil.process_iter(["pid", "cmdline", "exe"]):
        try:
            if process.pid == os.getpid():
                continue
            command = process.info.get("cmdline") or []
            if "--host" in command and process.info.get("exe") and Path(process.info["exe"]).resolve() in portable:
                found.append(process)
                continue
            for argument in command[1:]:
                if argument.endswith(("aim_host.py", "aim_control.py")) and Path(argument).is_absolute():
                    if Path(argument).resolve() in expected and (argument.endswith("aim_host.py") or "--host" in command):
                        found.append(process)
                        break
        except (psutil.Error, OSError):
            continue
    return found


def stop_host(root=ROOT, emit=print):
    processes = owned_hosts(root)
    for process in processes:
        try:
            process.terminate()
        except psutil.NoSuchProcess:
            pass
    _, alive = psutil.wait_procs(processes, timeout=5)
    if alive:
        raise SetupError("Host could not stop. Close this installation's host and retry. No new host or firmware write was started.")
    emit("Host stopped." if processes else "Host is already stopped.")


def start_host(root=ROOT, emit=print):
    # Validate before replacing the running host. Never echo configuration/keys.
    config = local_config(root)
    if not config['providers']:
        raise SetupError('Choose your AI providers in First-time setup before starting the host.')
    if not config.get('board'):
        raise SetupError('Choose your display board in First-time setup before starting the host.')
    board = get_board(config['board'])
    validate_options(config)
    if type(config['interval_s']) is not int or not 15 <= config['interval_s'] <= 240:
        raise SetupError('Quota refresh must be between 15 and 240 seconds. Save settings before starting.')
    host.zcode_key(config)
    if config['port'] == 'auto':
        try:
            candidates = sorted({serial_port(port.device) for port in list_ports.comports()
                                 if port.vid in board.usb_vids})
        except (ValueError, OSError):
            raise SetupError('USB ports could not be checked. Choose your display port in Setup and save settings.') from None
        if len(candidates) > 1:
            raise SetupError('More than one matching USB port was found: ' + ', '.join(candidates) +
                '. Select your display\'s explicit USB port in Setup, click Save settings, then Start host. '
                  'Any existing host was left unchanged; no new host was started.')
    stop_host(root, emit=emit)
    if getattr(sys, "frozen", False):
        helper = root / 'AI-Monitor-Console.exe'
        command = [str(helper) if helper.is_file() else sys.executable, "--host"]
    else:
        python = Path(sys.executable)
        pythonw = python.with_name("pythonw.exe")
        command = [str(pythonw if os.name == "nt" and pythonw.exists() else python), str(root / "tools/aim_host.py")]
    environment = dict(os.environ)
    if getattr(sys, "frozen", False):
        # The child must keep its own extracted runtime after this menu closes.
        environment["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    process = subprocess.Popen(command, cwd=root, env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, start_new_session=os.name != "nt", creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    time.sleep(1)
    if process.poll() is not None:
        raise SetupError("Host exited during startup. Use Status and View log.")
    emit("Host process started in the background. Check USB and provider status in the app; a running process does not confirm a connection.")


def firmware_file(kind, root=ROOT, board_id='guition-p4'):
    if kind not in ('install', 'update'): raise SetupError('Unknown firmware operation.')
    try: board = get_board(board_id)
    except ValueError: raise SetupError('Choose your display board before flashing.') from None
    name = "factory.bin" if kind == "install" else "application.bin"
    folder = root / 'firmware'
    manifest_path = root / "firmware/manifest.json"
    if not manifest_path.is_file():
        raise SetupError("Prebuilt firmware is missing. Download the Windows release package or see the developer guide.")
    try:
        manifest = read_local_json(manifest_path)
        modern = manifest.get('schema') == 2
        record = manifest['boards'][board.id] if modern else manifest
        if modern: folder = folder / board.id
        elif board.id != 'guition-p4': raise ValueError()
        expected_name = board.name if modern else 'GUITION JC4880P433'
        if record['board'] != expected_name or record['chip'] != board.chip: raise ValueError()
        def checked_image(filename, offset):
            file = folder / filename
            if not file.resolve().is_relative_to((root / 'firmware').resolve()): raise ValueError()
            item = record['files'][filename]
            digest = item['sha256']
            if not isinstance(digest, str) or not re.fullmatch(r'[a-f0-9]{64}', digest): raise ValueError()
            if not 0 < file.stat().st_size <= 16 * 1024 * 1024: raise ValueError()
            if modern and (type(item.get('bytes')) is not int or item['bytes'] != file.stat().st_size or
                           type(item.get('offset')) is not int or item['offset'] != offset): raise ValueError()
            data = file.read_bytes()
            if hashlib.sha256(data).hexdigest() != digest: raise ValueError()
            return file, data
        path, data = checked_image(name, 0 if kind == 'install' else 0x10000)
        if modern:
            _, app = checked_image('application.bin', 0x10000)
            def check_chip(image, offset=0):
                header = image[offset:offset+24]
                if len(header) != 24 or header[0] != 0xe9 or struct.unpack_from('<H',header,12)[0] != board.image_chip_id:
                    raise ValueError()
            check_chip(app)
            if kind == 'install':
                check_chip(data, board.bootloader_offset)
                from firmware_layout import validate_factory
                validate_factory(data, app, board)
    except (ValueError, KeyError, TypeError, AttributeError, OSError, struct.error):
        raise SetupError('Firmware board/chip/layout or checksum verification failed. Extract a matching release package.') from None
    return path


def flash_command(kind, port, root=ROOT, board_id='guition-p4'):
    path = firmware_file(kind, root, board_id)
    board = get_board(board_id)
    tool = root / "firmware-flasher.exe"
    command = [str(tool)] if tool.exists() else [sys.executable, "-m", "esptool"]
    if getattr(sys, "frozen", False) and not tool.exists():
        raise SetupError("Firmware flasher is missing. Extract the complete Windows package.")
    return command + ["--chip", board.chip, "--port", serial_port(port), "--baud", "115200", "write-flash",
                      "0x0" if kind == "install" else "0x10000", str(path)]


def flash(root=ROOT, ask=input):
    config = local_config(root)
    config['board'] = choose_board(config.get('board', ''), ask)
    board = get_board(config['board'])
    print('\nFirmware target: ' + board.name)
    if board.experimental: print('EXPERIMENTAL S3: unverified on physical hardware. Use the USB TO UART port.')
    print("1. First installation (writes bootloader/partitions; resets display settings)")
    print("2. Update an existing AI Monitor installation on this board (keeps its partition layout/settings)")
    choice = ask("Choose 1 or 2; Enter cancels: ").strip()
    if choice not in {"1", "2"}:
        return
    kind = "install" if choice == "1" else "update"
    port = choose_port(config["port"], ask)
    if port == "auto":
        ports = list({p.device for p in list_ports.comports() if p.vid in board.usb_vids})
        if len(ports) != 1:
            raise SetupError("Select an explicit port before flashing; no unambiguous display was found.")
        port = ports[0]
    command = flash_command(kind, port, root, board_id=board.id)
    if ask(f"Write firmware to {port} on {board.name}? Type FLASH to proceed: ").strip() != "FLASH":
        print("Cancelled. Nothing was written.")
        return
    stop_host(root)
    result = subprocess.run(command, cwd=root, check=False)
    if result.returncode:
        raise SetupError("Firmware installation failed. Check USB cable/port and close other serial clients.")
    config["port"] = port
    save_config(config, root)
    print("Firmware written. Use Start host next. The first display connection can take a few seconds.")


def status(root=ROOT):
    config = local_config(root)
    providers = config['providers']
    identifier = config.get('board', '')
    print('Board: ' + (get_board(identifier).name if identifier else 'not selected - open First-time setup'))
    print(f"Host: {'running' if owned_hosts(root) else 'stopped'} / USB port: {config['port']}")
    print('Selected providers: ' + (', '.join(PROVIDERS[key][0] for key in providers) or 'none - open First-time setup'))
    if 'codex' in providers:
        print(f"Official Codex CLI: {'found' if codex_command() else 'missing - use Provider integration help (menu 7)'}")
        print('Quota uses the CLI account interface; legacy file login is a fallback when the CLI is absent.')
    if 'zcode' in providers:
        key = host.zcode_key(config)
        print(f"ZCode quota key: {'configured' if key else 'optional, not configured'}")
    counters = host.TokenReporter(providers=providers, activity_dir=root / 'tools/activity').poll()
    mask = counters["sources"]
    print('Readable token counters: ' + (' + '.join(PROVIDERS[key][0] for key in providers if mask & PROVIDERS[key][1]) or 'none'))
    print("Available USB ports: " + (", ".join(p.device for p in list_ports.comports()) or "none"))
    print("Messages: tools/aim_host.log. Counter updates can lag until requests finish.")


def view_log(root=ROOT):
    path = root / "tools/aim_host.log"
    if not path.exists():
        print("No log yet. Start the host first.")
        return
    with path.open("rb") as log:
        log.seek(max(0, path.stat().st_size - 8192))
        lines = log.read().decode("utf-8", errors="replace").splitlines()
    print("\n".join(safe_text(line) for line in lines[-25:]))


def integration_help(root=ROOT, ask=input, home=None):
    config = local_config(root)
    for key in config['providers']:
        print(PROVIDERS[key][0] + ': ' + PROVIDERS[key][2])
    print('Full instructions: docs/PROVIDERS.md. No app passwords or browser cookies are imported.')
    if 'codex' in config['providers']:
        try: setup_codex(ask)
        except RuntimeError as error: raise SetupError(str(error)) from None
    if 'claude' not in config['providers']: return
    print('Optional Claude quota bridge uses the documented statusline fields.')
    if ask('Install the Claude quota bridge? Type INSTALL, or Enter to skip: ').strip() != 'INSTALL': return
    from provider_setup import claude_bridge
    try: print(claude_bridge(root, home=home))
    except ValueError as error: raise SetupError(str(error)) from None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", action="store_true", help="Run the background companion")
    parser.add_argument("--check", action="store_true", help="Show local diagnostics without connecting to the panel or API")
    parser.add_argument('--integrations', action='store_true', help='Open selected provider integrations interactively')
    parser.add_argument('--setup-codex', action='store_true', help='Install/sign in the explicitly selected official Codex CLI')
    parser.add_argument('--ingest', choices=list(PROVIDERS), help='Read a cumulative numeric telemetry record from stdin')
    parser.add_argument('--claude-statusline', action='store_true', help='Receive documented Claude statusline quota fields')
    args = parser.parse_args(argv)
    (ROOT / "tools").mkdir(exist_ok=True)
    if args.ingest or args.claude_statusline:
        from telemetry_bridge import ingest, claude_statusline
        try:
            raw = sys.stdin.buffer.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024: return 1
            data = json.loads(raw)
            if args.ingest: ingest(args.ingest, data, ROOT / 'tools/activity')
            else: print(claude_statusline(data, ROOT / 'tools/activity'))
            return 0
        except (ValueError, OSError, TypeError): return 1
    if args.host:
        return host.main()
    if args.check:
        status()
        return 0
    if args.integrations or args.setup_codex:
        try:
            if args.setup_codex:
                if 'codex' not in local_config()['providers']: raise SetupError('Select Codex and save settings first.')
                setup_codex()
            else:
                integration_help()
        except (ValueError, RuntimeError, OSError):
            print('Provider setup could not finish. Check your selected providers and official CLI installation.')
        try:
            input('Press Enter to close provider setup: ')
        except (EOFError, KeyboardInterrupt):
            pass
        return 0
    actions = {"1": configure, "2": start_host, "3": stop_host, "4": flash, "5": status, "6": view_log, '7': integration_help}
    while True:
        print("\nAI MONITOR\n1. First-time setup / choose board and AI providers\n2. Start host (hidden)\n3. Stop host\n4. Install / update display firmware\n5. Status / connection help\n6. View recent log\n7. Provider integration help\n0. Exit")
        try:
            choice = input("Choose: ").strip()
            if choice == "0":
                return 0
            if choice in actions:
                actions[choice]()
            else:
                print("Choose a number from the menu.")
        except SetupError as error:
            print(str(error))
        except (ValueError, RuntimeError, OSError, psutil.Error):
            # Credential errors can contain user input in third-party exceptions.
            print("Action failed. Check local configuration, permissions and the connection. No keys were printed.")
        except (KeyboardInterrupt, EOFError):
            return 0


if __name__ == "__main__":
    sys.exit(main())
