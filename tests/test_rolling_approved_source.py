"""The source hash gate is mandatory even when terrain summary statistics agree."""
import hashlib,sys,tempfile,unittest
from pathlib import Path
import numpy as np
from go2_ppo.rolling_approved_source import verify_heightfield,SourceMismatch,EXPECTED_SHA

class SourceGateTests(unittest.TestCase):
    def test_source_is_rejected_before_loading_arrays(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'heightfield.npz';p.write_bytes(b'unverified data')
            with patch('go2_ppo.rolling_approved_source.np.load') as loader:
                with self.assertRaises(SourceMismatch):verify_heightfield(p)
                loader.assert_not_called()
    def test_matching_shape_and_extremum_do_not_bypass_exact_hash(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'heightfield.npz';z=np.zeros((161,53));z[20,20]=.18932400342623854
            np.savez_compressed(p,x_m=np.linspace(-1,7,161),y_m=np.linspace(-1.3,1.3,53),z_m=z,slope_deg=np.zeros_like(z))
            with self.assertRaises(SourceMismatch):verify_heightfield(p)
    def test_non_npz_payload_is_rejected_as_source_mismatch(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'heightfield.npz';p.write_bytes(b'unverified source')
            with self.assertRaises(SourceMismatch):verify_heightfield(p)

if __name__=='__main__':unittest.main()
