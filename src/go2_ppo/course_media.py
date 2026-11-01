"""Direct native full-course capture, fixed-Z cameras and independent end cards."""
import csv,json,math
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
from .rolling_uneven_media import camera_calibration,is_true_90_side,font
from .presentation_media import make_layout,write_csv,dump,verify_pts
from .presentation import ruler_ticks
from .video_materials import writer,sha,inspect_video
from .course_completion import LEGS

VIEWS=('side','oblique','overhead');BG=(246,246,240);DARK=(25,48,48);GREEN=(20,113,78);RED=(170,40,36)


def show_gate_in_native_camera(mesh):
    """Genesis1.4.5 regular raster cameras skip Mesh.is_marker=True.

    The returned external pyrender mesh remains visual-only, with no entity,
    mass or collision. Clear only its render-filter attribute, not camera mode.
    """
    if not hasattr(mesh,'is_marker'):raise TypeError('Expected native external visual mesh')
    mesh.is_marker=False
    return mesh


def camera_poses(base_pos):
    x,y,_=base_pos
    return dict(side=dict(pos=(x+.05,y-.95,.34),lookat=(x+.05,y,.34),up=(0,0,1)),
        oblique=dict(pos=(x+1.1,y-1.7,1.12),lookat=(x+.25,y,.20),up=(0,0,1)),
        overhead=dict(pos=(x+.5,0,3.3),lookat=(x+.5,0,0),up=(0,1,0)))


def paired_layout(terrain):
    """Same standard layout, with room for the actual three-second goal tail.

    Only the displayed world-X axis expands. Never extrapolate finite terrain.
    """
    layout=make_layout(terrain)
    # Preserve the old display for old captures; an extended physical exit must
    # also appear completely in the profile. This axis is never a stop boundary.
    layout.plot_xlo=-1.;layout.plot_xhi=max(9.,float(layout.x[-1]))
    layout.xppm=1120/(layout.plot_xhi-layout.plot_xlo);layout.zppm=layout.xppm*layout.exaggeration
    layout._section=layout._make_section();d=ImageDraw.Draw(layout._section)
    for x in np.arange(float(layout.x[-1])+.5,layout.plot_xhi+1e-8,.5):
        px=layout._section_xy([x],[layout.zlow])[0,0]
        d.line((px,118,px,123),fill=DARK,width=1)
        if x==round(x):d.text((px-9,124),f'{x:g}',font=font(13),fill=DARK)
    return layout


def final_capture(recorder,cameras,rows,current_sim_s):
    """Never render an advanced failed scene under an earlier verified timestamp."""
    last=float(rows[-1]['time_s']) if rows else None
    verified=last is not None and abs(last-float(current_sim_s))<1e-8
    evidence=dict(terminal_snapshot_verified=False,terminal_measurement_verified=verified,last_verified_sim_s=last,
        terminal_physics_time_s=float(current_sim_s),
        status='VERIFIED_TERMINAL_STATE' if verified else 'UNAVAILABLE_UNVERIFIED_TERMINAL_STATE' if rows else 'UNAVAILABLE_NO_VERIFIED_STATE')
    if not verified:return evidence
    if recorder is None:
        evidence['status']='UNAVAILABLE_RECORDER';return evidence
    for view,pose in camera_poses([rows[-1][k] for k in ('x_m','y_m','height_m')]).items():cameras[view].set_pose(**pose)
    recorder.capture(cameras,last,rows[-1],terminal=True)
    views={r['view'] for r in recorder.records if abs(float(r['simulation_time_s'])-last)<1e-8}
    evidence['terminal_snapshot_verified']=views==set(VIEWS)
    if not evidence['terminal_snapshot_verified']:evidence['status']='UNAVAILABLE_PARTIAL_TERMINAL_CAPTURE'
    return evidence


def course_timeline(times,end_card_frames=50):
    times=list(map(float,times))
    if not times or abs(times[0])>1e-8 or any(not math.isfinite(t) for t in times) or any(b<=a for a,b in zip(times,times[1:])):
        raise ValueError('Nonmonotonic real source times')
    if any(abs(t-i/25)>1e-7 for i,t in enumerate(times[:-1])) or times[-1]>(len(times)-1)/25+1e-8:
        raise ValueError('Missing scheduled source25fps frame')
    records=[]
    for i,t in enumerate(times):
        kind='terminal_real_snapshot' if abs(t-i/25)>1e-7 else 'recorded_motion'
        records.append(dict(output_frame=i,video_pts_s=i/25,kind=kind,simulation_time_s=t,source_frame=i,frozen_at_sim_s=None))
    for _ in range(end_card_frames):
        i=len(records);records.append(dict(output_frame=i,video_pts_s=i/25,kind='end_card',simulation_time_s=None,source_frame=None,frozen_at_sim_s=times[-1]))
    return records


