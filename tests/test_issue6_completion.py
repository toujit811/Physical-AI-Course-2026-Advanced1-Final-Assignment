import unittest
import tempfile
from pathlib import Path
import numpy as np
from go2_ppo.course_completion import CourseTracker,outside_course_boundary
from go2_ppo.course_media import CourseRecorder
from go2_ppo.video_materials import writer
from test_course_completion import row


class Issue6Tests(unittest.TestCase):
    def test_first_complete_four_feet_pass_finishes_without_hold_or_base_requirement(self):
        tracker=CourseTracker(confirmation_s=0.)
        q=row(0.,x=1.,foot=6.41)
        self.assertFalse(tracker.update(q)['success'])
        q=row(.01,x=1.,foot=6.423)
        r=tracker.update(q)
        self.assertTrue(r['success']);self.assertEqual(r['terminal_sim_s'],.01)
        self.assertEqual(r['first_all_feet_pass_s'],.01)

    def test_flat_x_beyond_seven_and_nine_is_not_outside(self):
        for x in (7.003469,9.,100.):
            self.assertFalse(outside_course_boundary('FLAT',[x,.88,.3]))
            self.assertFalse(outside_course_boundary('FLAT',[x,1.2,.03],foot=True))

    def test_y_monitor_and_uneven_boundaries_are_unchanged(self):
        self.assertTrue(outside_course_boundary('FLAT',[7.1,1.26,.3]))
        self.assertTrue(outside_course_boundary('FLAT',[7.1,1.31,.03],foot=True))
        self.assertTrue(outside_course_boundary('ROLLING_UNEVEN',[6.96,0.,.3]))
        self.assertTrue(outside_course_boundary('ROLLING_UNEVEN',[7.001,0.,.03],foot=True))
        self.assertFalse(outside_course_boundary('ROLLING_UNEVEN',[6.94,0.,.3]))

    def test_raw_validation_adds_no_frames_or_edited_movies(self):
        with tempfile.TemporaryDirectory() as directory:
            rec=object.__new__(CourseRecorder);rec.output=Path(directory);rec.closed=True
            rec.records=[{'view':v} for v in ('side','oblique','overhead')]
            for view in ('side','oblique','overhead'):
                with writer(rec.output/f'native-{view}-raw.mp4') as w:w.append_data(np.zeros((720,1280,3),dtype=np.uint8))
            result=rec.validate_raw()
            self.assertEqual(len(list(rec.output.glob('*.mp4'))),3)
            self.assertEqual({r['frames'] for r in result.values()},{1})
            self.assertEqual({r['end_card_frames'] for r in result.values()},{0})
