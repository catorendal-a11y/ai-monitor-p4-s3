"""Read-only, bounded capture through the existing USB serial owner."""
import base64
import json
import re
import secrets
import struct
import time

WIDTH, HEIGHT, CHUNK, CHUNKS = 800, 480, 640, 600
BYTES = WIDTH * HEIGHT * 2


def decode_chunk(encoded):
    if not isinstance(encoded, str) or not 4 <= len(encoded) <= 3416:
        raise ValueError('Invalid mirror chunk')
    try: raw = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError): raise ValueError('Invalid mirror encoding') from None
    if not raw or len(raw) > 2560 or len(raw) % 4:
        raise ValueError('Invalid mirror run data')
    output = bytearray()
    for run, color in struct.iter_unpack('<HH', raw):
        if not 1 <= run <= CHUNK or len(output) + run * 2 > CHUNK * 2:
            raise ValueError('Invalid mirror run length')
        output.extend(struct.pack('<H', color) * run)
    if len(output) != CHUNK * 2: raise ValueError('Incomplete mirror chunk')
    return output


class UsbMirrorClient:
    def __init__(self, panel, request_id=None, clock=time.monotonic):
        self.panel, self.clock = panel, clock
        self.request_id = request_id or secrets.token_hex(16)
        if not re.fullmatch('[0-9a-f]{32}', self.request_id): raise ValueError('Invalid capture ID')
        self.frame_id = None
        self.index = 0
        self.pixels = bytearray()
        self.started = clock()
        self.captured_at = time.time()
        self.done = False
        self.waiting = False

    def _request(self, command, **fields):
        message = dict(cmd=command, requestId=self.request_id, **fields)
        if self.frame_id is not None: message['frameId'] = self.frame_id
        self.panel.send_line(json.dumps(message, separators=(',', ':')))
        reply = self.panel.wait_for('mirror', seconds=.4, command=command)
        if reply.get('requestId') != self.request_id: raise ValueError('Uncorrelated mirror response')
        frame = reply.get('frameId')
        if type(frame) is not int or not 0 < frame <= 0xffffffff:
            raise ValueError('Invalid mirror frame')
        if self.frame_id is not None and frame != self.frame_id:
            raise ValueError('Mirror frame changed')
        if reply.get('state') not in ('capturing', 'ready', 'closed'):
            raise RuntimeError('Device screen capture is unavailable')
        if command != 'mirror_end':
            expected = dict(width=WIDTH, height=HEIGHT, pixelsPerChunk=CHUNK, chunks=CHUNKS,
                            encoding='rle565le-base64')
            if any(reply.get(key) != value or (type(value) is int and type(reply.get(key)) is not int)
                   for key, value in expected.items()): raise ValueError('Invalid mirror dimensions')
        self.frame_id = frame
        return reply

    def step(self):
        if self.done: return True
        if self.clock() - self.started > 110: raise TimeoutError('Device capture timed out')
        self.waiting = False
        if self.frame_id is None:
            self.waiting = True
            self._request('mirror_begin')
            return False
        if self.index == CHUNKS:
            self._request('mirror_end')
            self.done = True
            return True
        if self.index == 0:
            reply = self._request('mirror_status')
            if reply['state'] != 'ready':
                self.waiting = True
                return False
        reply = self._request('mirror_chunk', index=self.index)
        if reply['state'] != 'ready' or type(reply.get('index')) is not int or reply['index'] != self.index:
            raise ValueError('Uncorrelated mirror chunk')
        self.pixels.extend(decode_chunk(reply.get('data')))
        self.index += 1
        return False

    def cancel(self):
        if self.frame_id is not None and not self.done:
            # Release without waiting; no retry or second serial owner.
            self.panel.send_line(json.dumps(dict(cmd='mirror_end', requestId=self.request_id, frameId=self.frame_id)))
        self.pixels.clear()
        self.done = True
