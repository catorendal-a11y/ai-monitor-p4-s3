import base64
import json
from pathlib import Path
import struct
import sys
import tempfile
import time
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from usb_mirror import UsbMirrorClient, decode_chunk, CHUNKS, BYTES
import mirror_service

class Panel:
    def __init__(self): self.commands=[]; self.bad=None; self.info={"mirrorProtocol":1}
    def send_line(self,line): self.current=json.loads(line);self.commands.append(self.current)
    def wait_for(self,kind,seconds,command):
        r=dict(type='mirror',cmd=command,requestId=self.current['requestId'],frameId=7,state='ready',width=800,height=480,pixelsPerChunk=640,chunks=600,encoding='rle565le-base64')
        if command=='mirror_chunk':r.update(index=self.current['index'],data=base64.b64encode(struct.pack('<HH',640,0xf800)).decode())
        if command=='mirror_end':r['state']='closed'
        if self.bad:r.update(self.bad)
        return r

class MirrorTests(unittest.TestCase):
    def test_lossless_bounded_decoder(self):
        encoded=base64.b64encode(struct.pack('<HHHH',320,0x001f,320,0x07e0)).decode()
        self.assertEqual(decode_chunk(encoded),b'\x1f\0'*320+b'\xe0\x07'*320)
        for value in ('!',base64.b64encode(struct.pack('<HH',0,3)).decode(),base64.b64encode(struct.pack('<HH',641,3)).decode(),base64.b64encode(struct.pack('<HH',639,3)).decode()):
            with self.assertRaises(ValueError):decode_chunk(value)
    def test_real_frame_correlation_and_one_shot(self):
        panel=Panel();client=UsbMirrorClient(panel)
        for _ in range(CHUNKS+3):client.step()
        self.assertTrue(client.done);self.assertEqual(len(client.pixels),BYTES)
        self.assertEqual(client.pixels[:2],b'\0\xf8')
        self.assertEqual(sum(c['cmd']=='mirror_chunk' for c in panel.commands),600)
        self.assertEqual(panel.commands[-1]['cmd'],'mirror_end')
        count=len(panel.commands);client.step();self.assertEqual(count,len(panel.commands))
    def test_wrong_nonce_dimensions_and_bool(self):
        for bad in (dict(requestId='0'*32),dict(width=True),dict(frameId=True),dict(encoding='hex')):
            p=Panel();p.bad=bad
            with self.assertRaises(ValueError):UsbMirrorClient(p).step()
    def test_fixed_mailbox_complete_and_cleanup(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'tools').mkdir();nonce=mirror_service.request(root)
            service=mirror_service.MirrorService(root);panel=Panel()
            for _ in range(25):service.pump(panel)
            pixels,stamp=mirror_service.receive(root,nonce)
            self.assertEqual(len(pixels),BYTES);self.assertLess(time.time()-stamp,3)
            mirror_service.cancel(root,nonce)
            self.assertIsNone(mirror_service.receive(root,nonce))
    def test_cancel_never_finishes_image(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'tools').mkdir();nonce=mirror_service.request(root)
            service=mirror_service.MirrorService(root);panel=Panel();service.pump(panel)
            mirror_service.cancel(root,nonce);service.pump(panel)
            self.assertIsNone(service.client);self.assertEqual(panel.commands[-1]['cmd'],'mirror_end')
    def test_request_paths_and_stale_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'tools').mkdir();mirror_service.directory(root);service=mirror_service.MirrorService(root)
            mirror_service.write(service.path/'request.json',dict(nonce='a'*32,operation='shell',at=time.time(),path='C:/secret'))
            panel=Panel();service.pump(panel);self.assertEqual(panel.commands,[])
    def test_no_mailbox_created_at_host_start_and_unsupported(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'tools').mkdir();service=mirror_service.MirrorService(root)
            self.assertFalse(service.path.exists())
            nonce=mirror_service.request(root);panel=Panel();panel.info={}
            service.pump(panel);self.assertEqual(panel.commands,[])
            with self.assertRaises(RuntimeError):mirror_service.receive(root,nonce)
    def test_reentrant_pump_and_storage_failure_are_optional(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'tools').mkdir();mirror_service.request(root)
            service=mirror_service.MirrorService(root);panel=Panel()
            service.busy=True;service.pump(panel);self.assertEqual(panel.commands,[])
            service.busy=False;panel.info={}
            with patch('mirror_service.write',side_effect=OSError('denied')):service.pump(panel)
            self.assertFalse(service.busy)
    def test_capture_timestamp_and_expired_response_cleanup(self):
        import os
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'tools').mkdir();nonce=mirror_service.request(root)
            service=mirror_service.MirrorService(root);panel=Panel();service.pump(panel)
            stamp=service.client.captured_at
            for _ in range(25):service.pump(panel)
            pixels,received_stamp=mirror_service.receive(root,nonce)
            self.assertEqual(received_stamp,stamp)
            response=service.path/'response.json'
            mirror_service.write(response,dict(nonce=nonce,at=time.time()-65,error='unavailable'))
            old=time.time()-65;os.utime(response,(old,old));service.last_cleanup=0
            service.pump(panel);self.assertFalse(response.exists())
    def test_idle_host_accelerates_only_active_capture_without_provider_calls(self):
        import aim_host
        from unittest.mock import Mock, patch
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'tools').mkdir();service=mirror_service.MirrorService(root)
            for active in (False, True):
                service.client=object() if active else None
                panel=Mock();panel.mirror_service=service;panel.refresh_request_id=None
                clock={'now':0.0};sleeps=[]
                def advance(seconds):sleeps.append(seconds);clock['now']+=seconds
                with patch.object(aim_host.time,'monotonic',side_effect=lambda:clock['now']), patch.object(aim_host.time,'sleep',side_effect=advance), patch.object(aim_host,'fetch_codex') as fetch:
                    aim_host.wait_connected(panel,1.1)
                self.assertLessEqual(max(sleeps),.05 if active else 1)
                fetch.assert_not_called()

    def test_old_viewer_does_not_consume_new_viewers_response(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'tools').mkdir()
            old=mirror_service.request(root);current=mirror_service.request(root)
            path=mirror_service.directory(root)/'response.json'
            mirror_service.write(path,dict(nonce=current,at=time.time(),pixels=base64.b64encode(bytes(BYTES)).decode()))
            self.assertIsNone(mirror_service.receive(root,old))
            self.assertTrue(path.exists())
            self.assertEqual(len(mirror_service.receive(root,current)[0]),BYTES)

    def test_invalid_response_nonce_is_rejected_without_waiting_for_timeout(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'tools').mkdir();nonce=mirror_service.request(root)
            path=mirror_service.directory(root)/'response.json'
            for invalid in (None, True, 'invalid', 'x'*32):
                with self.subTest(nonce=invalid):
                    mirror_service.write(path,dict(nonce=invalid,at=time.time(),error='unavailable'))
                    with self.assertRaises(ValueError):mirror_service.receive(root,nonce)
                    self.assertFalse(path.exists())

if __name__=='__main__':unittest.main()
