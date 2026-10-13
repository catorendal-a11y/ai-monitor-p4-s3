"""Synthetic complete/fragmented target batches; no board or provider activity."""
import json,sys,unittest
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from asset_baseline import validate_asset,collect_assets,POSES,CODECS


def row(pose='work',codec='raw'):
    return dict(type='asset_benchmark',schema=1,robot='nova',pose=pose,codec=codec,encodedBytes=12,
        decodedBytes=12,samples=5,medianDecodeUs=10,bitExact=True,outputBufferBytes=12,
        decoderStateBytes=0,cpuMHz=360,decodedSha256='a'*64)


def serial_batch(rows,complete=True):
    data=b'boot\n'+b'x'*2050+b'\n'+b''.join(json.dumps(value).encode()+b'\n' for value in rows)
    if complete:data+=b'{"type":"asset_benchmark_end","schema":1,"count":24}\n'
    port=Mock();port.write.return_value=7
    port.read.side_effect=[data[n:n+67] for n in range(0,len(data),67)]
    return port


class AssetBaselineTests(unittest.TestCase):
    def test_cache_report_is_strict_and_never_exports_extra_fields(self):
        rows=[row(p,c) for p in POSES for c in CODECS]
        cache=dict(type='asset_cache',schema=1,loads=6,allocatedBytes=630528,totalLoadUs=100000,
            hashRejected=True,decodeRejected=True,pinPreserved=True,private='not exported')
        raw=b''.join(json.dumps(value).encode()+b'\n' for value in rows+[cache])
        raw+=b'{"type":"asset_benchmark_end","schema":1,"count":24}\n'
        port=Mock();port.write.return_value=7;port.read.side_effect=[raw[n:n+256] for n in range(0,len(raw),256)]
        result={};self.assertEqual(len(collect_assets(port,'nova',cache_report=result)),24)
        self.assertNotIn('private',result);self.assertEqual(result['loads'],6)
        for fields in ({'loads':True},{'allocatedBytes':732801},{'pinPreserved':1}):
            port=Mock();port.write.return_value=7
            port.read.return_value=json.dumps(dict(cache,**fields)).encode()+b'\n'
            with self.assertRaises(ValueError):collect_assets(port,'nova',cache_report={})

    def test_fragmented_exact_batch_is_bounded_and_whitelisted(self):
        rows=[dict(row(p,c),private='not exported') for p in POSES for c in CODECS]
        data=collect_assets(serial_batch(rows),'nova')
        self.assertEqual(len(data),24);self.assertNotIn('private',data[0])
    def test_missing_types_invalid_sizes_and_unverified_success_are_rejected(self):
        for fields in ({'schema':True},{'samples':4},{'bitExact':1},{'decodedBytes':400000},
                       {'medianDecodeUs':0},{'outputBufferBytes':11},{'robot':'nova\n'}):
            with self.subTest(fields=fields),self.assertRaises(ValueError):validate_asset(dict(row(),**fields))
        for key in row():
            data=row();del data[key]
            with self.assertRaises(ValueError):validate_asset(data)
    def test_duplicate_missing_wrong_robot_or_changed_pixels_reject_entire_batch(self):
        original=[row(p,c) for p in POSES for c in CODECS]
        for kind in ('duplicate','missing','robot','digest','failed'):
            rows=[dict(value) for value in original]
            if kind=='duplicate':rows[-1]=rows[0]
            if kind=='missing':rows.pop()
            if kind=='robot':rows[0]['robot']='orbit'
            if kind=='digest':rows[1]['decodedSha256']='b'*64
            if kind=='failed':rows[0].update(bitExact=False,samples=0,medianDecodeUs=0)
            with self.subTest(kind=kind),self.assertRaises(ValueError):collect_assets(serial_batch(rows),'nova')
    def test_timeout_and_partial_query_never_return_partial_measurements(self):
        port=Mock();port.write.return_value=6
        with self.assertRaises(OSError):collect_assets(port,'nova')
        now=[0.0];port.write.return_value=7
        def read(_):now[0]+=.2;return b''
        port.read.side_effect=read
        with self.assertRaises(TimeoutError):collect_assets(port,'nova',clock=lambda:now[0])


if __name__=='__main__':unittest.main()
