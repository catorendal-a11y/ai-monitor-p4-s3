"""Synthetic Qt interaction/painting regressions for the new insight flows."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
import aim_control as control
import desktop_window as desktop
from insights_ui import SetupReportDialog


class InsightsUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        cls.app.setStyle('Fusion')

    def setUp(self):
        self.folder=tempfile.TemporaryDirectory(); self.root=Path(self.folder.name)
        control.save_config(dict(control.host.DEFAULT_CONFIG,board='guition-p4',providers=['copilot'],port='COM9999'),self.root)
        self.window=desktop.MonitorWindow(self.root,monitor=False)
        self.window.show(); self.app.processEvents()

    def tearDown(self):
        self.window.unsaved=False; self.window.quit_requested=True; self.window.config['keep_host_on_close']=True
        self.window.close(); self.window.status_pool.waitForDone(2000); self.window.deleteLater()
        self.app.processEvents(); self.folder.cleanup()

    def report(self):
        return [dict(provider='copilot',activity='readable',quota='unsupported',display='connected',
                     sessions='unsupported',next_step='Fixture next action')]

    def test_blocked_numeric_sampler_does_not_delay_fresh_health_or_create_workers(self):
        from token_activity import TokenSampler
        entered,release=threading.Event(),threading.Event()
        sampler=TokenSampler(home=self.root,providers=['copilot'],activity_dir=self.root/'tools/activity')
        def block():
            entered.set(); release.wait(3); return None
        sampler.reporter.poll=block
        try:
            sampler.poll(); self.assertTrue(entered.wait(1))
            with sampler.condition: sampler.read_started-=16
            health={'state':'connected','board':'guition-p4','port':'COM9999','providers':{},'local_reader':'stalled'}
            with patch.object(control,'owned_hosts',return_value=[]),patch.object(desktop,'read_status',return_value=health), \
                 patch.object(desktop.desktop,'connection_summary',return_value='Fixture connected'), \
                 patch.object(desktop.desktop,'recent_log',return_value=''):
                start=time.monotonic()
                data=desktop.collect_status(self.root,self.window.config,(),sampler,True)
                self.assertLess(time.monotonic()-start,.2)
                self.assertIs(data['health'],health)
                self.assertEqual(data['reader_state'],'stalled')
                self.window.token_reporter=sampler
                worker=sampler.worker
                for _ in range(10): self.window._reset_tokens()
                self.assertIs(sampler.worker,worker)
                self.window._status_finished((self.window.status_epoch,data))
                self.assertIn('TOKEN READER STALLED',self.window.token_state.text())
        finally:
            release.set(); sampler.close(); sampler.worker.join(timeout=2)

    def test_history_selection_clears_previous_export_while_worker_is_pending(self):
        view=self.window.history_view
        view.data={'tokens':[{'provider':'codex','day':20000,'total':10}], 'quota':[], 'forecasts':[], 'error':None}
        view.chart.set_rows(view.data['tokens']); view.export_button.setEnabled(True)
        view.worker=Mock()
        view.provider.setCurrentIndex(view.provider.findData('zcode'))
        self.assertIsNone(view.data); self.assertEqual(view.chart.rows,[])
        self.assertFalse(view.export_button.isEnabled())
        view.worker=None

    def test_stale_history_failure_still_schedules_current_selection(self):
        view=self.window.history_view
        view.generation=10; view.worker=Mock()
        with patch.object(view,'refresh') as refresh:
            view._finished((9,'codex',None)); self.app.processEvents()
            refresh.assert_called_once()

    def test_live_test_resets_cells_expires_and_deconfirms_wrong_or_stale_display(self):
        dialog=SetupReportDialog(self.report(),self.window)
        self.window.live_sampler=Mock(); self.window.live_sampler.poll.return_value=None
        dialog.observed={'copilot'}; dialog.table.item(0,1).setText('new increase observed')
        dialog.start_test()
        self.assertEqual(dialog.table.item(0,1).text(),'baseline pending')
        self.assertEqual(dialog.observed,set())
        health={'state':'connected','board':'guition-p4','port':'COM8888','display_sources':16,'display_sources_at':time.time()}
        result=(dialog.test_generation,None,{},health)
        dialog._sample_finished(result)
        self.assertEqual(dialog.table.item(0,3).text(),'not confirmed')
        health['port']='COM9999'; dialog._sample_finished(result)
        self.assertEqual(dialog.table.item(0,3).text(),'source echoed by display')
        health['display_sources_at']=time.time()-40; dialog._sample_finished(result)
        self.assertEqual(dialog.table.item(0,3).text(),'USB connected')
        dialog._sample_finished((dialog.test_generation,None,{},None))
        self.assertEqual(dialog.table.item(0,3).text(),'not confirmed')
        dialog.deadline=time.monotonic()-1; dialog._sample()
        self.assertFalse(dialog.test_active); self.assertTrue(dialog.test_button.isEnabled())
        dialog.reject(); dialog.deleteLater()

    def test_failed_status_discards_cached_echo_and_completed_pose_is_not_working(self):
        window=self.window
        window.cached_health={'state':'connected'}
        window._status_finished((window.status_epoch,None))
        self.assertIsNone(window.cached_health)
        data={'running':True,'summary':'Fixture connected','health':{'state':'connected','board':'guition-p4','port':'COM9999','providers':{}},
              'reporter':None,'sample':None,'log':'','working':True,
              'sessions':{'providers':[{'provider':'copilot','running':0,'waiting':0,'completed':1,'error':0}]}}
        window._status_finished((window.status_epoch,data))
        self.assertEqual(window.robot_pose,'done'); self.assertFalse(window.robot_working)
        data['sessions']['providers'][0]['completed']=0; data['sessions']['providers'][0]['waiting']=1
        window._status_finished((window.status_epoch,data))
        self.assertEqual(window.robot_pose,'attention'); self.assertFalse(window.nova.pixmap().isNull())
        data['sessions']=None; data['working']=False
        window._status_finished((window.status_epoch,data)); self.assertEqual(window.robot_pose,'done')
        data['health']['local_reader']='stalled'
        window._status_finished((window.status_epoch,data))
        self.assertIn('TOKEN READER STALLED',window.token_state.text())

    def test_history_chart_metrics_paint_without_shadowing_qt_methods(self):
        view=self.window.history_view
        now=int(time.time())//60
        view.data={'tokens':[{'provider':'copilot','day':now//1440,'total':15}],
                   'quota':[{'provider':'copilot','minute':now-2,'window':300,'kind':'model','used':10,'reset':now*60+1000,'epoch':1},
                            {'provider':'copilot','minute':now,'window':300,'kind':'model','used':20,'reset':now*60+1000,'epoch':1}],
                   'forecasts':[],'error':None}
        view._finished((view.generation,'copilot',view.data))
        self.window.tabs.setCurrentIndex(5); self.app.processEvents()
        self.assertFalse(view.chart.grab().isNull())
        view.metric_combo.setCurrentIndex(1); self.app.processEvents()
        self.assertEqual(len(view.chart.quota),2)
        self.assertFalse(view.chart.grab().isNull())
        self.assertIs(view.window(),self.window)

    def test_collection_failure_is_visible_and_stale_status_is_not_confirmed(self):
        view=self.window.history_view
        self.window.config['usage_history']=True
        data={'tokens':[],'quota':[],'forecasts':[],'error':None}
        self.window.cached_health={'board':'guition-p4','port':'COM9999','updated_at':time.time(),
            'history':{'enabled':True,'error':'History unavailable; check local storage. Some observations were missed.'}}
        view._finished((view.generation,'copilot',data))
        self.assertIn('History unavailable',view.summary.text())
        self.window.cached_health['updated_at']=time.time()-60
        view._finished((view.generation,'copilot',data))
        self.assertIn('Collection requested',view.summary.text())


if __name__=='__main__': unittest.main()
