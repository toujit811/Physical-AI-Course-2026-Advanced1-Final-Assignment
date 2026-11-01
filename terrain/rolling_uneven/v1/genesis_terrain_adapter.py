"""Load the approved rolling uneven terrain into Genesis 1.4.5.

NOTE: This adapter has NOT been executed with Genesis in this environment.
Use this as a terrain-construction helper inside the Mac's existing Go2 scene,
not as a replacement for its controller/observations/evaluation logic.
"""
from pathlib import Path
import numpy as np

GRID_SHAPE = (161, 53)
HORIZONTAL_SCALE_M = 0.05
VERTICAL_SCALE_M = 0.001
WORLD_ORIGIN_M = (-1.0, -1.3, 0.0)


def load_heightfield(asset_npz):
    """Return an integer Genesis height-field and quantization diagnostics."""
    path = Path(asset_npz)
    with np.load(path, allow_pickle=False) as src:
        x = src['x_m'].copy()
        y = src['y_m'].copy()
        z = src['z_m'].copy()
    if z.shape != GRID_SHAPE or x.shape != (161,) or y.shape != (53,):
        raise ValueError(f'Unexpected terrain grid shape: {z.shape}')
    if not (np.isfinite(z).all() and np.min(z) >= 0 and np.max(z) <= 0.20):
        raise ValueError('Nonfinite/out-of-range terrain')
    if not (np.allclose(np.diff(x), HORIZONTAL_SCALE_M, atol=1e-10)
            and np.allclose(np.diff(y), HORIZONTAL_SCALE_M, atol=1e-10)):
        raise ValueError('Unexpected terrain sampling scale')
    if not (abs(x[0] - WORLD_ORIGIN_M[0]) < 1e-10
            and abs(y[0] - WORLD_ORIGIN_M[1]) < 1e-10):
        raise ValueError('Unexpected world origin')
    scaled = np.rint(z / VERTICAL_SCALE_M)
    if np.max(np.abs(scaled)) > np.iinfo(np.int16).max:
        raise ValueError('Heightfield int16 overflow')
    hf = np.ascontiguousarray(scaled.astype(np.int16))
    reconstructed = hf.astype(np.float64) * VERTICAL_SCALE_M
    max_error_m = float(np.max(np.abs(reconstructed - z)))
    if max_error_m > VERTICAL_SCALE_M / 2 + 1e-9:
        raise AssertionError('Excessive quantization error')
    return hf, {
        'grid_shape': list(GRID_SHAPE),
        'horizontal_scale_m': HORIZONTAL_SCALE_M,
        'vertical_scale_m': VERTICAL_SCALE_M,
        'pos_m': list(WORLD_ORIGIN_M),
        'height_max_m': float(np.max(reconstructed)),
        'quantization_max_error_m': max_error_m,
        'collision_verified_in_genesis': False,
    }


def add_approved_terrain(scene, asset_npz):
    """Call after gs.init, before scene.build. Returns terrain entity, diagnostics."""
    import genesis as gs
    height_field, diagnostics = load_heightfield(asset_npz)
    entity = scene.add_entity(
        gs.morphs.Terrain(
            height_field=height_field,
            horizontal_scale=HORIZONTAL_SCALE_M,
            vertical_scale=VERTICAL_SCALE_M,
            pos=WORLD_ORIGIN_M,
        )
    )
    return entity, diagnostics
