"""Offline Issue4 presentation reconstruction; no Genesis or policy execution.

Reads preserved native RGB, K/E and timestamps. Only display HUD is fixed;
physical image motion, source camera motion and the terrain section are retained.
"""
from __future__ import annotations
import argparse
import csv
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import shutil
import subprocess
import numpy as np
from PIL import Image, ImageDraw
import imageio.v2 as imageio
import imageio_ffmpeg
from . import presentation as core
from .rolling_uneven_media import RollingUnevenRecorder, terrain_section, is_true_90_side, font
from .video_materials import sha, writer, inspect_video
from .rolling_native_audit import verify_finite_rows

ROOT=Path(__file__).resolve().parents[2]
VIEWS=('side','oblique','overhead')
CHECKPOINT='5d7fa7222067ff915942f2be546f9a9b3dcd6126b07eb3d7c8ea7fb4c05a4565'
DARK=(25,48,48);GREEN=(20,113,78);RED=(170,40,36);BG=(246,246,240)


def dump(path, data):
    Path(path).write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')


def csv_rows(path):
    with Path(path).open() as stream:return list(csv.DictReader(stream))


def write_csv(path, rows):
    if not rows:return
    with Path(path).open('w',newline='') as stream:
        w=csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)


def make_layout(terrain):
    """Reuse the exact existing physical-section renderer without a recorder.

    No files, metadata, source frames, or simulator are created by this layout.
    """
    layout=object.__new__(RollingUnevenRecorder)
    layout.x,layout.z=terrain_section(terrain)
    layout.y=np.asarray(terrain['y']);layout.heights=np.asarray(terrain['height_m'])
    layout.exaggeration=4.;layout.provenance={'label':'PRESERVED ISSUE3 RECORDING'}
    layout.zlow=min(0.,float(layout.z.min()));layout.zhigh=max(.20,float(layout.z.max()))
    layout.xppm=min(1120/(layout.x[-1]-layout.x[0]),110/((layout.zhigh-layout.zlow)*layout.exaggeration))
    layout.zppm=layout.xppm*layout.exaggeration;mid=(layout.x[0]+layout.x[-1])/2
    layout.plot_xlo=mid-560/layout.xppm;layout.plot_xhi=mid+560/layout.xppm
    layout._section=layout._make_section()
    return layout


def validate_frame(frame, calibration, state, digest):
    """Fail closed on frame/source/K-E/state disagreement."""
    index=int(frame['frame']);t=index/25
    if int(calibration['frame'])!=index or calibration['view']!=frame['view']:
        raise ValueError('Frame/calibration identity mismatch')
    for row in (frame,calibration):
        if abs(float(row['simulation_time_s'])-t)>1e-7 or abs(float(row['video_pts_s'])-t)>1e-7:
            raise ValueError('Saved simulation time / PTS mismatch')
        if row['raw_png_sha256']!=digest:raise ValueError('Raw PNG SHA mismatch')
    actual=[float(state[k]) for k in ('x_m','y_m','height_m')]
    mapped=[float(frame[k]) for k in ('base_x_m','base_y_m','base_z_m')]
    if not np.allclose(actual,mapped,rtol=0,atol=1e-7) or not np.allclose(actual,calibration['base_position_m'],rtol=0,atol=1e-7):
        raise ValueError('100Hz physical state / frame pose mismatch')
    K=np.asarray(calibration['intrinsics']);E=np.asarray(calibration['extrinsics'])
    if K.shape!=(3,3) or E.shape!=(4,4) or not np.isfinite(K).all() or not np.isfinite(E).all():
        raise ValueError('Missing/nonfinite saved camera K/E')
    if not np.allclose(E[:3,:3]@E[:3,:3].T,np.eye(3),atol=2e-5):
        raise ValueError('Invalid saved camera rotation')
    if frame['view']=='side' and not is_true_90_side(calibration):raise ValueError('Side is not true90')


