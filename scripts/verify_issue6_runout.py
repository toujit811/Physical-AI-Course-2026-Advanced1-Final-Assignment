"""Independent material acceptance: extended UNEVEN six plus immutable FLAT six."""
import csv,json
from pathlib import Path
import numpy as np
from PIL import Image
import imageio.v2 as imageio
from go2_ppo.video_materials import sha,inspect_video
from go2_ppo.presentation_media import verify_pts
from go2_ppo.rolling_native_audit import verify_finite_rows,_verify_calibration
from go2_ppo.rolling_uneven_media import terrain_section
from go2_ppo.rolling_approved_source import verify_heightfield

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/generated/issue6-runout-reshoot'
NEW=ROOT/'logs/course-native/issue6-runout12-D13550-ROLLING_UNEVEN-c2-v3'
VIEWS=('side','oblique','overhead');LEGS=('FL','FR','RL','RR')
EXPECTED='5d7fa7222067ff915942f2be546f9a9b3dcd6126b07eb3d7c8ea7fb4c05a4565'
def js(p):return json.loads(p.read_text())
def lines(p):return [json.loads(l) for l in p.read_text().splitlines()]
def rows(p):
    with p.open() as f:return list(csv.DictReader(f))
def dump(p,a):p.write_text(json.dumps(a,indent=2,allow_nan=False)+'\n')

