"""Upstream command-line flasher; double-click opens the graphical firmware tab."""
import os
from pathlib import Path
import subprocess
import sys


def open_firmware_ui(root: Path) -> int:
    from ctypes import windll
    app = root / 'AI-Monitor.exe'
    if not app.is_file():
        windll.user32.MessageBoxW(None, 'Extract the complete AI Monitor release first. '
            'Open AI-Monitor.exe and choose Firmware to install your display.', 'AI Monitor firmware', 0x10)
        return 1
    choice = windll.user32.MessageBoxW(None,
        'This is the command-line firmware helper. Normal installation happens in AI-Monitor.exe '
        'with visible progress and error messages.\n\nOpen the Firmware tab now? '
        'No firmware will be written until you confirm it in the app.', 'AI Monitor firmware', 0x24)
    if choice == 6:
        environment = dict(os.environ); environment['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
        subprocess.Popen([str(app), '--firmware'], cwd=root, env=environment,
                         creationflags=subprocess.CREATE_NO_WINDOW)
    return 0


def main() -> int:
    if len(sys.argv) == 1 and os.name == 'nt' and getattr(sys, 'frozen', False):
        return open_firmware_ui(Path(sys.executable).resolve().parent)
    import esptool
    esptool._main()
    return 0

if __name__ == "__main__":
    sys.exit(main())
