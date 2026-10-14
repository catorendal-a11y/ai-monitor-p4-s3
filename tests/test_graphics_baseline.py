import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from graphics_baseline import validate_graphics,interval


def sample():
    return dict(type='graphics',schema=1,enabled=True,saturated=False,ppaActive=False,displayRefreshHz=None,
        bootId=7,uptimeMs=1000,flushCalls=10,pixelsSubmitted=10000,rotationUs=3000,submissionUs=1200,
        maxRotationUs=400,maxSubmissionUs=200)


class GraphicsBaselineTests(unittest.TestCase):
    def test_interval_is_not_false_fps(self):
        first=sample(); last=dict(first,uptimeMs=2000,flushCalls=14,pixelsSubmitted=12000,rotationUs=4000,submissionUs=2000)
        result=interval(first,last)
        self.assertEqual(result['meanRotationUs'],250)
        self.assertIsNone(result['displayRefreshHz'])
        self.assertEqual(result['pixelsSubmitted'],2000)

    def test_reboot_saturation_disabled_decrease_and_rollover(self):
        first=sample()
        for change in (dict(bootId=8),dict(saturated=True),dict(flushCalls=1),dict(uptimeMs=1000)):
            self.assertIsNone(interval(first,dict(first,**change)))
        start=dict(first,uptimeMs=0xffffff00); end=dict(first,uptimeMs=256)
        self.assertEqual(interval(start,end)['durationMs'],512)
        disabled=dict(first,enabled=False,flushCalls=0,pixelsSubmitted=0,rotationUs=0,submissionUs=0,maxRotationUs=0,maxSubmissionUs=0)
        self.assertIsNone(interval(disabled,disabled))

    def test_unknown_gpu_claim_or_invalid_metric_is_rejected(self):
        for change in (dict(ppaActive=True),dict(displayRefreshHz=60),dict(bootId=True),dict(rotationUs=-1),
                       dict(flushCalls=1<<64),dict(maxRotationUs=99999)):
            with self.assertRaises(ValueError): validate_graphics(dict(sample(),**change))


if __name__=='__main__': unittest.main()
