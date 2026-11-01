"""Read existing results only; export tables/figures without training or judging F."""
import csv
import json
import os
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'reports/generated/issue2'


def write_csv(path, rows):
    if not rows:
        return
    fields = sorted(set().union(*(r.keys() for r in rows)))
    with path.open('w') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path):
    return list(csv.DictReader(path.open())) if path.exists() else []


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    figures = OUT / 'figures'
    figures.mkdir(exist_ok=True)
    training = []
    for path in sorted((ROOT / 'logs/mixed-d').glob('*/result.json')):
        r = json.loads(path.read_text())
        row = {k: r.get(k) for k in ('name', 'status', 'completed_updates', 'actual_env_steps',
                                     'wall_seconds', 'checkpoint_sha256', 'parent_sha256',
                                     'full_state_roundtrip_exact', 'parent_unchanged', 'reason')}
        rows = read_csv(path.parent / 'iterations.csv')
        resources = read_csv(path.parent / 'resources.csv')
        if rows:
            row['loop_env_steps_per_second'] = r['actual_env_steps'] / sum(float(x['collect_s']) + float(x['update_s']) for x in rows)
        if resources:
            row['peak_rss_bytes'] = max(int(x['process_rss_bytes']) for x in resources)
            row['mean_process_cpu_percent'] = float(np.mean([float(x['process_cpu_percent']) for x in resources[1:]]))
            row['swap_growth_bytes'] = int(resources[-1]['swap_used_bytes']) - int(resources[0]['swap_used_bytes'])
        training.append(row)
    write_csv(OUT / 'learning-runs.csv', training)
    validation = []
    for path in sorted((ROOT / 'logs/rolling-native').glob('*/result.json')):
        r = json.loads(path.read_text())
        if not r.get('evaluation_kind'):
            continue
        row = {'run': path.parent.name, 'kind': r['evaluation_kind'], 'status': r['status'],
               'checkpoint_sha256': r['checkpoint_sha256'], 'condition': r['args']['condition'],
               'duration_s': r.get('duration_s'), 'distance_m': r.get('distance_m'),
               'termination_reason': r.get('termination_reason'),
               'max_substep_joint_excursion_rad': r.get('max_substep_joint_excursion_rad'),
               'physical_fall': r.get('physical_fall_observed'), 'recorded': r['recording_performed'],
               'F': r['visual_gate_F']}
        row.update({'gate_' + k: v for k, v in (r.get('numeric_gates') or {}).items()})
        states = read_csv(path.parent / 'states.csv')
        if states:
            last = states[-1]
            row['terminal_base_y_m'] = float(last['y_m'])
            row['maximum_abs_base_y_m'] = max(abs(float(s['y_m'])) for s in states)
            row['terminal_foot_y_min_m'] = min(float(last[f'{leg}_center_y_m']) for leg in ('FL', 'FR', 'RL', 'RR'))
            row['terminal_foot_y_max_m'] = max(float(last[f'{leg}_center_y_m']) for leg in ('FL', 'FR', 'RL', 'RR'))
        validation.append(row)
    write_csv(OUT / 'validation.csv', validation)
    fig, axes = plt.subplots(2, 2, figsize=(12, 7))
    for run in sorted((ROOT / 'logs/mixed-d').glob('mixed128-*')):
        rows = read_csv(run / 'iterations.csv')
        if not rows:
            continue
        x = np.array([int(r['iteration']) for r in rows])
        for ax, key in zip(axes.flat, ('value', 'learning_rate', 'FLAT_mean_abs_y_m', 'ROLLING_UNEVEN_mean_abs_y_m')):
            ax.plot(x, [float(r[key]) for r in rows], label=run.name, linewidth=.8)
            ax.set(xlabel='Completed PPO iteration', ylabel=key)
            ax.grid(alpha=.2)
    axes[0, 0].legend(fontsize=7)
    fig.suptitle('Actual training metrics (stochastic rollout, not validation PASS)')
    fig.tight_layout()
    fig.savefig(figures / 'ppo-history.png', dpi=160)
    plt.close(fig)
    bench = [r for r in training if r['name'] in ('benchmark64-v2', 'benchmark128-v2')]
    bench.sort(key=lambda r: 64 if r['name'].startswith('benchmark64') else 128)
    write_csv(OUT / 'parallel-benchmark.csv', bench)
    if bench:
        fig, axes = plt.subplots(1, 3, figsize=(10, 3))
        names = [r['name'].replace('benchmark', '').replace('-v2', '') for r in bench]
        for ax, key, label in zip(axes, ('loop_env_steps_per_second', 'wall_seconds', 'peak_rss_bytes'), ('Loop envsteps/s', 'Total wall seconds', 'Peak RSS bytes')):
            ax.bar(names, [r[key] for r in bench])
            ax.set_title(label)
        fig.suptitle('Equal 153,600 environment steps including actual PPO updates')
        fig.tight_layout()
        fig.savefig(figures / 'parallel-benchmark.png', dpi=160)
        plt.close(fig)
    fig, ax = plt.subplots(figsize=(11, 5))
    seen = set()
    for r in validation:
        if r['kind'] != 'ROLLING_UNEVEN' or r['condition'] != 2 or r['checkpoint_sha256'] in seen:
            continue
        seen.add(r['checkpoint_sha256'])
        states = read_csv(ROOT / 'logs/rolling-native' / r['run'] / 'states.csv')
        if states:
            ax.plot([float(s['x_m']) for s in states], [float(s['y_m']) for s in states], label=r['run'].replace('validation-', '').replace('-ROLLING_UNEVEN', ''), linewidth=1)
    legacy = os.environ.get('GO2_LEGACY_ROOT')
    if legacy:
        rows = read_csv(Path(legacy) / 'logs/rolling-native/model6500-c2-v2/states.csv')
        if rows:
            ax.plot([float(s['x_m']) for s in rows], [float(s['y_m']) for s in rows], color='black', linewidth=2, label='6500 (existing Issue1 evidence, not rerun)')
    for y in (-1.3, 1.3):
        ax.axhline(y, color='red', linewidth=1)
    for y in (-1.25, 1.25):
        ax.axhline(y, color='red', linestyle='--', linewidth=.7)
    ax.set(xlabel='Actual world X (m)', ylabel='Actual base world Y (m)',
           title='Condition2 (seed2103) rolling base trajectories; feet can exit before base', xlim=(-.1, 7), ylim=(-1.5, 1.5))
    ax.legend(fontsize=7, ncols=2)
    ax.grid(alpha=.2)
    fig.tight_layout()
    fig.savefig(figures / 'rolling-xy-trajectories.png', dpi=160)
    plt.close(fig)
    comparison = [r for r in validation if r['run'].startswith('validation-') and r['condition'] == 2]
    if comparison:
        fig, axes = plt.subplots(1, 2, figsize=(12, 4))
        names = [r['run'].replace('validation-', '').replace('ROLLING_UNEVEN', 'ROLL').replace('-c2', '') for r in comparison]
        for ax, key, label in zip(axes, ('distance_m', 'max_substep_joint_excursion_rad'), ('Terminal progress (m)', 'Maximum actual joint excursion (rad)')):
            ax.bar(names, [r[key] or 0 for r in comparison])
            ax.tick_params(axis='x', rotation=65, labelsize=7)
            ax.set_title(label)
        axes[1].axhline(.002, color='red', linestyle='--', label='unchanged 0.002rad limit')
        axes[1].legend(fontsize=7)
        fig.suptitle('Condition2 (seed2103): progress alone does not establish PASS')
        fig.tight_layout()
        fig.savefig(figures / 'validation-comparison.png', dpi=160)
        plt.close(fig)
    print(f'Exported {len(training)} learning runs, {len(validation)} evaluations to {OUT}')


if __name__ == '__main__':
    main()
