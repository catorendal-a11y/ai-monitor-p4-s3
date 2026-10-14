"""Explicit PC/device enrollment over the existing serial owner. Never enables permissions."""
import json
import time
from interaction_auth import EnrollmentHost, number


class UsbEnrollmentClient:
    def __init__(self, panel, store, clock=time.monotonic, sleep=time.sleep):
        self.panel = panel; self.store = store; self.clock = clock; self.sleep = sleep
        self.host = None; self.boot = None; self.deadline = 0

    def begin(self):
        self.close()
        info = self.panel.info
        if (not isinstance(info, dict) or type(info.get('enrollmentProtocol')) is not int
                or info['enrollmentProtocol'] != 1 or not number(info.get('bootId'))):
            raise ValueError('Update display firmware before connecting this PC')
        self.boot = info['bootId']; self.deadline = self.clock() + 60
        self.host = EnrollmentHost(self.clock)
        try:
            reply = self._exchange(self.host.hello(), 'interaction_enrollment')
            if not isinstance(reply, dict) or reply.get('bootId') != self.boot or type(reply.get('bootId')) is not int:
                raise ValueError('Display restarted during enrollment')
            return self.host.offer(reply)
        except (ValueError, OSError, TimeoutError, RuntimeError):
            self.close(); raise ValueError('Open CONNECT PC on the display and retry') from None

    def finish(self, confirmed):
        if confirmed is not True or self.host is None:
            self.close(); raise ValueError('Connection cancelled; no permission enabled')
        try:
            while self.clock() < self.deadline:
                status = self.keep_alive()
                if status['confirmed']:
                    if status['armed'] or status['comparing']: raise ValueError('Ambiguous enrollment status')
                    break
                if not status['comparing'] or status['armed']: raise ValueError('Connection cancelled on display')
                self.sleep(.2)
            else: raise ValueError('Connection timed out')
            # One commit only. A timeout/corrupt reply must never cause a retry.
            reply = self._exchange(self.host.confirmation(True), 'interaction_enrolled')
            record = self.host.finish(reply)
            self.store.save(record)
            if self.store.load() != record: raise ValueError('Protected PC storage could not be verified')
            self.close(cancel=False)
        except (ValueError, OSError, TimeoutError, RuntimeError):
            self.close(); raise ValueError('Connection was not verified; retry setup. Permissions remain disabled') from None

    def keep_alive(self):
        status = self._exchange(dict(cmd='interaction_enroll_status', schema=1), 'interaction_enrollment_status')
        if (not isinstance(status, dict) or set(status) != {'type', 'schema', 'armed', 'comparing', 'confirmed'}
                or status['type'] != 'interaction_enrollment_status' or type(status['schema']) is not int
                or status['schema'] != 1 or any(type(status[key]) is not bool for key in ('armed', 'comparing', 'confirmed'))
                or status['armed'] or status['comparing'] == status['confirmed']):
            raise ValueError('Connection cancelled or invalid on display')
        return status

    def _exchange(self, message, kind):
        if self.host is None or self.clock() >= self.deadline: raise ValueError('Connection timed out')
        # Heartbeat verifies the selected board and catches reboot before accepting any response.
        self.panel.heartbeat()
        if self.panel.info.get('bootId') != self.boot: raise ValueError('Display restarted during enrollment')
        if self.clock() >= self.deadline: raise ValueError('Connection timed out')
        self.panel.send_line(json.dumps(message, separators=(',', ':')))
        return self.panel.wait_for(kind, seconds=min(2., self.deadline - self.clock()))

    def close(self, cancel=True):
        if self.host is not None:
            if cancel:
                try: self.panel.send_line('{"cmd":"interaction_enroll_cancel","schema":1}')
                except (OSError, RuntimeError): pass
            self.host.close()
        self.host = self.boot = None; self.deadline = 0
