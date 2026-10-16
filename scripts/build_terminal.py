"""Build the standalone read-only Windows terminal companion without replacing the host."""
import argparse
import hashlib
from importlib import metadata
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from project_version import HOST_VERSION,windows_version_resource


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if sys.platform!='win32':parser.error('Build the Windows terminal on Windows.')
    git_root=Path(subprocess.check_output(['git','rev-parse','--show-toplevel'],cwd=ROOT,text=True).strip())
    if git_root.resolve()!=ROOT.resolve():parser.error('The project itself must be the Git root.')
    output=args.output.resolve()
    if output.exists():parser.error('Use a new output directory.')
    output.mkdir(parents=True)
    (ROOT/'work').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='terminal-build-',dir=ROOT/'work') as scratch:
        scratch=Path(scratch);resource=scratch/'version.txt'
        resource.write_text(windows_version_resource(HOST_VERSION),encoding='utf-8')
        subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile','--console',
            '--name','AI-Monitor-Terminal','--paths',str(ROOT/'tools'),'--distpath',str(output),
            '--workpath',str(scratch/'build'),'--specpath',str(scratch),'--version-file',str(resource),
            '--icon',str(ROOT/'assets/desktop/nova.ico'),'--exclude-module','PySide6',
            '--exclude-module','esptool','--collect-all','textual','--copy-metadata','rich',
            str(ROOT/'tools/aim_terminal.py')],cwd=ROOT,check=True)
    subprocess.run([str(output/'AI-Monitor-Terminal.exe'),'--check'],check=True,timeout=45)
    # Source export is restricted to Git-tracked public tools, never runtime folders.
    tracked=subprocess.check_output(['git','ls-files','tools','LICENSE','docs/TERMINAL.md'],cwd=ROOT,text=True).splitlines()
    for name in tracked:
        relative=Path(name)
        if relative.suffix in ('.db','.sqlite','.sqlite3','.jsonl','.log','.exe','.bin','.key','.pem') or relative.name in ('aim_host.json','aim_host.status.json','auth.json','credentials.json'):
            raise ValueError('Private/generated path cannot be exported')
        target=output/'source'/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(ROOT/name,target)
    licenses=output/'licenses';licenses.mkdir()
    names=('textual','rich','markdown-it-py','mdurl','mdit-py-plugins','platformdirs','pygments',
           'typing-extensions','psutil','pyserial','cryptography','cffi','pycparser','lz4','altgraph')
    for name in names:
        dist=metadata.distribution(name);folder=licenses/name;folder.mkdir()
        for file in dist.files or []:
            if file.name.lower().startswith(('license','copying','notice')):
                path=dist.locate_file(file)
                if path.is_file():shutil.copy2(path,folder/str(file).replace('/','_').replace('\\','_'))
    shutil.copy2(Path(sys.base_prefix)/'LICENSE.txt',licenses/'Python-LICENSE.txt')
    shutil.copy2(ROOT/'docs/TERMINAL.md',output/'README.md')
    lines=[]
    for path in sorted(output.rglob('*')):
        if path.is_file():lines.append(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+path.relative_to(output).as_posix())
    (output/'SHA256SUMS.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    archive=output.parent/(output.name+'.zip')
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED) as zipped:
        for path in sorted(output.rglob('*')):
            if path.is_file():zipped.write(path,output.name+'/'+path.relative_to(output).as_posix())
    print('Terminal companion: '+str(output/'AI-Monitor-Terminal.exe'))


if __name__=='__main__':main()
