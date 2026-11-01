"""Direct native RGB recorder and calibrated Y=0 rolling-terrain section.

Terrain uses native Genesis ordering: height_m[x_index,y_index]. The caller owns
the native cameras and any tracking updates. No Genesis initialization, scene
stepping, re-rendering from saved poses, learning, or terrain approval occurs.
"""
from __future__ import annotations
import csv
from functools import lru_cache
import json
import os
from pathlib import Path
import shutil
import tempfile
import numpy as np
from PIL import Image,ImageDraw
os.environ.setdefault('MPLCONFIGDIR',str(Path(tempfile.gettempdir())/'physicaai-rolling-mpl'))
from .video_materials import writer,inspect_video,sha,font as _font

font=lru_cache(maxsize=16)(_font)
VIEWS=('side','oblique','overhead')
Z_RANGE=(0.,.20)


@lru_cache(maxsize=1)
def _viridis_lut():
    from matplotlib import colormaps
    return np.rint(colormaps['viridis'](np.arange(256)/255)[:,:3]*255).astype(np.uint8)


def viridis_rgb(height_m):
    """Shared native-texture/section LUT: absolute world Z, fixed 0..0.20 metres."""
    values=np.asarray(height_m,dtype=float)
    if not np.isfinite(values).all():raise ValueError('Height colors require finite world Z')
    indices=np.rint(np.clip((values-Z_RANGE[0])/(Z_RANGE[1]-Z_RANGE[0]),0,1)*255).astype(int)
    return _viridis_lut()[indices]


def terrain_section(terrain):
    """Interpolate actual native X-row/Y-column heights at world Y=0."""
    x=np.asarray(terrain['x'],dtype=float);y=np.asarray(terrain['y'],dtype=float);h=np.asarray(terrain['height_m'],dtype=float)
    if x.ndim!=1 or y.ndim!=1 or len(x)<2 or len(y)<2 or h.shape!=(len(x),len(y)):
        raise ValueError('Native terrain requires height_m.shape=(len(x),len(y)); rows X, columns Y')
    if not all(np.isfinite(a).all() for a in (x,y,h)) or np.any(np.diff(x)<=0) or np.any(np.diff(y)<=0):
        raise ValueError('Terrain axes must be strictly increasing and all values finite')
    if y[0]>0 or y[-1]<0:raise ValueError('World Y=0 must lie within the actual terrain')
    return x,np.array([np.interp(0.,y,row) for row in h])


def _array(value):
    if hasattr(value,'detach'):value=value.detach().cpu().numpy()
    return np.asarray(value)


def camera_calibration(camera):
    data={}
    for key in ('intrinsics','extrinsics','pos','lookat','up','res','transform'):
        if hasattr(camera,key):data[key]=_array(getattr(camera,key)).squeeze().tolist()
    data['fov_deg']=float(camera.fov)
    K=np.asarray(data['intrinsics']);E=np.asarray(data['extrinsics'])
    if K.shape!=(3,3) or E.shape!=(4,4) or not np.isfinite(K).all() or not np.isfinite(E).all():
        raise ValueError('Cameras must expose finite actual 3x3 intrinsics and 4x4 extrinsics')
    return data


def is_true_90_side(calibration,tolerance=1e-5):
    """Actual optical axis must be ±world Y, with image up along world +Z."""
    E=np.asarray(calibration['extrinsics'],dtype=float)
    return bool(E.shape==(4,4) and abs(E[2,0])<tolerance and abs(E[2,2])<tolerance
                and abs(abs(E[2,1])-1)<tolerance and abs(E[1,0])<tolerance
                and abs(E[1,1])<tolerance and abs(E[1,2]+1)<tolerance)


def project_world(points,calibration):
    xyz=np.asarray(points,dtype=float);E=np.asarray(calibration['extrinsics']);K=np.asarray(calibration['intrinsics'])
    local=(np.c_[xyz,np.ones(len(xyz))]@E.T)[:,:3];homogeneous=local@K.T
    result=np.full((len(xyz),2),np.nan);visible=local[:,2]>1e-9
    result[visible]=homogeneous[visible,:2]/homogeneous[visible,2,None]
    return result


