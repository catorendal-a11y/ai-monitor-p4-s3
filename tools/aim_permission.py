"""Dedicated Claude PermissionRequest helper. No observer, shell, network or config writes."""
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sys
import time
import psutil
from permission_ipc import connect,current_sid


def request_from_hook(payload):
    if not isinstance(payload,dict) or payload.get('hook_event_name')!='PermissionRequest':raise ValueError('Not a permission request')
    tool=payload.get('tool_name');arguments=payload.get('tool_input')
    if not isinstance(tool,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',tool) or not isinstance(arguments,dict):raise ValueError('Unsupported request')
    # Review all arguments, not a potentially misleading description. Long/non-ASCII requests
    # fall back to Claude's normal dialog instead of granting a partly visible request.
    hint=json.dumps(arguments,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
    if not 1<=len(hint)<=320 or any(ord(c)<32 or ord(c)>126 for c in hint):raise ValueError('Request not physically reviewable')
    return dict(schema=1,requestId=secrets.token_hex(16),nonce=secrets.token_hex(32),revision=1,
                tool=tool,hint=hint,expiresInMs=25000)


def decision_output(request,response,instance):
    if (not isinstance(response,dict) or set(response)!={'schema','instance','requestId','nonce','revision','decision'} or
            type(response['schema']) is not int or response['schema']!=1 or
            response['instance']!=instance or response['requestId']!=request['requestId'] or
            response['nonce']!=request['nonce'] or type(response['revision']) is not int or
            response['revision']!=request['revision'] or response['decision'] not in ('allow','deny')):raise ValueError('Uncorrelated decision')
    return {'hookSpecificOutput':{'hookEventName':'PermissionRequest','decision':{'behavior':response['decision']}}}


def exchange(root,request):
    # This is the helper's sole fixed file read; it never follows paths from the hook input.
    from host_security import read_local_json
    root=root.resolve();endpoint_file=root/'tools/permission-endpoint.json'
    if endpoint_file.is_symlink() or endpoint_file.resolve().parent!=root/'tools':raise ValueError('Invalid endpoint location')
    endpoint=read_local_json(endpoint_file,2048)
    if (not isinstance(endpoint,dict) or set(endpoint)!={'schema','pid','instance'} or type(endpoint['schema']) is not int or
            endpoint['schema']!=1 or type(endpoint['pid']) is not int or not 0<endpoint['pid']<2**32 or
            not isinstance(endpoint['instance'],str) or not re.fullmatch(r'[0-9a-f]{32}',endpoint['instance'])):raise ValueError('Invalid permission host')
    identity=str(root.resolve()).casefold()+'|'+current_sid()
    name='ai-monitor-permission-'+hashlib.sha256(identity.encode()).hexdigest()[:32]
    deadline=time.monotonic()+request['expiresInMs']/1000
    channel=connect(name)
    try:
        pid=channel.peer_pid(False)
        if pid!=endpoint['pid'] or Path(psutil.Process(pid).exe()).resolve()!=(root/'AI-Monitor-Console.exe').resolve():raise ValueError('Wrong host instance')
        channel.send(dict(request,instance=endpoint['instance']))
        remaining=deadline-time.monotonic()
        if remaining<=0:raise TimeoutError('Permission expired')
        response=channel.receive(remaining)
        if time.monotonic()>=deadline:raise TimeoutError('Permission expired')
        return decision_output(request,response,endpoint['instance'])
    finally:channel.close()


def main():
    try:
        if sys.argv[1:]==['--check']:return 0
        if sys.argv[1:] or os.name!='nt':return 0
        raw=sys.stdin.buffer.read(65537)
        # Parse larger hook envelopes, but never retain their transcript/prompt metadata.
        if len(raw)>65536:return 0
        def pairs(items):
            data={}
            for key,value in items:
                if key in data:raise ValueError('Duplicate hook field')
                data[key]=value
            return data
        payload=json.loads(raw,object_pairs_hook=pairs)
        request=request_from_hook(payload)
        root=Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[1]
        result=exchange(root,request)
        sys.stdout.write(json.dumps(result,separators=(',',':'))+'\n')
    except (ValueError,OSError,TypeError,RecursionError,TimeoutError,EOFError,psutil.Error):pass
    # Empty stdout is Claude's normal permission fallback. Never synthesize an allow.
    return 0


if __name__=='__main__':sys.exit(main())
