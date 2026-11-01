"""Freeze a numerically qualified policy before opening any heldout terrain."""
import argparse
import hashlib
import json
import os
from pathlib import Path
from datetime import datetime, timezone


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def freeze_candidate(checkpoint, validations, output):
    sha = digest(checkpoint)
    conditions = set()
    for path in validations:
        result = json.loads(Path(path).read_text())
        condition = (result['evaluation_kind'], result['args']['condition'])
        if (condition in conditions or result['checkpoint_sha256'] != sha
                or result['numeric_pass'] is not True
                or result['status'] != 'NUMERIC_PASS_VISUAL_PENDING'):
            raise ValueError('Candidate needs all six distinct, same-checkpoint numeric PASS results')
        conditions.add(condition)
    required = {(kind, index) for kind in ('FLAT', 'ROLLING_UNEVEN') for index in range(3)}
    if conditions != required:
        raise ValueError('Missing FLAT/ROLLING validation conditions')
    data = {'frozen': True, 'numeric_qualified': True, 'checkpoint_sha256': sha,
            'frozen_at_utc': datetime.now(timezone.utc).isoformat(),
            'validation_result_sha256': {str(p): digest(p) for p in validations},
            'visual_F': 'USER_REVIEW_PENDING'}
    with Path(output).open('x') as handle:
        handle.write(json.dumps(data, indent=2) + '\n')
    return data


def claim_heldout_seed(selection, checkpoint, seed, allowed_seeds, registry=None):
    selection = Path(selection)
    data = json.loads(selection.read_text())
    if (data.get('frozen') is not True or data.get('numeric_qualified') is not True
            or seed not in allowed_seeds or data['checkpoint_sha256'] != digest(checkpoint)):
        raise ValueError('Heldout requires an unchanged, frozen numeric-qualified model and unused allocated seed')
    if registry is None:
        registry = os.environ.get('GO2_HELDOUT_REGISTRY') or (
            Path(__file__).resolve().parents[2] / '.runtime/heldout-registry')
    registry = Path(registry)
    registry.mkdir(parents=True, exist_ok=True)
    marker = registry / f'heldout-{seed}.json'
    # Exclusive creation prevents concurrent evaluations from opening one seed twice.
    with marker.open('x') as handle:
        handle.write(json.dumps({'seed': seed, 'checkpoint_sha256': data['checkpoint_sha256'],
                                 'selection_sha256': digest(selection),
                                 'terrain_family': 'HELDOUT_ROLLING_V1',
                                 'status': 'opened_for_final_evaluation'}) + '\n')
    return marker


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--validations', type=Path, nargs='+', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    freeze_candidate(args.checkpoint, args.validations, args.output)
