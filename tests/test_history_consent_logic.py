"""Cross-process consent and lifecycle audit regressions; synthetic state only."""
from contextlib import closing
import hashlib,json,os
from pathlib import Path
import subprocess,sys,tempfile,time,unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import agent_history as history
from usage_history import HistoryRecorder,connect,read_history

class ConsentLogicTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
  with closing(connect(self.root,True)):pass
  history.configure(self.root,True,17)
  self.agent=hashlib.sha256(b'synthetic').hexdigest()
 def task(self,session,use,name='TaskUpdate'):
  if name=='TaskCreate':return dict(hook_event_name='PostToolUse',session_id=session,tool_use_id=use,tool_name=name,tool_input={},tool_response={'task':{'id':'1'}})
  return dict(hook_event_name='PostToolUse',session_id=session,tool_use_id=use,tool_name=name,tool_input={'taskId':'1','status':'completed'},tool_response={'success':True,'taskId':'1','statusChange':{'from':'in_progress','to':'completed'}})
 def wait_marker(self,predicate):
  deadline=time.monotonic()+3
  while time.monotonic()<deadline:
   try:
    v=json.loads((self.root/'agent-history-consent.json').read_text())
    if predicate(v):return v
   except OSError:pass
   time.sleep(.01)
  self.fail('Marker did not settle')
 def test_revocation_blocks_old_recorder_and_numeric_queue_until_explicit_reenable(self):
  recorder=HistoryRecorder(self.root,True);self.addCleanup(recorder.close)
  self.wait_marker(lambda m:m['epoch']==recorder.epoch)
  history.revoke(self.root)
  recorder.record_tokens({'claude':7});time.sleep(.15)
  marker=json.loads((self.root/'agent-history-consent.json').read_text())
  self.assertFalse(marker['enabled'])
  with closing(connect(self.root)) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM tokens').fetchone()[0],0)
  recorder.configure(False);recorder.configure(True)
  self.wait_marker(lambda m:m['enabled'])
  recorder.record_tokens({'claude':3});recorder.close()
  with closing(connect(self.root)) as db:self.assertEqual(db.execute('SELECT SUM(tokens) FROM tokens').fetchone()[0],3)
 def test_cross_process_revocation_cannot_be_undone_by_stale_recorder(self):
  code="""import sys,time,json
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from usage_history import HistoryRecorder
r=HistoryRecorder(Path(sys.argv[2]),True)
while not (Path(sys.argv[2])/'agent-history-consent.json').exists():time.sleep(.01)
time.sleep(.05)
print('ready',flush=True)
sys.stdin.readline()
r.record_tokens({'claude':9});time.sleep(.1);r.close()
"""
  child=subprocess.Popen([sys.executable,'-c',code,str(Path(history.__file__).parent),str(self.root)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
  self.assertEqual(child.stdout.readline().strip(),'ready')
  history.revoke(self.root)
  out,err=child.communicate('continue\n',timeout=10)
  self.assertEqual(child.returncode,0,err)
  with closing(connect(self.root)) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM tokens').fetchone()[0],0)
 def test_lease_refresh_same_epoch_does_not_drop_agent_or_task_event(self):
  original=history.read_local_json
  def refreshed(path,limit):
   value=original(path,limit)
   if Path(path).name=='agent-history-consent.json':history.configure(self.root,True,value['epoch'])
   return value
  with patch.object(history,'read_local_json',side_effect=refreshed):
   history.record(self.root,'claude',self.agent,7,'Stop','COMPLETED',10,True)
   history.observe_task(self.root,self.task('s','u'),7,10)
  with closing(connect(self.root)) as db:
   self.assertEqual(db.execute('SELECT COUNT(*) FROM agent_events').fetchone()[0],1)
   self.assertEqual(db.execute('SELECT COUNT(*) FROM task_events').fetchone()[0],1)
 def test_task_identity_uses_config_root_and_effective_task_list(self):
  config=str(self.root/'synthetic-config')
  with patch.dict(os.environ,{'CLAUDE_CONFIG_DIR':config,'CLAUDE_CODE_TASK_LIST_ID':'shared'}):
   history.observe_task(self.root,self.task('session-a','a'),7,10)
   history.observe_task(self.root,self.task('session-b','b'),7,20)
  with closing(connect(self.root)) as db:self.assertEqual(history.task_summary(db,'claude',0,100)['completedTasks'],1)
  for i in range(2):
   with patch.dict(os.environ,{'CLAUDE_CONFIG_DIR':config,'CLAUDE_CODE_TASK_LIST_ID':'list-'+str(i)}):
    history.observe_task(self.root,self.task('resumed-session',str(i),'TaskCreate'),7,30+i)
  with closing(connect(self.root)) as db:self.assertEqual(history.task_summary(db,'claude',0,100)['createdTasks'],2)
  with patch.dict(os.environ,{'CLAUDE_CONFIG_DIR':str(self.root/'other-config'),'CLAUDE_CODE_TASK_LIST_ID':'list-0'}):
   history.observe_task(self.root,self.task('resumed-session','other','TaskCreate'),7,40)
  with closing(connect(self.root)) as db:self.assertEqual(history.task_summary(db,'claude',0,100)['createdTasks'],3)
 def test_cancel_and_session_end_close_activity_without_outcome_evidence(self):
  for terminal,state in [('Interrupt','IDLE'),('SessionEnd','closed')]:
   with self.subTest(event=terminal):
    with closing(connect(self.root,True)) as db,db:db.execute('DELETE FROM agent_events')
    history.record(self.root,'claude',self.agent,7,'UserPromptSubmit','WORKING',10,True)
    history.record(self.root,'claude',self.agent,7,terminal,state,20,True)
    with closing(connect(self.root)) as db:result=history.summarize(db,'claude',0,100)
    self.assertEqual(result['activeSeconds'],10)
    self.assertIsNone(result['completedTurns']);self.assertIsNone(result['failedTurns'])

if __name__=='__main__':unittest.main()
