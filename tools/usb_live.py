"""Read-only live metadata through the existing serial owner; never provider tool decisions."""
import json
import re
from provider_catalog import PROVIDERS

STATES = frozenset(('UNKNOWN', 'IDLE', 'THINKING', 'EDITING', 'SEARCHING', 'BUILDING',
                    'TESTING', 'WAITING', 'FAILED', 'DONE', 'WORKING', 'READING', 'WRITING',
                    'RUNNING', 'NEEDS_ATTENTION', 'ERROR', 'COMPLETED'))
MAX_VALUE = (1 << 32) - 1


def integer(value):
    return type(value) is int and 0 <= value <= MAX_VALUE


LABEL = re.compile(r'[A-Za-z]+(?: [A-Za-z]+)*')
MAX_LABEL = 15      # the device label buffer
HUES = 12           # colors the device can draw
SUMMARY_KEYS = frozenset(('total', 'selected', 'linked'))


def validate_summary(summary, count):
    """Totals beyond the eight listed agents, and which AIs have observers: small bounded integers."""
    if not isinstance(summary, dict) or set(summary) != SUMMARY_KEYS:
        raise ValueError('Live summary contains unsupported fields')
    for key in SUMMARY_KEYS:
        if type(summary[key]) is not int or not 0 <= summary[key] <= 255:
            raise ValueError('Invalid live summary value')
    if summary['total'] < count:
        raise ValueError('Live summary total is smaller than the listed agents')
    return dict(summary)


def validate_agents(agents):
    if not isinstance(agents, list) or len(agents) > 8:
        raise ValueError('Live snapshots support at most eight agents')
    output, seen = [], set()
    for agent in agents:
        if (not isinstance(agent, dict) or not {'provider','id','state'} <= set(agent) or
                set(agent)-{'provider','id','state','elapsedSeconds','observedAgeSeconds','label','hue'}):
            raise ValueError('Live metadata contains unsupported fields')
        provider, identifier, state = agent['provider'], agent['id'], agent['state']
        if (not isinstance(provider, str) or provider not in PROVIDERS or
                not isinstance(identifier, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', identifier) or
                not isinstance(state, str) or state not in STATES):
            raise ValueError('Invalid live metadata')
        identity = (provider, identifier)
        if identity in seen:
            raise ValueError('Duplicate live agent identity')
        seen.add(identity)
        row=dict(provider=provider, id=identifier, state=state)
        for key,limit in (('elapsedSeconds',604800),('observedAgeSeconds',900)):
            if key in agent:
                if not integer(agent[key]) or agent[key]>limit:raise ValueError('Invalid live timing')
                row[key]=agent[key]
        if 'label' in agent:
            label=agent['label']
            if not isinstance(label,str) or len(label)>MAX_LABEL or not LABEL.fullmatch(label):raise ValueError('Invalid live name')
            row['label']=label
        if 'hue' in agent:
            if type(agent['hue']) is not int or not 0<=agent['hue']<HUES:raise ValueError('Invalid live color')
            row['hue']=agent['hue']
        output.append(row)
    return output


class UsbLiveClient:
    """Read-only live delivery, called only by the normal host's existing serial owner.

    No retries after ambiguous delivery. Reopen explicitly and republish a complete snapshot.
    No provider calls, model turns, USB discovery or additional serial connection.
    """
    def __init__(self, panel):
        self.panel = panel
        self.epoch = None
        self.sequence = 0
        self.request_id = 0
        self.boot_id = None

    def open(self):
        self.epoch = None
        info = self.panel.info
        if (not isinstance(info, dict) or type(info.get('liveProtocol')) is not int or
                info['liveProtocol'] != 1 or info.get('livePermissions') is not False or
                not integer(info.get('bootId')) or self.request_id == MAX_VALUE):
            raise ValueError('Panel does not support read-only USB live protocol')
        self.boot_id = info['bootId']
        self.request_id += 1
        reply = self._exchange(dict(cmd='live_open', schema=1, requestId=self.request_id))
        if (reply['requestId'] != self.request_id or not reply['epoch'] or reply['sequence'] != 0):
            raise ValueError('Uncorrelated live session reply')
        self.epoch, self.sequence = reply['epoch'], 0

    def send(self, agents, summary=None):
        agents = validate_agents(agents)
        summary = None if summary is None else validate_summary(summary, len(agents))
        extended = self.panel.info.get('liveSummary') == 1
        if not extended:
            # Firmware without liveSummary rejects unknown fields and would drop the whole snapshot.
            agents = [{key: value for key, value in row.items() if key not in ('label', 'hue')} for row in agents]
            summary = None
        if self.panel.info.get('liveMetadata')!=2:
            legacy={'WORKING':'UNKNOWN','READING':'UNKNOWN','WRITING':'EDITING','RUNNING':'UNKNOWN',
                    'NEEDS_ATTENTION':'WAITING','ERROR':'FAILED','COMPLETED':'DONE'}
            agents=[dict(provider=row['provider'],id=row['id'],state=legacy.get(row['state'],row['state'])) for row in agents]
        if self.epoch is None or self.sequence == MAX_VALUE:
            raise ValueError('Open a new USB live session before sending')
        epoch, sequence = self.epoch, self.sequence + 1
        try:
            message = dict(cmd='live_state', schema=1, bootId=self.boot_id, epoch=epoch, sequence=sequence, agents=agents)
            if summary is not None:
                message.update(total=summary['total'], selectedMask=summary['selected'], linkedMask=summary['linked'])
            reply = self._exchange(message)
            if reply['epoch'] != epoch or reply['sequence'] != sequence or reply['requestId'] != 0:
                raise ValueError('Uncorrelated live snapshot reply')
        except (ValueError, OSError, TimeoutError, RuntimeError):
            self.epoch = None
            raise
        self.sequence = sequence

    def close(self):
        epoch, self.epoch = self.epoch, None
        if epoch is not None:
            reply = self._exchange(dict(cmd='live_close', schema=1, bootId=self.boot_id, epoch=epoch))
            if reply['epoch'] != epoch or reply['sequence'] != self.sequence or reply['requestId'] != 0:
                raise ValueError('Uncorrelated live close reply')

    def _exchange(self, message):
        raw = json.dumps(message, ensure_ascii=True, separators=(',', ':'), allow_nan=False)
        if len(raw.encode('ascii')) > 4095:
            raise ValueError('USB live message exceeds frame limit')
        self.panel.send_line(raw)
        reply = self.panel.wait_for('live_reply', command=message['cmd'])
        fields = {'type', 'schema', 'cmd', 'ok', 'bootId', 'epoch', 'sequence', 'permissions', 'requestId'}
        if (not isinstance(reply, dict) or set(reply) != fields or reply['type'] != 'live_reply' or
                reply['cmd'] != message['cmd'] or type(reply['schema']) is not int or reply['schema'] != 1 or
                reply['ok'] is not True or reply['permissions'] is not False or
                any(not integer(reply[key]) for key in ('bootId', 'epoch', 'sequence', 'requestId')) or
                reply['bootId'] != self.boot_id):
            raise ValueError('Invalid USB live reply')
        return reply
