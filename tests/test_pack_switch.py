"""A validated old pack must settle on the UI before the next begin is sent."""
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

class PackSwitchTests(unittest.TestCase):
    def test_ready_and_clearing_defer_new_begin_until_UI_settles(self):
        for pending in ('ready','clearing'):
            with self.subTest(pending=pending),tempfile.TemporaryDirectory() as d:
                root=Path(d);source=root/'fixture.zip';source.write_bytes(archive())
                pack=packages.install(root,source);packages.select(root,pack.id)
                class Panel:
                    info={'bootId':17,'companionProtocol':1}
                    def __init__(self):self.state=pending;self.offset=100;self.id='a'*64;self.commands=[]
                    def send_line(self,line):self.message=json.loads(line);self.commands.append(self.message['cmd'])
                    def wait_for(self,kind,seconds,command):
                        m=self.message;ok=True
                        if command=='pack_begin':
                            ok=self.state not in ('ready','clearing')
                            if ok:self.offset=0;self.state='receiving';self.id=m['id']
                        elif command=='pack_chunk':self.offset+=len(bytes.fromhex(m['data']))
                        elif command=='pack_finish':self.state='active'
                        return dict(schema=1,bootId=17,nonce=m['nonce'],cmd=command,ok=ok,offset=self.offset,state=self.state,id=self.id)
                panel=Panel();service=CompanionService(root)
                try:
                    end=time.monotonic()+3
                    while not panel.commands and time.monotonic()<end:service.pump(panel);time.sleep(.005)
                    self.assertNotIn('pack_begin',panel.commands,'Never begin while an old UI adoption is pending')
                    panel.state='active'
                    end=time.monotonic()+3
                    while service.state!='active' and time.monotonic()<end:service.pump(panel);time.sleep(.005)
                    self.assertEqual(service.state,'active')
                    self.assertEqual(panel.id,pack.id)
                    self.assertEqual(panel.commands.count('pack_begin'),1)
                    self.assertEqual(panel.commands.count('pack_finish'),1)
                finally:service.close()