def compose(layout, rgb, view, t, state, goal, calibration, run_id):
    """Fixed-pixel ruler outside RGB; terrain Y0 section retains real heights."""
    pos=[float(state[k]) for k in ('x_m','y_m','height_m')]
    image=layout._annotated(rgb,view,t,pos,[]);d=ImageDraw.Draw(image)
    # All new text occupies dedicated margins, never the source RGB rectangle.
    d.rectangle((0,0,1279,69),fill=BG);d.rectangle((0,70,223,538),fill=BG)
    title=f'{run_id} / {view.upper()} / 保存RGB・原速 / HUD表示のみ修正'
    d.text((20,5),title,font=font(17),fill=DARK)
    d.text((20,32),'世界X距離目盛り',font=font(16),fill=DARK)
    d.text((20,53),'HUD：高さとは別指標',font=font(12),fill=DARK)
    values=np.arange(np.ceil(layout.x[0]*2)/2,layout.x[-1]+1e-8,.5)
    ticks=core.ruler_ticks(calibration,values);d.line((224,43,1055,43),fill=DARK,width=2)
    markers=core.ruler_ticks(calibration,[goal['start_x_m'],goal['goal_x_m']])
    for q in ticks:
        x=q['hud_x_px'];major=abs(q['world_xyz_m'][0]-round(q['world_xyz_m'][0]))<1e-7
        if x is None or not 226<=x<=1053:continue
        d.line((x,43,x,49 if major else 46),fill=DARK,width=2 if major else 1)
        if major and 240<=x<=1040 and all(a['hud_x_px'] is None or abs(a['hud_x_px']-x)>55 for a in markers):
            d.text((x,51),f"{q['world_xyz_m'][0]:g}m",font=font(13),fill=DARK,anchor='mt')
    for tag,color,q in zip(('START','GOAL'),(GREEN,RED),markers):
        x=q['hud_x_px']
        if x is not None and 226<=x<=1053:
            d.line((x,27,x,49),fill=color,width=3)
            d.polygon([(x,43),(x-5,33),(x+5,33)],fill=color)
            # Keep label wholly inside HUD, without falsifying marker position.
            tx=min(1020,max(258,x));d.text((tx,51),tag,font=font(12),fill=color,anchor='mt')
    x=pos[0];progress=x-goal['start_x_m'];remaining=max(0.,goal['goal_x_m']-x)
    old='PASS' if goal['historical_numeric_pass'] else 'FAIL'
    lines=[(83,'提示用 +X 4m目標',DARK,18),
        (119,'START 0.00 m',GREEN,20),(148,'GOAL 4.00 m',RED,20),
        (188,f'残り {remaining:.3f} m',DARK,22),(227,f'経過sim {t:.2f} s',DARK,21),
        (265,f'進行 {progress:.3f} m',DARK,19),(297,f'世界X {x:+.3f} m',DARK,17),
        (337,f'旧20秒評価：{old}',GREEN if old=='PASS' else RED,18),
        (367,'F：本人確認未済',DARK,17)]
    if not goal['historical_numeric_pass']:
        lines.extend([(399,'FL_calf 非足接触',RED,16),(424,'安全判定FAILを保持',RED,15)])
    else:lines.append((402,'旧数値判定を参照',DARK,15))
    seen=[e for e in goal['nonfoot_events'] if float(e['time_s'])<=t+1e-7]
    if seen:
        lines.extend([(457,'接触記録あり（転倒とは別）',RED,12),
                      (477,f"初回 {min(float(e['time_s']) for e in seen):.2f} sim s",RED,14)])
    if t>=goal['presentation_end_sim_s']-1e-8:
        lines.append((510,'距離到達' if goal['goal_reached'] else goal['end_reason'],GREEN if goal['goal_reached'] else RED,16))
    for y,text,color,size in lines:d.text((16,y),text,font=font(size),fill=color)
    for tag,color,wx in (('S',GREEN,goal['start_x_m']),('G',RED,goal['goal_x_m'])):
        sx=layout._section_xy([wx],[layout.zlow])[0,0]
        d.line((sx,570,sx,690),fill=color,width=2);d.text((sx+4,570),tag,font=font(13),fill=color)
    # Existing lower orange current-position marker remains tied to current base X.
    projected_base=core.ruler_ticks(calibration,[x])[0]
    audit=dict(baseline_y_px=43.,world_ticks=ticks,start_goal_markers=markers,
        base_x_m=x,base_world_x_projected_hud_x_px=projected_base['hud_x_px'],
        section_current_x_px=float(layout._section_xy([x],[layout.zlow])[0,0]),
        section_start_x_px=float(layout._section_xy([goal['start_x_m']],[layout.zlow])[0,0]),
        section_goal_x_px=float(layout._section_xy([goal['goal_x_m']],[layout.zlow])[0,0]),
        nonfoot_contact_notified=bool(seen),raw_rgb_region_unmodified=True)
    return image,audit


