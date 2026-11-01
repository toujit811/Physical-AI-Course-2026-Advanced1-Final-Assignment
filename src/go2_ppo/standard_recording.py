"""Common new-video format. Pure composition/recording, no physics or policy calls."""
import json,hashlib,shutil
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
from .video_materials import ROOT,writer,dump,csvout,font,flat_rgb,sha
from .stage2_visual_diagnostic import CM_RANGE,texture_rgb
from .xz_colour import colour_panel,height_rgb,lut_rgb,draw_contour
from .xz_profile import RECT,X_RANGE,Z_CM_RANGE,extract_profile,plot_pixels,compose_profile,side_metrics
from .world_x_ruler import lower_axis,overlay,tick_values,ORIGIN,SCALE

def load_standard():
    c=json.loads((ROOT/'configs/recording-standard.json').read_text())
    if c['viridis_z_cm']!=list(CM_RANGE) or c['graph_z_cm']!=list(Z_CM_RANGE) or c['world_x_range_m']!=list(X_RANGE):raise ValueError('Conflicting axes/colour scale')
    return c

def section_raster(xs,z):
    left,top,right,bottom=RECT
    px=np.arange(int(left),int(right)+1);py=np.arange(int(top),int(bottom)+1)
    world_x=X_RANGE[0]+(px-left)/(right-left)*(X_RANGE[1]-X_RANGE[0])
    world_z=(Z_CM_RANGE[1]-(py-top)/(bottom-top)*(Z_CM_RANGE[1]-Z_CM_RANGE[0]))/100
    surface=np.interp(world_x,xs,z);mask=world_z[:,None]<=surface[None,:]
    rgb=np.broadcast_to(height_rgb(world_z)[:,None,:],(*mask.shape,3)).copy()
    return dict(pixel_x_m=world_x,pixel_z_m=world_z,surface_z_m=surface,mask=mask,rgb=rgb)

class VideoTemplate:
    def __init__(self,terrain=None,seed=None):
        self.config=load_standard();self.seed=seed
        self.x,self.z=extract_profile(terrain,0.) if terrain is not None else (np.linspace(-1,7,321),np.zeros(321))
        self.raster=section_raster(self.x,self.z);im=colour_panel(self.x,self.z,seed);a=np.array(im)
        left,top,right,bottom=map(int,RECT);region=a[top:bottom+1,left:right+1];region[self.raster['mask']]=self.raster['rgb'][self.raster['mask']]
        im=Image.fromarray(a);d=ImageDraw.Draw(im);_,zero=plot_pixels(0,0)
        for x in range(left,right,12):d.line((x,zero,min(x+6,right),zero),fill=(65,70,80))
        draw_contour(d,self.x,self.z)
        d.rectangle((1080,90,1279,510),fill=(245,247,250))
        d.multiline_text((1080,100),'輪郭内＝画素Zの色\n地中の材質・厚みは\n表していません\n\n3Dは陰影あり\n断面は世界Y=0\n現在X≠足元の高度\n\n縦表示 13.34倍\n色域 −1.2〜+4cm\n範囲外は端色',fill=(40,55,70),font=font(15),spacing=7)
        d.rectangle((8,695,465,719),fill=(248,250,252));d.text((14,695),'断面内は画素Z色／物理厚みではない',font=font(15),fill=(40,55,70))
        self.background=lower_axis(im)
        symbols=Image.new('RGB',(1280,720));sd=ImageDraw.Draw(symbols)
        for x in range(left,right,12):sd.line((x,zero,min(x+6,right),zero),fill=(255,255,255))
        draw_contour(sd,self.x,self.z)
        self.audit_mask=self.raster['mask'] & ~np.any(np.asarray(symbols)[top:bottom+1,left:right+1],axis=2)
        self.definition=dict(section_world_y_m=0.,x_range_m=list(X_RANGE),z_axis_cm=list(Z_CM_RANGE),colour_range_cm=list(CM_RANGE),vertical_display_exaggeration=(RECT[3]-RECT[1])/((Z_CM_RANGE[1]-Z_CM_RANGE[0])/100)/((RECT[2]-RECT[0])/(X_RANGE[1]-X_RANGE[0])),physical_height_multiplier=1.,interior_fill=self.config['interior_fill'],colour_lut_sha256=hashlib.sha256(lut_rgb().tobytes()).hexdigest(),profile_points=len(self.x),profile_min_cm=float(self.z.min()*100),profile_max_cm=float(self.z.max()*100))

    def frame(self,rgb,camera,t,x,y,start,previous,view='side',title='standard video'):
        if np.asarray(rgb).shape!=(360,640,3):raise ValueError('Standard raw capture must be640x360 RGB')
        im=compose_profile(rgb,title,t,x,y,self.x,self.z,self.background)
        kwargs={}
        if view=='oblique':
            E=np.asarray(camera['side_extrinsics']);K=np.asarray(camera['side_intrinsics']);wx=np.r_[tick_values(),x]
            points=np.column_stack([wx,np.zeros(len(wx)),np.zeros(len(wx)),np.ones(len(wx))]);cv=(E@points.T).T[:,:3];valid=cv[:,2]>1e-8
            uv=np.full((len(wx),2),np.nan);p=(K@cv[valid].T).T;uv[valid]=ORIGIN+(p[:,:2]/p[:,2,None]+.5)*SCALE-.5
            kwargs=dict(projection=(uv[:-1],uv[-1]),fixed_baseline_y=465.5,caption='世界X距離目盛り（斜め視点の投影X／HUD）')
        else:
            m=side_metrics(camera['side_camera_to_world'])
            if max(abs(m['tilt_deg']),abs(m['angle_to_world_x_deg']-90),m['up_to_world_z_deg'])>1e-4:raise ValueError('Primary side camera is not true90deg')
        return overlay(im,camera,x,start,previous,**kwargs)

    def save_definition(self,path):
        path=Path(path);dump(path/'recording-format.json',dict(config=self.config,actual=self.definition,seed=self.seed))
        csvout(path/'xz-section-standard.csv',[dict(world_x_m=float(x),world_y_m=0.,world_z_m=float(z)) for x,z in zip(self.x,self.z)])
        self.background.save(path/'standard-background.png')

