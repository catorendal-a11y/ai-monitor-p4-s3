"""USB interaction authentication. No I/O, settings writes or permission decisions.

ECDH enrollment requires the same 64-bit comparison code on PC and physical device.
Normal sessions mutually prove the enrolled key, then authenticate direction/sequence/body.
This module never treats attachment, device metadata or an incoming boolean as authority.
"""
from dataclasses import dataclass, field
import hashlib
import hmac
import json
import re
import secrets
import struct
import time

MAX_BODY = 1024
MAX_SEQUENCE = 0xffffffff


def hex_text(value, size):
    return isinstance(value, str) and re.fullmatch(r'[0-9a-f]{%d}' % size, value) is not None


def number(value, maximum=MAX_SEQUENCE):
    return type(value) is int and 0 < value <= maximum


def mac(key, data):
    if not isinstance(key, bytes) or len(key) != 32:
        raise ValueError('Invalid interaction key')
    return hmac.digest(key, data, 'sha256')


def proof(key, label, transcript):
    return mac(key, label.encode('ascii') + b'\0' + transcript)


def session_transcript(device, instance, host_nonce, device_nonce, boot, epoch):
    if (not hex_text(device, 32) or not hex_text(instance, 32)
            or not hex_text(host_nonce, 64) or not hex_text(device_nonce, 64)
            or not number(boot) or not number(epoch)):
        raise ValueError('Invalid interaction transcript')
    return (b'AIM-AUTH-1\0' + (device + instance + host_nonce + device_nonce).encode('ascii')
            + struct.pack('>II', boot, epoch))


def packet_input(direction, session, sequence, body):
    if (direction not in ('host', 'device') or not hex_text(session, 64)
            or not number(sequence) or not isinstance(body, str)
            or not 1 <= len(body) <= MAX_BODY or any(not 32 <= ord(c) <= 126 for c in body)):
        raise ValueError('Invalid interaction packet')
    return (b'AIM-PACKET-1\0' + direction.encode('ascii') + b'\0' + session.encode('ascii')
            + struct.pack('>IH', sequence, len(body)) + body.encode('ascii'))


