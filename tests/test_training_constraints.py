import unittest
import torch
from go2_ppo.training_constraints import joint_guard_cost, check_native_errors, apply_ppo_overrides, progress_metadata, rollout_reward_metrics


class JointGuardTests(unittest.TestCase):
    def test_failed_run_still_reports_completed_learning_and_partial_collection(self):
        info = progress_metadata(64, 2, {'FLAT': 1700, 'ROLLING_UNEVEN': 1700}, 43)
        self.assertTrue(info['learning_performed'])
        self.assertEqual(info['updated_env_steps'], 3072)
        self.assertEqual(info['collected_env_steps'], 3400)
        self.assertEqual(info['optimizer_step_calls'], 43)
        self.assertFalse(progress_metadata(64, 0, {'FLAT': 0, 'ROLLING_UNEVEN': 0}, 0)['learning_performed'])

    def test_entropy_override_keeps_ppo_architecture_and_original_config(self):
        original = {'algorithm': {'class_name': 'PPO', 'entropy_coef': .01}}
        changed = apply_ppo_overrides(original, {'entropy_coef': .001})
        self.assertEqual(changed['algorithm']['entropy_coef'], .001)
        self.assertEqual(changed['algorithm']['class_name'], 'PPO')
        self.assertEqual(original['algorithm']['entropy_coef'], .01)
        for bad in ({'class_name': 'Other'}, {'entropy_coef': -.1}):
            with self.assertRaises(ValueError):
                apply_ppo_overrides(original, bad)

    def test_native_error_is_not_hidden_by_automatic_episode_reset(self):
        from types import SimpleNamespace
        groups = [SimpleNamespace(engine_errors=torch.tensor([False, False])),
                  SimpleNamespace(engine_errors=torch.tensor([False, True]))]
        with self.assertRaises(RuntimeError):
            check_native_errors(groups)
        groups[1].engine_errors.zero_()
        check_native_errors(groups)

    def test_margin_penalizes_approach_before_actual_excursion(self):
        q = torch.tensor([[0.0, 0.95], [-1.02, 1.03]])
        lower, upper = torch.full((2,), -1.0), torch.ones(2)
        physical = joint_guard_cost(q, lower, upper, 0.0)
        guard = joint_guard_cost(q, lower, upper, 0.1)
        torch.testing.assert_close(physical, torch.tensor([0.0, 0.0013]))
        torch.testing.assert_close(guard, torch.tensor([0.0025, 0.0313]))
        self.assertTrue(torch.isfinite(guard).all())

    def test_invalid_guard_cannot_invert_limits(self):
        with self.assertRaises(ValueError):
            joint_guard_cost(torch.zeros(1, 2), -torch.ones(2), torch.ones(2), 1.1)


class RewardHistoryTests(unittest.TestCase):
    def test_per_group_raw_rollout_reward_is_measured_not_filled(self):
        samples = torch.tensor([[1., 3., 5., 7.], [3., 5., 7., 9.]])
        r = rollout_reward_metrics(samples)
        self.assertEqual(r['FLAT_mean_step_reward'], 3.)
        self.assertEqual(r['ROLLING_UNEVEN_mean_step_reward'], 7.)
        with self.assertRaises(ValueError):
            rollout_reward_metrics(torch.tensor([[float('nan'), 1.]]))
