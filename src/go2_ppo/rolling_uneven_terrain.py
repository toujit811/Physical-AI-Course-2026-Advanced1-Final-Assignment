"""Load the exact approved archive, audit metre→millimetre conversion and native triangles.

No terrain approximation or fallback generator: a missing source is an input blocker.
"""
from pathlib import Path
import hashlib, json, zipfile
import numpy as np

PACKAGE_SHA='f8bc0ec78026a7ce9632bfc240c39de5f38e266be2554a535ca1465185b28069'

def quantize(height_m):
    h=np.asarray(height_m,dtype=np.float64)
    if h.ndim!=2 or not np.isfinite(h).all():raise ValueError('Height field must be finite and two dimensional')
    mm=np.rint(h/.001)
    if mm.min()<np.iinfo(np.int16).min or mm.max()>np.iinfo(np.int16).max:raise ValueError('int16 height overflow')
    q=mm.astype(np.int16);error=float(np.max(abs(q.astype(float)*.001-h)))
    if error>.000500000001:raise ValueError('Quantization exceeds 0.5mm')
    return q,error

def surface_height(terrain,x,y):
    xs,ys,h=terrain['x'],terrain['y'],terrain['height_m'];x,y=np.broadcast_arrays(x,y)
    dx=float(xs[1]-xs[0]);dy=float(ys[1]-ys[0]);px=(x-xs[0])/dx;py=(y-ys[0])/dy
    i=np.clip(np.floor(px).astype(int),0,len(xs)-2);j=np.clip(np.floor(py).astype(int),0,len(ys)-2)
    u=np.clip(px-i,0,1);v=np.clip(py-j,0,1)
    z00=h[i,j];z10=h[i+1,j];z01=h[i,j+1];z11=h[i+1,j+1]
    z=np.where(u+v<=1,z00+(z10-z00)*u+(z01-z00)*v,z11+(z01-z11)*(1-u)+(z10-z11)*(1-v))
    return np.where((x>=xs[0])&(x<=xs[-1])&(y>=ys[0])&(y<=ys[-1]),z,np.nan)

def load_approved(archive,destination):
    archive=Path(archive);digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    if digest!=PACKAGE_SHA:raise ValueError(f'Approved package SHA256 mismatch: {digest}')
    destination=Path(destination)
    if destination.exists():raise FileExistsError(destination)
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            p=Path(info.filename)
            if p.is_absolute() or '..' in p.parts or (info.external_attr>>16)&0o170000==0o120000:
                raise ValueError('Unsafe archive member')
        z.extractall(destination)
    candidates=list(destination.rglob('heightfield.npz'))
    if len(candidates)!=1:raise ValueError('Expected exactly one original heightfield.npz')
    with np.load(candidates[0],allow_pickle=False) as d:
        heights=[k for k in ('height_m','height_field','heightfield','Z','z','height') if k in d and d[k].shape==(161,53)]
        if len(heights)!=1:raise ValueError(f'Unrecognized original NPZ schema: {d.files}; do not guess/transcribe')
        h=d[heights[0]].astype(np.float64)
        x=np.linspace(-1,7,161);y=np.linspace(-1.3,1.3,53)
        for key in ('x','xs'):
            if key in d and d[key].shape==(161,):np.testing.assert_allclose(d[key],x,atol=1e-7)
        for key in ('y','ys'):
            if key in d and d[key].shape==(53,):np.testing.assert_allclose(d[key],y,atol=1e-7)
    if abs(float(h.max())-.189324003)>1e-7 or abs(float(h[:,26].max())-.188900187)>1e-7:
        raise ValueError('Original height extrema disagree with approved Issue')
    q,e=quantize(h)
    return {'x':x,'y':y,'original_height_m':h,'height_m':q.astype(float)*.001,'height_mm':q,
            'metadata':{'kind':'ROLLING_UNEVEN','seed':6553345583,'origin_m':[-1.,-1.3,0.],
            'grid_spacing_m':.05,'vertical_scale_m':.001,'friction':1.,'grid_shape':[161,53],
            'package_sha256':digest,'original_npz':str(candidates[0].resolve()),'max_quantization_error_m':e}}

def save_audit(terrain,directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(directory/'terrain-source-and-quantized.npz',x=terrain['x'],y=terrain['y'],
        original_height_m=terrain['original_height_m'],height_mm=terrain['height_mm'],height_m=terrain['height_m'])
    (directory/'terrain-metadata.json').write_text(json.dumps(terrain['metadata'],indent=2)+'\n')
