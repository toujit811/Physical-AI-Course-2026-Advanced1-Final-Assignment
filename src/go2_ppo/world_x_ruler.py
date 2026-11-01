"""Pure-raster, saved-camera world-X distance ruler; no simulator dependencies."""
import numpy as np
from PIL import Image,ImageDraw
from .video_materials import font
from .xz_profile import project_points,plot_pixels,RECT

ORIGIN=np.array([224.,44.]);SCALE=np.array([832/640,468/360])
HUD_SHIFT_PX=100.

def tick_values():return np.arange(-1.,7.0001,.5)
def is_major(x):return abs(x-round(x))<1e-9

def project_x(x,camera):
    points=np.column_stack([np.asarray(x,dtype=float),np.zeros(len(x)),np.zeros(len(x))])
    uv=project_points(points,camera['side_intrinsics'],camera['side_extrinsics'])
    # Pixel centres: Pillow's resize maps (u+.5)*scale-.5, not simply u*scale.
    return ORIGIN+(uv+.5)*SCALE-.5

def motion(x,start,previous):
    dx=x-previous
    direction='forward' if dx>1e-6 else 'backward' if dx< -1e-6 else 'stationary'
    return dict(world_x_m=float(x),start_x_m=float(start),delta_x_m=float(x-start),frame_delta_x_m=float(dx),direction=direction)

def crossings(times,x,ticks):
    out=[]
    for tick in ticks:
        for i,(a,b) in enumerate(zip(x[:-1],x[1:])):
            if (a<tick<=b) or (b<=tick<a):
                estimate=times[i]+(tick-a)/(b-a)*(times[i+1]-times[i])
                out.append(dict(world_tick_m=float(tick),bracket_start_s=float(times[i]),bracket_end_s=float(times[i+1]),linear_estimate_s=float(estimate),direction='forward' if b>a else 'backward',note='sample-bracketed crossing/touch; estimate is linear, not an observed substep'))
    return sorted(out,key=lambda e:e['linear_estimate_s'])

def lower_axis(background):
    im=background.copy();d=ImageDraw.Draw(im);left,top,right,bottom=RECT
    d.rectangle((left-15,bottom+1,right+15,694),fill=(248,250,252))
    for tick in tick_values():
        px,_=plot_pixels(tick,0);major=is_major(tick)
        d.line((px,bottom+1,px,bottom+(7 if major else 4)),fill=(35,50,65),width=2 if major else 1)
        if major:d.text((px,bottom+9),str(int(tick)),anchor='mt',font=font(16),fill=(35,50,65))
    return im

def overlay(frame,camera,x,start,previous,projection=None,fixed_baseline_y=None,caption=None):
    im=Image.fromarray(frame).copy();hud=Image.new('RGBA',(832,468));d=ImageDraw.Draw(hud)
    ticks=tick_values()
    uv,base=projection if projection is not None else (project_x(ticks,camera),project_x(np.array([x]),camera)[0])
    baseline=float(uv[0,1]+HUD_SHIFT_PX-ORIGIN[1]) if fixed_baseline_y is None else fixed_baseline_y-ORIGIN[1]
    if fixed_baseline_y is None:assert np.ptp(uv[:,1])<1e-8
    dark=(10,15,22,255);light=(248,250,252,255)
    d.text((10,393),caption or '世界X距離目盛り（Y=0・Z=0の投影／HUD）',font=font(14),fill=light,stroke_width=1,stroke_fill=dark)
    d.line((0,baseline,831,baseline),fill=dark,width=4);d.line((0,baseline,831,baseline),fill=light,width=1)
    audit=[]
    for tick,p in zip(ticks,uv):
        u=float(p[0]-ORIGIN[0]);major=is_major(tick);visible=1<=u<=830;label=False
        if visible:
            length=12 if major else 6
            d.line((u,baseline,u,baseline+length),fill=dark,width=4 if major else 3)
            d.line((u,baseline,u,baseline+length),fill=light,width=2 if major else 1)
            text=f'{int(tick)}m';box=d.textbbox((u,baseline+16),text,font=font(16),anchor='mt',stroke_width=1)
            if major and box[0]>=1 and box[2]<=830:
                d.text((u,baseline+16),text,font=font(16),anchor='mt',fill=light,stroke_width=1,stroke_fill=dark);label=True
        audit.append(dict(world_x_m=float(tick),world_y_m=0.,world_z_m=0.,upper_projected_x_px=float(p[0]) if np.isfinite(p[0]) else None,upper_ground_y_px=float(p[1]) if np.isfinite(p[1]) else None,upper_hud_y_px=float(baseline+ORIGIN[1]),visible=bool(visible),major=bool(major),label_visible=label,lower_x_px=float(plot_pixels(tick,0)[0])))
    bx=float(base[0]-ORIGIN[0]);d.polygon([(bx,baseline),(bx-6,baseline-11),(bx+6,baseline-11)],fill=(225,40,50,255),outline=dark)
    im.paste(hud,tuple(ORIGIN.astype(int)),hud)
    state=motion(x,start,previous);d=ImageDraw.Draw(im)
    direction={'forward':'前進（+X）','backward':'後退（−X）','stationary':'ほぼ静止'}[state['direction']]
    for y,text in [(382,f'世界X = {x:+.3f} m'),(410,f'開始からΔX = {x-start:+.3f} m'),(438,direction),(470,'赤▽＝現在Xの投影'),(492,'基準：世界Y=0 / Z=0')]:
        d.text((18,y),text,font=font(15),fill=(145,25,35) if y==438 else (35,50,65))
    mask=np.asarray(hud)[:,:,3]>0
    return np.asarray(im),audit,state,mask