def strict_body(raw):
    if not isinstance(raw, str) or not 1 <= len(raw) <= MAX_BODY:
        raise ValueError('Invalid interaction body')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result: raise ValueError('Duplicate interaction field')
            result[key] = value
        return result
    value = json.loads(raw, object_pairs_hook=pairs,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Invalid number')))
    if not isinstance(value, dict): raise ValueError('Interaction body must be an object')
    canonical = json.dumps(value, ensure_ascii=True, separators=(',', ':'), allow_nan=False)
    if canonical != raw: raise ValueError('Noncanonical interaction body')
    return value


@dataclass(frozen=True)
class TrustRecord:
    device_id: str
    key: bytes = field(repr=False)

    def __post_init__(self):
        if (not hex_text(self.device_id, 32) or not isinstance(self.key, bytes)
                or len(self.key) != 32 or self.key == bytes(32)):
            raise ValueError('Invalid enrolled device')


class SessionHost:
    """Serial-owner only. Authentication expires; ambiguous/corrupt traffic closes once."""
    def __init__(self, trust, instance, boot_id, clock=time.monotonic):
        if not isinstance(trust, TrustRecord) or not hex_text(instance, 32) or not number(boot_id):
            raise ValueError('Invalid interaction host')
        self._trust = trust; self.instance = instance; self.boot_id = boot_id; self._clock = clock
        self.host_nonce = secrets.token_hex(32)
        self.session = None; self._key = None; self._transcript = None
        self.authenticated = False; self.tx = self.rx = 0
        self._deadline = clock() + 3

    def hello(self):
        return dict(cmd='interaction_open', schema=1, deviceId=self._trust.device_id,
                    instance=self.instance, hostNonce=self.host_nonce)

    def challenge(self, reply):
        try:
            fields = {'type', 'schema', 'deviceId', 'instance', 'hostNonce', 'deviceNonce', 'bootId', 'epoch', 'proof'}
            if (self.authenticated or self._transcript is not None or self._clock() >= self._deadline
                    or not isinstance(reply, dict) or set(reply) != fields or reply['type'] != 'interaction_challenge'
                    or type(reply['schema']) is not int or reply['schema'] != 1
                    or reply['deviceId'] != self._trust.device_id or reply['instance'] != self.instance
                    or reply['hostNonce'] != self.host_nonce or reply['bootId'] != self.boot_id
                    or not hex_text(reply['proof'], 64)):
                raise ValueError('Invalid interaction challenge')
            transcript = session_transcript(reply['deviceId'], self.instance, self.host_nonce,
                                            reply['deviceNonce'], reply['bootId'], reply['epoch'])
            if not hmac.compare_digest(proof(self._trust.key, 'device', transcript).hex(), reply['proof']):
                raise ValueError('Device authentication failed')
            self._transcript = transcript
            self.session = proof(self._trust.key, 'session', transcript).hex()
            self._key = proof(self._trust.key, 'key', transcript)
            return dict(cmd='interaction_prove', schema=1, session=self.session,
                        proof=proof(self._trust.key, 'host', transcript).hex())
        except (ValueError, TypeError, KeyError):
            self.close(); raise ValueError('Interaction authentication failed') from None

    def ready(self, reply):
        try:
            if (self.authenticated or self._key is None or self._clock() >= self._deadline
                    or not isinstance(reply, dict) or set(reply) != {'type', 'schema', 'session', 'proof'}
                    or reply['type'] != 'interaction_ready' or type(reply['schema']) is not int or reply['schema'] != 1
                    or reply['session'] != self.session or not hex_text(reply['proof'], 64)
                    or not hmac.compare_digest(proof(self._key, 'ready', self.session.encode()).hex(), reply['proof'])):
                raise ValueError('Invalid interaction confirmation')
            self.authenticated = True; self._deadline = self._clock() + 5
        except (ValueError, TypeError, KeyError):
            self.close(); raise ValueError('Interaction authentication failed') from None

    def encode(self, body):
        try:
            if not self.alive() or not isinstance(body, dict) or self.tx >= MAX_SEQUENCE:
                raise ValueError('Interaction session unavailable')
            raw = json.dumps(body, ensure_ascii=True, separators=(',', ':'), allow_nan=False)
            strict_body(raw)
            self.tx += 1  # Reserve before serial write; a failed write is never retried.
            signature = mac(self._key, packet_input('host', self.session, self.tx, raw)).hex()
            return dict(cmd='interaction', schema=1, session=self.session, sequence=self.tx, body=raw, mac=signature)
        except (ValueError, TypeError, RecursionError):
            self.close(); raise ValueError('Interaction packet rejected') from None

    def decode(self, packet):
        try:
            fields = {'type', 'schema', 'session', 'sequence', 'body', 'mac'}
            if (not self.alive() or not isinstance(packet, dict) or set(packet) != fields
                    or packet['type'] != 'interaction_packet' or type(packet['schema']) is not int or packet['schema'] != 1
                    or packet['session'] != self.session or not number(packet['sequence'])
                    or packet['sequence'] != self.rx + 1 or not hex_text(packet['mac'], 64)):
                raise ValueError('Invalid interaction packet')
            signature = mac(self._key, packet_input('device', self.session, packet['sequence'], packet['body'])).hex()
            if not hmac.compare_digest(signature, packet['mac']): raise ValueError('Interaction signature mismatch')
            body = strict_body(packet['body'])
            self.rx = packet['sequence']; self._deadline = self._clock() + 5
            return body
        except (ValueError, TypeError, KeyError, RecursionError):
            self.close(); raise ValueError('Interaction packet rejected') from None

    def alive(self):
        if not self.authenticated or self._clock() >= self._deadline:
            self.close(); return False
        return True

    def close(self):
        self.authenticated = False; self._key = self.session = self._transcript = None
        self._deadline = 0


class EnrollmentHost:
    """Ephemeral P-256 enrollment; no trust record before explicit PC confirmation + device proof."""
    def __init__(self, clock=time.monotonic):
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        self._private = ec.generate_private_key(ec.SECP256R1())
        self.public = self._private.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint).hex()
        self.nonce = secrets.token_hex(32); self._clock = clock; self._deadline = clock() + 60
        self._key = None; self._transcript = None; self.device_id = None; self.code = None
        self._confirmed = False

    def hello(self):
        return dict(cmd='interaction_enroll', schema=1, publicKey=self.public, nonce=self.nonce)

    def offer(self, reply):
        from cryptography.hazmat.primitives.asymmetric import ec
        try:
            fields = {'type', 'schema', 'deviceId', 'publicKey', 'nonce', 'hostNonce', 'bootId'}
            if (self._key is not None or self._private is None or self._clock() >= self._deadline
                    or not isinstance(reply, dict) or set(reply) != fields or reply['type'] != 'interaction_enrollment'
                    or type(reply['schema']) is not int or reply['schema'] != 1 or reply['hostNonce'] != self.nonce
                    or not hex_text(reply['deviceId'], 32) or not hex_text(reply['nonce'], 64)
                    or not hex_text(reply['publicKey'], 130) or not reply['publicKey'].startswith('04')
                    or not number(reply['bootId'])):
                raise ValueError('Invalid enrollment offer')
            peer = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), bytes.fromhex(reply['publicKey']))
            shared = self._private.exchange(ec.ECDH(), peer)
            self._transcript = (b'AIM-ENROLL-1\0' + (reply['deviceId'] + self.public + reply['publicKey']
                                + self.nonce + reply['nonce']).encode() + struct.pack('>I', reply['bootId']))
            # RFC 5869 HKDF extract/one-block expand with SHA-256. No custom cipher/hash.
            salt = hashlib.sha256(self._transcript).digest()
            prk = hmac.digest(salt, shared, 'sha256')
            self._key = hmac.digest(prk, b'AI-Monitor USB enrollment v1\x01', 'sha256')
            code = proof(self._key, 'display', self._transcript).hex()[:16].upper()
            self.code = '-'.join(code[i:i+4] for i in range(0, 16, 4)); self.device_id = reply['deviceId']
            self._private = None
            return self.code
        except (ValueError, TypeError, KeyError):
            self.close(); raise ValueError('Enrollment failed') from None

    def confirmation(self, confirmed):
        if confirmed is not True or self._confirmed or self._key is None or self._clock() >= self._deadline:
            self.close(); raise ValueError('Enrollment requires explicit code verification')
        self._confirmed = True
        return dict(cmd='interaction_enroll_commit', schema=1, deviceId=self.device_id,
                    proof=proof(self._key, 'enroll-host', self._transcript).hex())

    def finish(self, reply):
        try:
            if (not self._confirmed or self._key is None or self._clock() >= self._deadline or not isinstance(reply, dict)
                    or set(reply) != {'type', 'schema', 'deviceId', 'proof'} or reply['type'] != 'interaction_enrolled'
                    or type(reply['schema']) is not int or reply['schema'] != 1 or reply['deviceId'] != self.device_id
                    or not hex_text(reply['proof'], 64)
                    or not hmac.compare_digest(proof(self._key, 'enroll-device', self._transcript).hex(), reply['proof'])):
                raise ValueError('Device enrollment was not confirmed')
            return TrustRecord(self.device_id, self._key)
        finally:
            self.close()

    def close(self):
        self._private = self._key = self._transcript = None
        self.code = self.device_id = None
        self._confirmed = False