def end_card(goal,run_id,view,last_sim,last_x):
    image=Image.new('RGB',(1280,720),(239,244,241));d=ImageDraw.Draw(image)
    d.rectangle((0,0,1279,78),fill=(25,65,57))
    d.text((40,20),'結果静止画 — シミュレーション時間外（2秒）',font=font(29),fill='white')
    d.text((42,102),f'{run_id} / {view.upper()} / D13550',font=font(23),fill=DARK)
    reached=goal['goal_reached'];old='PASS' if goal['historical_numeric_pass'] else 'FAIL'
    lines=[(160,'距離ゴール到達' if reached else '距離ゴール未到達',GREEN if reached else RED,38),
        (225,'スタート0.00 m → 目標4.00 m（+世界X）',DARK,27),
        (275,f"初回到達サンプル：{goal['first_crossing_sample_s']:.2f} sim秒（100Hz実測）" if reached else f"記録終了：{goal['recorded_end_sim_s']:.2f} sim秒",DARK,25),
        (320,f"最終実フレーム：{last_sim:.2f} sim秒 / 進行距離 {last_x-goal['start_x_m']:.3f} m",DARK,24),
        (365,f'旧20秒検証の数値判定：{old}（短尺映像からの再判定なし）',GREEN if old=='PASS' else RED,24),
        (410,'FL_calf非足接触FAIL（0N接触を転倒とは扱わない）' if not goal['historical_numeric_pass'] else '旧20秒評価の数値ゲートを維持',RED if old=='FAIL' else DARK,22),
        (460,'F：本人による動画評価は未済 / 正式採用保留',DARK,24),
        (510,f"終了理由：{goal['end_reason']}",DARK,24),
        (560,'保存済み25fps実映像の最初の到達直後フレームまで使用',DARK,21),
        (602,'過去の20秒走行を4m目標で制御したものではありません',DARK,20),
        (650,'静止表示は走行時間に加算しません / 元映像・モデル不変',DARK,20)]
    for y,text,color,size in lines:d.text((42,y),text,font=font(size),fill=color)
    return image


def snapshot_sources(run_paths,extra_paths):
    paths={p.resolve() for run in run_paths for p in run.rglob('*') if p.is_file()}
    paths.update(p.resolve() for p in extra_paths)
    return {str(p):dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted(paths)}


def verify_preserved(snapshot):
    for name,record in snapshot.items():
        path=Path(name)
        if not path.is_file() or path.stat().st_size!=record['bytes'] or sha(path)!=record['sha256']:
            raise ValueError(f'Protected source changed: {name}')
    return dict(status='PASS',files=len(snapshot),bytes=sum(r['bytes'] for r in snapshot.values()))


def validate_terrain(terrain, kind, approved_path):
    if kind=='ROLLING_UNEVEN':
        with np.load(approved_path) as source:
            if not np.array_equal(terrain['height_m'],np.rint(source['z_m']/.001)*.001):
                raise ValueError('Saved physical section differs from approved quantized heights')
            if not np.array_equal(terrain['x'],source['x_m']) or not np.array_equal(terrain['y'],source['y_m']):
                raise ValueError('Terrain coordinate axes differ from approved source')
    elif np.any(terrain['height_m']!=0):raise ValueError('FLAT section is not horizontal')