def compose_course(layout,rgb,view,row,finish,start,old_pass,completion,contact_first,run_id,condition=2):
    t=float(row['time_s']);x=float(row['x_m']);pos=[x,float(row['y_m']),float(row['height_m'])]
    image=layout._annotated(rgb,view,t,pos,[]);d=ImageDraw.Draw(image)
    d.rectangle((0,0,1279,69),fill=BG);d.rectangle((0,70,223,538),fill=BG)
    d.text((18,6),f'{run_id} / {view.upper()} / 新規native連続走行・原速 / カメラZ固定',font=font(17),fill=DARK)
    d.text((16,33),'世界X距離目盛り',font=font(16),fill=DARK);d.text((16,53),'固定HUD：高さとは別',font=font(12),fill=DARK)
    calibration=row['_calibration'];ticks=ruler_ticks(calibration,np.arange(-1,layout.plot_xhi+1e-8,.5));markers=ruler_ticks(calibration,[start,finish])
    d.line((224,43,1055,43),fill=DARK,width=2)
    for tick in ticks:
        px=tick['hud_x_px'];wx=tick['world_xyz_m'][0];major=abs(wx-round(wx))<1e-8
        if px is None or not 226<=px<=1053:continue
        d.line((px,43,px,49 if major else 46),fill=DARK,width=2 if major else 1)
        if major and 240<=px<=1040 and all(q['hud_x_px'] is None or abs(q['hud_x_px']-px)>60 for q in markers):
            d.text((px,51),f'{wx:g}m',anchor='mt',font=font(13),fill=DARK)
    for label,color,tick in zip(('START','FINISH'),(GREEN,RED),markers):
        px=tick['hud_x_px']
        if px is not None and 226<=px<=1053:
            d.line((px,27,px,49),fill=color,width=3)
            d.text((min(1020,max(258,px)),51),label,anchor='mt',font=font(12),fill=color)
    trailing=[float(row[l+'_center_x_m'])-float(row[l+'_sphere_radius_m']) for l in LEGS]
    passed=sum(v>finish for v in trailing);remaining=max(0.,finish-min(trailing))
    lines=[(83,'全4足コース通過',DARK,19),(117,f'START X={start:.2f}',GREEN,18),(147,f'FINISH X={finish:.2f}',RED,18),
        (187,f'全足通過 {passed}/4',GREEN if passed==4 else DARK,23),(223,f'後端残り {remaining:.3f}m',DARK,18),
        (261,f'進行 {x-start:.3f} m',DARK,19),(297,f'sim経過 {t:.2f} s',DARK,21),
        (335,f'旧20秒c{condition}：'+('PASS' if old_pass else 'FAIL'),DARK,16),(363,'F：本人確認未済',DARK,16),
        (398,'新run：非足接触あり' if contact_first is not None and t>=contact_first-1e-8 else '新run：非足接触なし',RED if contact_first is not None and t>=contact_first-1e-8 else DARK,15)]
    if contact_first is not None and t>=contact_first-1e-8:lines.append((425,f'初回 {contact_first:.2f}秒',RED,15))
    goal=completion.get('goal_sim_s')
    if goal is not None and t>=float(goal)-1e-8:
        lines.append((470,f'全足通過 {goal:.2f}秒',GREEN,18))
    elif t>=float(completion.get('terminal_sim_s') or float('inf'))-1e-8:
        lines.append((470,'踏破成功' if completion['success'] else '未踏破',GREEN if completion['success'] else RED,22))
    elif passed==4:lines.append((470,'0.2秒 安定確認中',DARK,16))
    for y,text,color,size in lines:d.text((16,y),text,font=font(size),fill=color)
    for wx,label,color in ((start,'START',GREEN),(finish,'FINISH',RED)):
        sx=layout._section_xy([wx],[layout.zlow])[0,0];d.line((sx,570,sx,690),fill=color,width=2)
        d.text((sx+3,570),label,font=font(12),fill=color)
    return image,dict(baseline_y_px=43.,world_ticks=ticks,gate_markers=markers,min_trailing_foot_x_m=min(trailing),passed_feet=passed,
        section_current_x_m=x,section_current_y_m=0.,section_current_pixel=layout._section_xy([x],[layout.zlow])[0].tolist(),
        goal_sim_s=goal,goal_displayed=goal is not None and t>=float(goal)-1e-8)


