"""Actual Qt companion import/selection with own synthetic data and no serial access."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import sys
import tempfile
import time
import unittest
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'tools'),str(Path(__file__).resolve().parent)]
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QThreadPool
from test_companion_packages import archive


class CompanionUiTests(unittest.TestCase):
    def test_import_use_and_builtin_selection_with_visible_rejection(self):
        from companion_ui import CompanionView
        import companion_packages as packages
        app=QApplication.instance() or QApplication([])
        class Owner:
            closed=False;busy=False;cached_health={};status_pool=QThreadPool()
        owner=Owner()
        with tempfile.TemporaryDirectory() as directory:
            owner.root=Path(directory);path=owner.root/'pack.zip';path.write_bytes(archive())
            view=CompanionView(owner)
            def settle():
                end=time.monotonic()+3
                while view.worker is not None and time.monotonic()<end:app.processEvents();time.sleep(.005)
                self.assertIsNone(view.worker)
            settle();view.import_path(path);settle()
            self.assertTrue(packages.selected(owner.root))
            self.assertEqual(view.choices.count(),1)
            owner.cached_health=dict(state='connected',updated_at=time.time(),companion=dict(
                state='active',id='f'*64,updated_at=time.time()))
            view.refresh_device()
            self.assertNotIn('activated',view.device_status.text())
            owner.cached_health['companion']['id']=packages.selected(owner.root)
            owner.cached_health['updated_at']=time.time()-60
            view.refresh_device()
            self.assertNotIn('activated',view.device_status.text())
            owner.cached_health['updated_at']=time.time()
            view.refresh_device();self.assertIn('activated',view.device_status.text())
            view.use_builtin();settle()
            self.assertEqual(packages.selected(owner.root),'')
            path.write_bytes(b'not a pack');view.import_path(path);settle()
            self.assertIn('rejected',view.status.text().lower())
            self.assertEqual(packages.selected(owner.root),'')
            owner.closed=True;view.close();view.deleteLater();app.processEvents()
            owner.status_pool.waitForDone(2000)
