"""Windowed desktop entry point; host/telemetry stay in the console helper."""
import sys
import os
import tempfile
from pathlib import Path
import aim_control


def main():
    if sys.argv[1:] == ['--gui-check']:
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication
        from desktop_window import MonitorWindow
        application = QApplication.instance() or QApplication(sys.argv[:1])
        with tempfile.TemporaryDirectory(prefix='ai-monitor-gui-check-') as directory:
            window = MonitorWindow(Path(directory), monitor=False)
            valid = not window.nova.pixmap().isNull() and not window.windowIcon().isNull() and all(
                not image.isNull() for image in window.session_pixmaps.values())
            window.close()
        if getattr(sys, 'frozen', False):
            from desktop_support import check_flasher_runtime
            if not check_flasher_runtime(aim_control.ROOT):
                return 1
        return 0 if valid else 1
    if len(sys.argv) > 1 and sys.argv[1:] != ['--firmware']:
        # Keep read-only diagnostics compatible with old shortcuts. Interactive
        # integrations and stdin telemetry use AI-Monitor-Console.exe.
        return aim_control.main(sys.argv[1:])
    from desktop_window import run_desktop
    return run_desktop(firmware='--firmware' in sys.argv[1:])


if __name__ == '__main__':
    try:
        result = main()
    except ImportError:
        message = ('The desktop runtime could not load. Extract the complete release into a new folder '
                   'and keep _internal next to AI-Monitor.exe.')
        if sys.argv[1:] != ['--gui-check'] and os.name == 'nt':
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, message, 'AI Monitor startup', 0x10)
        elif sys.stderr is not None:
            print(message, file=sys.stderr)
        result = 1
    sys.exit(result)
