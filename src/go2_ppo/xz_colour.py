"""Colour-only X–Z composition. Reuse the existing unlit terrain colour mapping."""
import numpy as np
import matplotlib as mpl
from matplotlib.colors import Normalize
from PIL import ImageDraw
from .stage2_visual_diagnostic import CM_RANGE,texture_rgb
from .video_materials import font
from .xz_profile import RECT,plot_pixels,panel_background

def lut_rgb():
    return np.round(mpl.colormaps['viridis'](np.arange(256)/255)[:,:3]*255).astype(np.uint8)

def normalised_indices(z_m):
    # Native heightfield and its texture are float32; retain that precision/order.
    h=np.asarray(z_m,dtype=np.float32)
    if not np.isfinite(h).all():raise ValueError('Non-finite elevation')
    n=np.asarray(Normalize(*CM_RANGE)(h*100))
    return n,np.minimum((np.clip(n,0,1)*256).astype(int),255)

def height_rgb(z_m):
    h=np.asarray(z_m,dtype=np.float32)
    if not np.isfinite(h).all():raise ValueError('Non-finite elevation')
    return texture_rgb(h.reshape(-1,1))[0].reshape(h.shape+(3,))

def colour_panel(xs,z,seed):
    im=panel_background(xs,z,seed);d=ImageDraw.Draw(im)
    left,top,right,bottom=RECT
    # Replace the old tan/blue fills and dark contour; neutral gray only denotes soil.
    d.rectangle((left-3,top-3,right+3,bottom+3),fill=(248,250,252))
    px,pz=plot_pixels(xs,z)
    d.polygon([(left,bottom),*zip(px,pz),(right,bottom)],fill=(224,228,231))
    for value in range(-1,8):
        x,_=plot_pixels(value,0);d.line((x,top,x,bottom),fill=(225,230,235))
    for value in [-1.,2.,4.]:
        _,y=plot_pixels(0,value/100);d.line((left,y,right,y),fill=(220,225,230))
    _,zero=plot_pixels(0,0)
    for x in range(int(left),int(right),12):d.line((x,zero,min(x+6,right),zero),fill=(60,70,80))
    draw_contour(d,xs,z)
    d.text((18,90),'共通の標高色（照明前）',fill=(30,45,60),font=font(16))
    for i,cm in enumerate([-1.2,0.,2.,4.]):
        c=tuple(height_rgb(np.array(cm/100)));y=120+i*32
        d.rectangle((20,y,46,y+19),fill=c);d.text((56,y-2),f'{cm:+g} cm',fill=(30,45,60),font=font(18))
    d.multiline_text((18,265),'viridis / 範囲固定\n-1.2 ～ +4.0 cm\n全試行で共通\n自動正規化なし',fill=(45,60,75),font=font(16),spacing=8)
    d.multiline_text((1080,100),'輪郭線 ＝ 実標高\n灰塗り ＝ 地面側\n\n3Dは陰影あり\n断面は世界Y=0\n現在Xは赤線\n\n0cm基準とFLATの\n輪郭線は重なります',fill=(45,60,75),font=font(16),spacing=8)
    return im

def draw_contour(d,xs,z):
    px,pz=plot_pixels(xs,z)
    # Subdivide at <=0.5 horizontal pixels; colour each segment from its actual Z.
    for i in range(len(xs)-1):
        n=max(1,int(np.ceil((px[i+1]-px[i])*2)))
        xx=np.linspace(xs[i],xs[i+1],n+1);zz=np.linspace(z[i],z[i+1],n+1)
        sx,sy=plot_pixels(xx,zz);colors=height_rgb((zz[:-1]+zz[1:])/2)
        for j,c in enumerate(colors):d.line((sx[j],sy[j],sx[j+1],sy[j+1]),fill=tuple(c),width=4)
    # Preserve exact unlit source RGB at the native profile samples for raster audits.
    for x,y,c in zip(px,pz,height_rgb(z)):d.point((int(x),int(y)),fill=tuple(c))
