"""Trusted asset input validation; never flash or read real provider records."""
import ctypes,hashlib,json,os,shutil,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from export_asset_benchmark import trusted_frames, POSES
from benchmark_asset_codecs import ROOT, build_codecs, encode_frame


class AssetExportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.raw=b'\x00\x12\xff'*4
        self.frames=[]
        for robot in ('nova','orbit'):
            for pose in POSES:
                name=robot+'-'+pose+'.rgb565a8';(self.root/name).write_bytes(self.raw)
                self.frames.append(dict(robot=robot,pose=pose,file=name,width=2,height=2,originX=0,
                    originY=0,decodedBytes=12,sha256=hashlib.sha256(self.raw).hexdigest()))
    def save(self):
        (self.root/'frames.json').write_text(json.dumps(dict(schema=1,format='RGB565A8',frames=self.frames)))
    def test_exact_twelve_frames_and_hashes(self):
        self.save();self.assertEqual(len(trusted_frames(self.root)),12)
    def test_bad_geometry_paths_duplicates_digest_and_types_are_rejected(self):
        for key,value in (('width',True),('originY',300),('decodedBytes',11),('file','../x'),
                          ('sha256','x'*64),('pose','work\n'),('robot','unknown')):
            saved=self.frames[1].copy();self.frames[1][key]=value;self.save()
            with self.subTest(key=key),self.assertRaises(ValueError):trusted_frames(self.root)
            self.frames[1]=saved
        self.frames[1]=self.frames[0].copy();self.save()
        with self.assertRaises(ValueError):trusted_frames(self.root)
    def test_changed_or_truncated_payload_is_rejected(self):
        self.save();(self.root/self.frames[0]['file']).write_bytes(b'bad')
        with self.assertRaises(ValueError):trusted_frames(self.root)


class NativeLz4BoundsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (ROOT/'.pio/libdeps/esp32p4-release/lvgl/src/libs/lz4/lz4.c').is_file():
            raise unittest.SkipTest('Build P4 first to install the pinned native codec sources')
        compiler=shutil.which('gcc')
        if not compiler and Path('C:/msys64/mingw64/bin/gcc.exe').is_file():compiler='C:/msys64/mingw64/bin/gcc.exe'
        if not compiler:raise unittest.SkipTest('Native C compiler required for pinned LZ4 boundary tests')
        cls.temp=tempfile.TemporaryDirectory()
        try:cls.codec=build_codecs(Path(cls.temp.name),compiler)
        except BaseException:cls.temp.cleanup();raise
    @classmethod
    def tearDownClass(cls):
        if os.name=='nt':
            import _ctypes
            _ctypes.FreeLibrary(cls.codec._handle)
        cls.temp.cleanup()
    def test_exact_roundtrip_and_truncation_never_overwrite_capacity(self):
        raw=bytes(range(128))*8
        encoded=encode_frame(raw,self.codec)['lz4']
        source=ctypes.create_string_buffer(encoded)
        for length in range(len(encoded)+1):
            output=ctypes.create_string_buffer(b'\xa5'*(len(raw)+16),len(raw)+16)
            count=self.codec.LZ4_decompress_safe(source,output,length,len(raw))
            self.assertEqual(output.raw[len(raw):],b'\xa5'*16)
            if length==len(encoded):self.assertEqual(output.raw[:count],raw)
            else:self.assertNotEqual(count,len(raw))
        output=ctypes.create_string_buffer(b'\xa5'*(len(raw)+16),len(raw)+16)
        self.assertLess(self.codec.LZ4_decompress_safe(source,output,len(encoded),len(raw)-1),0)
        self.assertEqual(output.raw[len(raw)-1:],b'\xa5'*17)


if __name__=='__main__':unittest.main()
