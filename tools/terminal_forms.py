"""Keyboard-friendly native terminal forms; cancel never saves or runs an action."""
from textual.app import ComposeResult
from textual.containers import Horizontal,Vertical,VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button,Input,Select,Static,Switch
from board_profiles import BOARDS
from provider_catalog import PROVIDERS
from host_status import FLAGS,OPTIONS
from host_security import serial_port


class ActionForm(ModalScreen):
    DEFAULT_CSS='''
    ActionForm { align: center middle; background: #000000 60%; }
    ActionForm > Vertical { width: 90%; max-width: 100; height: 90%; border: round #35d07f; background: #11191d; padding: 1 2; }
    ActionForm VerticalScroll { height: 1fr; }
    ActionForm Static { height: auto; margin-bottom: 1; }
    ActionForm Input, ActionForm Select { margin-bottom: 1; }
    ActionForm Horizontal { height: 3; align: right middle; }
    ActionForm Button { margin-left: 1; }
    '''
    BINDINGS=[('escape','cancel','Cancel')]

    def __init__(self,title,fields=(),note='',confirm=None,validator=None):
        super().__init__();self.caption=title;self.fields=list(fields);self.note=note;self.confirm=confirm;self.validator=validator
        if confirm:self.fields.append(('confirm','Type '+confirm+' to confirm','text','',None))

    def compose(self)->ComposeResult:
        with Vertical():
            yield Static(self.caption,markup=False)
            with VerticalScroll():
                yield Static(self.note,markup=False)
                for key,label,kind,value,choices in self.fields:
                    yield Static(label,markup=False)
                    if kind=='bool':yield Switch(bool(value),id='field-'+key)
                    elif kind=='select':yield Select(choices,value=value if value is not None and value!='' else Select.NULL,id='field-'+key)
                    else:yield Input(str(value or ''),password=kind=='secret',id='field-'+key)
            yield Static('',id='form-error',markup=False)
            with Horizontal():
                yield Button('Cancel',id='cancel')
                yield Button('Continue',id='submit',variant='success')

    def on_mount(self):self.query_one('#cancel',Button).focus()

    def action_cancel(self):
        self.scrub();self.dismiss(None)

    def scrub(self):
        for key,_,kind,_,_ in self.fields:
            if kind=='secret':self.query_one('#field-'+key,Input).value=''

    def on_button_pressed(self,event):
        event.stop()
        if event.button.id=='cancel':self.action_cancel();return
        values={}
        for key,_,kind,_,_ in self.fields:
            value=self.query_one('#field-'+key).value
            values[key]=None if value is Select.NULL else value
        if self.confirm and values.get('confirm')!=self.confirm:
            self.query_one('#form-error',Static).update('Confirmation did not match. Nothing was changed.')
            self.query_one('#field-confirm').focus();return
        error=self.validator(values) if self.validator else None
        if error:
            key,message=error
            self.query_one('#form-error',Static).update(message+' Nothing was saved.')
            self.query_one('#field-'+key).focus();return
        self.scrub();self.dismiss(values)


FLAG_LABELS={'start_host_at_login':'Start at Windows sign-in (adds a Startup entry for this user)'}


def settings_form(settings):
    fields=[('board','Display board','select',settings.get('board'),[(b.name,b.id) for b in BOARDS.values()]),
            ('port','USB port (auto or explicit COM port)','text',settings.get('port','auto'),None),
            ('interval','Quota refresh seconds (15–240)','text',settings.get('interval_s',30),None)]
    fields += [('provider-'+key,name,'bool',key in settings.get('providers',[]),None) for key,(name,_,_) in PROVIDERS.items()]
    fields += [('key','Optional Z.AI key (empty keeps saved key)','secret','',None),
               ('clear_key','Clear saved Z.AI key','bool',False,None)]
    fields += [('option-'+key,key.replace('_',' ').title(),'text',settings.get(key,limits[2]),None) for key,limits in OPTIONS.items()]
    fields += [('option-'+key,FLAG_LABELS.get(key) or (key.replace('_',' ').title()+' (desktop preference)' if key in ('start_host_on_open','keep_host_on_close','minimize_to_tray','close_to_tray') else key.replace('_',' ').title()),
                'bool',settings.get(key,default),None) for key,default in FLAGS.items() if key!='usb_permissions']
    return ActionForm('SETTINGS / BOARD / PROVIDERS',fields,
        'Save applies the same validation and protected storage as the desktop app. Cancel preserves everything. Physical AI approval remains disabled.',
        validator=validate_settings_fields)


def validate_settings_fields(fields):
    """Local draft checks only; the shared save action remains authoritative."""
    if fields.get('board') not in BOARDS:return 'board','Choose a display board.'
    try:serial_port(fields.get('port'))
    except ValueError:return 'port','Use auto, a COM port or a /dev/ serial device.'
    for key,label,low,high in [('interval','Quota refresh',15,240)]+[
            ('option-'+key,key.replace('_',' ').title(),limits[0],limits[1]) for key,limits in OPTIONS.items()]:
        try:value=int(fields[key])
        except (ValueError,TypeError,KeyError):return key,f'{label} must be a whole number between {low} and {high}.'
        if not low<=value<=high:return key,f'{label} must be between {low} and {high}.'
    if not any(fields.get('provider-'+key) is True for key in PROVIDERS):
        return 'provider-'+next(iter(PROVIDERS)),'Choose at least one AI provider.'
    return None


def settings_values(fields):
    return dict(board=fields['board'],port=fields['port'],interval=fields['interval'],
        providers=[key for key in PROVIDERS if fields.get('provider-'+key) is True],
        key=fields['key'],clear_key=fields['clear_key'],
        options={key: int(fields['option-'+key]) if key in OPTIONS else fields['option-'+key]
                 for key in set(OPTIONS)| (set(FLAGS)-{'usb_permissions'})})


class ResultScreen(ModalScreen):
    DEFAULT_CSS='''
    ResultScreen { align: center middle; background: #000000 60%; }
    ResultScreen > Vertical { width: 95%; height: 90%; border: round #35d07f; padding: 1 2; background: #11191d; }
    ResultScreen VerticalScroll { height: 1fr; }
    ResultScreen Static { height: auto; }
    ResultScreen Button { height: 3; }
    '''
    BINDINGS=[('escape','close','Close')]
    def __init__(self,title,content):super().__init__();self.caption=title;self.content=content
    def compose(self):
        with Vertical():
            yield Static(self.caption,markup=False)
            with VerticalScroll():yield Static(self.content,markup=False)
            yield Button('Close',id='close')
    def action_close(self):self.dismiss(None)
    def on_button_pressed(self,event):event.stop();self.action_close()
