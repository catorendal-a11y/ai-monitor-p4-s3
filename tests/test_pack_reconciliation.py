"""A lost activation ACK is uncertainty, never proof that the old pack survived."""
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'tools'),str(Path(__file__).resolve().parent)]
from test_companion_packages import archive
import companion_packages as packages
from companion_service import CompanionService
from companion_ui import CompanionView

class PackReconciliationTests(unittest.TestCase):
    def exercise(self,activate):
        class Panel:
            info={'bootId':17,'companionProtocol':1}
            def __init__(self):self.offset=0;self.active='a'*64;self.finishes=0;self.messages=[]
            def send_line(self,line):self.messages.append(json.loads(line))
            def wait_for(self,kind,seconds,command):
                m=self.messages[-1]
                if command=='pack_begin':self.offset=0
                elif command=='pack_chunk':self.offset+=len(bytes.fromhex(m['data']))
                elif command=='pack_finish':
                    self.finishes+=1
                    if activate:self.active=mypack.id
                    raise TimeoutError('Synthetic missing finish reply')
                return dict(schema=1,bootId=17,nonce=m['nonce'],cmd=command,ok=True,offset=self.offset,
                            state='active' if command=='pack_status' else 'receiving',id=self.active)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'own.zip';source.write_bytes(archive());mypack=packages.install(root,source);packages.select(root,mypack.id)
            service=CompanionService(root);panel=Panel()
            try:
                deadline=time.monotonic()+3
                while service.state not in ('error','unconfirmed') and time.monotonic()<deadline:
                    service.pump(panel);time.sleep(.005)
                self.assertEqual(service.state,'unconfirmed')
                class View:pass
                class Label:
                    def setText(self,text):self.text=text
                view=View();view.owner=View()
                view.owner.config={'board':'guition-p4','port':'COM9999'}
                view.owner.cached_health={'state':'connected','updated_at':time.time(),
                    'board':'guition-p4','port':'COM9999','companion':service.snapshot()}
                view.selected_id=mypack.id;view.device_status=Label()
                CompanionView.refresh_device(view)
                self.assertNotIn('previous companion retained',view.device_status.text)
                service.next_status=0;service.pump(panel)
                self.assertEqual(service.state,'active' if activate else 'different')
                self.assertEqual(panel.finishes,1,'Never repeat an ambiguous activation')
                self.assertEqual(service.snapshot()['total_bytes'],len(mypack.blob))
            finally:service.close()

    def test_lost_ack_is_reconciled_to_actual_new_active_pack(self):self.exercise(True)
    def test_lost_ack_does_not_pretend_old_pack_means_success(self):self.exercise(False)