class RollingUnevenRecorder:
    """directory is a NEW output folder; append(cameras,t,base_pos), close/save.

    Cameras must be side/oblique/overhead native 640x360 RGB cameras. append times
    are exactly 0,.04,.08,... seconds. A moved tracking camera is recorded with
    its current actual calibration at every frame; side orientation is verified
    before any camera render. ``save()`` is an idempotent alias of ``close()``.
    """
    def __init__(self,directory,terrain,vertical_exaggeration=4.0):
        self.output=Path(directory);self.x,self.z=terrain_section(terrain)
        self.y=np.asarray(terrain['y'],dtype=float);self.heights=np.asarray(terrain['height_m'],dtype=float)
        self.exaggeration=float(vertical_exaggeration)
        if not np.isfinite(self.exaggeration) or self.exaggeration<=0:raise ValueError('Vertical display exaggeration must be positive')
        self.output.mkdir(parents=True,exist_ok=False)
        (self.output/'source').mkdir();shutil.copyfile(__file__,self.output/'source'/Path(__file__).name)
        np.savez_compressed(self.output/'terrain-input.npz',x=self.x,y=self.y,height_m=self.heights)
        np.save(self.output/'viridis-lut.npy',_viridis_lut())
        self.provenance=terrain.get('provenance',{'kind':'unspecified caller input; no approval claim'})
        self.index=0;self.closed=False;self.handles={};self.last_images={};self.initial_cameras=None;self.side_verified=0
        self.map_handle=(self.output/'frame-map.csv').open('w',newline='')
        self.map=csv.DictWriter(self.map_handle,fieldnames=['frame','view','simulation_time_s','video_pts_s','base_x_m','base_y_m','base_z_m','raw_png','raw_png_sha256'])
        self.map.writeheader();self.calibration_handle=(self.output/'camera-frame-map.jsonl').open('w')
        # Keep the declared exaggeration while extending the displayed X domain
        # if needed, so all real section heights fit without vertical clipping.
        self.zlow=min(0.,float(self.z.min()));self.zhigh=max(.20,float(self.z.max()))
        self.xppm=min(1120/(self.x[-1]-self.x[0]),110/((self.zhigh-self.zlow)*self.exaggeration))
        self.zppm=self.xppm*self.exaggeration;mid=(self.x[0]+self.x[-1])/2
        self.plot_xlo=mid-560/self.xppm;self.plot_xhi=mid+560/self.xppm
        self._section=self._make_section();self._metadata()

    def _section_xy(self,x,z):
        return np.column_stack([80+(np.asarray(x)-self.plot_xlo)*self.xppm,685-(np.asarray(z)-self.zlow)*self.zppm])

    def _make_section(self):
        layer=Image.new('RGB',(1280,153),(246,246,240));draw=ImageDraw.Draw(layer)
        draw.rectangle((50,0,1230,151),fill=(253,253,248),outline=(173,184,168))
        # A world-height gradient is masked by the actual filled section. Every
        # interior pixel therefore uses its own absolute world Z, not a top color.
        mask=Image.new('L',(1280,153),0);md=ImageDraw.Draw(mask)
        outline=np.vstack([self._section_xy(self.x,self.z),self._section_xy([self.x[-1],self.x[0]],[self.zlow,self.zlow])])
        outline[:,1]-=567;md.polygon([tuple(p) for p in outline],fill=255)
        world_z=self.zlow+(685-(np.arange(153)+567))/self.zppm
        gradient=np.repeat(viridis_rgb(world_z)[:,None,:],1280,axis=1)
        layer.paste(Image.fromarray(gradient),(0,0),mask);draw=ImageDraw.Draw(layer)
        curve=self._section_xy(self.x,self.z);curve[:,1]-=567
        draw.line([tuple(p) for p in curve],fill=(36,56,40),width=2)
        ticks=np.arange(np.ceil(self.x[0]*2)/2,self.x[-1]+1e-9,.5)
        for x in ticks:
            px=self._section_xy([x],[self.zlow])[0,0]
            draw.line((px,118,px,123),fill=(45,65,42),width=1)
            if abs(x-round(x))<1e-8:draw.text((px-9,124),f'{x:g}',font=font(13),fill=(45,65,42))
        for z in np.arange(0,.2001,.05):
            py=self._section_xy([self.plot_xlo],[z])[0,1]-567
            draw.text((51,py-6),f'{z:.2f}',font=font(12),fill=(45,65,42))
        draw.text((1100,133),'world X [m]',font=font(13),fill=(45,65,42))
        return layer

    def _ticks(self,calibration):
        values=np.arange(np.ceil(self.x[0]*2)/2,self.x[-1]+1e-9,.5)
        points=np.column_stack([values,np.zeros(len(values)),np.interp(values,self.x,self.z)+.002])
        pixels=project_world(points,calibration);tops=project_world(points+[0,0,.015],calibration)
        ticks=[]
        for point,pixel,top in zip(points,pixels,tops):
            finite=bool(np.isfinite(pixel).all() and np.isfinite(top).all())
            ticks.append({'world_xyz_m':point.tolist(),'native_pixel_xy':pixel.tolist() if finite else None,
                'native_tick_top_xy':top.tolist() if finite else None,
                'annotated_pixel_xy':(pixel*1.3+[224,70]).tolist() if finite else None,
                'label':f'{point[0]:g} m' if abs(point[0]-round(point[0]))<1e-8 else None})
        return ticks

    def _annotated(self,rgb,view,t,base_pos,ticks):
        image=Image.new('RGB',(1280,720),(246,246,240))
        image.paste(Image.fromarray(rgb).resize((832,468),Image.Resampling.LANCZOS),(224,70));draw=ImageDraw.Draw(image)
        label=str(self.provenance.get('label','ROLLING UNEVEN')) if isinstance(self.provenance,dict) else 'ROLLING UNEVEN'
        heading=f'{label} / DIRECT NATIVE CAMERA / {view.upper()} / t={t:.2f}s'
        draw.text((20,8),heading,font=font(17 if len(heading)>85 else 23),fill=(22,54,48))
        draw.text((20,39),f'World X={base_pos[0]:.3f} m | fixed world-distance ticks: 0.5 m; labels: 1 m | native RGB, no pose replay',font=font(17),fill=(43,65,50))
        for tick in ticks:
            if tick['native_pixel_xy'] is None:continue
            p=np.asarray(tick['annotated_pixel_xy']);q=np.asarray(tick['native_tick_top_xy'])*1.3+[224,70]
            if 227<=p[0]<=1052 and 75<=p[1]<=520:
                draw.line([tuple(p),tuple(q)],fill=(245,245,226),width=2)
                if tick['label']:draw.text((p[0]-13,p[1]+3),tick['label'],font=font(13),fill=(28,54,35),stroke_width=1,stroke_fill=(249,249,232))
        draw.text((20,150),'Y = 0 section',font=font(18),fill=(35,65,48))
        draw.text((20,183),f'Vertical x{self.exaggeration:g}',font=font(18),fill=(121,66,27))
        draw.text((20,214),'display only',font=font(15),fill=(67,78,53))
        draw.text((1090,130),'WORLD Z',font=font(16),fill=(35,65,48))
        for py in range(251):
            color=tuple(viridis_rgb(.20*(1-py/250)))
            draw.line((1100,165+py,1125,165+py),fill=color)
        for z in (0,.05,.10,.15,.20):
            py=165+(1-z/.20)*250
            draw.text((1133,py-7),f'{z:.2f} m',font=font(13),fill=(35,65,48))
        draw.text((20,543),f'ACTUAL TERRAIN Y=0 / world X-Z section / vertical display exaggeration x{self.exaggeration:g} / physics heights unchanged',font=font(17),fill=(35,65,48))
        image.paste(self._section,(0,567));draw=ImageDraw.Draw(image)
        marker=self._section_xy([base_pos[0]],[self.zlow])[0,0]
        if 80<=marker<=1200:
            draw.line((marker,570,marker,690),fill=(223,87,27),width=2)
            draw.polygon([(marker,568),(marker-6,560),(marker+6,560)],fill=(223,87,27))
        draw.text((20,708),'Native X rows / Y columns; section colors are absolute world Z, 0..0.20 m.',font=font(11),fill=(45,65,42))
        return image

    def append(self,cameras,t,base_pos):
        if self.closed:raise RuntimeError('Recorder is closed')
        if set(cameras)!=set(VIEWS):raise ValueError('Provide side, oblique and overhead native cameras')
        t=float(t);expected=self.index/25;base_pos=np.asarray(base_pos,dtype=float)
        if abs(t-expected)>1e-6:raise ValueError(f'Exact 25fps source time required: expected {expected}, got {t}')
        if base_pos.shape!=(3,) or not np.isfinite(base_pos).all():raise ValueError('base_pos must be a finite xyz position')
        calibrations={name:camera_calibration(camera) for name,camera in cameras.items()}
        if not is_true_90_side(calibrations['side']):raise ValueError('Side camera must be true 90 degrees: optical axis ±world Y, upright world Z')
        if self.initial_cameras is None:
            self.initial_cameras=calibrations
            for name in VIEWS:
                (self.output/'raw'/name).mkdir(parents=True)
                self.handles[name]={'raw':writer(self.output/f'native-{name}-raw.mp4'),'annotated':writer(self.output/f'native-{name}.mp4')}
        for name in VIEWS:
            calibration=calibrations[name];rgb=_array(cameras[name].render()[0])
            if rgb.shape==(1,360,640,3):rgb=rgb[0]
            if rgb.shape!=(360,640,3) or rgb.dtype!=np.uint8:raise ValueError('Native camera RGB must be uint8 640x360')
            path=self.output/'raw'/name/f'frame{self.index:06d}.png';Image.fromarray(rgb).save(path);digest=sha(path)
            ticks=self._ticks(calibration);annotated=self._annotated(rgb,name,t,base_pos,ticks)
            self.handles[name]['raw'].append_data(np.asarray(Image.fromarray(rgb).resize((1280,720),Image.Resampling.LANCZOS)))
            self.handles[name]['annotated'].append_data(np.asarray(annotated))
            if self.index==0:annotated.save(self.output/f'native-{name}-initial.png')
            self.last_images[name]=annotated
            self.map.writerow({'frame':self.index,'view':name,'simulation_time_s':t,'video_pts_s':expected,
                'base_x_m':base_pos[0],'base_y_m':base_pos[1],'base_z_m':base_pos[2],
                'raw_png':str(path.resolve()),'raw_png_sha256':digest})
            record={'frame':self.index,'view':name,'simulation_time_s':t,'video_pts_s':expected,
                'base_position_m':base_pos.tolist(),'true_90_side':is_true_90_side(calibration) if name=='side' else None,
                **calibration,'world_ticks':ticks,'raw_png_sha256':digest}
            self.calibration_handle.write(json.dumps(record,allow_nan=False)+'\n')
        self.map_handle.flush();self.calibration_handle.flush();self.index+=1;self.side_verified+=1

    def _metadata(self):
        metadata={'kind':'direct native rolling-terrain camera recording','fps':25,'frames_per_view':self.index,
            'native_rgb_size':[640,360],'video_size':[1280,720],'new_physics_steps_by_recorder':0,
            'pose_replay':False,'interpolated_poses':False,'terrain_array_order':'height_m[x_index,y_index]',
            'terrain_provenance_as_supplied':self.provenance,'terrain_approval_verified_by_recorder':False,
            'terrain_input_sha256':sha(self.output/'terrain-input.npz'),'source_sha256':sha(Path(__file__)),
            'viridis_lut_sha256':sha(self.output/'viridis-lut.npy'),'absolute_world_z_color_range_m':list(Z_RANGE),
            'native_texture_shared_helper':'viridis_rgb(height_m); caller applies to actual native ground',
            'native_surface_color_verified_by_recorder':False,'section_vertical_display_exaggeration':self.exaggeration,
            'section_x_pixels_per_metre':self.xppm,'section_z_pixels_per_metre':self.zppm,
            'section_world_x_display_m':[self.plot_xlo,self.plot_xhi],'section_world_z_display_m':[self.zlow,self.zhigh],
            'true_90_side_frames_verified':self.side_verified,'per_frame_calibration':'camera-frame-map.jsonl',
            'initial_cameras':self.initial_cameras,'world_tick_spacing_m':.5,'world_label_spacing_m':1.,
            'height_colors_saturated_below_zero_samples':int(np.count_nonzero(self.heights<0)),
            'height_colors_saturated_above_point20_samples':int(np.count_nonzero(self.heights>.20))}
        (self.output/'recording-metadata.json').write_text(json.dumps(metadata,indent=2,allow_nan=False)+'\n')

    def close(self):
        if self.closed:return
        self.closed=True
        for group in self.handles.values():
            for handle in group.values():handle.close()
        self.map_handle.close();self.calibration_handle.close()
        for name,image in self.last_images.items():image.save(self.output/f'native-{name}-final.png')
        self._metadata();validation={}
        if self.index:
            for name in VIEWS:
                for suffix in ('','-raw'):
                    path=self.output/f'native-{name}{suffix}.mp4';validation[path.name]=inspect_video(path,decode=False)
        (self.output/'video-validation.json').write_text(json.dumps(validation,indent=2)+'\n')

    def save(self):
        self.close()
