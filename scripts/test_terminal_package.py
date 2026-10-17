"""Exercise an extracted, EXE-free terminal package on a disposable Windows directory."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package',type=Path,required=True)
    args=parser.parse_args();root=args.package.resolve()
    if os.name!='nt':parser.error('Windows installation check')
    if (root/'.venv').exists():parser.error('Use a clean extracted package')
    if any(root.rglob('*.exe')):raise ValueError('Application executables are not allowed in the terminal archive')
    powershell=str(Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe')
    with tempfile.TemporaryDirectory(prefix='nova command smoke ') as directory:
        command=Path(directory)/'bin'
        install=[powershell,'-NoProfile','-ExecutionPolicy','Bypass','-File',str(root/'Install-Nova.ps1'),'-CommandDirectory',str(command),'-EnvironmentScope','Process']
        subprocess.run(install,cwd=root,check=True,timeout=300)
        python=root/'.venv/Scripts/python.exe'
        subprocess.run([str(python),'-c',"import importlib.util; assert importlib.util.find_spec('PySide6') is None; assert importlib.util.find_spec('PyInstaller') is None"],check=True,timeout=20)
        env=dict(os.environ,PATH=str(command)+os.pathsep+os.environ['PATH'])
        env.pop('AI_MONITOR_PYTHON',None)
        for option,expected in [('--check','Color: truecolor'),('--help','nova'),('--version','v1.')]:
            result=subprocess.run([powershell,'-NoProfile','-ExecutionPolicy','Restricted','-Command','nova '+option],cwd=directory,env=env,capture_output=True,text=True,timeout=30)
            if result.returncode or expected not in result.stdout:raise RuntimeError('Installed terminal command failed: '+option+' '+result.stderr[-1000:])
        subprocess.run(install+['-RegisterOnly'],check=True,timeout=20)
        subprocess.run(install+['-Uninstall'],check=True,timeout=20)
        assert not (command/'nova.cmd').exists()
        assert (root/'tools/aim_host.json').exists(),'Uninstall must preserve private settings'
    print('Clean terminal install, bare nova, idempotent registration and safe unregister passed.')

if __name__=='__main__':main()
