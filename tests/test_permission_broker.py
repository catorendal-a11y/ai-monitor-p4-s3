"""Synthetic host permission authority; these tests establish no USB trust."""
from dataclasses import replace
from pathlib import Path
import sys
import threading
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from permission_broker import Broker, TrustedContext


class PermissionBrokerTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.
        self.context = TrustedContext(True, True, 'a' * 32, 'b' * 32, 'c' * 64, True)
        self.broker = Broker(lambda: self.now)
        self.broker.update_context(self.context)
        self.message = dict(schema=1, instance='a' * 32, requestId='d' * 32, nonce='e' * 64,
                            revision=1, tool='Read', hint='{"file_path":"fixture.txt"}', expiresInMs=25000)

    def decide(self, **changes):
        args = dict(request_id='d' * 32, nonce='e' * 64, revision=1, decision='allow', context=self.context)
        return self.broker.decide(**dict(args, **changes))

    def test_correlated_once_response_without_sensitive_arguments(self):
        request = self.broker.submit(self.message)
        self.assertEqual(request.expires_at, 125.)
        response = self.decide()
        self.assertEqual(response['decision'], 'allow')
        self.assertNotIn('hint', response); self.assertNotIn('tool', response)
        self.assertIsNone(self.broker.current())
        with self.assertRaises(ValueError): self.decide()
        with self.assertRaises(ValueError): self.broker.submit(self.message)
        with self.assertRaises(ValueError): self.broker.submit(dict(self.message, nonce='f' * 64))
        with self.assertRaises(ValueError): self.broker.submit(dict(self.message, requestId='f' * 32))

    def test_every_local_authority_change_cancels_and_cannot_replay(self):
        for changes in ({'opted_in': False}, {'connected': False}, {'authenticated': False},
                        {'host_instance': 'f' * 32}, {'device_id': 'f' * 32}, {'session_id': 'f' * 64}):
            broker = Broker(lambda: self.now); broker.update_context(self.context)
            broker.submit(self.message); broker.update_context(replace(self.context, **changes))
            self.assertIsNone(broker.current())
            with self.assertRaises(ValueError):
                broker.decide('d' * 32, 'e' * 64, 1, 'allow', self.context)
            broker.update_context(self.context)
            with self.assertRaises(ValueError): broker.submit(self.message)

    def test_invalid_or_expired_decisions_consume_without_retry(self):
        for changes in ({'nonce': 'f' * 64}, {'request_id': 'f' * 32}, {'revision': True},
                        {'decision': 'retry'}, {'context': replace(self.context, session_id='f' * 64)}):
            self.broker = Broker(lambda: self.now); self.broker.update_context(self.context)
            self.broker.submit(self.message)
            with self.assertRaises(ValueError): self.decide(**changes)
            with self.assertRaises(ValueError): self.decide()
        self.broker = Broker(lambda: self.now); self.broker.update_context(self.context)
        self.broker.submit(self.message); self.now = 125.
        with self.assertRaises(ValueError): self.decide()

    def test_strict_bounds_and_wire_trust_cannot_enable_authority(self):
        for changes in ({'schema': True}, {'revision': True}, {'expiresInMs': True},
                        {'expiresInMs': 25001}, {'expiresInMs': 0}, {'tool': 'a' * 65},
                        {'hint': 'a' * 321}, {'hint': 'ø'}, {'trusted': True},
                        {'instance': 'f' * 32}, {'nonce': []}):
            with self.assertRaises(ValueError): self.broker.submit(dict(self.message, **changes))
        self.broker.update_context(TrustedContext())
        with self.assertRaises(ValueError): self.broker.submit(self.message)
        with self.assertRaises(ValueError): self.broker.update_context({'authenticated': True})

    def test_single_pending_request_and_bounded_fail_closed_ledger(self):
        broker = Broker(lambda: self.now, ledger_limit=1); broker.update_context(self.context)
        broker.submit(self.message)
        with self.assertRaises(ValueError): broker.submit(dict(self.message, requestId='f' * 32))
        broker.cancel()
        with self.assertRaises(ValueError): broker.submit(dict(self.message, requestId='f' * 32))

    def test_concurrent_decisions_only_one_response(self):
        self.broker.submit(self.message); responses = []; barrier = threading.Barrier(3)
        def worker():
            barrier.wait()
            try: responses.append(self.decide())
            except ValueError: pass
        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads: thread.start()
        barrier.wait()
        for thread in threads: thread.join(2)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(len(responses), 1)


if __name__ == '__main__': unittest.main()
