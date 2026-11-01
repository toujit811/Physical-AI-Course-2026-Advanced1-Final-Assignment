import unittest
from go2_ppo.course_completion import CourseTracker
from go2_ppo.course_media import course_timeline
from test_course_completion import row

class TwelveRecordingTests(unittest.TestCase):
    def test_goal_is_immediate_and_tail_is_three_seconds_of_actual_samples(self):
        t=CourseTracker(confirmation_s=0,post_goal_s=3)
        t.update(row(0,foot=6.41))
        q=t.update(row(.01,x=1,foot=6.423))
        self.assertTrue(q['goal_achieved']);self.assertEqual(q['reason'],'RUNNING')
        for i in range(2,301):q=t.update(row(i*.01,x=1,foot=6.0))
        self.assertEqual(q['reason'],'RUNNING')
        q=t.update(row(3.01,x=1,foot=6.0))
        self.assertEqual(q['reason'],'POST_GOAL_RECORDED')
        self.assertTrue(q['success']);self.assertEqual(q['confirmed_at_sim_s'],.01)
        self.assertEqual(q['post_goal_recorded_s'],3.)

    def test_post_goal_boundary_and_fall_are_recorded_without_fabricating_tail(self):
        t=CourseTracker(confirmation_s=0,post_goal_s=3)
        t.update(row(0,foot=6.5))
        q=t.update(row(.01,foot=6.5,out_of_terrain=True,fallen=True))
        self.assertEqual(q['reason'],'RUNNING')
        q=t.update(row(.02,foot=6.5,physical_fallen=True,fallen=True))
        self.assertEqual(q['reason'],'RUNNING')
        self.assertEqual(q['post_goal_first_events_s'],{'OUT_OF_BOUNDS':.01,'FALL':.02})
        q=t.update(row(.03,foot=6.5,engine_error=True))
        self.assertEqual(q['reason'],'ENGINE_ERROR');self.assertFalse(q['success'])
        self.assertTrue(q['goal_achieved']);self.assertAlmostEqual(q['post_goal_recorded_s'],.03)

    def test_pre_goal_boundary_remains_failure_and_missing_sample_after_goal_errors(self):
        t=CourseTracker(confirmation_s=0,post_goal_s=3)
        self.assertEqual(t.update(row(0,out_of_terrain=True))['reason'],'OUT_OF_BOUNDS')
        t=CourseTracker(confirmation_s=0,post_goal_s=3)
        t.update(row(0,foot=6.5))
        self.assertEqual(t.update(row(.02,foot=6.5))['reason'],'STATE_ERROR')

    def test_no_cards_same_real_frame_timeline_including_offgrid_terminal(self):
        q=course_timeline([0,.04,.07],end_card_frames=0)
        self.assertEqual(len(q),3)
        self.assertEqual([r['simulation_time_s'] for r in q],[0,.04,.07])
        self.assertEqual([r['video_pts_s'] for r in q],[0,.04,.08])
        self.assertFalse(any(r['kind']=='end_card' for r in q))

    def test_paired_profile_keeps_post_goal_position_visible_without_inventing_ground(self):
        import numpy as np
        from go2_ppo.course_media import paired_layout
        terrain={'x':np.array([-1.,0.,7.]),'y':np.array([-1.,0.,1.]),'height_m':np.zeros((3,3))}
        layout=paired_layout(terrain)
        self.assertEqual(layout.plot_xlo,-1.)
        self.assertEqual(layout.plot_xhi,9.)
        self.assertLess(layout._section_xy([8.36],[0.])[0,0],1200)
        np.testing.assert_array_equal(layout.x,terrain['x'])
        np.testing.assert_array_equal(layout.z,[0.,0.,0.])
