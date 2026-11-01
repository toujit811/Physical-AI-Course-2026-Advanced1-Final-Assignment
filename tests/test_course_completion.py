import unittest
from go2_ppo import course_completion as c


def row(t,x=0.,foot=0.,**flags):
    q=dict(time_s=t,x_m=x,y_m=0.,height_m=.3,roll_deg=0.,pitch_deg=0.,
           physical_fallen=False,out_of_terrain=False,fallen=False,
           unexpected_floor_contact=False,engine_error=False)
    for leg in ('FL','FR','RL','RR'):
        q[leg+'_center_x_m']=foot;q[leg+'_sphere_radius_m']=.022
    q.update(flags);return q


class CourseCompletionTests(unittest.TestCase):
    def test_api(self):self.assertTrue(callable(getattr(c,'CourseTracker',None)))

    def test_base_and_front_feet_crossing_is_not_full_completion(self):
        tracker=c.CourseTracker()
        for i in range(25):
            q=row(i*.01,6.6,6.6);q['RL_center_x_m']=6.2;q['RR_center_x_m']=6.3
            tracker.update(q)
        self.assertFalse(tracker.summary()['success']);self.assertEqual(tracker.summary()['reason'],'RUNNING')

    def test_entire_sphere_must_pass_then_remain_for_point_two_seconds(self):
        tracker=c.CourseTracker()
        for i in range(5):tracker.update(row(i*.01,6.7,6.41))
        self.assertIsNone(tracker.summary()['first_all_feet_pass_s'])
        for i in range(5,25):tracker.update(row(i*.01,6.7,6.45))
        self.assertFalse(tracker.summary()['success'])
        tracker.update(row(.25,6.7,6.45));s=tracker.summary()
        self.assertTrue(s['success']);self.assertEqual(s['first_all_feet_pass_s'],.05)
        self.assertEqual(s['confirmed_at_sim_s'],.25)

    def test_retreat_resets_continuous_confirmation(self):
        tracker=c.CourseTracker()
        for i in range(10):tracker.update(row(i*.01,6.7,6.45))
        tracker.update(row(.10,6.7,6.41))
        for i in range(11,31):tracker.update(row(i*.01,6.7,6.45))
        self.assertFalse(tracker.summary()['success'])
        tracker.update(row(.31,6.7,6.45));self.assertTrue(tracker.summary()['success'])
        self.assertEqual(tracker.summary()['confirmation_start_s'],.11)

    def test_safety_precedes_success_and_zero_force_contact_is_not_stop(self):
        for flag,reason in [('physical_fallen','FALL'),('out_of_terrain','OUT_OF_BOUNDS'),('engine_error','ENGINE_ERROR')]:
            tracker=c.CourseTracker()
            for i in range(20):tracker.update(row(i*.01,6.7,6.45,unexpected_floor_contact=True))
            tracker.update(row(.2,6.7,6.45,**{flag:True}))
            self.assertFalse(tracker.summary()['success']);self.assertEqual(tracker.summary()['reason'],reason)

    def test_nonfinite_or_missing_measurement_cannot_pass(self):
        for bad in ('nan','missing'):
            tracker=c.CourseTracker();q=row(0,6.7,6.45)
            if bad=='nan':q['RR_center_x_m']=float('nan')
            else:del q['RR_center_x_m']
            tracker.update(q);self.assertEqual(tracker.summary()['reason'],'STATE_ERROR')

    def test_stall_and_independent_sixty_second_timeout(self):
        tracker=c.CourseTracker()
        for i in range(601):tracker.update(row(i*.01,0.,0.))
        self.assertEqual(tracker.summary()['reason'],'STALLED_NOT_REACHED')
        tracker=c.CourseTracker()
        for i in range(6001):tracker.update(row(i*.01,i*.0005,i*.0005))
        self.assertEqual(tracker.summary()['reason'],'TIMEOUT_NOT_REACHED')

    def test_missing_hundred_hz_sample_is_rejected(self):
        tracker=c.CourseTracker();tracker.update(row(0.));tracker.update(row(.02))
        self.assertEqual(tracker.summary()['reason'],'STATE_ERROR')

    def test_no_physics_after_terminal_and_summary_cannot_mutate_tracker(self):
        tracker=c.CourseTracker();tracker.stop('WALL_TIMEOUT_NOT_REACHED',0.)
        with self.assertRaises(ValueError):tracker.update(row(.01))
        snapshot=tracker.summary();snapshot['reason']='PASS'
        self.assertEqual(tracker.summary()['reason'],'WALL_TIMEOUT_NOT_REACHED')

    def test_historical_reference_selects_actual_condition_without_upgrading_fail(self):
        source={'results':[{'kind':'FLAT','condition':0,'numeric_pass':True,'numeric_gates':{'A':True}},
                           {'kind':'ROLLING_UNEVEN','condition':0,'numeric_pass':False,'numeric_gates':{'no_abnormal_contact':False}}]}
        self.assertTrue(c.historical_reference(source,'FLAT',0)['numeric_pass'])
        self.assertFalse(c.historical_reference(source,'ROLLING_UNEVEN',0)['numeric_pass'])
        with self.assertRaises(ValueError):c.historical_reference(source,'FLAT',2)

    def test_initial_measurement_failure_returns_unknown_safety_not_max_empty_error(self):
        safety=c.summarize_safety([],[],{},[],terminal_verified=False)
        self.assertFalse(safety['measurements_available'])
        self.assertIsNone(safety['joint_input_pass'])
        self.assertIsNone(safety['physical_fall'])
        self.assertIsNone(safety['max_FK_error_m'])
