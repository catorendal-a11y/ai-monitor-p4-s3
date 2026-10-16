"""One library reader, one bounded transaction on the existing serial owner."""
from pathlib import Path
import threading
import time
from companion_packages import selected,load
from usb_companions import UsbPackClient


class CompanionService:
    def __init__(self,root):
        self.root=Path(root);self.condition=threading.Condition();self.closed=False
        self.loaded=None;self.client=None;self.state='builtin';self.identifier='';self.name=''
        self.generation=0;self.reload=True
        self.stamp=time.time();self.next_status=0
        self.worker=threading.Thread(target=self._read,daemon=True,name='aim-companion-library')
        self.worker.start()

    def _read(self):
        previous=None
        while True:
            with self.condition:
                if self.closed:return
                generation=self.generation;force=self.reload;self.reload=False
            try:
                path=self.root/'tools/companions/selection.json'
                meta=path.stat() if path.exists() else None
                signature=(meta.st_mtime_ns,meta.st_size) if meta else ('missing',)
                if signature!=previous or force:
                    identifier=selected(self.root)
                    pack=load(self.root,identifier) if identifier else None
                    result=(identifier,pack,False)
                else:result=None
            except (OSError,ValueError,TypeError):
                signature=('error',);result=('',None,True) if previous!=signature or force else None
            with self.condition:
                if self.closed:return
                if result is not None and generation==self.generation:self.loaded=result
                previous=signature
                self.condition.wait(.5)

    def pump(self,panel):
        with self.condition:
            if self.closed:return
            loaded,self.loaded=self.loaded,None
        if loaded is not None:
            if self.client:self.client.cancel()
            self.client=None;self.identifier,pack,error=loaded;self.name=pack.name if pack else ''
            self.stamp=time.time()
            if error:self.state='error';return
            try:self.client=UsbPackClient(panel,pack)
            except ValueError:self.state='unsupported';return
            self.state='installing'
        if self.client is None:return
        if self.client.done:
            if self.state=='active' and time.monotonic()>=self.next_status:
                try:
                    value=self.client.request('pack_status',check_offset=False)
                    if value.get('state')=='builtin' and value.get('id')=='':self.state='overridden'
                    elif value.get('state')!='active' or value.get('id')!=self.identifier:self.state='error'
                    self.stamp=time.time();self.next_status=time.monotonic()+15
                except (OSError,ValueError,RuntimeError,TimeoutError):self.state='error';self.stamp=time.time()
            return
        deadline=time.monotonic()+.12
        try:
            for _ in range(8):
                if self.client.step():
                    self.state='active' if self.identifier else 'builtin';self.stamp=time.time()
                    self.next_status=time.monotonic()+15;return
                if time.monotonic()>=deadline:return
        except (OSError,ValueError,RuntimeError,TimeoutError):
            self.client.cancel();self.state='error';self.stamp=time.time()

    def snapshot(self):
        client=self.client
        return dict(state=self.state,id='' if self.state=='overridden' else self.identifier,name=self.name,
            sent_bytes=client.offset if client else 0,total_bytes=len(client.pack.blob) if client and client.pack else 0,
            updated_at=self.stamp)

    def close(self):
        with self.condition:self.closed=True;self.loaded=None;self.condition.notify_all()
        if self.client:self.client.cancel()
        self.worker.join(timeout=.6)

    def detach(self):
        if self.client:self.client.cancel()
        self.client=None
        with self.condition:
            self.generation+=1;self.loaded=None

    def reconnect(self):
        self.detach();self.state='installing';self.stamp=time.time()
        with self.condition:
            if self.closed:return
            self.reload=True;self.condition.notify_all()
