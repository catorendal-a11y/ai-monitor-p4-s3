"""Synthetic serial-owner fixture; no real USB or provider calls."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from usb_live import UsbLiveClient, validate_agents


class UsbLiveTests(unittest.TestCase):
    def test_timers_require_v2_capability_and_strict_numeric_limits(self):
        panel,client=self.fixture();client.open()
        row=dict(provider='claude',id='opaque',state='NEEDS_ATTENTION',elapsedSeconds=123,observedAgeSeconds=45)
        client.send([row])
        self.assertEqual(json.loads(panel.send_line.call_args.args[0])['agents'],
                         [dict(provider='claude',id='opaque',state='WAITING')])
        panel.info['liveMetadata']=2
        client.send([row])
        self.assertEqual(json.loads(panel.send_line.call_args.args[0])['agents'],[row])
        for key,value in [('elapsedSeconds',True),('elapsedSeconds',604801),
                          ('observedAgeSeconds',901),('observedAgeSeconds',-1)]:
            with self.assertRaises(ValueError):validate_agents([dict(row,**{key:value})])

    def fixture(self):
        panel = Mock()
        panel.info = dict(liveProtocol=1, livePermissions=False, bootId=17)
        def reply(kind, command):
            request = json.loads(panel.send_line.call_args.args[0])
            return dict(type=kind, schema=1, cmd=command, ok=True, bootId=17, epoch=2,
                        sequence=request.get('sequence', 0), permissions=False,
                        requestId=request.get('requestId', 0))
        panel.wait_for.side_effect = reply
        return panel, UsbLiveClient(panel)

    def test_open_send_and_close_share_existing_serial_owner(self):
        panel, client = self.fixture()
        client.open()
        client.send([dict(provider='claude', id='opaque_1', state='TESTING')])
        self.assertEqual(client.sequence, 1)
        panel.wait_for.side_effect = None
        panel.wait_for.return_value = dict(type='live_reply', schema=1, cmd='live_close', ok=True,
            bootId=17, epoch=2, sequence=1, permissions=False, requestId=0)
        client.close()
        self.assertIsNone(client.epoch)
        self.assertEqual([json.loads(call.args[0])['cmd'] for call in panel.send_line.call_args_list],
                         ['live_open', 'live_state', 'live_close'])

    def test_old_firmware_or_permission_capability_never_opens(self):
        for fields in ({}, {'liveProtocol': True}, {'liveProtocol': 2}, {'livePermissions': True},
                       {'bootId': False}):
            panel, client = self.fixture()
            panel.info = {} if not fields else dict(panel.info, **fields)
            with self.subTest(fields=fields), self.assertRaises(ValueError): client.open()
            panel.send_line.assert_not_called()

    def test_bad_metadata_never_reaches_usb(self):
        panel, client = self.fixture(); client.open(); panel.send_line.reset_mock()
        for data in ([dict(provider='claude', id='x', state='DONE', hint='private')],
                     [dict(provider='claude', id='x\0y', state='DONE')],
                     [dict(provider='claude', id='x'*65, state='DONE')],
                     [dict(provider='claude', id='x', state='APPROVE')],
                     [dict(provider='claude', id='x', state='DONE')]*2,
                     [dict(provider='claude', id=str(i), state='UNKNOWN') for i in range(9)]):
            with self.subTest(data=data), self.assertRaises(ValueError): client.send(data)
        panel.send_line.assert_not_called()

    def test_ambiguous_delivery_closes_session_without_retry(self):
        panel, client = self.fixture(); client.open()
        panel.wait_for.side_effect = TimeoutError('synthetic timeout')
        with self.assertRaises(TimeoutError): client.send([])
        self.assertIsNone(client.epoch)
        count=panel.send_line.call_count
        with self.assertRaises(ValueError): client.send([])
        self.assertEqual(panel.send_line.call_count,count)

    def test_changed_boot_sequence_epoch_or_security_rejects_reply(self):
        for fields in ({'bootId': 18}, {'epoch': 3}, {'sequence': 0}, {'sequence': True},
                       {'permissions': True}, {'requestId': 7}, {'private': 'ignored?'}):
            panel, client = self.fixture(); client.open()
            panel.wait_for.side_effect = None
            panel.wait_for.return_value = dict(type='live_reply', schema=1, cmd='live_state', ok=True,
                bootId=17, epoch=2, sequence=1, permissions=False, requestId=0, **{})
            panel.wait_for.return_value.update(fields)
            with self.subTest(fields=fields), self.assertRaises(ValueError): client.send([])
            self.assertIsNone(client.epoch)

    def test_complete_snapshot_copy_and_unknown_state(self):
        rows=[dict(provider='codex',id='opaque',state='UNKNOWN')]
        copied=validate_agents(rows); rows[0]['state']='DONE'
        self.assertEqual(copied[0]['state'],'UNKNOWN')
        self.assertEqual(validate_agents([]),[])


if __name__ == '__main__': unittest.main()
