"""Owned synthetic workers only; no accounts, USB, personal files or UI."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import psutil
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from process_runtime import start_child,stop_child


@unittest.skipUnless(os.name=='nt','Windows Job Objects')
class WindowsContainmentTests(unittest.TestCase):
    def gone(self,pid):
        deadline=time.monotonic()+3
        while psutil.pid_exists(pid) and time.monotonic()<deadline: time.sleep(.01)
        self.assertFalse(psutil.pid_exists(pid),'Owned test process survived containment close')

    def test_exited_parent_cannot_leave_descendant_and_unrelated_process_survives(self):
        unrelated=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'],creationflags=subprocess.CREATE_NO_WINDOW)
        source='import subprocess,sys; p=subprocess.Popen([sys.executable,"-c","import time;time.sleep(60)"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);print(p.pid,flush=True)'
        process=None
        try:
            process=start_child([sys.executable,'-u','-c',source],stdout=subprocess.PIPE)
            pid=int(process.stdout.readline()); process.wait(timeout=5)
            self.assertTrue(psutil.pid_exists(pid))
            stop_child(process); self.gone(pid)
            self.assertIsNone(unrelated.poll())
        finally:
            if process is not None: stop_child(process); process.stdout.close()
            unrelated.terminate(); unrelated.wait(timeout=3)

    def test_abrupt_owner_exit_closes_job_and_kills_worker(self):
        source='import os,sys;from process_runtime import start_child;p=start_child([sys.executable,"-c","import time;time.sleep(60)"]);print(p.pid,flush=True);os._exit(7)'
        environment=dict(os.environ,PYTHONPATH=str(Path(__file__).resolve().parents[1]/'tools'))
        owner=subprocess.Popen([sys.executable,'-u','-c',source],stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            env=environment,creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            out,error=owner.communicate(timeout=10)
            self.assertEqual(owner.returncode,7,error.decode(errors='replace'))
            self.gone(int(out))
        finally:
            if owner.poll() is None: owner.kill(); owner.wait(timeout=3)

    def test_assignment_failure_never_executes_worker(self):
        from windows_job import WindowsJob
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'should-not-exist.txt'
            source=f'from pathlib import Path;Path({str(path)!r}).write_text("executed")'
            captured=[]
            def reject(_job,process): captured.append(process); raise OSError('Fixture denied assignment')
            with patch.object(WindowsJob,'attach_and_resume',reject):
                with self.assertRaises(OSError): start_child([sys.executable,'-c',source])
            self.assertFalse(path.exists())
            self.assertEqual(len(captured),1); self.assertIsNotNone(captured[0].poll())

    def test_nested_worker_containment_is_stopped_with_outer_job(self):
        source='import sys,time;from process_runtime import start_child;p=start_child([sys.executable,"-c","import time;time.sleep(60)"]);print(p.pid,flush=True);time.sleep(60)'
        environment=dict(os.environ,PYTHONPATH=str(Path(__file__).resolve().parents[1]/'tools'))
        parent=start_child([sys.executable,'-u','-c',source],stdout=subprocess.PIPE,env=environment)
        try:
            child=int(parent.stdout.readline())
            self.assertTrue(psutil.pid_exists(child))
            stop_child(parent); self.gone(child)
        finally: stop_child(parent); parent.stdout.close()


class ContainmentFailureTests(unittest.TestCase):
    def test_unconfirmed_startup_cleanup_blocks_another_quota_worker(self):
        import aim_host as host
        from process_runtime import ChildCleanupError
        from unittest.mock import Mock
        pool=host.FetchPool()
        with patch.object(host,'start_child',side_effect=ChildCleanupError('fixture')) as spawn:
            with self.assertRaises(ChildCleanupError): pool.fetch('zcode','',Mock())
            with self.assertRaises(RuntimeError): pool.fetch('codex','',Mock())
            self.assertEqual(spawn.call_count,1)


if __name__=='__main__': unittest.main()
