import unittest
from go2_ppo.evaluation_status import exit_code, recording_status, enforce_substep_safety, substep_events


class EvaluationStatusTests(unittest.TestCase):
    def test_task_failure_is_not_a_successful_exit_and_f_stays_separate(self):
        self.assertEqual(exit_code({'status': 'TASK_FAIL', 'numeric_pass': False}), 2)
        self.assertEqual(exit_code({'status': 'TIMEOUT'}), 1)
        self.assertEqual(exit_code({'status': 'ERROR'}), 1)
        self.assertEqual(exit_code({'status': 'NUMERIC_PASS_VISUAL_PENDING', 'numeric_pass': True}), 0)

    def test_requested_but_failed_recording_cannot_claim_started_or_performed(self):
        r = recording_status(True, {'rows': 0, 'status': 'ERROR'}, None)
        self.assertTrue(r['recording_requested'])
        self.assertFalse(r['recording_performed'])
        self.assertFalse(r['recording_started_before_first_physics_step'])
        self.assertEqual(r['visual_gate_F'], 'NOT_RECORDED')
        r = recording_status(True, {'rows': 2, 'recording_started_before_first_physics_step': True}, {'frames_per_view': 1})
        self.assertTrue(r['recording_performed'])
        self.assertTrue(r['recording_started_before_first_physics_step'])
        self.assertEqual(r['visual_gate_F'], 'USER_REVIEW_PENDING')
        self.assertFalse(recording_status(False, {'rows': 2}, {'frames_per_view': 1})['recording_performed'])


class SubstepSafetyTests(unittest.TestCase):
    def safe(self, time):
        return {'time_s': time, 'physical_fallen': False, 'out_of_terrain': False, 'fallen': False}

    def test_odd_substep_fall_or_boundary_cannot_pass_flat_or_rolling(self):
        for field, reason in [('physical_fallen', 'physical_fall'), ('out_of_terrain', 'terrain_boundary')]:
            with self.subTest(field=field):
                states = [self.safe(0), self.safe(.01), self.safe(.02)]
                states[1][field] = True
                states[1]['fallen'] = True
                self.assertFalse(states[-1]['fallen'])
                for gate in ('A', 'progress'):
                    metrics = {'numeric_gates': {gate: True, 'other': True}, 'numeric_pass': True}
                    out = enforce_substep_safety(metrics, states)
                    self.assertFalse(out['numeric_gates'][gate])
                    self.assertFalse(out['numeric_pass'])
                    self.assertTrue(metrics['numeric_gates'][gate])
                    self.assertEqual(out['substep_safety']['termination_reason'], reason)
                    self.assertEqual(out['substep_safety']['first_unsafe_time_s'], .01)

    def test_safe_csv_false_strings_preserve_gates_and_do_not_upgrade_failures(self):
        states = [{'time_s': '0', 'physical_fallen': 'False', 'out_of_terrain': 'False', 'fallen': 'False'}]
        self.assertFalse(substep_events(states)['unsafe'])
        for original in (True, False):
            metrics = {'numeric_gates': {'A': original, 'B': True}, 'numeric_pass': original}
            self.assertEqual(enforce_substep_safety(metrics, states)['numeric_pass'], original)
