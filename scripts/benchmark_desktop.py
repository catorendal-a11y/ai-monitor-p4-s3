"""Controlled offscreen desktop baseline: no cloud, real accounts or USB writes."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import Mock, patch

started = time.perf_counter()
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[1])
parser.add_argument('--seconds', type=int, default=10)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--io-delay-ms', type=int, default=0, help='Synthetic slow token read, without real records')
args = parser.parse_args()
if not 3 <= args.seconds <= 30: parser.error('Use a phase duration of 3–30 seconds')
if not 0 <= args.io_delay_ms <= 1000: parser.error('Use an I/O delay of 0–1000 ms')
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.path.insert(0, str(args.source.resolve()/'tools'))
import psutil
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QSystemTrayIcon
from PySide6.QtTest import QTest
import aim_control as control
from desktop_window import MonitorWindow, APP_VERSION

application = QApplication([])
process = psutil.Process()
polls = []
latencies = []
previous_tick = None
def tick():
    global previous_tick
    now = time.perf_counter()
    if previous_tick is not None: latencies.append(max(0, (now - previous_tick)*1000 - 20))
    previous_tick = now
timer = QTimer(); timer.setInterval(20); timer.timeout.connect(tick)
def phase():
    global previous_tick
    polls.clear(); latencies.clear(); previous_tick = None
    before = process.cpu_times(); start = time.perf_counter()
    timer.start(); QTest.qWait(args.seconds*1000); timer.stop()
    elapsed = time.perf_counter()-start; after = process.cpu_times()
    values = sorted(latencies)
    return dict(duration_s=round(elapsed,3),cpu_percent_one_core=round(
        ((after.user+after.system)-(before.user+before.system))/elapsed*100,3),
        rss_mib=round(process.memory_info().rss/1048576,2),ui_refreshes=len(polls),
        event_loop_delay_p95_ms=round(values[int((len(values)-1)*.95)],3) if values else 0,
        event_loop_delay_max_ms=round(max(values,default=0),3))

with tempfile.TemporaryDirectory(prefix='ai-monitor-benchmark-') as directory:
    root=Path(directory)
    control.save_config(dict(control.host.DEFAULT_CONFIG,board='guition-p4',providers=['copilot'],port='COM9999'),root)
    def slow_read():
        if args.io_delay_ms: time.sleep(args.io_delay_ms/1000)
        return None
    with patch.object(control,'owned_hosts',return_value=[]), \
            patch.object(control.host.TokenReporter,'poll',side_effect=slow_read), \
            patch.object(QSystemTrayIcon,'isSystemTrayAvailable',return_value=True):
        window=MonitorWindow(root,monitor=False)
        original=window.refresh_status
        def refresh(): polls.append(time.perf_counter()); original()
        window.timer.timeout.disconnect(); window.timer.timeout.connect(refresh)
        window.monitor_enabled=True
        if hasattr(window,'tray'):
            window.tray=Mock(); window.tray.isVisible.return_value=True
            window.tray_start=Mock(); window.tray_stop=Mock(); window.tray_quit=Mock()
            window.tray_timer.start()
        window.show(); application.processEvents()
        startup_ms=(time.perf_counter()-started)*1000
        window.timer.start(); QTest.qWait(500)
        visible=phase()
        window.showMinimized(); QTest.qWait(300)
        minimized=phase()
        window.monitor_enabled=False; window.unsaved=False
        if hasattr(window,'quit_requested'): window.quit_requested=True
        window.config['keep_host_on_close']=True
        window.close()
        if hasattr(window, 'status_pool'): window.status_pool.waitForDone(3000)
        window.deleteLater()
report=dict(version=APP_VERSION,mode='controlled offscreen; token polling mocked; no API/USB',
            synthetic_io_delay_ms=args.io_delay_ms,
            startup_to_widgets_ms=round(startup_ms,2),visible=visible,minimized=minimized)
args.output.parent.mkdir(parents=True,exist_ok=True)
args.output.write_text(json.dumps(report,indent=2))
print(json.dumps(report))
