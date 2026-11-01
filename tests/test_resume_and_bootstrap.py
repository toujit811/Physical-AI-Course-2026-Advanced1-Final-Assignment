import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from go2_ppo import bootstrap_source
from go2_ppo.train import synchronize_lr


class ResumeTests(unittest.TestCase):
    def test_restored_adam_rate_replaces_stale_adaptive_rate(self):
        group = {'lr': 1e-5, 'params': ['untouched']}
        alg = SimpleNamespace(learning_rate=.001, optimizer=SimpleNamespace(param_groups=[group]))
        self.assertEqual(synchronize_lr(alg), 1e-5)
        self.assertEqual(alg.learning_rate, 1e-5)
        self.assertEqual(group['params'], ['untouched'])

    def test_ambiguous_or_nonfinite_rates_are_rejected(self):
        for rates in ([], [0.], [float('nan')], [.001, .002]):
            alg = SimpleNamespace(optimizer=SimpleNamespace(param_groups=[{'lr': r} for r in rates]))
            with self.assertRaises(ValueError):
                synchronize_lr(alg)

    def test_train_validation_heldout_are_disjoint(self):
        root = Path(__file__).resolve().parents[1]
        for p in (root / 'configs/training').glob('*.json'):
            seeds = json.loads(p.read_text())['seeds']
            groups = [set(v) for v in seeds.values()]
            self.assertEqual(sum(map(len, groups)), len(set.union(*groups)))


class BootstrapTests(unittest.TestCase):
    def test_bad_reference_does_not_replace_existing_target(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / 'terrain/rolling_uneven/v1/heightfield.npz'
            target.parent.mkdir(parents=True)
            target.write_bytes(b'old output preserved')
            source = root / 'bad.npz'
            source.write_bytes(b'bad reference')
            with patch.object(bootstrap_source, '__file__', str(root / 'src/go2_ppo/bootstrap_source.py')):
                with patch.dict(os.environ, {'APPROVED_HEIGHTFIELD_SOURCE': str(source)}):
                    with self.assertRaises(ValueError):
                        bootstrap_source.main()
            self.assertEqual(target.read_bytes(), b'old output preserved')

    def test_unapproved_target_is_quarantined_before_exact_restore(self):
        reference = Path(__file__).resolve().parents[1] / 'assets/approved/heightfield.npz'
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / 'terrain/rolling_uneven/v1/heightfield.npz'
            target.parent.mkdir(parents=True)
            target.write_bytes(b'unapproved generator bytes')
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            with patch.object(bootstrap_source, '__file__', str(root / 'src/go2_ppo/bootstrap_source.py')):
                with patch.dict(os.environ, {'APPROVED_HEIGHTFIELD_SOURCE': str(reference)}):
                    bootstrap_source.main()
            self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(), bootstrap_source.EXPECTED)
            self.assertEqual((root / f'reports/generated/terrain/rejected-{digest}.npz').read_bytes(), b'unapproved generator bytes')
