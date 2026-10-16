"""Terminal adapters for the existing desktop operations and their safety gates."""
import csv
from datetime import datetime,timezone
import io
from itertools import islice
import json
import os
from pathlib import Path
import time
import aim_control as control
import desktop_support as desktop
from host_security import safe_text
from host_status import read_status,OPTIONS,FLAGS
from provider_catalog import PROVIDERS


def require(value,word):
    if value!=word:raise ValueError('Confirmation required: '+word)


class TerminalActions:
    def __init__(self,root,comparison=None):
        self.root=Path(root);self.prepared=None;self.comparison=comparison

    def execute(self,action,values=None):
        values=values or {};lines=[]
        try:config=control.local_config(self.root)
        except (ValueError,OSError):
            if action!='recover':raise
            config={}
        secrets=[value for value in (config.get('zai_key'),values.get('key')) if isinstance(value,str) and value]
        def emit(text):
            text=str(text)
            for secret in secrets:text=text.replace(secret,'[REDACTED]')
            lines.append(safe_text(text,1024))
            del lines[:-128]
        result={}
        if action in ('start','stop'):
            if action=='start' and control.owned_hosts(self.root):emit('Host is already running; no restart was requested.')
            else:getattr(control,action+'_host')(self.root,emit=emit)
        elif action=='settings':
            result['settings']={key:config.get(key,default) for key,default in FLAGS.items() if key!='usb_permissions'}
            result['settings'].update({key:config.get(key,limits[2]) for key,limits in OPTIONS.items()})
            result['settings'].update({key:config.get(key) for key in ('board','port','interval_s','providers')})
        elif action=='save':
            options=values.get('options',{})
            if 'usb_permissions' in options:raise ValueError('Production approval settings are not enabled here')
            desktop.save_settings(self.root,values['board'],values['providers'],values['port'],int(values['interval']),
                key=values.get('key',''),clear_key=values.get('clear_key',False),options=options)
            self.prepared=None;emit('Settings saved. Unchanged credentials were preserved.')
        elif action=='ports':
            result['ports']=[safe_text(port.device,40) for port in islice(control.list_ports.comports(),64)]
        elif action=='check_usb':desktop.check_connection(self.root,emit)
        elif action=='setup_report':
            from provider_setup import setup_report
            result['providers']=setup_report(self.root)
        elif action in ('link_events','unlink_events','link_quota','unlink_quota'):
            require(values.get('confirm'),'LINK')
            provider=values.get('provider');remove=action.startswith('unlink')
            if provider not in ('codex','claude','zcode') or (not remove and provider not in config['providers']):
                raise ValueError('Select and save this provider first')
            import provider_setup
            if action.endswith('quota'):
                if provider!='claude':raise ValueError('Quota bridge is specific to Claude')
                function=provider_setup.claude_bridge
            else:function=getattr(provider_setup,provider+'_session_link')
            emit(function(self.root,remove=remove))
        elif action=='codex_setup':
            require(values.get('confirm'),'SETUP')
            if 'codex' not in config['providers']:raise ValueError('Select and save Codex first')
            desktop.open_integrations(self.root,codex_only=True)
            emit('Official Codex setup opened in a separate terminal for installation/sign-in.')
        elif action=='clear_history':
            require(values.get('confirm'),'CLEAR');desktop.clear_local_history(self.root,emit)
        elif action=='recover':
            require(values.get('confirm'),'RESET');desktop.reset_invalid_settings(self.root,emit)
        elif action=='prepare_flash':
            kind=values.get('kind')
            if kind not in ('install','update'):raise ValueError('Choose install or update')
            board=config['board'];port,_=desktop.prepare_flash(self.root,board,kind)
            self.prepared=(board,kind,port)
            result['prepared']=dict(board=board,kind=kind,port=port)
            emit('Firmware checked. Confirm the exact board, operation and port before writing.')
        elif action=='flash':
            require(values.get('confirm'),'FLASH')
            if self.prepared is None:raise ValueError('Prepare firmware first')
            prepared,self.prepared=self.prepared,None
            desktop.write_firmware(self.root,*prepared,emit)
            emit('Host remains stopped. Start it explicitly when ready.')
        elif action=='diagnostics':
            from diagnostic_report import build
            health=read_status(self.root,{p.pid for p in control.owned_hosts(self.root)})
            self.export(values['path'],json.dumps(build(config,health),indent=2).encode('utf-8'))
            emit('Diagnostic metadata exported without credentials or conversations.')
        elif action in ('history_report','export_history'):
            from usage_history import read_history
            if not config.get('usage_history'):raise ValueError('History is disabled')
            report=read_history(self.root/'tools/activity',config['providers'],days=int(values.get('days',7)))
            if report.get('error'):raise ValueError('History unavailable')
            if action=='history_report':result['history']=report
            else:
                stream=io.StringIO(newline='');writer=csv.writer(stream)
                writer.writerow(['metric','provider','observed_utc','value','window_minutes','kind','reset_epoch','local_date'])
                for row in report['tokens']:
                    writer.writerow(['observed_tokens',row['provider'],'',row['total'],'','','',row['date']])
                for row in report['quota']:
                    writer.writerow(['quota_used_percent',row['provider'],datetime.fromtimestamp(row['minute']*60,timezone.utc).isoformat(),row['used'],row['window'],row['kind'],row['reset'],''])
                for row in report.get('daily_agents',[]):
                    for field in ('sessions','activeSeconds','completedTurns','failedTurns','createdTasks','startedTasks','completedTasks','failedTasks'):
                        if row.get(field) is not None:writer.writerow([field,row['provider'],'',row[field],'','','',row['date']])
                self.export(values['path'],stream.getvalue().encode('utf-8'));emit('Numeric history exported.')
        elif action in ('packs','import_pack','select_pack','builtin','remove_pack'):
            import companion_packages as packs
            if action=='import_pack':
                require(values.get('confirm'),'IMPORT')
                pack=packs.install(self.root,Path(values['path']));packs.select(self.root,pack.id)
                emit('Pack validated and selected; wait for the host activation receipt.')
            elif action in ('select_pack','builtin'):
                packs.select(self.root,'' if action=='builtin' else values['id'])
                emit('Selection saved. Device activation is separate; check host status.')
            elif action=='remove_pack':
                require(values.get('confirm'),'REMOVE');packs.remove(self.root,values['id'])
                emit('Unused local pack removed.')
            rows=[];paths=list(islice(packs.directory(self.root,create=False).glob('*.pack'),17))
            if len(paths)>16:raise ValueError('Companion library capacity exceeded')
            for path in sorted(paths):
                try:
                    pack=packs.load(self.root,path.stem);rows.append(dict(id=pack.id,name=safe_text(pack.name,64)))
                except (ValueError,OSError):emit('An invalid local pack was omitted.')
            result['packs']=rows;result['selected']=packs.selected(self.root)
            health=read_status(self.root,{p.pid for p in control.owned_hosts(self.root)}) or {}
            selected_device=health.get('board')==config.get('board') and config.get('port') in ('auto',health.get('port'))
            companion=health.get('companion',{})
            if health.get('state')!='connected' or not selected_device:
                result['activation']='Display: connect the saved board/port and start the host.'
            elif companion.get('state') in ('active','builtin') and companion.get('id')!=result['selected']:
                result['activation']='Display: selected companion is not confirmed.'
            else:result['activation']='Display: '+safe_text(companion.get('state','unconfirmed'),30)
        elif action=='log':result['log']=desktop.recent_log(self.root,tuple(secrets))
        elif action=='connect_pc':
            require(values.get('confirm'),'CONNECT')
            if self.comparison is None:raise ValueError('Physical code comparison is unavailable')
            from enrollment_setup import connect_device
            connect_device(self.root,self.comparison,emit)
        elif action=='screen':
            from mirror_service import request,receive,cancel
            nonce=request(self.root)
            try:
                deadline=time.monotonic()+110
                while time.monotonic()<deadline:
                    frame=receive(self.root,nonce)
                    if frame:
                        result['pixels']=frame[0];break
                    time.sleep(.5)
                else:raise TimeoutError('Screen capture timed out')
            finally:cancel(self.root,nonce)
        else:raise ValueError('Unsupported terminal action')
        result['output']='\n'.join(lines)
        return result

    @staticmethod
    def export(path,content):
        path=Path(path).expanduser().resolve()
        if path.exists():raise ValueError('Choose a new output file; existing files are preserved')
        from private_files import temporary_file,protect
        path.parent.mkdir(parents=True,exist_ok=True)
        descriptor,temporary=temporary_file(path.parent)
        try:
            with os.fdopen(descriptor,'wb') as stream:
                protect(temporary);stream.write(content);stream.flush();os.fsync(stream.fileno())
            os.link(temporary,path)  # Atomic exclusive publication; a concurrent export is never overwritten.
        finally:Path(temporary).unlink(missing_ok=True)
