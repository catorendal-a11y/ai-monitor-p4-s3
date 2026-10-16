"""Cross-process consent and lifecycle audit regressions; synthetic state only."""
from contextlib import closing
import hashlib,json,os,threading
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
 def test_stale_enabled_startup_cannot_override_saved_disabled_policy(self):
  policy=self.root.parent/(self.root.name+'-synthetic-policy.json')
  self.addCleanup(lambda:policy.unlink(missing_ok=True))
  policy.write_text(json.dumps({'usage_history':False}))
  recorder=HistoryRecorder(self.root,True,policy_path=policy);self.addCleanup(recorder.close)
  recorder.record_tokens({'claude':9});time.sleep(.1);recorder.close()
  with closing(connect(self.root)) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM tokens').fetchone()[0],0)
  self.assertFalse(json.loads((self.root/'agent-history-consent.json').read_text())['enabled'])
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
 def test_revocation_while_initial_epoch_is_pending_cannot_mint_fresh_authority(self):
  import history_consent
  original=history_consent.mint_epoch;entered=threading.Event();resume=threading.Event()
  def delayed(directory,**kwargs):entered.set();resume.wait(2);return original(directory,**kwargs)
  with patch('history_consent.mint_epoch',side_effect=delayed):
   recorder=HistoryRecorder(self.root,True);self.addCleanup(recorder.close)
   try:
    self.assertTrue(entered.wait(2));history.revoke(self.root)
    recorder.record_tokens({'claude':5});resume.set();time.sleep(.1);recorder.close()
   finally:resume.set()
  with closing(connect(self.root)) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM tokens').fetchone()[0],0)
  self.assertFalse(json.loads((self.root/'agent-history-consent.json').read_text())['enabled'])
 def test_constructor_contains_unavailable_authority_and_keeps_host_caller_responsive(self):
  with patch('history_consent.mint_epoch',side_effect=OSError('synthetic unavailable store')):
   recorder=HistoryRecorder(self.root,True);self.addCleanup(recorder.close)
   deadline=time.monotonic()+2
   while recorder.last_error is None and time.monotonic()<deadline:time.sleep(.01)
   self.assertIsNotNone(recorder.last_error)
   self.assertTrue(recorder.worker.is_alive())
   recorder.close()
 def test_constructor_and_reenable_never_wait_for_authority_on_caller(self):
  entered=threading.Event();release=threading.Event()
  import history_consent
  original=history_consent.mint_epoch
  def slow(directory,**kwargs):entered.set();release.wait(2);return original(directory,**kwargs)
  with patch('history_consent.mint_epoch',side_effect=slow):
   start=time.monotonic();recorder=HistoryRecorder(self.root,True)
   try:
    self.assertLess(time.monotonic()-start,.15)
    self.assertTrue(entered.wait(2))
   finally:release.set();recorder.close()
  recorder=HistoryRecorder(self.root,False);self.addCleanup(recorder.close)
  entered.clear();release.clear()
  with patch('history_consent.mint_epoch',side_effect=slow):
   try:
    start=time.monotonic();recorder.configure(True)
    self.assertLess(time.monotonic()-start,.15)
   finally:release.set();recorder.close()
 def test_authority_lock_contention_keeps_hook_bounded(self):
  from history_consent import lock
  entered=threading.Event();release=threading.Event()
  def held():
   with lock(self.root):entered.set();release.wait(2)
  worker=threading.Thread(target=held);worker.start()
  try:
   self.assertTrue(entered.wait(2));start=time.monotonic()
   history.record(self.root,'claude',self.agent,7,'Stop','COMPLETED',10,True)
   self.assertLess(time.monotonic()-start,.15)
  finally:release.set();worker.join(2)
  with closing(connect(self.root)) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM agent_events').fetchone()[0],0)
 def test_saved_disabled_policy_blocks_hooks_and_policy_write_failure_stays_revoked(self):
  from history_consent import policy_update
  import private_files
  store=self.root/'tools/activity';store.mkdir(parents=True)
  with closing(connect(store,True)):pass
  history.configure(store,True,17)
  policy=self.root/'tools/aim_host.json';policy.write_text(json.dumps({'usage_history':False}))
  history.record(store,'claude',self.agent,7,'Stop','COMPLETED',10,True)
  with closing(connect(store)) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM agent_events').fetchone()[0],0)
  with self.assertRaises(OSError):
   with policy_update(self.root,enabled=False):raise OSError('synthetic saved-file failure')
  history.record(self.root,'claude',self.agent,7,'Stop','COMPLETED',10,True)
  with closing(connect(self.root)) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM agent_events').fetchone()[0],0)
 def test_durable_floor_blocks_hooks_if_disabled_marker_write_fails(self):
  import private_files
  original=private_files.write_bytes
  def fail_marker(path,data):
   if Path(path).name=='agent-history-consent.json':raise OSError('synthetic marker failure')
   return original(path,data)
  with patch.object(private_files,'write_bytes',side_effect=fail_marker):
   with self.assertRaises(OSError):history.revoke(self.root)
  self.assertTrue(json.loads((self.root/'agent-history-consent.json').read_text())['enabled'])
  history.record(self.root,'claude',self.agent,7,'Stop','COMPLETED',10,True)
  with closing(connect(self.root)) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM agent_events').fetchone()[0],0)
 def test_policy_update_new_parent_preserves_missing_activity_directory(self):
  from history_consent import policy_update
  folder=self.root/'new-parent/activity'
  with policy_update(folder):self.assertFalse(folder.exists())
  self.assertFalse(folder.exists())
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