def camera_metadata(cam):
    return dict(side_intrinsics=np.asarray(cam.intrinsics).tolist(),side_extrinsics=np.asarray(cam.extrinsics).tolist(),side_camera_to_world=np.asarray(cam.transform).tolist())

def set_recording_cameras(cameras,pos):
    x,y,z=pos
    cameras['side'].set_pose(pos=(x+.20,-3.,.30),lookat=(x+.20,0.,.30),up=(0.,0.,1.))
    cameras['oblique'].set_pose(pos=(x+1.1,y-1.5,.98),lookat=(x+.25,y,.10))

def recording_surface(terrain=None):
    import genesis as gs
    return gs.surfaces.Default(diffuse_texture=gs.textures.ImageTexture(image_array=texture_rgb(terrain['height_m'])),roughness=1.) if terrain is not None else gs.surfaces.Default(color=tuple(flat_rgb()/255),roughness=1.)

def flat_visual_override(ground):
    for v in ground.vgeoms:v.vmesh.set_color((*tuple(flat_rgb()/255),1.))

class StandardRecorder:
    def __init__(self,directory,terrain=None,seed=None,template=None):
        self.directory=Path(directory);self.template=template if template is not None else VideoTemplate(terrain,seed);self.writers={};self.records=[];self.cameras=[];self.ticks=[];self.previous={};self.start=None;self.time_origin=None
        self.template.save_definition(directory)
        sources=self.directory/'standard-sources';sources.mkdir()
        for name in ['standard_recording.py','world_x_ruler.py','xz_colour.py','xz_profile.py','video_materials.py','stage2_visual_diagnostic.py']:shutil.copy2(ROOT/'src/go2_ppo'/name,sources/name)
        shutil.copy2(ROOT/'configs/recording-standard.json',sources/'recording-standard.json')
        dump(sources/'sha256.json',{p.name:sha(p) for p in sources.iterdir() if p.is_file()})
        for view in ['side','oblique']:
            self.writers[view]=writer(self.directory/(view+'-incomplete.mp4'));self.writers[view+'-clean']=writer(self.directory/(view+'-clean-incomplete.mp4'))
            (self.directory/('raw-'+view)).mkdir()

    def append(self,view,rgb,camera,t,pos):
        rgb=np.asarray(rgb);rgb=rgb[0] if rgb.ndim==4 else rgb
        if self.time_origin is None:self.time_origin=t
        relative_t=t-self.time_origin;i=round(relative_t*25)
        if abs(i/25-relative_t)>1e-8:raise ValueError('Recording timestamp is not25fps aligned')
        if self.start is None:self.start=pos[0]
        previous=self.previous.get(view,pos[0]);metadata=camera_metadata(camera)
        frame,ticks,state,mask=self.template.frame(rgb,metadata,t,pos[0],pos[1],self.start,previous,view,title='recorded / '+view)
        self.previous[view]=pos[0];self.writers[view].append_data(frame)
        self.writers[view+'-clean'].append_data(np.asarray(Image.fromarray(rgb).resize((1280,720),Image.Resampling.LANCZOS)))
        Image.fromarray(rgb).save(self.directory/('raw-'+view)/f'{i:06d}.png',compress_level=1)
        self.records.append(dict(view=view,frame_index=i,source_time_s=t,video_pts_s=i/25,base_x_m=float(pos[0]),base_y_m=float(pos[1]),**state))
        self.cameras.append(dict(view=view,frame_index=i,source_time_s=t,**metadata))
        self.ticks.extend([dict(view=view,frame_index=i,source_time_s=t,**a) for a in ticks])
        return frame

    def save(self):
        csvout(self.directory/'recording-frame-map.csv',self.records);dump(self.directory/'recording-cameras.json',self.cameras);csvout(self.directory/'recording-world-ticks.csv',self.ticks)