def result_card(result,view):
    image=Image.new('RGB',(1280,720),(239,244,241));d=ImageDraw.Draw(image);c=result['completion'];success=c['success'];s=result['new_run_safety']
    d.rectangle((0,0,1279,78),fill=(25,65,57));d.text((36,20),'結果静止画 — シミュレーション時間外（2秒）',font=font(29),fill='white')
    d.text((38,102),f"{result['run_id']} / {view.upper()} / D13550・PPO更新なし",font=font(22),fill=DARK)
    lines=[(160,'踏破成功：全4足が終端を完全通過' if success else '未踏破：'+c['reason'],GREEN if success else RED,33),
        (219,f"START X={result['start_x_m']:.2f} → FINISH X={c['finish_x_m']:.2f}m",DARK,25),
        (267,f"実sim終了 {result['terminal_sim_s']:.2f}秒 / base進行 {result['distance_m']:.3f}m",DARK,25),
        (313,f"初回全足通過 {c['first_all_feet_pass_s']}秒 / 安定確認完了 {c['confirmed_at_sim_s']}秒",DARK,21),
        (355,'全足球の後端X > FINISH、base通過、0.20秒連続保持',DARK,22),
        (397,f"新run：非足接触{s['nonfoot_contact_points']}点 / 関節可動域判定 {'PASS' if s['joint_input_pass'] else 'FAIL'}",RED if s['nonfoot_contact_points'] or not s['joint_input_pass'] else GREEN,22),
        (440,f"転倒={s['physical_fall']} / 逸脱={s['boundary_excursion']} / 計算異常={s['engine_error']}",DARK,22),
        (481,'旧20秒評価：4/6合格、ROLLING c0/c1非足接触FAILのまま',DARK,22),
        (525,'F：本人による動画評価は未済 / 正式モデル採用保留',DARK,22),
        (571,'新規native t=0→終了イベントの全実フレームを使用',DARK,21),
        (614,'全4足通過と旧20秒安全ゲートは別判定',DARK,20),
        (657,'既存20秒映像の切り抜き・疑似走行・速度変更なし',DARK,20)]
    for y,text,color,size in lines:d.text((38,y),text,font=font(size),fill=color)
    return image


