"""Terminal distribution never delegates to a legacy application executable."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]

@unittest.skipUnless(os.name=='nt','Windows command launchers')
class NoExecutableLauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='nova source ')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        (self.root/'AI-Monitor-Terminal.bat').write_text('@echo off\necho PYTHON_TERMINAL\nexit /b 0\n')
        (self.root/'AI-Monitor-Console.exe').write_bytes(b'legacy executable must never run')

    def test_registered_limitbuddy_ignores_legacy_executable(self):
        shutil.copyfile(ROOT/'Install-LimitBuddy.ps1',self.root/'Install-LimitBuddy.ps1')
        target=self.root/'bin'
        result=subprocess.run(['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File',str(self.root/'Install-LimitBuddy.ps1'),'-CommandDirectory',str(target),'-EnvironmentScope','Process','-RegisterOnly'],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)
        for name in ('limitbuddy','nova'):
            result=subprocess.run([os.environ['COMSPEC'],'/c',str(target/(name+'.cmd')),'--check'],capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('PYTHON_TERMINAL',result.stdout)

    def test_package_launchers_ignore_legacy_executable(self):
        (self.root/'terminal-bin').mkdir()
        for name in ('limitbuddy.cmd','nova.cmd'):
            shutil.copyfile(ROOT/'terminal-bin'/name,self.root/'terminal-bin'/name)
            result=subprocess.run([os.environ['COMSPEC'],'/c',str(self.root/'terminal-bin'/name),'--check'],capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('PYTHON_TERMINAL',result.stdout)

class TerminalDistributionTests(unittest.TestCase):
    def test_runtime_dependencies_exclude_gui_and_freezer(self):
        dependencies=(ROOT/'tools/requirements.txt').read_text().lower()
        self.assertNotIn('pyside',dependencies)
        self.assertNotIn('pyinstaller',dependencies)

if __name__=='__main__':unittest.main()