def load_trial(run, snapshot):
    result=json.loads((run/'result.json').read_text());states=csv_rows(run/'states.csv');controls=csv_rows(run/'controls.csv')
    verify_finite_rows(states);verify_finite_rows(controls)
    if result['checkpoint_sha256']!=CHECKPOINT:raise ValueError('Wrong source checkpoint')
    if len(states)!=2001 or len(controls)!=1001:raise ValueError('Incomplete historical20s states/controls')
    for i,c in enumerate(controls):
        if abs(float(c['time_s'])-i*.02)>1e-7:raise ValueError('Nonuniform50Hz controls')
        # Each control snapshot is the same actual physical pose at the even substep.
        for key in ('x_m','y_m','height_m','physical_fallen','out_of_terrain','unexpected_floor_contact'):
            if c[key]!=states[i*2][key]:raise ValueError(f'Control/state mismatch: {key}')
    contacts=[json.loads(l) for l in (run/'contacts.jsonl').read_text().splitlines()]
    if any(e.get('foot') not in (True,False) or not np.isfinite(float(e['time_s'])) for e in contacts):
        raise ValueError('Unknown contact state/time')
    goal=core.analyse_trial(states,result,contacts)
    if goal['end_reason']=='UNKNOWN':raise ValueError('UNKNOWN timeline: '+repr(goal['errors']))
    terrain=dict(np.load(run/'native-media/terrain-input.npz'))
    validate_terrain(terrain,result['evaluation_kind'],ROOT/'assets/approved/heightfield.npz')
    goal['goal_in_saved_terrain_and_lane']=bool(terrain['x'][0]<goal['start_x_m']<goal['goal_x_m']<terrain['x'][-1]
        and all(-1.25<=float(q['y_m'])<=1.25 and -.95<=float(q['x_m'])<=6.95 for q in states))
    if not goal['goal_in_saved_terrain_and_lane']:raise ValueError('Presentation goal/path is not in recorded lane')
    frames=csv_rows(run/'native-media/frame-map.csv')
    calibration=[json.loads(l) for l in (run/'native-media/camera-frame-map.jsonl').read_text().splitlines()]
    byframe={(int(q['frame']),q['view']):q for q in frames}
    bycal={(int(q['frame']),q['view']):q for q in calibration}
    if len(frames)!=1503 or len(calibration)!=1503 or set(byframe)!=set(bycal) or len(byframe)!=1503:
        raise ValueError('Missing/duplicate historical camera/frame records')
    # Audit all501 frames/view, including tail omitted from the presentation.
    sidez=[];old_tick_y=[]
    for i in range(501):
        for view in VIEWS:
            q=byframe[(i,view)];c=bycal[(i,view)];raw=(run/'native-media/raw'/view/f'frame{i:06d}.png').resolve()
            if Path(q['raw_png']).resolve()!=raw:raise ValueError('Raw source path mismatch')
            validate_frame(q,c,states[i*4],snapshot[str(raw)]['sha256'])
            if view=='side':
                sidez.append(c['pos'][2])
                first=next((v for v in c['world_ticks'] if abs(v['world_xyz_m'][0]-4)<1e-6),None)
                if first and first['annotated_pixel_xy']:old_tick_y.append(first['annotated_pixel_xy'][1])
    goal.update(source_run_id=run.name,checkpoint_sha256=CHECKPOINT,
        numerical_gate_source=str((run/'result.json').relative_to(ROOT)),
        source_result_sha256=sha(run/'result.json'),
        source_side_camera_z_range_m=[min(sidez),max(sidez)],source_side_z_fixed=False,
        original_world_x4_tick_y_range_px=[min(old_tick_y),max(old_tick_y)] if old_tick_y else None,
        source_camera_note='Preserved source actually tracks camera Z; HUD only fixed. No re-render, crop, stabilization or new physics.',
        full_state_samples=len(states),full_control_samples=len(controls),full_source_frames_per_view=501)
    return goal,states,terrain,byframe,bycal


def verify_pts(path, expected_frames):
    """Decode every frame through ffmpeg and check actual container PTS."""
    command=[imageio_ffmpeg.get_ffmpeg_exe(),'-hide_banner','-copyts','-i',str(path),
             '-vf','showinfo','-fps_mode','passthrough','-f','null','-']
    completed=subprocess.run(command,capture_output=True,text=True)
    import re
    pts=[float(v) for v in re.findall(r'\bn:\s*\d+\s+pts:\s*-?\d+\s+pts_time:([\d.e+-]+)',completed.stderr)]
    if completed.returncode or len(pts)!=expected_frames or any(abs(t-i/25)>1e-5 for i,t in enumerate(pts)):
        raise ValueError('Actual MP4 PTS/decode mismatch: '+str(path))
    return dict(status='PASS',count=len(pts),first_pts_s=pts[0],last_pts_s=pts[-1],max_error_s=max(abs(t-i/25) for i,t in enumerate(pts)))


