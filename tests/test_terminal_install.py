"""Per-user terminal command installation with isolated command/PATH fixtures."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
# limitbuddy is the command; nova stays as an alias for existing hooks and statuslines.
COMMANDS=('limitbuddy','nova')


@unittest.skipUnless(os.name=='nt','Windows command installation')
class TerminalInstallTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory(prefix='ai monitor command ')
        self.addCleanup(self.directory.cleanup)
        self.bin=Path(self.directory.name)/'bin'

    def install(self,*extra):
        return subprocess.run(['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File',
            str(ROOT/'Install-LimitBuddy.ps1'),'-CommandDirectory',str(self.bin),
            '-EnvironmentScope','Process','-RegisterOnly',*extra],
            capture_output=True,text=True,timeout=20)

    def owned_files(self):
        return [self.bin/(name+suffix) for name in COMMANDS for suffix in ('.cmd','-launcher.ps1')]

    def test_install_is_idempotent_and_both_commands_run_in_current_terminal(self):
        for _ in range(2):
            result=self.install();self.assertEqual(result.returncode,0,result.stderr)
        for path in self.owned_files():self.assertTrue(path.is_file(),path.name)
        for name in COMMANDS:
            result=subprocess.run([os.environ['COMSPEC'],'/c',str(self.bin/(name+'.cmd')),'--check'],
                                  capture_output=True,text=True,timeout=20,
                                  env=dict(os.environ,AI_MONITOR_PYTHON=sys.executable))
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('Terminal UI check passed. Color: truecolor',result.stdout)
            # Resolve the bare command with normal PowerShell policy, from an unrelated folder.
            result=subprocess.run(['powershell','-NoProfile','-ExecutionPolicy','Restricted','-Command',name+' --check'],
                                  cwd=self.directory.name,capture_output=True,text=True,timeout=20,
                                  env=dict(os.environ,AI_MONITOR_PYTHON=sys.executable,
                                           PATH=os.environ['PATH']+';'+str(self.bin)))
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('Terminal UI check passed.',result.stdout)
        result=self.install('-Uninstall');self.assertEqual(result.returncode,0,result.stderr)
        for path in self.owned_files():self.assertFalse(path.exists(),path.name)

    def test_unrelated_command_is_never_overwritten_or_removed(self):
        for name in COMMANDS:
            with self.subTest(command=name):
                self.bin.mkdir(exist_ok=True);file=self.bin/(name+'.cmd');file.write_text('@echo user command')
                self.assertNotEqual(self.install().returncode,0)
                self.assertEqual(file.read_text(),'@echo user command')
                self.assertEqual(self.install('-Uninstall').returncode,0)
                self.assertEqual(file.read_text(),'@echo user command')
                for path in self.owned_files():
                    if path!=file:self.assertFalse(path.exists(),path.name)
                file.unlink()

    def test_uninstall_repairs_each_partial_owned_installation(self):
        for missing in self.owned_files():
            result=self.install();self.assertEqual(result.returncode,0,result.stderr)
            missing.unlink()
            result=self.install('-Uninstall');self.assertEqual(result.returncode,0,result.stderr)
            for path in self.owned_files():self.assertFalse(path.exists(),path.name)
