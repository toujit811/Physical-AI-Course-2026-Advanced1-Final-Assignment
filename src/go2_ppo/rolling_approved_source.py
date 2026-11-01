"""Exact heightfield gate for Issue #6554055922. No statistical or geometry fallback."""
from pathlib import Path
import hashlib
import numpy as np
from .rolling_uneven_terrain import quantize

EXPECTED_SHA='69979149fa5814316b7abea1b4ea01ccb12a0dfd6d36bfe72f55ce79d4071913'

class SourceMismatch(ValueError):pass

def verify_heightfield(path):
    path=Path(path);digest=hashlib.sha256(path.read_bytes()).hexdigest()
    if digest!=EXPECTED_SHA:raise SourceMismatch(f'Approved heightfield SHA256 mismatch: expected={EXPECTED_SHA}; actual={digest}')
    with np.load(path,allow_pickle=False) as d:
        if set(d.files)!={'x_m','y_m','z_m','slope_deg'}:raise ValueError('Unexpected approved NPZ schema')
        x,y,z,s=(d[k].copy() for k in ('x_m','y_m','z_m','slope_deg'))
    if x.shape!=(161,) or y.shape!=(53,) or z.shape!=(161,53) or s.shape!=(161,53):raise ValueError('Wrong terrain shape')
    if not all(np.isfinite(v).all() for v in (x,y,z,s)):raise ValueError('Nonfinite approved terrain arrays')
    np.testing.assert_allclose(x,np.linspace(-1,7,161),rtol=0,atol=1e-12);np.testing.assert_allclose(y,np.linspace(-1.3,1.3,53),rtol=0,atol=1e-12)
    if abs(float(z.max())-.18932400342623854)>1e-12:raise ValueError('Wrong terrain maximum')
    mm,error=quantize(z)
    return {'x':x,'y':y,'original_height_m':z,'height_mm':mm,'height_m':mm.astype(float)*.001,'slope_deg':s,
        'metadata':{'kind':'ROLLING_UNEVEN','source_sha256':digest,'authority_comment':6554055922,'grid_spacing_m':.05,'vertical_scale_m':.001,'origin_m':[-1,-1.3,0],'friction':1.,'grid_shape':[161,53],'max_quantization_error_m':error}}
