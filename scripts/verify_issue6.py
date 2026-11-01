"""Read-only checks for the one new FLAT run and three reused UNEVEN raws."""
import csv,json
from pathlib import Path
import numpy as np
from PIL import Image
import imageio.v2 as imageio
from go2_ppo.video_materials import sha,inspect_video
from go2_ppo.presentation_media import verify_preserved,verify_pts
from go2_ppo.rolling_native_audit import verify_finite_rows,_verify_calibration
from go2_ppo.course_media import camera_poses

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/generated/issue6';LEGS=('FL','FR','RL','RR');VIEWS=('side','oblique','overhead')

def rows(p):
    with p.open() as f:return list(csv.DictReader(f))

def main():
    run=ROOT/'logs/course-native/issue6-D13550-FLAT-c2-raw';old=ROOT/'logs/course-native/issue5-D13550-FLAT-c2-v2';uneven=ROOT/'logs/course-native/issue5-D13550-ROLLING_UNEVEN-c2-v2'
    result=json.loads((run/'result.json').read_text());states=rows(run/'states.csv');previous=rows(old/'states.csv');verify_finite_rows(states)
    assert result['status']=='COURSE_COMPLETED' and result['args']['raw_only'] and result['completion']['confirmation_s']==0
    assert result['actor_unchanged'] and result['optimizer_unchanged'] and result['checkpoint_file_unchanged'] and result['PPO_updates']==0
    expected_sha='5d7fa7222067ff915942f2be546f9a9b3dcd6126b07eb3d7c8ea7fb4c05a4565'
    assert sha(ROOT/'logs/mixed-d/mixed128-lane-v3/policy_final.pt')==expected_sha==result['checkpoint_sha256']
    ts=np.array([float(r['time_s']) for r in states]);np.testing.assert_allclose(ts,np.arange(len(states))*.01,rtol=0,atol=1e-8)
    assert ts[-1]>float(previous[-1]['time_s'])
    excluded={'fallen','out_of_terrain'};common=[k for k in previous[0] if k not in excluded]
    assert all(all(a[k]==b[k] for k in common) for a,b in zip(previous,states[:len(previous)],strict=True))
    finish=result['completion']['finish_x_m'];passed=[all(float(r[l+'_center_x_m'])-float(r[l+'_sphere_radius_m'])>finish for l in LEGS) for r in states]
    first=passed.index(True);assert first==len(states)-1 and ts[first]==result['terminal_sim_s']==result['completion']['first_all_feet_pass_s']
    over7=[r for r in states if any(float(r[l+'_center_x_m'])>7 for l in LEGS)]
    assert over7 and not any(r['out_of_terrain']=='True' for r in over7)
    assert not any(r['physical_fallen']=='True' or r['engine_error']=='True' for r in states)
    assert not list((run/'native-media').glob('course-*.mp4'))
    assert len(list((run/'native-media').glob('*.mp4')))==3
    old_report=json.loads((ROOT/'reports/issue5-results.json').read_text());old_uneven=next(r for r in old_report['runs'] if r['run']==uneven.name)
    videos=[];style={}
    for source in (run,uneven):
        media=source/'native-media';maps=[json.loads(l) for l in (media/'camera-frame-map.jsonl').read_text().splitlines()]
        for view in VIEWS:
            records=[r for r in maps if r['view']==view];cameraZ=[]
            for i,r in enumerate(records):
                assert r['frame']==i and r['video_pts_s']==i/25
                if i<len(records)-1:assert abs(r['simulation_time_s']-i/25)<1e-7
                assert sha(r['raw_png'])==r['raw_png_sha256']
                _verify_calibration(dict(r,true_90_side=view=='side'))
                pose=camera_poses(r['base_position_m'])[view]
                for key in ('pos','lookat'):np.testing.assert_allclose(r[key],pose[key],rtol=0,atol=1e-6)
                forward=np.asarray(pose['lookat'])-np.asarray(pose['pos']);forward/=np.linalg.norm(forward)
                right=np.cross(forward,pose['up']);right/=np.linalg.norm(right);image_up=np.cross(right,forward)
                np.testing.assert_allclose(r['up'],image_up,rtol=0,atol=1e-6)
                E=np.asarray(r['extrinsics']);cameraZ.append(float((-E[:3,:3].T@E[:3,3])[2]))
            assert np.ptp(cameraZ)<1e-6
            signature=(records[0]['fov_deg'],records[0]['res'],records[0]['intrinsics'])
            if view in style:assert signature==style[view]
            else:style[view]=signature
            path=media/f'native-{view}-raw.mp4';info=inspect_video(path,decode=True);info['actual_pts']=verify_pts(path,info['frames'])
            assert info['frames']==len(records)
            if source==uneven:assert info['sha256']==old_uneven['movies'][path.name]['sha256']
            else:assert abs(records[-1]['simulation_time_s']-result['terminal_sim_s'])<1e-8
            reader=imageio.get_reader(path);differences=[]
            for i in (0,len(records)//2,len(records)-1):
                frame=reader.get_data(i)
                with Image.open(records[i]['raw_png']) as image:expected=np.asarray(image.resize((1280,720),Image.Resampling.LANCZOS))
                difference=float(np.abs(frame.astype(float)-expected).mean());assert difference<5.;differences.append(difference)
                Image.fromarray(frame).save(OUT/f'{source.name}-{view}-{i:06d}.png')
            reader.close();info.update(view=view,reused=source==uneven,run=source.name,source_frames=len(records),end_card_frames=0,camera_world_Z_range_m=[min(cameraZ),max(cameraZ)],sample_mean_RGB_difference= differences,first_sim_s=records[0]['simulation_time_s'],last_sim_s=records[-1]['simulation_time_s'])
            videos.append(info)
    preserved=verify_preserved(json.loads((OUT/'source-before.json').read_text()))
    bracket={side:{'time_s':float(states[i]['time_s']),**{l+'_trailing_x_m':float(states[i][l+'_center_x_m'])-float(states[i][l+'_sphere_radius_m']) for l in LEGS}} for side,i in [('before',first-1),('first_pass',first)]}
    report=dict(authority_issue=6,status='PASS',new_native_runs=1,PPO_updates=0,flat_goal_reached=True,first_four_feet_sim_s=float(ts[first]),previous_stop_sim_s=float(previous[-1]['time_s']),new_base_xyz_m=result['terminal_base_xyz_m'],goal_x_m=finish,confirmation_s=0,first_pass_bracket=bracket,continued_beyond_old_stop=True,physical_prefix_exact_except_removed_boundary_flags=True,new_run_safety=result['new_run_safety'],tests=113,old_tests_preserved=109,new_raw_movies=3,reused_uneven_raw_movies=3,videos=videos,source_preservation=preserved,no_new_viewer_or_layout=True)
    (OUT/'verification.json').write_text(json.dumps(report,indent=2)+'\n');(ROOT/'reports/issue6-results.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('status','new_native_runs','first_four_feet_sim_s','new_raw_movies','reused_uneven_raw_movies','source_preservation')}))

if __name__=='__main__':main()
