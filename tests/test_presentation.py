import copy
import unittest
from go2_ppo import presentation as p


def samples(xs, **flags):
    return [dict(time_s=i*.01, x_m=x, y_m=0., physical_fallen=False,
                 fallen=False, out_of_terrain=False, unexpected_floor_contact=False,
                 **flags) for i,x in enumerate(xs)]


def historical(passed=True):
    return dict(numeric_pass=passed, numeric_gates={'A': True, 'E': passed},
                status='NUMERIC_PASS_VISUAL_PENDING' if passed else 'TASK_FAIL',
                engine_error=False, terminal_sim_s=.04, termination_reason='duration_complete')


def camera(x=0.,z=.3):
    return dict(intrinsics=[[600,0,320],[0,600,180],[0,0,1]],
                extrinsics=[[1,0,0,-x],[0,0,-1,z],[0,1,0,3],[0,0,0,1]])


class PresentationTests(unittest.TestCase):
    def test_api_is_present(self):
        self.assertTrue(all(callable(getattr(p,n,None)) for n in
                            ('analyse_trial','ruler_ticks','select_frames','timeline')))

    def test_start_relative_goal_and_first_observed_crossing(self):
        result=p.analyse_trial(samples([1.2,3.0,5.19,5.21,5.5]),historical(),[])
        self.assertAlmostEqual(result['goal_x_m'],5.2)
        self.assertEqual(result['first_crossing_sample_s'],.03)
        self.assertEqual(result['crossing_bracket']['before']['time_s'],.02)
        self.assertEqual(result['crossing_bracket']['at_or_after']['x_m'],5.21)
        self.assertEqual(result['end_reason'],'GOAL_REACHED')

    def test_backtracking_uses_first_crossing_not_later_recrossing(self):
        result=p.analyse_trial(samples([0,4.1,3.8,4.2,4.4]),historical(),[])
        self.assertEqual(result['first_crossing_sample_s'],.01)

    def test_no_arrival_does_not_invent_continued_motion(self):
        r=p.analyse_trial(samples([0,1,2,3,3.9]),historical(),[])
        self.assertFalse(r['goal_reached']); self.assertEqual(r['end_reason'],'RECORDING_ENDED_WITHOUT_GOAL')
        self.assertEqual(r['presentation_end_sim_s'],.04)

    def test_fall_before_goal_stops_even_if_later_x_crosses(self):
        rows=samples([0,1,2,4.1,4.2]);rows[2]['physical_fallen']=True;rows[2]['fallen']=True
        r=p.analyse_trial(rows,historical(),[])
        self.assertFalse(r['goal_reached']);self.assertEqual(r['end_reason'],'FALL')
        self.assertEqual(r['presentation_end_sim_s'],.02)

    def test_boundary_distinct_from_fall(self):
        rows=samples([0,1,2,3,4.1]);rows[1]['out_of_terrain']=True;rows[1]['fallen']=True
        self.assertEqual(p.analyse_trial(rows,historical(),[])['end_reason'],'OUT_OF_BOUNDS')

    def test_engine_error_is_not_a_fall(self):
        h=historical();h.update(status='ERROR',engine_error=True)
        self.assertEqual(p.analyse_trial(samples([0,1,2,3,3.9]),h,[])['end_reason'],'ENGINE_ERROR')

    def test_missing_and_nonfinite_state_are_unknown(self):
        for mutation in ('missing','nan','gap'):
            rows=samples([0,1,2,3,4.1])
            if mutation=='missing':del rows[1]['physical_fallen']
            elif mutation=='nan':rows[1]['x_m']=float('nan')
            else:rows[1]['time_s']=.015
            self.assertEqual(p.analyse_trial(rows,historical(),[])['end_reason'],'UNKNOWN')

    def test_unloaded_nonfoot_contact_is_not_fall_and_old_gates_immutable(self):
        h=historical(False);original=copy.deepcopy(h)
        event={'time_s':.03,'foot':False,'force_on_robot_N':[0,0,0],'part':'FL_calf'}
        r=p.analyse_trial(samples([0,1,2,4.1,4.2]),h,[event])
        self.assertTrue(r['goal_reached']);self.assertFalse(r['historical_numeric_pass'])
        self.assertEqual(r['nonfoot_events'][0]['time_s'],.03)
        self.assertEqual(h,original);self.assertEqual(r['historical_numeric_gates'],h['numeric_gates'])

    def test_contact_after_goal_is_retained_as_historical_not_in_shown_motion(self):
        r=p.analyse_trial(samples([0,4.1,4.2,4.3,4.4]),historical(False),[{'time_s':.04,'foot':False}])
        self.assertEqual(r['nonfoot_events'][0]['time_s'],.04)
        self.assertEqual(r['presentation_end_sim_s'],.01)

    def test_frame_cutoff_includes_first_real_25fps_frame_after_100hz_crossing(self):
        r=p.analyse_trial(samples([0,1,2,4.1,4.2]),historical(),[])
        self.assertEqual(p.select_frames(r,[0,.04,.08]),[0,1])
        with self.assertRaises(ValueError):p.select_frames(r,[0,.02,.04])
        with self.assertRaises(ValueError):p.select_frames(r,[0.])

    def test_end_card_is_50_frames_outside_simulation_time(self):
        t=p.timeline([0,.04,.08]);self.assertEqual(len(t),53)
        self.assertEqual(t[2]['video_pts_s'],.08)
        self.assertEqual(t[3]['video_pts_s'],.12)
        self.assertIsNone(t[3]['simulation_time_s'])
        self.assertEqual(t[-1]['frozen_at_sim_s'],.08)

    def test_baseline_y_fixed_despite_camera_z_motion(self):
        a=p.ruler_ticks(camera(z=.1),[0,.5,1]);b=p.ruler_ticks(camera(z=.6),[0,.5,1])
        self.assertEqual({q['hud_y_px'] for q in a+b},{43.})
        self.assertNotEqual(a[0]['native_pixel_xy'][1],b[0]['native_pixel_xy'][1])

    def test_saved_projection_pixel_centres_and_world_ticks_move_left(self):
        a=p.ruler_ticks(camera(),[0,1]);b=p.ruler_ticks(camera(.5),[0,1])
        self.assertAlmostEqual(a[0]['hud_x_px'],224+(320+.5)*1.3-.5)
        self.assertAlmostEqual(b[0]['hud_x_px']-a[0]['hud_x_px'],-130.)
        self.assertEqual(a[1]['world_xyz_m'],[1.,0.,0.])

    def test_behind_camera_point_is_not_drawn(self):
        c=camera();c['extrinsics'][2][3]=-3
        self.assertIsNone(p.ruler_ticks(c,[0])[0]['hud_x_px'])
