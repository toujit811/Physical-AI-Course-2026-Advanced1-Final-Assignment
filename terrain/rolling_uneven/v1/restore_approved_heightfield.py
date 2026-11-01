"""Deterministically restore the approved PhysicaAI rolling terrain NPZ.
Run with Python, NumPy and SciPy; SHA-256 must match approved artifact.
"""
from pathlib import Path
import hashlib
import numpy as np
from scipy.interpolate import PchipInterpolator

EXPECTED_SHA256 = "69979149fa5814316b7abea1b4ea01ccb12a0dfd6d36bfe72f55ce79d4071913"
X_KNOT = np.array([-1.0, -0.6, 0.0, 0.45, 1.1, 1.6, 2.15, 2.6,
                   3.18, 3.65, 4.25, 4.9, 5.5, 6.1, 6.6, 7.0])
Z_KNOT = np.array([0.0, 0.0, 0.0, 0.025, 0.09, 0.05, 0.125, 0.078,
                   0.175, 0.135, 0.05, 0.125, 0.08, 0.025, 0.0, 0.0])

def heights(x, y):
    lateral_shift = (0.10*np.sin(np.pi*y/1.3)
                     + 0.06*np.sin(2*np.pi*y/2.7+0.4))
    centerline = PchipInterpolator(X_KNOT, Z_KNOT)(np.clip(x-lateral_shift, -1.0, 7.0))
    e1 = np.clip((x - 0.1)/1.0, 0.0, 1.0)
    e2 = np.clip((6.5 - x)/1.0, 0.0, 1.0)
    smoothstep = lambda t: t*t*(3.0 - 2.0*t)
    envelope = smoothstep(e1) * smoothstep(e2)
    lateral = (0.012*np.sin((x-0.2)*2*np.pi/2.7)*np.cos(np.pi*y/1.3)
               +0.007*np.cos((x-0.8)*2*np.pi/1.5)*np.sin(np.pi*y/0.95))
    local_hills = (0.009*np.exp(-((x-3.4)/0.55)**2-((y-0.35)/0.65)**2)
                   -0.007*np.exp(-((x-4.2)/0.62)**2-((y+0.40)/0.58)**2))
    return np.maximum(centerline + (lateral+local_hills)*envelope, 0.0)*envelope

def main():
    x = np.linspace(-1.0, 7.0, 161)
    y = np.linspace(-1.3, 1.3, 53)
    X, Y = np.meshgrid(x, y, indexing='ij')
    Z = heights(X, Y)
    gx, gy = np.gradient(Z, x, y, edge_order=2)
    slope = np.rad2deg(np.arctan(np.hypot(gx, gy)))
    target = Path(__file__).with_name('heightfield.npz')
    np.savez_compressed(target, x_m=x, y_m=y, z_m=Z, slope_deg=slope)
    sha = hashlib.sha256(target.read_bytes()).hexdigest()
    print(f'Generated {target} | SHA256: {sha}')
    if sha != EXPECTED_SHA256:
        raise SystemExit(f'SHA256 mismatch: expected {EXPECTED_SHA256}; got {sha}')
    print('VERIFIED: exact approved heightfield.npz')

if __name__ == '__main__':
    main()
