"""Compact atomic history packets through the existing Panel owner, no DB/port/model access."""
import json
import secrets
import time

class UsbHistoryClient:
    def __init__(self,panel,clock=time.time):self.panel=panel;self.clock=clock;self.epoch=secrets.randbelow(0xffffffff)+1;self.revision=0
    def send(self,summary):
        if self.revision>=0xffffffff:raise ValueError('History revision exhausted')
        self.revision+=1
        age=self.clock()-summary['sampledAt']
        if not 0<=age<=120:raise ValueError('Stale history sample')
        providers=summary['providers']
        capability=self.panel.info.get('historyProtocol')
        schema=capability if type(capability) is int and capability in (2,3) else 1
        begin=dict(cmd='history_begin',schema=schema,bootId=self.panel.info['bootId'],epoch=self.epoch,revision=self.revision,
                   enabled=summary['enabled'],error=summary['error'],date=summary['date'],sampleAgeSeconds=int(age),providers=[p['provider'] for p in providers])
        self._send(begin)
        for index,provider in enumerate(providers):
            message=dict(cmd='history_provider',schema=schema,epoch=self.epoch,revision=self.revision,index=index,
                            **{key:provider[key] for key in ('today','daily','hourly','quota')})
            if schema>=2:
                keys=['sessions','activeSeconds','completedTurns','failedTurns']
                if schema>=3:keys+=['createdTasks','startedTasks','completedTasks','failedTasks']
                message['agents']={key:provider.get('agents',{}).get(key) for key in keys}
            self._send(message)
    def _send(self,message):
        raw=json.dumps(message,separators=(',',':'),allow_nan=False)
        if len(raw.encode('ascii'))>4095:raise ValueError('History packet too large')
        self.panel.send_line(raw)
        reply=self.panel.wait_for('history_reply',seconds=.5,command=message['cmd'])
        expected=dict(type='history_reply',schema=message['schema'],cmd=message['cmd'],ok=True,bootId=self.panel.info['bootId'],
                      epoch=self.epoch,revision=self.revision,index=message.get('index',0))
        if reply!=expected or type(reply.get('ok')) is not bool or any(type(reply[k]) is not int for k in ('schema','bootId','epoch','revision','index')):
            raise ValueError('Uncorrelated history receipt')
