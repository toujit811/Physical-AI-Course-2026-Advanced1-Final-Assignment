"""Fixed world-Y terrain sections and camera geometry; no physical modifications."""
import math
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
from .video_materials import font
from .stage2_terrain import height_at

X_RANGE=(-1.,7.);Z_CM_RANGE=(-1.5,4.)
RECT=(94.,562.,1250.,668.)

def elevation_extrema(z):
    return dict(height_cm=max(0.,float(np.max(z)*100)),depth_cm=max(0.,float(-np.min(z)*100)))

def extract_profile(terrain,y=0.):
    xs=np.asarray(terrain['x']);ys=np.asarray(terrain['y'])
    if not ys[0]-1e-12<=y<=ys[-1]+1e-12:raise ValueError('Section Y outside terrain')
    near=np.flatnonzero(abs(ys-y)<1e-10)
    if len(near):return xs.copy(),np.asarray(terrain['height_m'][:,near[0]],dtype=float).copy()
    j=int(np.clip(np.searchsorted(ys,y)-1,0,len(ys)-2));v=(y-ys[j])/(ys[j+1]-ys[j])
    # A non-grid section crosses each native cell's anti-diagonal as well as its X edges.
    x=np.unique(np.concatenate([xs,xs[:-1]+(1-v)*np.diff(xs)]))
    return x,np.asarray(height_at(terrain,x,np.full_like(x,y)),dtype=float)

def side_metrics(T):
    T=np.asarray(T);right=T[:3,0];up=T[:3,1];forward=-T[:3,2]
    forward=forward/np.linalg.norm(forward);up=up/np.linalg.norm(up);right=right/np.linalg.norm(right)
    return dict(forward=forward.tolist(),up=up.tolist(),right=right.tolist(),position=T[:3,3].tolist(),
        tilt_deg=math.degrees(math.asin(float(np.clip(forward[2],-1,1)))),
        angle_to_world_x_deg=math.degrees(math.acos(float(np.clip(forward[0],-1,1)))),
        up_to_world_z_deg=math.degrees(math.acos(float(np.clip(up[2],-1,1)))))

def project_points(points,K,E):
    world=np.column_stack([points,np.ones(len(points))]);cam=(np.asarray(E)@world.T).T[:,:3]
    if np.any(cam[:,2]<=0):raise ValueError('Projection point behind camera')
    projected=(np.asarray(K)@cam.T).T
    return projected[:,:2]/projected[:,2,None]

def framing_bounds(points,K,E,res,margin=2.):
    uv=project_points(points,K,E);lo=uv.min(axis=0);hi=uv.max(axis=0)
    return dict(min_uv=lo.tolist(),max_uv=hi.tolist(),inside=bool(lo[0]>=margin and lo[1]>=margin and hi[0]<=res[0]-1-margin and hi[1]<=res[1]-1-margin),
                minimum_margin_px=float(min(lo[0],lo[1],res[0]-1-hi[0],res[1]-1-hi[1])))

def plot_pixels(x,z_m):
    left,top,right,bottom=RECT
    px=left+(np.asarray(x)-X_RANGE[0])/(X_RANGE[1]-X_RANGE[0])*(right-left)
    pz=bottom-(np.asarray(z_m)*100-Z_CM_RANGE[0])/(Z_CM_RANGE[1]-Z_CM_RANGE[0])*(bottom-top)
    return px,pz

def panel_background(xs,z,seed):
    im=Image.new('RGB',(1280,720),(245,247,250));d=ImageDraw.Draw(im)
    d.rectangle((0,520,1279,719),fill=(248,250,252))
    d.text((18,523),f'世界Y=0m固定のX–Z断面 / seed={seed if seed is not None else "FLAT"}',fill=(25,40,55),font=font(19))
    d.text((735,523),'縦方向を拡大表示（X[m]・Z[cm]）',fill=(100,55,20),font=font(19))
    method='FLAT: 解析平面Z=0 / 図の標本間隔2.5cm' if seed is None else 'heightfield格子2.5cm / native対角線に沿う三角形線形補間'
    d.text((18,545),method,fill=(45,60,75),font=font(14))
    d.text((1085,545),'赤線＝現在X',fill=(170,25,35),font=font(14))
    left,top,right,bottom=RECT
    for value in [-1,0,1,2,3,4,5,6,7]:
        x,_=plot_pixels(value,0)
        d.line((x,top,x,bottom),fill=(225,230,235));d.text((x-8,bottom+4),str(value),fill=(35,50,65),font=font(17))
    for value in [-1.,0.,2.,4.]:
        _,y=plot_pixels(0,value/100)
        d.line((left,y,right,y),fill=(220,225,230));d.text((left-42,y-10),f'{value:g}',fill=(35,50,65),font=font(17))
    d.text((8,566),'Z[cm]',fill=(25,40,55),font=font(18));d.text((1100,695),'世界X [m]',fill=(25,40,55),font=font(18))
    px,pz=plot_pixels(xs,z);points=list(zip(px.tolist(),pz.tolist()))
    d.polygon([(left,bottom),*points,(right,bottom)],fill=(216,221,224))
    _,zero=plot_pixels(0,0)
    # Positive relief and depressions relative to Z=0; the gray fill only denotes ground side.
    for i in range(len(xs)-1):
        if z[i]>=0 and z[i+1]>=0:color=(224,198,151)
        elif z[i]<=0 and z[i+1]<=0:color=(166,200,220)
        else:continue
        d.polygon([(px[i],zero),(px[i],pz[i]),(px[i+1],pz[i+1]),(px[i+1],zero)],fill=color)
    d.line(points,fill=(25,50,55),width=2)
    for x in range(int(left),int(right),12):d.line((x,zero,min(x+6,right),zero),fill=(25,40,55),width=1)
    d.text((14,695),'0cm基準 / 面塗りは地面側の模式表示',fill=(45,60,70),font=font(16))
    ext=elevation_extrema(z)
    d.text((475,695),f'断面: 高さ+{ext["height_cm"]:.2f}cm / 深さ{ext["depth_cm"]:.2f}cm',fill=(45,60,70),font=font(16))
    return im

def compose_profile(rgb,title,t,base_x,base_y,xs,z,background):
    im=background.copy();d=ImageDraw.Draw(im)
    d.text((18,5),f'{title}  [保存姿勢の再描画・試作]  t={t:.2f}s  X={base_x:.3f}m  Y={base_y:+.3f}m',fill=(25,40,55),font=font(19))
    im.paste(Image.fromarray(rgb).resize((832,468),Image.Resampling.LANCZOS),(224,44));d=ImageDraw.Draw(im)
    mx,mz=plot_pixels(base_x,float(np.interp(base_x,xs,z)))
    d.line((mx,RECT[1],mx,RECT[3]),fill=(195,35,45),width=2);d.ellipse((mx-4,mz-4,mx+4,mz+4),fill=(195,35,45))
    d.polygon([(mx,RECT[1]+7),(mx-4,RECT[1]+1),(mx+4,RECT[1]+1)],fill=(195,35,45))
    return np.asarray(im)