class CourseRecorder:
    def __init__(self,directory,terrain):
        self.output=Path(directory);self.output.mkdir(parents=True,exist_ok=False)
        self.terrain=terrain;self.records=[];self.handles={};self.camera_z={};self.closed=False
        np.savez_compressed(self.output/'terrain-input.npz',x=terrain['x'],y=terrain['y'],height_m=terrain['height_m'])
        for view in VIEWS:
            (self.output/'raw'/view).mkdir(parents=True)
            self.handles[view]=writer(self.output/f'native-{view}-raw.mp4')

    def capture(self,cameras,tm,state,terminal=False):
        if self.closed:raise ValueError('Capture after close')
        index=len(self.records)//3;expected=index/25
        if self.records and tm<=self.records[-1]['simulation_time_s']+1e-8:return
        if abs(tm-expected)>1e-7 and not terminal:raise ValueError('Missing native25fps source frame')
        for view in VIEWS:
            camera=cameras[view];cal=camera_calibration(camera)
            if view=='side' and not is_true_90_side(cal):raise ValueError('Not true90side')
            z=float(cal['pos'][2]);self.camera_z.setdefault(view,z)
            if abs(z-self.camera_z[view])>1e-7:raise ValueError('Camera Z moved')
            rgb=camera.render()[0]
            if hasattr(rgb,'cpu'):rgb=rgb.cpu().numpy()
            rgb=np.asarray(rgb).reshape((360,640,3))
            if rgb.dtype!=np.uint8:raise ValueError('Native RGB is not uint8')
            raw=self.output/'raw'/view/f'frame{index:06d}.png';Image.fromarray(rgb).save(raw)
            self.handles[view].append_data(np.asarray(Image.fromarray(rgb).resize((1280,720),Image.Resampling.LANCZOS)))
            record=dict(frame=index,view=view,simulation_time_s=float(tm),video_pts_s=expected,
                terminal_offgrid=abs(tm-expected)>1e-7,raw_png=str(raw.resolve()),raw_png_sha256=sha(raw),
                base_position_m=[float(state[k]) for k in ('x_m','y_m','height_m')],**cal)
            self.records.append(record)

    def close(self):
        if self.closed:return
        self.closed=True
        for handle in self.handles.values():handle.close()
        with (self.output/'camera-frame-map.jsonl').open('w') as stream:
            for record in self.records:stream.write(json.dumps(record,allow_nan=False)+'\n')
        write_csv(self.output/'frame-map.csv',[{k:r[k] for k in ('frame','view','simulation_time_s','video_pts_s','terminal_offgrid','raw_png','raw_png_sha256')} for r in self.records])
        dump(self.output/'recording-metadata.json',dict(kind='direct native full-course capture',frames_per_view=len(self.records)//3,fps=25,world_camera_z_m=self.camera_z,raw_source_size=[640,360],video_size=[1280,720],new_physics_by_recorder=0,pose_replay=False))

    def validate_raw(self):
        if not self.closed:raise ValueError('Close native capture before validation')
        validations={}
        for view in VIEWS:
            path=self.output/f'native-{view}-raw.mp4'
            info=inspect_video(path,decode=True);info['actual_pts']=verify_pts(path,info['frames'])
            expected=sum(r['view']==view for r in self.records)
            if info['frames']!=expected:raise ValueError('Raw MP4 count differs from actual captured frames')
            info.update(source_frames=expected,end_card_frames=0,postprocessed_hud=False,playback_rate=1.)
            validations[path.name]=info
        dump(self.output/'video-validation.json',validations)
        return validations

    def present(self,result,states,end_card_frames=50,standard_subdir=None):
        if not self.closed:raise ValueError('Close native capture before encoding presentation')
        output=self.output
        if standard_subdir:
            output=self.output/standard_subdir;output.mkdir(exist_ok=False)
        layout=paired_layout(self.terrain) if end_card_frames==0 else make_layout(self.terrain)
        validations={};completion=result['completion']
        dump(output/'section-layout.json',dict(x_limits_m=[layout.plot_xlo,layout.plot_xhi],native_terrain_x_limits_m=[float(layout.x[0]),float(layout.x[-1])],x_pixels_per_m=layout.xppm,z_pixels_per_m=layout.zppm,extrapolated_terrain=False))
        for view in VIEWS:
            records=[r for r in self.records if r['view']==view];times=[r['simulation_time_s'] for r in records]
            mapping=course_timeline(times,end_card_frames=end_card_frames);path=output/f'course-{view}.mp4';audits=[]
            with writer(path) as handle:
                for i,r in enumerate(records):
                    state=dict(states[round(r['simulation_time_s']*100)]);state['_calibration']=r
                    with Image.open(r['raw_png']) as src:rgb=np.asarray(src.convert('RGB'))
                    frame,audit=compose_course(layout,rgb,view,state,completion['finish_x_m'],result['start_x_m'],result.get('historical_numeric_pass',result.get('historical_c2_numeric_pass')),completion,result['new_run_safety']['first_nonfoot_sim_s'],result['run_id'],result.get('historical_condition',2))
                    expected=np.asarray(Image.fromarray(rgb).resize((832,468),Image.Resampling.LANCZOS))
                    if not np.array_equal(np.asarray(frame)[70:538,224:1056],expected):raise ValueError('HUD touched native RGB')
                    handle.append_data(np.asarray(frame));audit.update(source_frame=i,simulation_time_s=r['simulation_time_s'],video_pts_s=i/25,raw_png_sha256=r['raw_png_sha256']);audits.append(audit)
                    if i in (0,len(records)//2,len(records)-1):frame.save(output/f'{view}-frame{i:06d}.png')
                if end_card_frames:
                    card=result_card(result,view);card.save(output/f'{view}-result.png')
                    for _ in range(end_card_frames):handle.append_data(np.asarray(card))
            write_csv(output/f'{view}-timeline.csv',mapping)
            with (output/f'{view}-hud-map.jsonl').open('w') as stream:
                for record in audits:stream.write(json.dumps(record,allow_nan=False)+'\n')
            for file in (path,self.output/f'native-{view}-raw.mp4'):
                v=inspect_video(file,decode=True);v['actual_pts']=verify_pts(file,v['frames']);validations[file.name]=v
            if validations[path.name]['frames']!=len(records)+end_card_frames:raise ValueError('Frame count mismatch')
            validations[path.name].update(source_frames=len(records),end_card_frames=end_card_frames,playback_rate=1.)
        dump(output/'video-validation.json',validations);return validations
