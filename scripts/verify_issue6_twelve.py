"""Read-only independent checks of the paired twelve native Issue6 recordings."""
import csv,json,math,hashlib
from pathlib import Path
import numpy as np
from PIL import Image
import imageio.v2 as imageio
from go2_ppo.video_materials import sha,inspect_video
from go2_ppo.presentation_media import verify_pts
from go2_ppo.rolling_native_audit import verify_finite_rows,_verify_calibration
from go2_ppo.rolling_uneven_media import terrain_section

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/generated/issue6-twelve'
LEGS=('FL','FR','RL','RR');VIEWS=('side','oblique','overhead')
EXPECTED='5d7fa7222067ff915942f2be546f9a9b3dcd6126b07eb3d7c8ea7fb4c05a4565'

def rows(p):
    with p.open() as f:return list(csv.DictReader(f))
def js(p):return json.loads(p.read_text())
def lines(p):return [json.loads(l) for l in p.read_text().splitlines()]
def dump(p,o):p.write_text(json.dumps(o,indent=2,allow_nan=False)+'\n')

def main():
    before=js(OUT/'preservation-before.json')
    assert all(Path(p).is_file() and sha(Path(p))==h for p,h in before.items()),'Prior artifact changed'
    assert sha(ROOT/'logs/mixed-d/mixed128-lane-v3/policy_final.pt')==EXPECTED
    source=np.load(ROOT/'assets/approved/heightfield.npz')
    videos=[];trials=[];style={};layout_style=None
    for kind in ('FLAT','ROLLING_UNEVEN'):
        run=ROOT/'logs/course-native'/f'issue6-twelve-D13550-{kind}-c2';media=run/'native-media';standard=media/'standard-final'
        r=js(run/'result.json');s=rows(run/'states.csv');verify_finite_rows(s)
        ts=np.array([float(q['time_s']) for q in s]);np.testing.assert_allclose(ts,np.arange(len(s))*.01,rtol=0,atol=1e-8)
        assert r['PPO_updates']==0 and not r['learning_performed'] and not r['heldout']
        assert r['actor_unchanged'] and r['optimizer_unchanged'] and r['checkpoint_file_unchanged']
        assert r['checkpoint_sha256']==EXPECTED and r['completion']['confirmation_s']==0
        assert r['status']=='COURSE_COMPLETED' and r['completion']['reason']=='POST_GOAL_RECORDED'
        finish=r['completion']['finish_x_m'];assert finish==6.4
        passed=[all(float(q[l+'_center_x_m'])-float(q[l+'_sphere_radius_m'])>finish for l in LEGS) for q in s]
        first=passed.index(True);goal=ts[first]
        assert abs(goal-r['completion']['first_all_feet_pass_s'])<1e-8
        assert abs(goal-r['completion']['confirmed_at_sim_s'])<1e-8
        assert abs(ts[-1]-goal-3)<1e-8 and r['completion']['post_goal_recorded_s']==3
        assert not any(q['physical_fallen']=='True' or q['out_of_terrain']=='True' or q['engine_error']=='True' for q in s[:first+1])
        assert r['terminal_evidence']['terminal_snapshot_verified'] and r['recording_started_before_first_physics_step']
        assert not r.get('presentation_error') and not r.get('recording_error')
        old=ROOT/'logs/course-native'/('issue6-D13550-FLAT-c2-raw' if kind=='FLAT' else 'issue5-D13550-ROLLING_UNEVEN-c2-v2')
        old_s=rows(old/'states.csv');old_r=js(old/'result.json')
        assert r['physical_build']==old_r['physical_build'] and r['control']==old_r['control']
        assert js(run/'config.json')['effective_cfgs']==js(old/'config.json')['effective_cfgs']
        assert all(all(a[k]==b[k] for k in a) for a,b in zip(old_s,s[:len(old_s)],strict=True)),'Physical prefix changed'
        for name,h in r['source_sha256s'].items():assert sha(run/'source'/name)==h
        terrain=np.load(media/'terrain-input.npz')
        if kind=='FLAT':assert not np.any(terrain['height_m'])
        else:np.testing.assert_allclose(terrain['height_m'],np.rint(source['z_m']*1000).astype(np.int16)/1000,rtol=0,atol=1e-8)
        # Profile uses only actual Y=0 interpolated native heights, no fake exit terrain.
        x,z=terrain_section({'x':terrain['x'],'y':terrain['y'],'height_m':terrain['height_m']})
        np.savetxt(standard/'verified-section-data.csv',np.c_[x,z],delimiter=',',header='world_x_m,native_y0_height_m',comments='')
        layout=js(standard/'section-layout.json')
        assert layout['x_limits_m']==[-1,9] and layout['native_terrain_x_limits_m']==[-1,7] and not layout['extrapolated_terrain']
        if layout_style is None:layout_style=layout
        else:assert layout_style==layout
        maps=lines(media/'camera-frame-map.jsonl');times_by_view={};camera_report={}
        for view in VIEWS:
            m=[q for q in maps if q['view']==view];hud=lines(standard/f'{view}-hud-map.jsonl');timeline=rows(standard/f'{view}-timeline.csv')
            assert len(m)==len(hud)==len(timeline)
            times_by_view[view]=[q['simulation_time_s'] for q in m]
            assert abs(m[0]['simulation_time_s'])<1e-8 and abs(m[-1]['simulation_time_s']-ts[-1])<1e-8
            raw=media/f'native-{view}-raw.mp4';display=standard/f'course-{view}.mp4'
            infos=[];camera_z=[];ticks_x=[];base_in_frame=[]
            for i,(q,h,tl) in enumerate(zip(m,hud,timeline,strict=True)):
                tm=q['simulation_time_s'];idx=round(tm*100);state=s[idx]
                assert q['frame']==i and q['video_pts_s']==i/25
                assert abs(tm-i/25)<1e-7 or (i==len(m)-1 and abs(tm-i/25)<.04)
                assert sha(q['raw_png'])==q['raw_png_sha256']==h['raw_png_sha256']
                assert h['source_frame']==i and h['simulation_time_s']==tm and h['video_pts_s']==i/25
                assert int(tl['source_frame'])==i and abs(float(tl['simulation_time_s'])-tm)<1e-8
                assert tl['kind'] in ('recorded_motion','terminal_real_snapshot') and not tl['frozen_at_sim_s']
                np.testing.assert_allclose(q['base_position_m'],[float(state[k]) for k in ('x_m','y_m','height_m')],rtol=0,atol=1e-7)
                _verify_calibration(dict(q,true_90_side=view=='side'))
                # Independent fixed-Z and pose expectations; optical up is orthogonalized.
                bx,by,_=q['base_position_m']
                expected={'side':([bx+.05,by-.95,.34],[bx+.05,by,.34],[0,0,1]),'oblique':([bx+1.1,by-1.7,1.12],[bx+.25,by,.20],[0,0,1]),'overhead':([bx+.5,0,3.3],[bx+.5,0,0],[0,1,0])}[view]
                for value,ex in zip((q['pos'],q['lookat']),expected[:2]):np.testing.assert_allclose(value,ex,rtol=0,atol=1e-6)
                forward=np.array(expected[1])-np.array(expected[0]);forward/=np.linalg.norm(forward);right=np.cross(forward,expected[2]);right/=np.linalg.norm(right)
                np.testing.assert_allclose(q['up'],np.cross(right,forward),rtol=0,atol=1e-6)
                K=np.asarray(q['intrinsics']);E=np.asarray(q['extrinsics']);camera_z.append(float((-E[:3,:3].T@E[:3,3])[2]))
                camera_point=E@np.r_[q['base_position_m'],1.];uv=K@camera_point[:3];uv=uv[:2]/uv[2]
                base_in_frame.append(bool(camera_point[2]>0 and 0<=uv[0]<640 and 0<=uv[1]<360))
                assert h['baseline_y_px']==43 and h['section_current_x_m']==float(state['x_m']) and h['section_current_y_m']==0
                px=80+(float(state['x_m'])+1)*layout['x_pixels_per_m']
                np.testing.assert_allclose(h['section_current_pixel'],[px,685],rtol=0,atol=1e-7)
                assert 80<=px<=1200 and h['goal_displayed']==(tm>=goal-1e-8)
                world=[v['world_xyz_m'][0] for v in h['world_ticks']];np.testing.assert_allclose(np.diff(world),.5,rtol=0,atol=1e-8)
                for tick in h['world_ticks']+h['gate_markers']:
                    local=E@np.r_[tick['world_xyz_m'],1.]
                    if local[2]>1e-9:
                        uv=K@local[:3];uv=uv[:2]/uv[2]
                        expected_px=(uv[0]+.5)*1.3-.5+224
                        assert abs(tick['hud_x_px']-expected_px)<1e-7
                    else:assert tick['hud_x_px'] is None
                ticks_x.append([q0['hud_x_px'] for q0 in h['world_ticks']])
            assert np.ptp(camera_z)<1e-6
            signature=(m[0]['fov_deg'],m[0]['res'],m[0]['intrinsics'])
            if view in style:assert signature==style[view]
            else:style[view]=signature
            for form,path,pair in [('raw',raw,display),('standard',display,raw)]:
                info=inspect_video(path,decode=True);info['actual_pts']=verify_pts(path,info['frames'])
                assert path.is_file() and path.is_absolute() and info['frames']==len(m)
                assert info['fps']==25 and tuple(info['size'])==(1280,720) and info['faststart'] and not info['audio']
                assert abs(info['duration_s']-len(m)/25)<1e-7
                # Decode samples and compare directly with the same saved native source.
                reader=imageio.get_reader(path);diffs=[]
                for j in (0,len(m)//2,len(m)-1):
                    frame=reader.get_data(j)
                    with Image.open(m[j]['raw_png']) as png:
                        if form=='raw':expected_rgb=np.asarray(png.resize((1280,720),Image.Resampling.LANCZOS));actual=frame
                        else:expected_rgb=np.asarray(png.resize((832,468),Image.Resampling.LANCZOS));actual=frame[70:538,224:1056]
                    diff=float(np.abs(actual.astype(float)-expected_rgb).mean());assert diff<5;diffs.append(diff)
                    Image.fromarray(frame).save(OUT/f'{kind}-{view}-{form}-{j:06d}.png')
                reader.close()
                info.update(environment=kind,view=view,format=form,paired_path=str(pair.resolve()),run=run.name,sim_start_s=0.,sim_end_s=float(ts[-1]),goal_sim_s=float(goal),actual_post_goal_s=3.,end_card_frames=0,sample_native_rgb_mean_error=diffs)
                videos.append(info);infos.append(info)
            assert infos[0]['frames']==infos[1]['frames'] and infos[0]['duration_s']==infos[1]['duration_s']
            camera_report[view]={'fov_deg':m[0]['fov_deg'],'native_res':m[0]['res'],'intrinsics':m[0]['intrinsics'],'world_z_range_m':[min(camera_z),max(camera_z)],'frames':len(m),'true_90_side_verified':view=='side','base_center_visible_at_last_frame':base_in_frame[-1],'first_base_center_out_of_frame_s':next((m[j]['simulation_time_s'] for j,visible in enumerate(base_in_frame) if not visible),None)}
        assert times_by_view['side']==times_by_view['oblique']==times_by_view['overhead']
        event_first={flag:next((float(q['time_s']) for q in s if q[flag]=='True'),None) for flag in ('physical_fallen','out_of_terrain','engine_error','unexpected_floor_contact')}
        bracket=[{'time_s':float(s[i]['time_s']),**{l+'_trailing_x_m':float(s[i][l+'_center_x_m'])-float(s[i][l+'_sphere_radius_m']) for l in LEGS}} for i in (first-1,first)]
        trials.append(dict(kind=kind,run=run.name,goal_x_m=finish,first_all_feet_sim_s=float(goal),crossing_bracket=bracket,terminal_sim_s=float(ts[-1]),actual_post_goal_s=3.,post_goal_interval_s=[float(goal),float(ts[-1])],first_events=event_first,full_run_safety=r['new_run_safety'],physical_settings_unchanged=True,old_physical_prefix_exact=True,initial_camera_actual=camera_report,PPO_updates=0,source_snapshot_verified=True))
    assert len(videos)==12 and len({v['path'] for v in videos})==12
    report=dict(status='PASS',authority='Issue6 top section updated2026-11-01T17:23:32Z + user3seconds',native_runs=2,videos=videos,runs=trials,all12_fully_decoded=True,same_run_and_time_ranges_verified=True,cameras_measured_same=True,layout_measured_same=True,prior_artifact_hashes_unchanged=len(before),checkpoint_sha256=EXPECTED,PPO_updates=0,heldout=False,human_F='USER_REVIEW_PENDING',initial_flat_standard_attempt='Retained native-media/course-*.mp4; superseded by native-media/standard-final/course-*.mp4 because terminal position exceeded old profile axis',post_goal_safety_rule='Record actual motion for 3s after goal; retain boundary/fall events; engine/state/resource/wall errors stop; no extension of physical terrain')
    dump(OUT/'verification.json',report)
    dump(ROOT/'reports/issue6-twelve-results.json',report)
    print(json.dumps({k:report[k] for k in ('status','native_runs','all12_fully_decoded','prior_artifact_hashes_unchanged')}))
    for r in trials:print(json.dumps(r))

if __name__=='__main__':main()
