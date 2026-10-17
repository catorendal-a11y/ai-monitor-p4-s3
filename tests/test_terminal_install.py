"""Per-user terminal command installation with isolated command/PATH fixtures."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name=='nt','Windows command installation')
class TerminalInstallTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory(prefix='ai monitor command ')
        self.addCleanup(self.directory.cleanup)
        self.bin=Path(self.directory.name)/'bin'

    def install(self,*extra):
        return subprocess.run(['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File',
            str(ROOT/'Install-Terminal.ps1'),'-CommandDirectory',str(self.bin),
            '-EnvironmentScope','Process','-RegisterOnly',*extra],
            capture_output=True,text=True,timeout=20)

    def test_install_is_idempotent_and_command_runs_in_current_terminal(self):
        for _ in range(2):
            result=self.install();self.assertEqual(result.returncode,0,result.stderr)
        self.assertTrue((self.bin/'ai-monitor.cmd').is_file())
        result=subprocess.run([os.environ['COMSPEC'],'/c',str(self.bin/'ai-monitor.cmd'),'--check'],
                              capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('Terminal UI check passed. Color: truecolor',result.stdout)
        result=self.install('-Uninstall');self.assertEqual(result.returncode,0,result.stderr)
        self.assertFalse((self.bin/'ai-monitor.cmd').exists())
        self.assertFalse((self.bin/'ai-monitor.ps1').exists())

    def test_unrelated_command_is_never_overwritten_or_removed(self):
        self.bin.mkdir();file=self.bin/'ai-monitor.cmd';file.write_text('@echo user command')
        self.assertNotEqual(self.install().returncode,0)
        self.assertEqual(file.read_text(),'@echo user command')
        self.assertEqual(self.install('-Uninstall').returncode,0)
        self.assertEqual(file.read_text(),'@echo user command')
        self.assertFalse((self.bin/'ai-monitor.ps1').exists())
