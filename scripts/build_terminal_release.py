"""Build a source-based NOVA terminal ZIP with verified firmware; no application EXEs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from board_profiles import BOARDS
from aim_control import firmware_file
from project_version import HOST_VERSION, fw_version


def export_source(root,package):
    files=subprocess.check_output(['git','-C',str(root),'ls-files'],text=True).splitlines()
    for name in files:
        relative=Path(name)
        if relative.is_absolute() or '..' in relative.parts or not relative.parts:
            raise ValueError('Unsafe tracked source path')
        if any(part in {'.git','.pio','.venv','.codex','.zcode','node_modules','work','__pycache__','outputs'} for part in relative.parts):
            raise ValueError('Private/generated tracked path')
        if relative.parts[:2] in (('tools','activity'),('tools','companions')):
            raise ValueError('Runtime data is not release source')
        if relative.name.startswith(('aim_host.invalid-','permission-trust','permission-endpoint.')) or relative.name in {'aim_host.json','aim_host.status.json','auth.json','credentials.json','secrets.json','.env'} or (relative.name.startswith('.env.') and relative.name!='.env.example') or relative.suffix.lower() in {'.log','.db','.sqlite','.sqlite3','.jsonl','.lock','.bin','.exe','.lnk','.pem','.key'}:
            raise ValueError('Private/generated tracked file')
        source=root/relative
        if source.is_symlink() or not source.resolve().is_relative_to(root.resolve()):
            raise ValueError('Linked source cannot be exported')
        target=package/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source,target)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--firmware-dir',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=ROOT/'work/terminal-release')
    args=parser.parse_args()
    git_root=Path(subprocess.check_output(['git','-C',str(ROOT),'rev-parse','--show-toplevel'],text=True).strip())
    if git_root.resolve()!=ROOT.resolve():parser.error('This project must be its own Git root')
    version=fw_version(ROOT)
    if version!=HOST_VERSION:parser.error('Host and firmware versions must match')
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    package=output/('nova-'+version+'-terminal')
    if package.exists() or package.with_suffix('.zip').exists():parser.error('Use a new output directory')
    package.mkdir()
    try:build_package(output,package,version,args)
    except BaseException:
        if package.resolve().parent!=output:raise RuntimeError('Unsafe cleanup path') from None
        shutil.rmtree(package)
        raise
    print('Terminal package: '+str(output/(package.name+'.zip')))


def build_package(output,package,version,args):
    export_source(ROOT,package)
    firmware = package / 'firmware'
    firmware.mkdir()
    manifest = {'schema': 2, 'version': version, 'boards': {}}
    for board in BOARDS.values():
        folder = firmware / board.id
        folder.mkdir()
        record = {'board':board.name, 'chip':board.chip, 'experimental':board.experimental, 'files':{}}
        for name, offset in [('application.bin', 0x10000), ('factory.bin', 0)]:
            image = args.firmware_dir / board.id / name
            if not image.is_file(): raise RuntimeError('Required board-specific firmware is missing')
            data = image.read_bytes()
            if name == 'application.bin' and version.encode() not in data:
                raise RuntimeError('Firmware version does not match source')
            shutil.copy2(image, folder / name)
            record['files'][name] = {'sha256':hashlib.sha256(data).hexdigest(), 'bytes':len(data), 'offset':offset}
        manifest['boards'][board.id] = record
    (firmware / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    for board in BOARDS.values():
        firmware_file('install', package, board.id)
        firmware_file('update', package, board.id)
    from build_companion_packages import build as build_companion
    for robot in ('nova','orbit'):build_companion(robot,package/'companion-packs')
    hashes=[]
    for path in sorted(package.rglob('*')):
        if path.is_file():hashes.append(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+path.relative_to(package).as_posix())
    (package/'SHA256SUMS.txt').write_text('\n'.join(hashes)+'\n',encoding='utf-8')
    archive_package(package,output/(package.name+'.zip'))


def archive_package(package, archive):
    partial = archive.with_name(archive.name + '.partial')
    # Write beside the destination, then publish atomically: an interrupted run
    # must not leave a truncated archive that still looks like a deliverable.
    try:
        with zipfile.ZipFile(partial, 'w', zipfile.ZIP_DEFLATED) as bundle:
            for path in sorted(package.rglob('*')):
                if path.is_file():
                    bundle.write(path, package.name + '/' + path.relative_to(package).as_posix())
        os.replace(partial, archive)
    finally:
        partial.unlink(missing_ok=True)


if __name__=='__main__':main()
