"""Untrusted companion archives, fixed-path library and USB transaction tests."""
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))


def archive(change=None,extra=None):
    frames=[];files={}
    for name,data in [('one',b'\x10\x20\xff'),('two',b'\x30\x40\xff')]:
        digest=hashlib.sha256(data).hexdigest()
        frames.append(dict(id=name,file=name+'.raw',width=1,height=1,originX=28,originY=0,
            encodedBytes=3,decodedBytes=3,encodedSha256=digest,decodedSha256=digest))
        files[name+'.raw']=data
    manifest=dict(version=2,name='Fixture Robot',format='RGB565A8',codec='raw',fallback='resting',
        frames=frames,animations=[dict(mood=mood,loop=loop,frames=[dict(id='one',durationMs=100),
            dict(id='two',durationMs=150)]) for mood,loop in [('resting',True),('success',False)]])
    if change:change(manifest,files)
    files['manifest.json']=json.dumps(manifest).encode()
    files.update(extra or {})
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:
        for name,data in files.items():z.writestr(name,data)
    return stream.getvalue()


class CompanionPackageTests(unittest.TestCase):
    def setUp(self):
        import companion_packages
        self.p=companion_packages
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def test_verified_archive_becomes_content_addressed_payload_without_extraction(self):
        pack=self.p.parse_archive(archive())
        self.assertEqual(pack.name,'Fixture Robot')
        self.assertEqual(pack.id,hashlib.sha256(pack.blob).hexdigest())
        again=self.p.parse_blob(pack.blob)
        self.assertEqual(again.id,pack.id)
        source=self.root/'robot.zip';source.write_bytes(archive())
        saved=self.p.install(self.root,source)
        self.assertEqual(saved.id,pack.id)
        self.assertEqual(self.p.load(self.root,pack.id).blob,pack.blob)
        self.assertEqual(self.p.selected(self.root),'')
        self.p.select(self.root,pack.id)
        self.assertEqual(self.p.selected(self.root),pack.id)
        self.p.select(self.root,'')
        self.assertEqual(self.p.selected(self.root),'')

    def test_rejects_paths_extra_files_duplicate_fields_geometry_hash_and_bad_animation(self):
        bad=[archive(extra={'../outside':b'no'}),archive(extra={'run.exe':b'no'}),
             archive(lambda m,f:m.update(version=True)),
             archive(lambda m,f:m['frames'][0].update(encodedSha256='0'*64)),
             archive(lambda m,f:m['frames'][1].update(originX=29)),
             archive(lambda m,f:m['animations'][0]['frames'][0].update(durationMs=39)),
             archive(lambda m,f:m['animations'][0]['frames'][0].update(id='missing')),
             archive(lambda m,f:m.update(fallback='unknown'))]
        for raw in bad:
            with self.subTest(index=bad.index(raw)),self.assertRaises(ValueError):self.p.parse_archive(raw)
        blob=self.p.parse_archive(archive()).blob
        for raw in (blob+b'garbage',blob[:-1],b'\xff'*10):
            with self.assertRaises(ValueError):self.p.parse_blob(raw)

    def test_corrupted_library_or_unsafe_selection_never_becomes_active(self):
        source=self.root/'robot.zip';source.write_bytes(archive())
        pack=self.p.install(self.root,source)
        with self.assertRaises(ValueError):self.p.select(self.root,'../escape')
        path=self.root/'tools/companions'/(pack.id+'.pack')
        path.write_bytes(pack.blob[:-1])
        with self.assertRaises(ValueError):self.p.select(self.root,pack.id)
        self.assertEqual(self.p.selected(self.root),'')

    def test_duplicate_zip_member_is_rejected(self):
        stream=io.BytesIO(archive())
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter('ignore',UserWarning)
            with zipfile.ZipFile(stream,'a') as z:z.writestr('one.raw',b'bad')
        with self.assertRaises(ValueError):self.p.parse_archive(stream.getvalue())


if __name__=='__main__':unittest.main()
