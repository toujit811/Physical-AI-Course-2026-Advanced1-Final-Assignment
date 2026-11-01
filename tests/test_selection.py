import hashlib
import json
from pathlib import Path
import tempfile
import os
from unittest.mock import patch
import unittest

from go2_ppo.selection import freeze_candidate, claim_heldout_seed


class SelectionTests(unittest.TestCase):
    def make_inputs(self, root):
        checkpoint = root / 'policy.pt'
        checkpoint.write_bytes(b'fixed model')
        digest = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
        paths = []
        for kind in ('FLAT', 'ROLLING_UNEVEN'):
            for condition in range(3):
                p = root / f'{kind}-{condition}.json'
                p.write_text(json.dumps({'evaluation_kind': kind, 'args': {'condition': condition},
                                         'checkpoint_sha256': digest, 'numeric_pass': True,
                                         'status': 'NUMERIC_PASS_VISUAL_PENDING'}))
                paths.append(p)
        return checkpoint, paths

    def test_only_same_qualified_checkpoint_all_six_conditions_can_be_frozen(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            checkpoint, paths = self.make_inputs(root)
            selection = root / 'selection.json'
            registry = root / 'claims'
            freeze_candidate(checkpoint, paths, selection)
            claim_heldout_seed(selection, checkpoint, 82001, [82001, 82002, 82003], registry=registry)
            with self.assertRaises(FileExistsError):
                claim_heldout_seed(selection, checkpoint, 82001, [82001, 82002, 82003], registry=registry)
            with self.assertRaises(ValueError):
                claim_heldout_seed(selection, checkpoint, 62001, [82001, 82002, 82003], registry=registry)
            checkpoint.write_bytes(b'changed model')
            with self.assertRaises(ValueError):
                claim_heldout_seed(selection, checkpoint, 82002, [82001, 82002, 82003], registry=registry)

    def test_failed_missing_duplicate_or_mixed_checkpoint_evaluations_are_rejected(self):
        for failure in ('failed', 'missing', 'duplicate', 'mixed'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                checkpoint, paths = self.make_inputs(root)
                r = json.loads(paths[0].read_text())
                if failure == 'failed':
                    r['numeric_pass'] = False
                elif failure == 'missing':
                    paths.pop()
                elif failure == 'duplicate':
                    paths[-1] = paths[-2]
                else:
                    r['checkpoint_sha256'] = 'wrong'
                paths[0].write_text(json.dumps(r))
                with self.assertRaises(ValueError):
                    freeze_candidate(checkpoint, paths, root / 'selection.json')
                self.assertFalse((root / 'selection.json').exists())

    def test_distinct_selection_directories_share_experiment_consumption(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            a, b = root / 'candidateA', root / 'candidateB'
            a.mkdir(); b.mkdir()
            ca, va = self.make_inputs(a)
            cb, vb = self.make_inputs(b)
            sa, sb = a / 'selection.json', b / 'selection.json'
            freeze_candidate(ca, va, sa)
            freeze_candidate(cb, vb, sb)
            registry = root / 'project-registry'
            with patch.dict(os.environ, {'GO2_HELDOUT_REGISTRY': str(registry)}):
                claim_heldout_seed(sa, ca, 82001, [82001, 82002])
                with self.assertRaises(FileExistsError):
                    claim_heldout_seed(sb, cb, 82001, [82001, 82002])
                claim_heldout_seed(sb, cb, 82002, [82001, 82002])
            self.assertEqual(len(list(registry.glob('heldout-*.json'))), 2)
