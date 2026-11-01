"""Seeded static heightfields; no rubble or movable objects."""
import math
import numpy as np
KINDS=("FLAT","BUMPS","SLOPE","STEPS","COMPOUND")
def generate(kind,seed,cfg):
    if kind not in KINDS:raise ValueError(kind)
    grid=cfg["grid"];dx=grid["spacing_m"]
    x=np.arange(grid["x_min_m"],grid["x_max_m"]+dx/2,dx)
    y=np.arange(grid["y_min_m"],grid["y_max_m"]+dx/2,dx)
    X,Y=np.meshgrid(x,y,indexing="ij");h=np.zeros_like(X)
    rng=np.random.default_rng(seed)
    shift=float(rng.uniform(*cfg["seed_geometry_shift_range_m"]))
    wave=float(rng.uniform(*cfg["bumps"]["wavelength_range_m"]))
    phase=float(rng.uniform(0,2*np.pi))
    angle=float(rng.uniform(*cfg["slope"]["angle_range_deg"]))
    step=float(rng.uniform(*cfg["steps"]["height_range_m"]))
    components=[]
    if kind in ("BUMPS","COMPOUND"):
        a,b=(.55,1.25) if kind=="COMPOUND" else (.6,3.2)
        a+=shift;b+=shift
        envelope=np.sin(np.pi*np.clip((X-a)/(b-a),0,1))**2
        envelope[(X<=a)|(X>=b)]=0
        h+=cfg["bumps"]["amplitude_m"]*envelope*np.sin(2*np.pi*(X-a)/wave+phase+.8*Y)
        components.append({"kind":"bumps","start_m":a,"end_m":b,"amplitude_m":cfg["bumps"]["amplitude_m"],"wavelength_m":wave,"phase_rad":phase})
    if kind in ("SLOPE","COMPOUND"):
        a,b,c,d=(1.35,1.85,2.,2.5) if kind=="COMPOUND" else (.65,1.35,1.75,2.45)
        a+=shift;b+=shift;c+=shift;d+=shift
        top=math.tan(math.radians(angle))*(b-a)
        profile=np.minimum(np.clip((X-a)/(b-a),0,1),np.clip((d-X)/(d-c),0,1))
        h+=top*profile
        components.append({"kind":"slope","start_m":a,"up_end_m":b,"down_start_m":c,"end_m":d,"angle_deg":angle,"top_height_m":top})
    if kind in ("STEPS","COMPOUND"):
        a,b=(2.65,3.05) if kind=="COMPOUND" else (.75,1.25)
        a=round((a+shift)/dx)*dx;b=round((b+shift)/dx)*dx
        # Exact one-cell risers, as declared in the fixed configuration.
        up=np.clip((X-(a-dx))/dx,0,1);down=np.clip(((b+dx)-X)/dx,0,1)
        h+=step*np.minimum(up,down)
        components.append({"kind":"low_step","start_m":a,"end_m":b,"height_m":step,"riser_width_m":dx})
    return {"kind":kind,"seed":seed,"x":x,"y":y,"height_m":h.astype(np.float32),
            "metadata":{"kind":kind,"seed":seed,"components":components,"origin_m":[grid["x_min_m"],grid["y_min_m"],0],
                        "grid_spacing_m":dx,"height_min_m":float(h.min()),"height_max_m":float(h.max()),
                        "friction":cfg["friction"],"static":True,"grid_shape":list(h.shape)}}

def height_at(terrain,x,y):
    # Native collision and visual meshes use the (i+1,j)<->(i,j+1) diagonal.
    xs,ys=terrain["x"],terrain["y"];dx=xs[1]-xs[0]
    px=(np.asarray(x)-xs[0])/dx;py=(np.asarray(y)-ys[0])/dx
    i=np.clip(np.floor(px).astype(int),0,len(xs)-2);j=np.clip(np.floor(py).astype(int),0,len(ys)-2)
    u=np.clip(px-i,0,1);v=np.clip(py-j,0,1);h=terrain["height_m"]
    z00=h[i,j];z10=h[i+1,j];z01=h[i,j+1];z11=h[i+1,j+1]
    return np.where(u+v<=1,z00+(z10-z00)*u+(z01-z00)*v,
                    z11+(z01-z11)*(1-u)+(z10-z11)*(1-v))