def generate_view(run, output, view, goal, states, terrain, frames, calibrations):
    directory=output/run.name/view;directory.mkdir(parents=True,exist_ok=False)
    selected=core.select_frames(goal,[float(frames[(i,view)]['simulation_time_s']) for i in range(501)])
    times=[i/25 for i in selected];mapping=core.timeline(times);layout=make_layout(terrain)
    video=directory/'presentation.mp4';audits=[];checkpoints={0:'start',selected[len(selected)//2]:'middle',selected[-1]:'last-motion'}
    with writer(video) as handle:
        for i in selected:
            raw=run/'native-media/raw'/view/f'frame{i:06d}.png'
            with Image.open(raw) as source:rgb=np.asarray(source.convert('RGB'))
            if rgb.shape!=(360,640,3):raise ValueError('Unexpected source RGB resolution')
            image,audit=compose(layout,rgb,view,i/25,states[i*4],goal,calibrations[(i,view)],run.name)
            # Structural QA: the entire robot/terrain image rectangle is untouched.
            expected=np.asarray(Image.fromarray(rgb).resize((832,468),Image.Resampling.LANCZOS))
            if not np.array_equal(np.asarray(image)[70:538,224:1056],expected):raise ValueError('HUD altered raw RGB region')
            handle.append_data(np.asarray(image))
            if i in checkpoints:image.save(directory/(checkpoints[i]+'.png'))
            audit.update(source_frame=i,simulation_time_s=i/25,video_pts_s=i/25,
                raw_png_sha256=frames[(i,view)]['raw_png_sha256'],
                actual_camera_K=calibrations[(i,view)]['intrinsics'],actual_camera_E=calibrations[(i,view)]['extrinsics'])
            audits.append(audit)
        last_x=float(states[selected[-1]*4]['x_m']);card=end_card(goal,run.name,view,times[-1],last_x)
        card.save(directory/'end-card.png')
        for _ in range(50):handle.append_data(np.asarray(card))
    write_csv(directory/'timeline.csv',mapping)
    with (directory/'hud-frame-map.jsonl').open('w') as stream:
        for record in audits:stream.write(json.dumps(record,allow_nan=False)+'\n')
    validation=inspect_video(video,decode=True);validation['actual_pts']=verify_pts(video,len(mapping))
    if validation['frames']!=len(mapping) or validation['fps']!=25:raise ValueError('Output timing mismatch')
    # Independently decode/check fixed line pixels and a genuinely static2s card.
    reader=imageio.get_reader(video);end_digest=None;baseline_rows=[]
    sample_images={};card_identical=True
    for i,decoded in enumerate(reader):
        if i<len(selected):
            luminance=decoded[40:47,226:1053].mean(axis=2)
            measured_y=40+int(luminance.mean(axis=1).argmin());baseline_rows.append(measured_y)
        else:
            digest=__import__('hashlib').sha256(decoded.tobytes()).hexdigest()
            if end_digest is None:end_digest=digest
            elif digest!=end_digest:card_identical=False
        if i in (0,len(selected)//2,len(selected)-1,len(selected),len(mapping)-1):
            Image.fromarray(decoded).save(directory/f'decoded-{i:06d}.png')
            sample_images[str(i)]=f'decoded-{i:06d}.png'
    reader.close()
    # Lossy codec can change frozen pixels slightly due to interframe coding;
    # exact input50 frames and perceptual decoded stability are audited separately.
    baseline_range=[min(baseline_rows),max(baseline_rows)]
    if baseline_range[1]-baseline_range[0]>1:raise ValueError(f'Encoded HUD baseline moves: {baseline_range}')
    validation.update(source_run_id=run.name,view=view,checkpoint_sha256=CHECKPOINT,
        motion_frames=len(selected),last_real_sim_s=times[-1],last_real_x_m=last_x,
        end_card_frames=50,end_card_duration_s=2.,end_card_start_video_pts_s=len(selected)/25,
        final_sim_s_not_video_duration=True,decoded_baseline_y_range_px=baseline_range,
        decoded_end_card_exact_pixels_identical=card_identical,
        all_preencode_end_card_frames_identical=True,inspection_images=sample_images,
        all_raw_rgb_regions_identical_before_encode=True,source_native_steps=0,
        source_rgb_pil_resize_scale=1.3,source_rgb_origin_px=[224,70],
        old_numerical_gates_preserved=True,hud_baseline_y_range_px=[43,43])
    dump(directory/'validation.json',validation)
    return validation


def make_index(output, runs):
    chunks=['<!doctype html><meta charset="utf-8"><title>Issue4 個別動画</title>',
        '<style>body{font-family:sans-serif;max-width:1200px;margin:30px auto;color:#183d36}table{border-collapse:collapse}td,th{border:1px solid #aaa;padding:12px}img{width:240px}video{width:640px;max-width:100%}</style>',
        '<h1>Issue4：試行・視点ごとの単独動画</h1><p>元RGB・原速25fps。末尾2秒はシミュレーション時間外の結果静止画。4m到達と旧20秒数値判定は別軸。F本人確認未済。</p>',
        '<p>保存済みsideカメラは実際にはZ追従。映像は安定化せず原状保持し、世界X目盛りHUDだけY固定。</p>']
    for run in runs:
        g=run['goal'];chunks.append(f"<h2>{html.escape(g['source_run_id'])}</h2><p>4m到達 {g['first_crossing_sample_s']} sim秒 / 旧20秒 {'PASS' if g['historical_numeric_pass'] else 'FAIL（非足接触）'}</p>")
        for v in run['videos']:
            rel=Path(v['path']).relative_to(output);directory=rel.parent
            chunks.append(f'<h3>{v["view"]}</h3><p><a href="{rel}">個別MP4を開く</a> | <a href="{directory}/validation.json">検証</a> | <a href="{directory}/timeline.csv">時間対応</a></p><video controls preload="none" src="{rel}"></video><p>')
            for name in ('start','middle','last-motion','end-card'):
                chunks.append(f'<a href="{directory}/{name}.png"><img alt="{name}" src="{directory}/{name}.png"></a>')
            chunks.append('</p>')
    (output/'index.html').write_text('\n'.join(chunks))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--run',action='append',help='Optional individual source run IDs');p.add_argument('--view',choices=VIEWS,action='append')
    a=p.parse_args();output=a.output.resolve();output.mkdir(parents=True,exist_ok=False)
    if (ROOT/'logs').resolve() in output.parents:raise ValueError('Presentation outputs must not enter original logs')
    started=datetime.now(timezone.utc).isoformat()
    source_results=json.loads((ROOT/'reports/issue3-results.json').read_text())['results']
    selected=[q for q in source_results if not a.run or q['run'] in a.run]
    if not selected or (a.run and len(selected)!=len(a.run)):raise ValueError('Unknown source run')
    paths=[ROOT/'logs/rolling-native'/q['run'] for q in selected]
    extras=[ROOT/'assets/approved/heightfield.npz',ROOT/'reports/issue3-results.json',
        ROOT/'logs/mixed-d/mixed128-lane-v3/policy_final.pt',ROOT/'logs/mixed-d/mixed128-contact-v4/policy_final.pt',
        ROOT.parent/'Physical-AI-Course-2026-Advanced1-Final-Assignment/logs/stage1/natural/training/slip20-margin012-64x1500/model_6500.pt']
    protected=snapshot_sources(paths,extras);dump(output/'source-before.json',protected)
    summary=dict(authority_issue=4,started_at_utc=started,native_runs=0,PPO_updates=0,heldout=False,
        source_main='8fe46546679bb06b9b167104aace3ba5bf601153',checkpoint_sha256=CHECKPOINT,
        goal_is_presentation_only=True,end_card_outside_simulation_s=2.,runs=[],failures=[])
    (output/'source').mkdir()
    for name in ('presentation.py','presentation_media.py'):
        shutil.copyfile(ROOT/'src/go2_ppo'/name,output/'source'/name)
    for run,old in zip(paths,selected):
        try:
            goal,states,terrain,frames,calibration=load_trial(run,protected)
            if goal['historical_numeric_gates']!=old['numeric_gates'] or goal['historical_numeric_pass']!=old['numeric_pass']:
                raise ValueError('Historical gate disagreement')
            current=dict(goal=goal,videos=[]);summary['runs'].append(current)
            for view in a.view or VIEWS:
                try:
                    validation=generate_view(run,output,view,goal,states,terrain,frames,calibration)
                    current['videos'].append(validation)
                    print(json.dumps(dict(run=run.name,view=view,frames=validation['frames'],arrival_s=goal['first_crossing_sample_s'],qa='PASS')),flush=True)
                except Exception as error:
                    import traceback
                    summary['failures'].append(dict(run=run.name,view=view,error=str(error),traceback=traceback.format_exc()))
                    print(traceback.format_exc(),flush=True)
            dump(output/'summary.json',summary)
        except Exception as error:
            import traceback
            summary['failures'].append(dict(run=run.name,error=str(error),traceback=traceback.format_exc()));print(traceback.format_exc(),flush=True)
    summary['source_preservation']=verify_preserved(protected)
    summary['finished_at_utc']=datetime.now(timezone.utc).isoformat()
    summary['generated_videos']=sum(len(q['videos']) for q in summary['runs'])
    summary['status']='PASS' if not summary['failures'] and summary['generated_videos']==len(selected)*len(a.view or VIEWS) else 'INCOMPLETE'
    dump(output/'summary.json',summary);make_index(output,summary['runs'])
    print(json.dumps({k:summary[k] for k in ('status','generated_videos','source_preservation')}),flush=True)
    return int(summary['status']!='PASS')


if __name__=='__main__':raise SystemExit(main())
