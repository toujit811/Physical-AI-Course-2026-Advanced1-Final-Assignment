import pathlib
import sys
import types
import unittest
import numpy as np
from genesis_terrain_adapter import load_heightfield, add_approved_terrain

ASSET = pathlib.Path(__file__).with_name('heightfield.npz')

class AdapterOfflineTests(unittest.TestCase):
    def test_load_sample_geometry(self):
        hf, metrics = load_heightfield(ASSET)
        self.assertEqual(hf.shape, (161, 53))
        self.assertTrue(np.issubdtype(hf.dtype, np.integer))
        self.assertGreater(hf.max(), 180)
        self.assertLess(hf.max(), 195)
        self.assertLessEqual(metrics['quantization_max_error_m'], .000500001)
        self.assertEqual(metrics['pos_m'], [-1.0, -1.3, 0.0])
    def test_integration_wiring_without_genesis(self):
        class FakeMorphs:
            @staticmethod
            def Terrain(**kwargs):
                return kwargs
        class FakeScene:
            def add_entity(self, x):
                self.entity = x
                return x
        old = sys.modules.get('genesis')
        sys.modules['genesis'] = types.SimpleNamespace(morphs=FakeMorphs)
        try:
            obj, d = add_approved_terrain(FakeScene(), ASSET)
            self.assertEqual(obj['pos'], (-1.0,-1.3,0.0))
            self.assertEqual(obj['height_field'].shape, (161,53))
            self.assertEqual(obj['vertical_scale'], .001)
            self.assertFalse(d['collision_verified_in_genesis'])
        finally:
            if old is None: sys.modules.pop('genesis',None)
            else: sys.modules['genesis']=old

if __name__ == '__main__':
    unittest.main()
