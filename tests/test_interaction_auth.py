"""Actual standard cryptography plus Python/native USB auth interoperability; no approvals."""
from dataclasses import replace
import hashlib
import hmac
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from interaction_auth import EnrollmentHost, SessionHost, TrustRecord, proof, packet_input, session_transcript, strict_body
from interaction_trust import TrustStore, protect
from usb_enrollment import UsbEnrollmentClient


class EnrollmentTests(unittest.TestCase):
    def offer(self, client):
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        device = ec.generate_private_key(ec.SECP256R1())
        public = device.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint).hex()
        peer = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), bytes.fromhex(client.public))
        shared = device.exchange(ec.ECDH(), peer)
        message = dict(type='interaction_enrollment', schema=1, deviceId='b' * 32,
                       publicKey=public, nonce='c' * 64, hostNonce=client.nonce, bootId=17)
        code = client.offer(message)
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF
        from cryptography.hazmat.primitives import hashes
        key = HKDF(algorithm=hashes.SHA256(), length=32,
                   salt=hashlib.sha256(client._transcript).digest(), info=b'AI-Monitor USB enrollment v1').derive(shared)
        self.assertEqual(client._key, key)
        return key, code

    def test_real_ecdh_hkdf_and_both_explicit_confirmations_required(self):
        client = EnrollmentHost(); key, code = self.offer(client)
        self.assertRegex(code, r'^[A-F0-9]{4}(?:-[A-F0-9]{4}){3}$')
        reply = dict(type='interaction_enrolled', schema=1, deviceId='b' * 32,
                     proof=proof(key, 'enroll-device', client._transcript).hex())
        with self.assertRaises(ValueError): client.finish(reply)  # No PC confirmation yet.
        client = EnrollmentHost(); key, code = self.offer(client)
        command = client.confirmation(True)
        self.assertEqual(command['proof'], proof(key, 'enroll-host', client._transcript).hex())
        record = client.finish(dict(type='interaction_enrolled', schema=1, deviceId='b' * 32,
                                   proof=proof(key, 'enroll-device', client._transcript).hex()))
        self.assertEqual(record.key, key); self.assertNotIn(key.hex(), repr(record))
        self.assertIsNone(client._key); self.assertIsNone(client._private)
        self.assertIsNone(client.code); self.assertIsNone(client.device_id)

    def test_no_decline_timeout_or_wrong_proof_can_create_trust(self):
        for confirmed in (False, None, 1, 'yes'):
            client = EnrollmentHost(); self.offer(client)
            with self.assertRaises(ValueError): client.confirmation(confirmed)
            self.assertIsNone(client.code); self.assertIsNone(client.device_id)
        now = [0.]; client = EnrollmentHost(lambda: now[0]); self.offer(client); now[0] = 60
        with self.assertRaises(ValueError): client.confirmation(True)
        client = EnrollmentHost(); self.offer(client); client.confirmation(True)
        with self.assertRaises(ValueError):
            client.finish(dict(type='interaction_enrolled', schema=1, deviceId='b' * 32, proof='0' * 64))

    def test_invalid_curve_point_and_duplicate_canonical_fields_rejected(self):
        with self.assertRaises(ValueError): TrustRecord('b' * 32, bytes(32))
        client = EnrollmentHost()
        with self.assertRaises(ValueError):
            client.offer(dict(type='interaction_enrollment', schema=1, deviceId='b' * 32,
                              publicKey='04' + '0' * 128, nonce='c' * 64, hostNonce=client.nonce, bootId=17))
        for raw in ('{"kind":"heartbeat","kind":"request"}', '{ "kind":"heartbeat"}',
                    '{"value":NaN}', '[]', 'x' * 1025):
            with self.assertRaises(ValueError): strict_body(raw)

    @unittest.skipUnless(os.name == 'nt', 'Current-user Windows DPAPI')
    def test_real_dpapi_encrypted_at_rest_install_binding_and_forget(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / 'tools').mkdir()
            store = TrustStore(root); self.assertIsNone(store.load())
            record = TrustRecord('b' * 32, bytes(range(1, 33))); store.save(record)
            self.assertNotIn(record.key.hex().encode(), store.path.read_bytes())
            self.assertEqual(store.load(), record)
            encoded = json.loads(store.path.read_text())['encrypted']
            import base64
            with self.assertRaises(OSError): protect(base64.b64decode(encoded), b'\0' * 32, decrypt=True)
            store.forget(); self.assertIsNone(store.load())


class NativeAuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which(os.environ.get('CXX', 'g++'))
        if not compiler and os.name == 'nt':
            compiler = 'C:/msys64/mingw64/bin/g++.exe' if Path('C:/msys64/mingw64/bin/g++.exe').is_file() else None
        if not compiler: raise unittest.SkipTest('Native authentication tests require g++')
        include = ROOT / '.pio/libdeps/esp32p4-release/ArduinoJson/src'
        if not include.is_dir(): raise unittest.SkipTest('Build firmware first to install ArduinoJson')
        cls.temp = tempfile.TemporaryDirectory(); cls.addClassCleanup(cls.temp.cleanup)
        cls.binary = Path(cls.temp.name) / ('auth.exe' if os.name == 'nt' else 'auth')
        subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror', '-I', str(ROOT / 'src'),
                        '-I', str(include), str(ROOT / 'tests/native/interaction_auth_driver.cpp'),
                        '-o', str(cls.binary), '-lbcrypt' if os.name == 'nt' else '-lcrypto'], check=True, capture_output=True)

    def setUp(self):
        self.process = subprocess.Popen([str(self.binary)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, text=True)
        self.addCleanup(self.stop)
        self.now = [0.1]
        self.host = SessionHost(TrustRecord('b' * 32, bytes(range(1, 33))), 'a' * 32, 17, lambda: self.now[0])

    def stop(self):
        if self.process.stdin: self.process.stdin.close()
        self.process.wait(timeout=3)
        self.process.stdout.close(); self.process.stderr.close()

    def call(self, op, now=102, **fields):
        self.process.stdin.write(json.dumps(dict(op=op, now=now, **fields)) + '\n'); self.process.stdin.flush()
        return json.loads(self.process.stdout.readline())

    def establish(self, now=100):
        response = self.call('open', now, message=self.host.hello())
        self.assertTrue(response['ok']); self.assertFalse(response['authenticated'])
        command = self.host.challenge(response['reply'])
        response = self.call('prove', now + 1, message=command)
        self.assertTrue(response['authenticated']); self.host.ready(response['reply'])
        return command

    def enroll_offer(self, now=100):
        self.assertTrue(self.call('enroll_arm', now)['ok'])
        client = EnrollmentHost(lambda: 0.)
        offered = self.call('enroll_begin', now + 1, message=client.hello())
        self.assertTrue(offered['ok'])
        self.assertEqual(client.offer(offered['reply']), offered['code'])
        self.assertEqual(offered['saves'], 0)
        return client

    def test_native_enrollment_real_ecdh_matching_code_and_session(self):
        client = self.enroll_offer()
        self.assertTrue(self.call('enroll_confirm', visible=True, awake=True)['ok'])
        response = self.call('enroll_commit', message=client.confirmation(True))
        self.assertTrue(response['ok']); self.assertEqual(response['saves'], 1)
        self.assertFalse(response['enrolledOptedIn']); self.assertEqual(response['code'], '')
        record = client.finish(response['reply'])
        # Prove the stored native key matches the PC record without exporting it.
        self.assertTrue(self.call('enrolled_session')['ok'])
        self.host = SessionHost(record, 'a' * 32, 17, lambda: self.now[0])
        self.establish(now=200)
        self.assertTrue(self.call('receive', now=202, message=self.host.encode({'kind': 'heartbeat'}))['ok'])
        self.assertFalse(self.call('enroll_commit', message={})['ok'])
        self.assertEqual(self.call('enroll_poll')['saves'], 1)

    def test_native_enrollment_cannot_be_started_or_confirmed_from_wire(self):
        client = EnrollmentHost()
        self.assertFalse(self.call('enroll_begin', message=client.hello())['ok'])
        client = self.enroll_offer()
        response = self.call('enroll_commit', message=client.confirmation(True))
        self.assertFalse(response['ok']); self.assertEqual(response['saves'], 0)
        self.assertEqual(response['code'], '')
        for visible, awake in ((False, True), (True, False)):
            self.enroll_offer()
            response = self.call('enroll_confirm', visible=visible, awake=awake)
            self.assertFalse(response['ok']); self.assertEqual(response['enrollmentState'], 0)

    def test_native_enrollment_replacement_disconnect_and_stale_commit(self):
        client = self.enroll_offer()
        self.assertFalse(self.call('enroll_begin', message=client.hello())['ok'])
        self.assertEqual(self.call('enroll_poll')['code'], '')
        client = self.enroll_offer()
        self.call('enroll_confirm', visible=True, awake=True)
        command = client.confirmation(True); self.call('enroll_cancel')
        response = self.call('enroll_commit', message=command)
        self.assertFalse(response['ok']); self.assertEqual(response['saves'], 0)
        # A new offer derives a different key, so an old valid proof cannot commit it.
        self.enroll_offer(); self.call('enroll_confirm', visible=True, awake=True)
        self.assertFalse(self.call('enroll_commit', message=command)['ok'])

    def test_native_enrollment_deadline_includes_arm_and_handles_rollover(self):
        client = self.enroll_offer()
        self.assertFalse(self.call('enroll_confirm', now=60100, visible=True, awake=True)['ok'])
        self.assertEqual(self.call('enroll_poll')['saves'], 0)
        self.call('enroll_arm', now=0xfffffff0)
        client = EnrollmentHost()
        offer = self.call('enroll_begin', now=16, message=client.hello())
        self.assertTrue(offer['ok']); client.offer(offer['reply'])
        self.assertTrue(self.call('enroll_confirm', now=32, visible=True, awake=True)['ok'])
        response = self.call('enroll_commit', now=59984, message=client.confirmation(True))
        self.assertFalse(response['ok']); self.assertEqual(response['saves'], 0)

    def test_native_enrollment_rejects_malformed_points_types_and_fields(self):
        for change in ({'publicKey': '04' + '0' * 128}, {'publicKey': '0' * 130},
                       {'schema': True}, {'nonce': 'A' * 64}, {'physicalConfirmed': True},
                       {'publicKey': '04' + '0' * 128 + '\0'}, {'nonce': '0' * 63}):
            self.call('enroll_arm'); client = EnrollmentHost()
            response = self.call('enroll_begin', message=dict(client.hello(), **change))
            self.assertFalse(response['ok']); self.assertEqual(response['saves'], 0)
            self.assertEqual(response['code'], '')
        for change in ({'proof': '0' * 64}, {'schema': True}, {'deviceId': 'c' * 32}, {'optedIn': True}):
            client = self.enroll_offer(); self.call('enroll_confirm', visible=True, awake=True)
            self.assertFalse(self.call('enroll_commit', message=dict(client.confirmation(True), **change))['ok'])

    def test_native_enrollment_storage_and_crypto_failures_never_acknowledge(self):
        client = self.enroll_offer(); self.call('enroll_confirm', visible=True, awake=True)
        self.call('storage_failure')
        response = self.call('enroll_commit', message=client.confirmation(True))
        self.assertFalse(response['ok']); self.assertNotIn('reply', response)
        self.assertEqual(response['saves'], 0); self.assertEqual(response['code'], '')
        self.call('enroll_arm'); self.call('fail_crypto')
        response = self.call('enroll_begin', message=EnrollmentHost().hello())
        self.assertFalse(response['ok']); self.assertEqual(response['enrollmentState'], 0)

    def test_native_enrollment_stale_physical_confirmation_cancels_new_offer(self):
        self.enroll_offer(); old = self.call('enroll_poll')['enrollmentRevision']
        client = self.enroll_offer()
        response = self.call('enroll_confirm', displayedRevision=old, visible=True, awake=True)
        self.assertFalse(response['ok']); self.assertEqual(response['code'], '')
        self.assertFalse(self.call('enroll_commit', message=client.confirmation(True))['ok'])

    def test_native_enrollment_crypto_failure_after_confirmation_and_double_confirmation(self):
        client = self.enroll_offer(); self.call('enroll_confirm', visible=True, awake=True)
        response = self.call('enroll_confirm', visible=True, awake=True)
        self.assertFalse(response['ok']); self.assertEqual(response['code'], '')
        self.assertFalse(self.call('enroll_commit', message=client.confirmation(True))['ok'])
        client = self.enroll_offer(); self.call('enroll_confirm', visible=True, awake=True)
        self.call('fail_crypto')
        response = self.call('enroll_commit', message=client.confirmation(True))
        self.assertFalse(response['ok']); self.assertNotIn('reply', response)
        self.assertEqual(response['saves'], 0)

    def test_device_trust_record_load_is_strict_and_never_restores_opt_in(self):
        self.assertFalse(self.call('storage_load')['ok'])
        self.assertTrue(self.call('storage_save_fixture')['ok'])
        response = self.call('storage_load')
        self.assertTrue(response['ok']); self.assertEqual(response['storedBytes'], 104)
        self.assertFalse(response['enrolledOptedIn'])
        self.call('enrolled_session'); self.establish()
        self.assertTrue(self.call('storage_load')['ok'])
        self.assertFalse(self.call('storage_load')['enrolledOptedIn'])
        self.assertFalse(self.call('storage_save_fixture', optedIn=True)['ok'])
        for index in (0, 7, 8, 39, 40, 71, 72, 103):
            self.assertTrue(self.call('storage_save_fixture')['ok'])
            self.call('storage_corrupt', index=index)
            self.assertFalse(self.call('storage_load')['ok'])
        self.call('storage_save_fixture'); self.call('storage_short')
        self.assertFalse(self.call('storage_load')['ok'])

    def test_device_trust_storage_readback_failure_prevents_enrollment_ack(self):
        client = self.enroll_offer(); self.call('enroll_confirm', visible=True, awake=True)
        self.call('storage_corrupt_write')
        response = self.call('enroll_commit', message=client.confirmation(True))
        self.assertFalse(response['ok']); self.assertEqual(response['saves'], 0)
        self.assertNotIn('reply', response); self.assertFalse(self.call('storage_load')['ok'])

    def test_device_trust_write_failure_preserves_existing_record(self):
        self.assertTrue(self.call('storage_save_fixture')['ok'])
        client = self.enroll_offer(); self.call('enroll_confirm', visible=True, awake=True)
        self.call('storage_write_fail')
        response = self.call('enroll_commit', message=client.confirmation(True))
        self.assertFalse(response['ok']); self.assertNotIn('reply', response)
        self.assertTrue(self.call('storage_load')['ok'])
        self.call('enrolled_session'); self.establish()  # Prior fixture key remains unchanged.

    def test_device_trust_read_and_erase_errors_fail_closed(self):
        self.call('storage_save_fixture'); self.call('storage_erase_fail')
        self.assertFalse(self.call('storage_forget')['ok'])
        self.assertTrue(self.call('storage_load')['ok'])
        self.call('storage_read_fail'); self.assertFalse(self.call('storage_load')['ok'])
        self.assertFalse(self.call('storage_load')['enrolledOptedIn'])

    def test_device_trust_forget_and_empty_key(self):
        self.call('storage_save_fixture')
        self.assertTrue(self.call('storage_forget')['ok'])
        self.assertFalse(self.call('storage_load')['ok'])
        self.call('empty_key'); self.assertFalse(self.call('storage_save_fixture')['ok'])

    def test_enrollment_final_local_gate_is_rechecked_after_physical_confirmation(self):
        client = self.enroll_offer(); self.call('enroll_confirm', visible=True, awake=True)
        self.call('lose_enrollment_gate')
        response = self.call('enroll_commit', message=client.confirmation(True))
        self.assertFalse(response['ok']); self.assertNotIn('reply', response)
        self.assertEqual(response['saves'], 0)

    def test_enrollment_gate_loss_during_storage_never_acknowledges_or_enables(self):
        client = self.enroll_offer(); self.call('enroll_confirm', visible=True, awake=True)
        self.call('lose_gate_on_save')
        response = self.call('enroll_commit', message=client.confirmation(True))
        self.assertFalse(response['ok']); self.assertNotIn('reply', response)
        self.assertFalse(response['enrolledOptedIn'])
        self.assertTrue(self.call('storage_load')['ok'])
        self.assertFalse(self.call('storage_load')['enrolledOptedIn'])

    def enrollment_panel(self):
        native = self
        class Panel:
            info = dict(enrollmentProtocol=1, bootId=17)
            def __init__(self): self.messages = []; self.pending = None; self.heartbeats = 0
            def heartbeat(self): self.heartbeats += 1
            def send_line(self, raw):
                message = json.loads(raw); self.messages.append(message); command = message['cmd']
                if command == 'interaction_enroll': response = native.call('enroll_begin', message=message)
                elif command == 'interaction_enroll_commit': response = native.call('enroll_commit', message=message)
                elif command == 'interaction_enroll_cancel':
                    native.call('enroll_cancel'); self.pending = None; return
                else:
                    state = native.call('enroll_poll')['enrollmentState']
                    self.pending = dict(type='interaction_enrollment_status', schema=1,
                                        armed=state == 1, comparing=state == 2, confirmed=state == 3)
                    return
                self.pending = response.get('reply')
            def wait_for(self, kind, seconds=2):
                if self.pending is None or self.pending.get('type') != kind: raise TimeoutError('Synthetic response unavailable')
                return self.pending
        return Panel()

    def test_pc_enrollment_adapter_real_native_exchange_and_protected_record(self):
        class Store:
            value = None
            def save(self, record): self.value = record
            def load(self): return self.value
        self.call('enroll_arm'); panel = self.enrollment_panel(); store = Store()
        client = UsbEnrollmentClient(panel, store)
        self.assertEqual(client.begin(), self.call('enroll_poll')['code'])
        self.assertIsNone(store.value)
        self.call('enroll_confirm', visible=True, awake=True); client.finish(True)
        self.assertEqual(store.value.device_id, 'b' * 32)
        self.assertEqual(sum(message['cmd'] == 'interaction_enroll_commit' for message in panel.messages), 1)
        self.assertFalse(self.call('enroll_poll')['enrolledOptedIn']); self.assertIsNone(client.host)

    def test_pc_enrollment_adapter_decline_reboot_and_ambiguous_commit_never_retry(self):
        from unittest.mock import Mock
        store = Mock(); self.call('enroll_arm'); panel = self.enrollment_panel()
        client = UsbEnrollmentClient(panel, store); client.begin()
        with self.assertRaises(ValueError): client.finish(False)
        store.save.assert_not_called()
        self.call('enroll_arm'); panel = self.enrollment_panel(); client = UsbEnrollmentClient(panel, store); client.begin()
        panel.info = dict(enrollmentProtocol=1, bootId=18)
        with self.assertRaises(ValueError): client.finish(True)
        store.save.assert_not_called()
        self.call('enroll_arm'); panel = self.enrollment_panel(); client = UsbEnrollmentClient(panel, store); client.begin()
        self.call('enroll_confirm', visible=True, awake=True)
        original = panel.wait_for
        def fail_commit(kind, **kwargs):
            if kind == 'interaction_enrolled': raise TimeoutError('Synthetic ambiguous commit')
            return original(kind, **kwargs)
        panel.wait_for = fail_commit
        with self.assertRaises(ValueError): client.finish(True)
        self.assertEqual(sum(message['cmd'] == 'interaction_enroll_commit' for message in panel.messages), 1)
        store.save.assert_not_called()

    def test_pc_enrollment_requires_physical_confirmation_and_strict_status(self):
        from unittest.mock import Mock
        now = [0.]; self.call('enroll_arm'); panel = self.enrollment_panel()
        def sleep(seconds): now[0] += 20
        client = UsbEnrollmentClient(panel, Mock(), lambda: now[0], sleep); client.begin()
        with self.assertRaises(ValueError): client.finish(True)
        self.assertFalse(any(message['cmd'] == 'interaction_enroll_commit' for message in panel.messages))
        self.call('enroll_arm'); panel = self.enrollment_panel(); client = UsbEnrollmentClient(panel, Mock()); client.begin()
        panel.wait_for = lambda *args, **kwargs: dict(type='interaction_enrollment_status', schema=True, armed=False, comparing=False, confirmed=True)
        with self.assertRaises(ValueError): client.finish(True)
        self.assertFalse(any(message['cmd'] == 'interaction_enroll_commit' for message in panel.messages))

    def test_real_cross_language_hmac_and_bidirectional_packets(self):
        self.establish(); packet = self.host.encode({'kind': 'heartbeat'})
        response = self.call('receive', message=packet)
        self.assertEqual(response['body'], '{"kind":"heartbeat"}')
        response = self.call('send', body='{"kind":"heartbeat"}')
        self.assertEqual(self.host.decode(response['reply']), {'kind': 'heartbeat'})

    def test_replay_reflection_corruption_and_type_confusion_fail_closed(self):
        self.establish(); packet = self.host.encode({'kind': 'heartbeat'})
        self.assertTrue(self.call('receive', message=packet)['ok'])
        response = self.call('receive', message=packet)
        self.assertFalse(response['ok']); self.assertFalse(response['authenticated'])
        for change in ({'schema': True}, {'sequence': True}, {'mac': '0' * 64},
                       {'body': '{"kind":"request"}'}, {'trustedChannel': True}):
            self.host = SessionHost(TrustRecord('b' * 32, bytes(range(1, 33))), 'a' * 32, 17, lambda: self.now[0])
            self.establish(); packet = self.host.encode({'kind': 'heartbeat'})
            response = self.call('receive', message=dict(packet, **change))
            self.assertFalse(response['ok']); self.assertFalse(response['authenticated'])

    def test_opt_out_crypto_failure_timeout_and_rollover(self):
        self.establish(); self.assertFalse(self.call('poll', now=5101)['authenticated'])
        self.host = SessionHost(TrustRecord('b' * 32, bytes(range(1, 33))), 'a' * 32, 17, lambda: self.now[0])
        self.establish(now=0xfffffff0)
        self.assertTrue(self.call('poll', now=16)['authenticated'])
        self.assertFalse(self.call('poll', now=5010)['authenticated'])
        self.call('opt_out'); self.assertFalse(self.call('open', message=self.host.hello())['ok'])

    def test_wrong_host_proof_and_device_proof_are_not_authority(self):
        response = self.call('open', message=self.host.hello())
        command = self.host.challenge(response['reply']); command['proof'] = '0' * 64
        self.assertFalse(self.call('prove', message=command)['authenticated'])
        host = SessionHost(TrustRecord('b' * 32, bytes(range(1, 33))), 'a' * 32, 17, lambda: self.now[0])
        response = self.call('open', message=host.hello()); response['reply']['proof'] = '0' * 64
        with self.assertRaises(ValueError): host.challenge(response['reply'])
        self.assertFalse(host.authenticated)

    def test_crypto_failure_and_outgoing_reflection_never_authorize(self):
        self.establish(); packet = self.host.encode({'kind': 'heartbeat'})
        packet['type'] = 'interaction_packet'; del packet['cmd']
        with self.assertRaises(ValueError): self.host.decode(packet)
        self.assertFalse(self.host.authenticated)
        self.call('fail_crypto')
        response = self.call('send', body='{"kind":"heartbeat"}')
        self.assertFalse(response['ok']); self.assertFalse(response['authenticated'])

    def establish_layer(self):
        response = self.call('layer_handle', now=100, message=self.host.hello())
        command = self.host.challenge(response['reply'])
        response = self.call('layer_handle', now=101, message=command)
        self.assertTrue(response['layerTrusted']); self.host.ready(response['reply'])

    def request(self, **changes):
        return dict(dict(kind='request', requestId='d' * 32, nonce='e' * 64, revision=1,
                         tool='Read', hint='{"file_path":"fixture.txt"}', expiresInMs=2000), **changes)

    def test_bounded_request_nonce_and_one_signed_denial(self):
        self.establish_layer()
        response = self.call('layer_handle', message=self.host.encode(self.request()))
        self.assertTrue(response['requestPresent']); self.assertEqual(response['requestNonce'], 'e' * 64)
        self.assertEqual(self.host.decode(response['reply'])['kind'], 'received')
        response = self.call('layer_deny', now=103, wrongNonce=True)
        self.assertFalse(response['ok'])
        response = self.call('layer_deny', now=104)
        self.assertEqual(self.host.decode(response['reply'])['decision'], 'deny')
        self.assertFalse(self.call('layer_deny', now=105)['ok'])

    def test_heartbeats_do_not_renew_request_deadline(self):
        self.establish_layer()
        response = self.call('layer_handle', message=self.host.encode(self.request()))
        self.host.decode(response['reply'])
        response = self.call('layer_handle', now=2000, message=self.host.encode({'kind': 'heartbeat'}))
        self.assertTrue(response['layerTrusted']); self.host.decode(response['reply'])
        response = self.call('layer_poll', now=2102)
        self.assertFalse(response['requestPresent']); self.assertTrue(response['layerTrusted'])
        self.assertFalse(self.call('layer_deny', now=2103)['ok'])

    def test_invalid_signed_requests_cannot_gain_wire_authority(self):
        for changes in ({'hint': 'x' * 321}, {'hint': 'ø'}, {'tool': 'bad tool'},
                        {'revision': True}, {'expiresInMs': True}, {'expiresInMs': 25001},
                        {'trustedChannel': True}, {'nonce': 'bad'}, {'requestId': []}):
            self.host = SessionHost(TrustRecord('b' * 32, bytes(range(1, 33))), 'a' * 32, 17, lambda: self.now[0])
            self.establish_layer()
            response = self.call('layer_handle', message=self.host.encode(self.request(**changes)))
            self.assertFalse(response['requestPresent']); self.assertFalse(response['layerTrusted'])

    def test_active_request_replacement_and_cancel_fail_closed(self):
        self.establish_layer()
        response = self.call('layer_handle', message=self.host.encode(self.request()))
        self.host.decode(response['reply'])
        response = self.call('layer_handle', message=self.host.encode(self.request(requestId='f' * 32, nonce='a' * 64)))
        self.assertFalse(response['requestPresent']); self.assertFalse(response['layerTrusted'])
        self.host = SessionHost(TrustRecord('b' * 32, bytes(range(1, 33))), 'a' * 32, 17, lambda: self.now[0])
        self.establish_layer()
        response = self.call('layer_handle', message=self.host.encode(self.request()))
        self.host.decode(response['reply'])
        response = self.call('layer_handle', message=self.host.encode(dict(kind='cancel', requestId='d' * 32, nonce='e' * 64, revision=1)))
        self.assertFalse(response['requestPresent']); self.assertTrue(response['layerTrusted'])
        self.host.decode(response['reply'])
        response = self.call('layer_handle', message=self.host.encode(self.request()))
        self.assertFalse(response['layerTrusted'])  # Reserved request ID cannot be reused in this session.

    def usb_client(self, opted_in=True):
        from usb_interaction import UsbPermissionClient
        from permission_broker import Broker
        fixture = self
        class Panel:
            info = dict(interactionProtocol=1, bootId=17)
            def __init__(self): self.responses = []
            def send_line(self, line):
                response = fixture.call('layer_handle', now=int(fixture.now[0]*1000), message=json.loads(line))
                if response.get('reply'): self.responses.append(response['reply'])
            def wait_for(self, kind, seconds=1):
                for i, response in enumerate(self.responses):
                    if response['type'] == kind: return self.responses.pop(i)
                raise TimeoutError('Fixture reply absent')
        class Service:
            def __init__(self, context):
                self.broker = Broker(lambda: fixture.now[0]); self.broker.update_context(context)
                self.responses = []; self.started = self.closed = False
            def start(self): self.started = True
            def update_context(self, context): self.broker.update_context(context)
            def close(self): self.closed = True; self.broker.cancel()
            def resolve(self, *args): self.responses.append(self.broker.decide(*args))
        return UsbPermissionClient(Panel(), TrustRecord('b' * 32, bytes(range(1, 33))),
                                   'a' * 32, opted_in, Service, lambda: self.now[0])

    def test_serial_adapter_helper_contract_and_authenticated_native_denial(self):
        from aim_permission import decision_output
        client = self.usb_client(); client.open(); self.addCleanup(client.close)
        self.assertTrue(client.context().eligible()); self.assertTrue(client.service.started)
        request = dict(schema=1, instance='a' * 32, requestId='d' * 32, nonce='e' * 64,
                       revision=1, tool='Read', hint='{"file_path":"fixture.txt"}', expiresInMs=2000)
        client.service.broker.submit(request); client.pump()
        response = self.call('layer_deny', now=101)
        self.assertTrue(client.handle_event(response['reply']))
        self.assertEqual(decision_output(request, client.service.responses[0], 'a' * 32),
                         {'hookSpecificOutput': {'hookEventName': 'PermissionRequest', 'decision': {'behavior': 'deny'}}})
        client.pump(); self.assertIsNone(client._request)
        self.assertFalse(self.call('layer_poll', now=102)['requestPresent'])

    def test_serial_adapter_opt_in_expiry_and_corruption_cancel_helper(self):
        with self.assertRaises(ValueError): self.usb_client(False)
        client = self.usb_client(); client.open(); service = client.service
        self.addCleanup(client.close)
        request = dict(schema=1, instance='a' * 32, requestId='d' * 32, nonce='e' * 64,
                       revision=1, tool='Read', hint='{}', expiresInMs=2000)
        service.broker.submit(request); client.pump()
        response = self.call('layer_deny', now=101)['reply']; response['mac'] = '0' * 64
        client.handle_event(response)
        self.assertTrue(service.closed); self.assertIsNone(service.broker.current()); self.assertEqual(service.responses, [])

    def test_serial_adapter_heartbeat_and_request_clock_are_independent(self):
        client = self.usb_client(); client.open(); self.addCleanup(client.close)
        self.now[0] = 1.2; client.pump()
        self.assertTrue(client.context().eligible())
        self.now[0] = 7; client.pump()
        self.assertIsNone(client.auth); self.assertIsNone(client.service)

    def test_serial_adapter_shutdown_cancels_native_request_without_wait_or_retry(self):
        client = self.usb_client(); client.open(); service = client.service
        request = dict(schema=1, instance='a' * 32, requestId='d' * 32, nonce='e' * 64,
                       revision=1, tool='Read', hint='{}', expiresInMs=2000)
        service.broker.submit(request); client.pump()
        self.assertTrue(self.call('layer_poll', now=101)['requestPresent'])
        with patch.object(client.panel, 'wait_for', side_effect=AssertionError('Shutdown must not await a reply')):
            client.close(); client.close()
        native = self.call('layer_poll', now=102)
        self.assertFalse(native['requestPresent']); self.assertFalse(native['layerTrusted'])
        self.assertTrue(service.closed); self.assertEqual(service.responses, [])

    def test_serial_adapter_cannot_replace_a_service_that_failed_to_stop(self):
        client = self.usb_client(); client.open()
        with patch.object(client.service, 'close', side_effect=RuntimeError('Synthetic shutdown failure')):
            client.close()
        self.assertFalse(client.shutdown_complete)
        with self.assertRaises(RuntimeError): client.open()
        self.assertIsNone(client.auth);self.assertIsNone(client.service)

    def test_default_empty_device_key_cannot_establish_an_authenticated_session(self):
        self.call('empty_key')
        self.assertFalse(self.call('open', message=self.host.hello())['ok'])
        self.assertFalse(self.call('layer_handle', message=self.host.hello())['layerTrusted'])
