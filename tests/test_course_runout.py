"""A measured post-goal path must retain physical support beyond the old edge."""
import copy
from pathlib import Path
import unittest
import numpy as np
from go2_ppo import rolling_approved_source as source
from go2_ppo.rolling_native_env import terrain_options
from go2_ppo.course_completion import outside_course_boundary
from go2_ppo.rolling_uneven_terrain import surface_height

class CourseRunoutTests(unittest.TestCase):
    def setUp(self):
        self.original=source.verify_heightfield(Path(__file__).resolve().parents[1]/'assets/approved/heightfield.npz')

    def test_exit_extension_preserves_approved_heights_and_supports_tail_at_eight_metres(self):
        before=copy.deepcopy(self.original)
        extend=getattr(source,'extend_flat_runout',None)
        self.assertIsNotNone(extend,'Missing physical post-goal runout')
        t=extend(self.original,12.)
        np.testing.assert_array_equal(t['height_mm'][:161],before['height_mm'])
        np.testing.assert_array_equal(t['original_height_m'][:161],before['original_height_m'])
        np.testing.assert_array_equal(self.original['height_mm'],before['height_mm'])
        self.assertEqual(t['x'][-1],12.)
        self.assertEqual(terrain_options(t)['height_field'].shape,(261,53))
        self.assertEqual(float(surface_height(t,8.6,.4)),0.)
        self.assertFalse(outside_course_boundary('ROLLING_UNEVEN',[8.6,.4,.33],terrain_x_end=12.))
        self.assertTrue(outside_course_boundary('ROLLING_UNEVEN',[12.01,0,.03],foot=True,terrain_x_end=12.))
        self.assertTrue(outside_course_boundary('ROLLING_UNEVEN',[8.6,1.31,.03],foot=True,terrain_x_end=12.))
        self.assertTrue(outside_course_boundary('ROLLING_UNEVEN',[7.01,0,.03],foot=True))

    def test_extension_rejects_raised_seam_invalid_length_and_changed_core(self):
        extend=getattr(source,'extend_flat_runout',None)
        self.assertIsNotNone(extend,'Missing runout validation')
        for end in [6.9,7.,12.01,float('nan')]:
            with self.assertRaises(ValueError):extend(self.original,end)
        bad=copy.deepcopy(self.original);bad['height_mm'][-1,0]=1
        with self.assertRaises(ValueError):extend(bad,12.)
        t=extend(self.original,12.);t['height_mm'][30,26]+=1
        with self.assertRaises(ValueError):terrain_options(t)
        t=extend(self.original,12.);t['height_mm'][180,26]=1
        with self.assertRaises(ValueError):terrain_options(t)

    def test_profile_and_distance_axis_cover_the_actual_twelve_metre_floor(self):
        from go2_ppo.course_media import paired_layout
        t=source.extend_flat_runout(self.original,12.)
        layout=paired_layout(t)
        self.assertEqual(layout.plot_xlo,-1.)
        self.assertEqual(layout.plot_xhi,12.)
        self.assertLessEqual(layout._section_xy([12.],[0.])[0,0],1200.)
        np.testing.assert_array_equal(layout.x,t['x'])
        self.assertEqual(float(layout.z[-1]),0.)