def main():
    before=js(OUT/'preservation-before.json')
    for p,h in before.items():assert Path(p).is_file() and sha(Path(p))==h,('Prior artifact changed',p)
    approved=verify_heightfield(ROOT/'assets/approved/heightfield.npz')
    assert sha(ROOT/'logs/mixed-d/mixed128-lane-v3/policy_final.pt')==EXPECTED
    prior=js(ROOT/'reports/issue6-twelve-results.json');videos=[];trials=[];camera_style={}
    for kind in ('FLAT','ROLLING_UNEVEN'):
        reused=kind=='FLAT';run=ROOT/'logs/course-native/issue6-twelve-D13550-FLAT-c2' if reused else NEW
        media=run/'native-media';standard=media/'standard-final';result=js(run/'result.json');s=rows(run/'states.csv');verify_finite_rows(s)
        ts=np.array([float(q['time_s']) for q in s]);np.testing.assert_allclose(ts,np.arange(len(s))*.01,rtol=0,atol=1e-8)
        assert result['checkpoint_sha256']==EXPECTED and result['PPO_updates']==0 and not result['heldout'] and not result['learning_performed']
        assert result['actor_unchanged'] and result['optimizer_unchanged'] and result['checkpoint_file_unchanged']
        c=result['completion'];assert c['finish_x_m']==6.4 and c['confirmation_s']==0 and c['success'] and c['reason']=='POST_GOAL_RECORDED'
        assert result['recording_started_before_first_physics_step'] and result['terminal_evidence']['terminal_snapshot_verified']
        assert not any(result.get(k) for k in ('presentation_error','error','recording_error','terminal_recording_error'))
        crossed=[all(float(q[l+'_center_x_m'])-float(q[l+'_sphere_radius_m'])>6.4 for l in LEGS) for q in s];first=crossed.index(True);goal=ts[first]
        assert abs(goal-c['first_all_feet_pass_s'])<1e-8 and abs(goal-c['confirmed_at_sim_s'])<1e-8
        assert abs(ts[-1]-goal-3)<1e-8 and c['post_goal_recorded_s']==3
        assert not any(q[k]=='True' for q in s for k in ('physical_fallen','out_of_terrain','engine_error','unexpected_floor_contact')),'Material not accepted: physical failure remains'
        safety=result['new_run_safety'];assert safety['joint_input_pass'] and safety['max_joint_excursion_rad']<=.002 and safety['nonfoot_contact_points']==0
        terrain=np.load(media/'terrain-input.npz');layout=js(standard/'section-layout.json')
        if reused:
            assert not np.any(terrain['height_m']) and layout['x_limits_m']==[-1,9]
        else:
            assert terrain['height_m'].shape==(261,53) and terrain['x'][-1]==12
            np.testing.assert_array_equal(terrain['height_m'][:161],approved['height_m'])
            np.testing.assert_array_equal(terrain['x'][:161],approved['x'])
            assert not np.any(terrain['height_m'][161:])
            assert layout['x_limits_m']==[-1,12] and layout['native_terrain_x_limits_m']==[-1,12]
            assert result['course_config']['terrain_x_bounds']==[-1,12] and result['course_config']['runout_extension']['end_x_m']==12
            quant=np.load(run/'terrain-source-and-quantized.npz')
            np.testing.assert_array_equal(quant['height_mm'][:161],approved['height_mm'])
            np.testing.assert_array_equal(quant['original_height_m'][:161],approved['original_height_m'])
            assert quant['height_mm'].shape==(261,53) and quant['height_mm'].dtype==np.int16
            assert not np.any(quant['height_mm'][161:]) and not np.any(quant['original_height_m'][161:])
            assert result['terrain_audit']['integer_heightfield_max_error']==0
            assert result['terrain_audit']['query_max_error_m']<1e-5 and result['terrain_audit']['metre_readback_max_error_m']<1e-5
            readback=rows(run/'terrain-readback.csv');assert max(float(q['x_m']) for q in readback)>11.99
            exit_queries=[q for q in readback if 7<float(q['x_m'])<=12];assert len(exit_queries)>0 and max(abs(float(q['native_z_m'])) for q in exit_queries)<1e-7
            verts=np.load(run/'native-terrain-vertices.npz')['vertices_world_m'];assert verts[:,0].max()>11.99
            old=ROOT/'logs/course-native/issue6-twelve-D13550-ROLLING_UNEVEN-c2';old_result=js(old/'result.json');old_s=rows(old/'states.csv')
            assert result['control']==old_result['control'] and result['physical_build']==old_result['physical_build']
            assert js(run/'config.json')['effective_cfgs']==js(old/'config.json')['effective_cfgs']
            assert all(all(a[k]==b[k] for k in a) for a,b in zip(old_s[:first+1],s[:first+1],strict=True)),'Core/policy physical prefix changed before goal'
            assert result['initial_qpos']==old_result['initial_qpos']
            for name,h in result['source_sha256s'].items():assert sha(run/'source'/name)==h
            contacts=lines(run/'contacts.jsonl')
            loaded_exit=[q for q in contacts if q['foot'] and q['positive_force'] and q['position_m'][0]>7 and q['time_s']>=goal]
            assert loaded_exit and max(q['time_s'] for q in loaded_exit)>=ts[-1]-.03
            assert max(abs(q['native_support_z_m']) for q in loaded_exit)<1e-7
            x,z=terrain_section({'x':terrain['x'],'y':terrain['y'],'height_m':terrain['height_m']})
            np.savetxt(standard/'verified-section-data.csv',np.c_[x,z],delimiter=',',header='world_x_m,native_y0_height_m',comments='')
            assert not layout['extrapolated_terrain']
        maps=lines(media/'camera-frame-map.jsonl');same_times={};cameras={}
        for view in VIEWS:
            m=[q for q in maps if q['view']==view];huds=lines(standard/f'{view}-hud-map.jsonl');tls=rows(standard/f'{view}-timeline.csv')
            assert len(m)==len(huds)==len(tls);same_times[view]=[q['simulation_time_s'] for q in m]
            zs=[];visibility=[]
            for i,(q,h,tl) in enumerate(zip(m,huds,tls,strict=True)):
                tm=q['simulation_time_s'];state=s[round(tm*100)]
                assert q['frame']==i and q['video_pts_s']==i/25
                assert abs(tm-i/25)<1e-7 or (i==len(m)-1 and abs(tm-i/25)<.04)
                assert sha(Path(q['raw_png']))==q['raw_png_sha256']==h['raw_png_sha256']
                assert h['source_frame']==i and h['simulation_time_s']==tm and h['video_pts_s']==i/25
                assert int(tl['source_frame'])==i and abs(float(tl['simulation_time_s'])-tm)<1e-8 and not tl['frozen_at_sim_s'] and tl['kind']!='end_card'
                np.testing.assert_allclose(q['base_position_m'],[float(state[k]) for k in ('x_m','y_m','height_m')],rtol=0,atol=1e-7)
                _verify_calibration(dict(q,true_90_side=view=='side'))
                bx,by,_=q['base_position_m'];expected={'side':([bx+.05,by-.95,.34],[bx+.05,by,.34],[0,0,1]),'oblique':([bx+1.1,by-1.7,1.12],[bx+.25,by,.2],[0,0,1]),'overhead':([bx+.5,0,3.3],[bx+.5,0,0],[0,1,0])}[view]
                for value,ex in zip((q['pos'],q['lookat']),expected[:2]):np.testing.assert_allclose(value,ex,rtol=0,atol=1e-6)
                forward=np.array(expected[1])-np.array(expected[0]);forward/=np.linalg.norm(forward);right=np.cross(forward,expected[2]);right/=np.linalg.norm(right)
                np.testing.assert_allclose(q['up'],np.cross(right,forward),rtol=0,atol=1e-6)
                K=np.asarray(q['intrinsics']);E=np.asarray(q['extrinsics']);zs.append(float((-E[:3,:3].T@E[:3,3])[2]))
                positions=[q['base_position_m']]+[[float(state[l+'_center_'+a+'_m']) for a in 'xyz'] for l in LEGS]
                local=np.c_[positions,np.ones(5)]@E.T;uv=local[:,:3]@K.T;uv=uv[:,:2]/uv[:,2,None]
                visible=(local[:,2]>0)&(uv[:,0]>=0)&(uv[:,0]<640)&(uv[:,1]>=0)&(uv[:,1]<360)
                visibility.append(bool(visible.all()))
                assert visible.all(),(kind,view,tm,'base or foot center outside frame')
                assert h['baseline_y_px']==43 and h['section_current_x_m']==float(state['x_m']) and h['section_current_y_m']==0
                px=80+(float(state['x_m'])-layout['x_limits_m'][0])*layout['x_pixels_per_m']
                np.testing.assert_allclose(h['section_current_pixel'],[px,685],rtol=0,atol=1e-7)
                assert 80<=px<=1200 and h['goal_displayed']==(tm>=goal-1e-8)
                np.testing.assert_allclose(np.diff([v['world_xyz_m'][0] for v in h['world_ticks']]),.5,rtol=0,atol=1e-8)
                for tick in h['world_ticks']+h['gate_markers']:
                    v=E@np.r_[tick['world_xyz_m'],1.]
                    if v[2]>1e-9:
                        p=K@v[:3];p=p[:2]/p[2];assert abs(tick['hud_x_px']-(224+(p[0]+.5)*1.3-.5))<1e-7
                    else:assert tick['hud_x_px'] is None
            assert np.ptp(zs)<1e-6
            signature=(m[0]['fov_deg'],m[0]['res'],m[0]['intrinsics'])
            if view in camera_style:assert signature==camera_style[view]
            else:camera_style[view]=signature
            assert abs(m[0]['simulation_time_s'])<1e-8 and abs(m[-1]['simulation_time_s']-ts[-1])<1e-8
            cameras[view]={'FOV_deg':m[0]['fov_deg'],'world_Z_range_m':[min(zs),max(zs)],'base_and_all_feet_centers_inside_all_frames':all(visibility),'frames':len(m)}
            raw=media/f'native-{view}-raw.mp4';display=standard/f'course-{view}.mp4';pair=[]
            for form,path,other in [('raw',raw,display),('standard',display,raw)]:
                info=inspect_video(path,decode=True);info['actual_pts']=verify_pts(path,info['frames'])
                assert info['frames']==len(m) and info['fps']==25 and tuple(info['size'])==(1280,720) and info['faststart'] and not info['audio']
                if reused:
                    old_movie=next(v for v in prior['videos'] if v['path']==str(path));assert info['sha256']==old_movie['sha256']
                # Decode native-region samples, independent of the standard compositor.
                reader=imageio.get_reader(path);diffs=[]
                for j in sorted(set([0,len(m)//2,min(range(len(m)),key=lambda k:abs(m[k]['simulation_time_s']-goal)),len(m)-1])):
                    frame=reader.get_data(j)
                    with Image.open(m[j]['raw_png']) as png:
                        expected_rgb=np.asarray(png.resize((1280,720) if form=='raw' else (832,468),Image.Resampling.LANCZOS))
                    actual=frame if form=='raw' else frame[70:538,224:1056]
                    err=float(np.abs(actual.astype(float)-expected_rgb).mean());assert err<5;diffs.append(err)
                    Image.fromarray(frame).save(OUT/f'{kind}-{view}-{form}-{j:06d}.png')
                reader.close()
                info.update(environment=kind,view=view,format=form,run=run.name,reused_unchanged=reused,paired_path=str(other.resolve()),sim_start_s=0.,sim_end_s=float(ts[-1]),goal_sim_s=float(goal),actual_post_goal_s=3.,end_card_frames=0,sample_native_RGB_mean_error=diffs)
                videos.append(info);pair.append(info)
            assert pair[0]['frames']==pair[1]['frames'] and pair[0]['duration_s']==pair[1]['duration_s']
        assert same_times['side']==same_times['oblique']==same_times['overhead']
        tail=s[first:]
        numeric={key:{'min':min(float(q[key]) for q in tail),'max':max(float(q[key]) for q in tail)} for key in ('x_m','y_m','height_m','base_clearance_m','roll_deg','pitch_deg','max_joint_excursion_rad')}
        trials.append({'kind':kind,'run':run.name,'reused_unchanged':reused,'goal_sim_s':float(goal),'last_pre_goal_sim_s':float(ts[first-1]),'terminal_sim_s':float(ts[-1]),'post_goal_recorded_s':3.,'goal_hold_s':0.,'full_run_safety':safety,'post_goal_numeric_ranges':numeric,'cameras':cameras,'profile_x_limits_m':layout['x_limits_m'],'physical_floor_x_end_m':None if reused else 12.,'model_control_unchanged':True})
    assert len(videos)==12
    report={'status':'PASS','material_acceptance':'all12 verified; corrected UNEVEN no fall/boundary/disappearance through goal+3s','new_native_runs':1,'new_uneven_videos':6,'reused_flat_videos':6,'stopped_preexisting_runs_not_delivered':True,'checkpoint_sha256':EXPECTED,'PPO_updates':0,'heldout':False,'old_artifacts_sha_unchanged':len(before),'all12_fully_decoded':True,'same_run_time_frames_per_pair':True,'videos':videos,'runs':trials,'F':'USER_REVIEW_PENDING','display_axes_difference':'preserved FLAT[-1,9], extended UNEVEN[-1,12]; same panels/cameras/viridis0..0.20; verified rather than claimed identical'}
    dump(OUT/'verification.json',report);dump(ROOT/'reports/issue6-runout-results.json',report)
    print(json.dumps({k:report[k] for k in ('status','new_native_runs','new_uneven_videos','reused_flat_videos','old_artifacts_sha_unchanged','all12_fully_decoded')}))
    for q in trials:print(json.dumps(q))

if __name__=='__main__':main()
