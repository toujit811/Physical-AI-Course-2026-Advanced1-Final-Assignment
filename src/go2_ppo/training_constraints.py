"""Training rewards only; these margins never change physical/evaluation limits."""
import copy
import math
import torch


def rollout_reward_metrics(samples):
    if samples.ndim != 2 or samples.shape[1] % 2 or not torch.isfinite(samples).all():
        raise ValueError('Expected finite balanced rollout rewards [steps, environments]')
    half = samples.shape[1] // 2
    return {'FLAT_mean_step_reward': float(samples[:, :half].mean()),
            'ROLLING_UNEVEN_mean_step_reward': float(samples[:, half:].mean())}


def progress_metadata(num_envs, completed_updates, environment_steps, optimizer_steps):
    return {'learning_performed': completed_updates > 0,
            'updated_env_steps': num_envs * 24 * completed_updates,
            'collected_env_steps': sum(environment_steps.values()),
            'optimizer_step_calls': optimizer_steps}


def apply_ppo_overrides(config, overrides):
    if set(overrides) - {'entropy_coef'}:
        raise ValueError('Only the versioned entropy regularizer may be overridden')
    if any(not math.isfinite(v) or v < 0 for v in overrides.values()):
        raise ValueError('Invalid PPO regularization coefficient')
    result = copy.deepcopy(config)
    result['algorithm'].update(overrides)
    return result


def check_native_errors(groups):
    for index, group in enumerate(groups):
        if bool(group.engine_errors.any()):
            raise RuntimeError(f'Native solver error in mixed group {index}')


def joint_guard_cost(q, lower, upper, margin):
    if margin < 0 or bool(((upper - lower) <= 2 * margin).any()):
        raise ValueError('Guard margin must leave a nonempty joint interval')
    return (torch.clamp(lower + margin - q, min=0)
            + torch.clamp(q - upper + margin, min=0)).square().sum(-1)
