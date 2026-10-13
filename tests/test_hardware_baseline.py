"""Synthetic telemetry; no actual board, files, account or radio probing."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from hardware_baseline import collect,validate_hardware
from hardware_presentation import hardware_text


def fixture():
    return dict(type='hardware',schema=1,boardId='guition-p4',chip='esp32p4',firmwareVersion='test',
        sdkVersion='test-sdk',chipRevision=103,cpuMHz=400,bootId=17,uptimeMs=2000,
        flash=dict(bytes=16777216,frequencyHz=80000000,applicationBytes=4500000,partitionBytes=6553600,partitionOffset=65536),
        internalHeap=dict(total=300000,free=150000,minimumFree=140000,largestFreeBlock=100000),
        psram=dict(sizeBytes=33554432,heapTotal=33000000,free=28000000,minimumFree=27000000,largestFreeBlock=24000000),
        display=dict(width=800,height=480,color='RGB565',drawCount=2,drawBytes=1536000,
            rotationBytes=768000,framebufferCount=2,framebufferBytes=1536000,bounceBytes=0),
        hosted=dict(compiled=True,hostVersion='2.12.13',probeState='not-probed',detectedChip=None,coprocessorVersion=None),
        ppa=dict(supported=True,active=False))


class HardwareBaselineTests(unittest.TestCase):
    def test_presentation_distinguishes_snapshot_unknown_radio_and_bad_data(self):
        data=fixture()
        text=hardware_text(dict(state='connected',board='guition-p4',hardware=data))
        self.assertIn('32.00 MiB',text); self.assertIn('free app space',text)
        self.assertIn('C6 and SD: not probed',text); self.assertIn('not continuous telemetry',text)
        self.assertNotIn('32.00 MiB',hardware_text(None))
        self.assertIn('not received',hardware_text(dict(state='connected')))
        data['psram']['free']=1<<40
        self.assertIn('unavailable',hardware_text(dict(state='connected',board='guition-p4',hardware=data)))

    def test_startup_samples_are_bounded_ordered_and_private_fields_are_removed(self):
        data=fixture()
        names=('before-display','after-display','after-lvgl','after-companion')
        data['startupMemory']=[dict(stage=name,captured=True,uptimeMs=100+i*100,
            internalHeap=copy.deepcopy(data['internalHeap']),
            psram=dict(total=data['psram']['heapTotal'],free=data['psram']['free'],
                minimumFree=data['psram']['minimumFree'],largestFreeBlock=data['psram']['largestFreeBlock']),
            private='do not export') for i,name in enumerate(names)]
        result=validate_hardware(data,'guition-p4')
        self.assertEqual(result['flash']['freeApplicationBytes'],2053600)
        self.assertEqual(len(result['startupMemory']),4)
        self.assertNotIn('private',result['startupMemory'][0])
        for change in ('order','type','missing','oversize','time','free-app'):
            broken=copy.deepcopy(data)
            if change=='order': broken['startupMemory'][1]['stage']='before-display'
            if change=='type': broken['startupMemory'][1]['captured']=1
            if change=='missing': broken['startupMemory'][1]['captured']=False
            if change=='oversize': broken['startupMemory'][1]['psram']['free']=40000000
            if change=='time': broken['startupMemory'][1]['uptimeMs']=0
            if change=='free-app': broken['flash']['freeApplicationBytes']=0
            with self.assertRaises(ValueError): validate_hardware(broken,'guition-p4')
        data['startupMemory'][3]=dict(stage=names[3],captured=False)
        self.assertFalse(validate_hardware(data,'guition-p4')['startupMemory'][3]['captured'])

    def test_versions_capabilities_and_physical_capacity_are_distinct(self):
        data=fixture(); data['mac']='private-device'; data['private']='fixture never export'
        report=validate_hardware(data,'guition-p4')
        self.assertNotIn('mac',report); self.assertNotIn('private',report)
        self.assertGreater(report['psram']['sizeBytes'],report['psram']['heapTotal'])
        self.assertIsNone(report['hosted']['detectedChip'])
        self.assertFalse(report['ppa']['active'])

    def test_invalid_numbers_memory_and_guessed_radio_are_rejected(self):
        changes=[('schema',True),('chip','esp32s3'),('cpuMHz',False)]
        for key,value in changes:
            data=fixture(); data[key]=value
            with self.assertRaises(ValueError): validate_hardware(data,'guition-p4')
        for section,key,value in [('flash','applicationBytes',7000000),('psram','free',40000000),
            ('internalHeap','largestFreeBlock',200000),('display','drawCount',3),('hosted','detectedChip','esp32c6'),
            ('ppa','active',True),('flash','bytes',1<<40)]:
            data=fixture(); data[section][key]=value
            with self.assertRaises(ValueError): validate_hardware(data,'guition-p4')

    def test_legacy_diagnostics_unavailable_do_not_guess_a_c6(self):
        panel=Mock(); panel.wait_for.side_effect=[dict(boardId='guition-p4',chip='esp32p4'),RuntimeError('unsupported')]
        data=collect(panel,'guition-p4')
        self.assertEqual(data['telemetry'],'unavailable-in-installed-firmware')
        self.assertEqual(data['hosted']['probeState'],'not-probed')
        self.assertEqual(panel.send_line.call_args_list[1].args[0],'{"cmd":"get_hardware"}')

    def test_wrong_identity_stops_before_second_request(self):
        panel=Mock(); panel.wait_for.return_value=dict(boardId='waveshare-s3-43',chip='esp32s3')
        with self.assertRaises(ValueError): collect(panel,'guition-p4')
        self.assertEqual(panel.send_line.call_count,1)


if __name__=='__main__': unittest.main()
