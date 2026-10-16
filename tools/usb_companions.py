"""One chunk per step through the existing serial owner; no ports, retries or file paths."""
import json
import secrets
import time


class UsbPackClient:
    def __init__(self,panel,pack,clock=time.monotonic):
        info=getattr(panel,'info',{})
        if type(info.get('companionProtocol')) is not int or info['companionProtocol']!=1:
            raise ValueError('External companions require supported P4 firmware')
        if type(info.get('bootId')) is not int or not 0<info['bootId']<=0xffffffff:
            raise ValueError('Invalid companion device identity')
        self.panel=panel;self.pack=pack;self.clock=clock;self.boot=info['bootId']
        self.nonce=secrets.token_hex(16);self.offset=0;self.phase='begin';self.started=clock();self.done=False
        self.total_bytes=len(pack.blob) if pack else 0

    def request(self,command,check_offset=True,**fields):
        self.panel.send_line(json.dumps(dict(cmd=command,bootId=self.boot,nonce=self.nonce,**fields),separators=(',',':')))
        value=self.panel.wait_for('pack_reply',seconds=.4,command=command)
        if (not isinstance(value,dict) or type(value.get('schema')) is not int or value['schema']!=1 or
                value.get('cmd')!=command or value.get('nonce')!=self.nonce or
                type(value.get('bootId')) is not int or value['bootId']!=self.boot or
                type(value.get('ok')) is not bool or not value['ok'] or
                type(value.get('offset')) is not int or not 0<=value['offset']<=2*1024*1024 or
                (check_offset and value['offset']!=self.offset)):
            raise ValueError('Companion transfer was not acknowledged by the selected device')
        return value

    def step(self):
        if self.done:return True
        if self.clock()-self.started>300:raise TimeoutError('Companion installation timed out')
        if self.phase=='begin':
            if self.pack is None:self.request('pack_builtin');self.phase='status'
            else:self.request('pack_begin',id=self.pack.id,bytes=len(self.pack.blob));self.phase='chunks'
        elif self.phase=='chunks':
            if self.offset<len(self.pack.blob):
                offset=self.offset;data=self.pack.blob[offset:offset+512];self.offset+=len(data)
                self.request('pack_chunk',offset=offset,data=data.hex())
            else:self.request('pack_finish');self.phase='status'
        else:
            value=self.request('pack_status')
            if self.pack is None:
                if value.get('state')=='builtin' and value.get('id')=='':self.done=True
            elif value.get('state')=='active' and value.get('id')==self.pack.id:self.done=True
            if not self.done and value.get('state') not in ('ready','clearing'):
                raise ValueError('Companion activation did not match the selected pack')
        return self.done

    def cancel(self):
        # Closing the serial owner must not write or retry an ambiguous activation.
        self.done=True;self.pack=None
