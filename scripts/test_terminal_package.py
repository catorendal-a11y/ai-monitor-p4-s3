"""Exercise an extracted terminal package without any NOVA application EXE."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from terminal_runtime import verify_runtime

def unexpected_executables(root):
    root=Path(root).resolve()
    allowed={root/'runtime/python.exe',root/'runtime/pythonw.exe'}
    return [path for path in root.rglob('*.exe') if path.resolve() not in allowed]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package',type=Path,required=True)
    args=parser.parse_args();root=args.package.resolve()
    if os.name!='nt':parser.error('Windows installation check')
    if (root/'.venv').exists():parser.error('Use a clean extracted package')
    bundled=verify_runtime(root)
    unexpected=unexpected_executables(root)
    if unexpected:raise ValueError('Unexpected executable in terminal package: '+unexpected[0].relative_to(root).as_posix())
    powershell=str(Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe')
    with tempfile.TemporaryDirectory(prefix='nova command smoke ') as directory:
        command=Path(directory)/'bin'
        install=[powershell,'-NoProfile','-ExecutionPolicy','Bypass','-File',str(root/'Install-Nova.ps1'),'-CommandDirectory',str(command),'-EnvironmentScope','Process']
        env=dict(os.environ)
        if bundled:
            env.update(PATH=str(Path(os.environ['SystemRoot'])/'System32'),USERPROFILE=directory,
                       PIP_NO_INDEX='1',HTTP_PROXY='http://127.0.0.1:9',HTTPS_PROXY='http://127.0.0.1:9')
        env.pop('AI_MONITOR_PYTHON',None)
        if bundled:
            click=[os.environ['COMSPEC'],'/d','/c','call',str(root/'Install-Nova.cmd'),'-CommandDirectory',str(command),'-EnvironmentScope','Process']
            result=subprocess.run(click,cwd=root,env=env,input='\n',capture_output=True,text=True,timeout=60)
            if result.returncode or 'NOVA is ready' not in result.stdout:raise RuntimeError('One-click installer failed: '+result.stdout[-1500:]+result.stderr[-1500:])
        else:subprocess.run(install,cwd=root,env=env,check=True,timeout=300)
        python=bundled or root/'.venv/Scripts/python.exe'
        if bundled:assert not (root/'.venv').exists(),'Bundled install must not need a separate Python environment'
        subprocess.run([str(python),'-c',"import importlib.util; assert importlib.util.find_spec('PySide6') is None; assert importlib.util.find_spec('PyInstaller') is None"],check=True,timeout=20)
        env['PATH']=str(command)+os.pathsep+env['PATH']
        env.pop('AI_MONITOR_PYTHON',None)
        for option,expected in [('--check','Color: truecolor'),('--help','nova'),('--version','v1.')]:
            result=subprocess.run([powershell,'-NoProfile','-ExecutionPolicy','Restricted','-Command','nova '+option],cwd=directory,env=env,capture_output=True,text=True,timeout=30)
            if result.returncode or expected not in result.stdout:raise RuntimeError('Installed terminal command failed: '+option+' '+result.stderr[-1000:])
        subprocess.run(install+['-RegisterOnly'],env=env,check=True,timeout=20)
        subprocess.run(install+['-Uninstall'],env=env,check=True,timeout=20)
        assert not (command/'nova.cmd').exists()
        assert (root/'tools/aim_host.json').exists(),'Uninstall must preserve private settings'
    print('Clean terminal install, bare nova, idempotent registration and safe unregister passed.')

if __name__=='__main__':main()
