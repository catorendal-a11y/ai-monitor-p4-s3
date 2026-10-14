"""Synthetic diagnostic identities/results; no USB or radio operations."""
import sys
import unittest
import json
from unittest.mock import Mock
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from c6_baseline import validate_probe, collect_probe
from ppa_baseline import validate_ppa


def c6():
    return dict(type='c6_probe', schema=1, stage='completed', error=0, hostVersion='2.12.5',
        coprocessorResponded=True, coprocessorVersion='2.12.5', configuredSlaveTarget='esp32c6',
        detectedChip='esp32c6', controllerEnableConfirmed=True, deadlineExceeded=False, retryAllowed=False)


def ppa():
    return dict(type='ppa_benchmark', schema=1, status='passed', width=800, height=480,
        samples=8, cpuMedianUs=20000, ppaMedianUs=4000, bitExact=True,
        resourcesRetained=False, isolated=True, productionPpaActive=False)


class ProbeBaselineTests(unittest.TestCase):
    def test_identity_only_schema_never_reports_bluetooth_enabled(self):
        identity = dict(c6(), schema=2, controllerEnableConfirmed=False)
        self.assertEqual(validate_probe(identity)['stage'], 'completed')
        for fields in ({'controllerEnableConfirmed': True}, {'schema': 3},
                       {'coprocessorResponded': False, 'coprocessorVersion': None},
                       {'stage': 'controller-init-failed', 'error': 263},
                       {'stage': 'controller-enable-failed', 'error': 263}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                validate_probe(dict(identity, **fields))
        # Historical measurements stay readable; they are not new radio operations.
        self.assertTrue(validate_probe(c6())['controllerEnableConfirmed'])

    def test_collector_handles_boot_noise_fragmentation_pending_and_terminal_failure(self):
        pending = dict(c6(), stage='pending', coprocessorResponded=False,
            coprocessorVersion=None, detectedChip=None, controllerEnableConfirmed=False)
        failed = dict(pending, stage='transport-failed', error=263)
        raw = b'boot noise\n' + b'x'*2100 + b'\n' + json.dumps(pending).encode() + b'\n' + json.dumps(failed).encode() + b'\n'
        chunks = [raw[n:n+73] for n in range(0, len(raw), 73)]
        connection = Mock(); connection.read.side_effect = chunks; connection.write.return_value = 6
        self.assertEqual(collect_probe(connection)['stage'], 'transport-failed')
        self.assertTrue(all(call.args == (b'probe\n',) for call in connection.write.call_args_list))

    def test_collector_rejects_duplicate_fields_and_partial_writes(self):
        connection = Mock(); connection.write.return_value = 6
        connection.read.return_value = b'{"type":"c6_probe","type":"c6_probe"}\n'
        with self.assertRaises(ValueError): collect_probe(connection)
        connection.write.return_value = 5
        with self.assertRaises(OSError): collect_probe(connection)

    def test_collector_has_a_hard_deadline_without_reinitializing_radio(self):
        now = [0.0]
        connection = Mock(); connection.write.return_value = 6
        def read(_): now[0] += .2; return b''
        connection.read.side_effect = read
        with self.assertRaises(TimeoutError): collect_probe(connection, clock=lambda: now[0])
        self.assertLessEqual(connection.write.call_count, 30)

    def test_missing_fields_and_unstructured_states_fail_validation(self):
        for fixture, validate, state in ((c6, validate_probe, 'stage'), (ppa, validate_ppa, 'status')):
            for key in fixture():
                data = fixture(); del data[key]
                with self.subTest(key=key), self.assertRaises(ValueError): validate(data)
            with self.assertRaises(ValueError): validate(dict(fixture(), **{state: []}))

    def test_completed_results_are_whitelisted_without_private_fields(self):
        for fixture, validate in ((c6, validate_probe), (ppa, validate_ppa)):
            result = fixture(); result['private'] = 'not exported'
            self.assertNotIn('private', validate(result))

    def test_probe_rejects_false_identity_success_retry_and_wrong_types(self):
        for fields in ({'schema': True}, {'error': False}, {'retryAllowed': True},
                       {'detectedChip': None}, {'coprocessorVersion': 'unknown'},
                       {'controllerEnableConfirmed': False}, {'deadlineExceeded': True},
                       {'stage': 'pending\n'}, {'hostVersion': '1.2.3\n'}):
            with self.subTest(fields=fields), self.assertRaises(ValueError): validate_probe(dict(c6(), **fields))

    def test_absent_coprocessor_and_timeout_never_become_success(self):
        failed = dict(c6(), stage='transport-failed', error=263, detectedChip=None,
            coprocessorResponded=False, coprocessorVersion=None, controllerEnableConfirmed=False)
        self.assertIsNone(validate_probe(failed)['detectedChip'])
        late = dict(c6(), stage='deadline-exceeded', error=263, deadlineExceeded=True)
        self.assertEqual(validate_probe(late)['stage'], 'deadline-exceeded')

    def test_ppa_rejects_unsafe_or_incomplete_results(self):
        for fields in ({'schema': True}, {'samples': 9}, {'width': 480}, {'samples': 7},
                       {'productionPpaActive': True}, {'isolated': False}, {'cpuMedianUs': 0},
                       {'bitExact': False}, {'resourcesRetained': True}):
            with self.subTest(fields=fields), self.assertRaises(ValueError): validate_ppa(dict(ppa(), **fields))

    def test_pixel_mismatch_and_retained_timeout_are_reported_honestly(self):
        self.assertEqual(validate_ppa(dict(ppa(), status='pixel-mismatch', bitExact=False))['status'], 'pixel-mismatch')
        timeout = dict(ppa(), status='timeout-resources-retained', samples=0, cpuMedianUs=0,
            ppaMedianUs=0, bitExact=False, resourcesRetained=True)
        self.assertTrue(validate_ppa(timeout)['resourcesRetained'])


if __name__ == '__main__': unittest.main()
