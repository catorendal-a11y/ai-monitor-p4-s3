"""Synthetic permission contracts and real local Windows pipes; no Claude or USB approvals."""
import io
import json
import os
from pathlib import Path
import secrets
import sys
import threading
import unittest
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import aim_permission as helper
import permission_ipc as ipc


class PermissionHelperTests(unittest.TestCase):
    def fixture(self):
        return dict(hook_event_name='PermissionRequest',tool_name='Bash',tool_input={'command':'echo fixture'},
                    transcript_path='private path',session_id='private session',prompt='private prompt')
    def test_request_contains_only_reviewable_arguments_and_random_correlation(self):
        one=helper.request_from_hook(self.fixture());two=helper.request_from_hook(self.fixture())
        self.assertNotEqual(one['nonce'],two['nonce']);self.assertNotEqual(one['requestId'],two['requestId'])
        self.assertEqual(set(one),{'schema','requestId','nonce','revision','tool','hint','expiresInMs'})
        self.assertNotIn('private',json.dumps(one));self.assertEqual(one['hint'],'{"command":"echo fixture"}')
        for change in ({'tool_name':'x'*65},{'tool_input':[]},{'tool_input':{'command':'x'*321}},
                       {'tool_input':{'command':'Ø'}},{'hook_event_name':'PreToolUse'},
                       {'tool_input':{'value':float('nan')}}):
            with self.assertRaises(ValueError):helper.request_from_hook(dict(self.fixture(),**change))
    def test_exact_once_decision_contract_never_changes_arguments_or_permissions(self):
        request=helper.request_from_hook(self.fixture())
        response=dict(schema=1,instance='a'*32,requestId=request['requestId'],nonce=request['nonce'],revision=1,decision='allow')
        self.assertEqual(helper.decision_output(request,response,'a'*32),
            {'hookSpecificOutput':{'hookEventName':'PermissionRequest','decision':{'behavior':'allow'}}})
        for change in ({'nonce':'wrong'},{'requestId':'wrong'},{'revision':True},{'instance':'wrong'},
                       {'decision':'retry'},{'schema':True},{'updatedInput':{'command':'wrong'}}):
            with self.assertRaises(ValueError):helper.decision_output(request,dict(response,**change),'a'*32)
    def test_unavailable_timeout_or_ambiguous_host_falls_back_without_output(self):
        for failure in (OSError('private error'),TimeoutError(),ValueError(),EOFError()):
            with patch.object(helper.sys,'argv',['fixture']),patch.object(helper.os,'name','nt'),\
                 patch.object(helper.sys,'stdin',Mock(buffer=io.BytesIO(json.dumps(self.fixture()).encode()))),\
                 patch.object(helper,'exchange',side_effect=failure),patch.object(helper.sys,'stdout',io.StringIO()) as output:
                self.assertEqual(helper.main(),0);self.assertEqual(output.getvalue(),'')
    def test_strict_ipc_bytes_never_unpickles_or_accepts_duplicate_fields(self):
        for raw in (b'{"schema":1,"schema":2}',b'{"value":NaN}',b'x'*4097,b''):
            with self.assertRaises(ValueError):ipc.strict_json(raw)
        for name in ('remote\\pipe','../fixture','ai-monitor-permission-'+'x'*32):
            with self.assertRaises(ValueError):ipc._address(name)

    def test_wrong_host_pid_cannot_return_a_decision(self):
        channel=Mock();channel.peer_pid.return_value=456
        with patch('host_security.read_local_json',return_value=dict(schema=1,pid=123,instance='a'*32)),\
             patch.object(helper,'current_sid',return_value='fixture-sid'),patch.object(helper,'connect',return_value=channel):
            with self.assertRaises(ValueError):helper.exchange(Path.cwd(),helper.request_from_hook(self.fixture()))
        channel.send.assert_not_called();channel.receive.assert_not_called();channel.close.assert_called_once()

    @unittest.skipUnless(os.name=='nt','Windows same-user IPC')
    def test_real_acl_pipe_bounded_bytes_and_correlated_peer_pid(self):
        name='ai-monitor-permission-'+secrets.token_hex(16);listener=ipc.Listener(name)
        self.assertEqual(listener.sddl,'D:P(A;;GA;;;'+ipc.current_sid()+')')
        errors=[]
        def server():
            channel=None
            try:
                channel=listener.accept(3);self.assertEqual(channel.peer_pid(True),os.getpid())
                message=channel.receive(2);self.assertEqual(message,{'schema':1,'nonce':'fixture'})
                channel.send({'schema':1,'nonce':'fixture'})
            except BaseException as error:errors.append(error)
            finally:
                if channel:channel.close()
        thread=threading.Thread(target=server);thread.start()
        channel=None
        try:
            channel=ipc.connect(name);self.assertEqual(channel.peer_pid(False),os.getpid())
            channel.send({'schema':1,'nonce':'fixture'});self.assertEqual(channel.receive(2),{'schema':1,'nonce':'fixture'})
        finally:
            if channel:channel.close()
            thread.join(5);listener.close()
        self.assertFalse(thread.is_alive());self.assertEqual(errors,[])


if __name__=='__main__':unittest.main()
