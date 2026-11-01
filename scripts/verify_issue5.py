#!/usr/bin/env python3
"""Read-only independent native course evidence verification; no Genesis init."""
import argparse,csv,json,math,sys,xml.etree.ElementTree as ET
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation
import imageio.v2 as imageio
from PIL import Image
from go2_ppo.go2_kinematics import Go2Kinematics
from go2_ppo.rolling_native_audit import verify_finite_rows,_surface,_verify_calibration
from go2_ppo.video_materials import sha,inspect_video
from go2_ppo.presentation_media import verify_pts,verify_preserved

LEGS=('FL','FR','RL','RR')
URDF=Path(sys.executable).parent.parent/'lib/python3.12/site-packages/genesis/assets/urdf/go2/urdf/go2.urdf'
def rows(path):
    with Path(path).open() as f:return list(csv.DictReader(f))
def true(v):
    assert v in ('True','False',True,False);return v is True or v=='True'


def audit(run):
    result=json.loads((run/'result.json').read_text());states=rows(run/'states.csv');controls=rows(run/'controls.csv');media=run/'native-media'
    verify_finite_rows(states);verify_finite_rows(controls)
    terminal=float(result['terminal_sim_s']);ts=np.array([float(q['time_s']) for q in states])
    np.testing.assert_allclose(ts,np.arange(round(terminal*100)+1)/100,rtol=0,atol=1e-8)
    assert terminal>20.,'Required new run must actually continue beyond original20s'
    ct=np.array([float(q['time_s']) for q in controls]);np.testing.assert_allclose(ct,np.arange(len(ct))*.02,rtol=0,atol=1e-8)
    assert ts[-1]-ct[-1]<=.02+1e-7
    assert result['actor_unchanged'] and result['optimizer_unchanged'] and result['checkpoint_file_unchanged'];assert result['PPO_updates']==0
    assert result['checkpoint_sha256']=='5d7fa7222067ff915942f2be546f9a9b3dcd6126b07eb3d7c8ea7fb4c05a4565'
    for name,digest in result['source_sha256s'].items():assert sha(run/'source'/name)==digest
    assert result['physical_build']['entities']==2 and result['visual_gates']['no_collision_entities_added']
    assert result['recording_started_before_first_physics_step']
    finish=float(result['completion']['finish_x_m']);assert abs(finish-6.4)<1e-8
    terrain=dict(np.load(media/'terrain-input.npz'));kin=Go2Kinematics();maxfk=0.;firstall=None;pending=None;confirmed=None;firstfatal=None
    independent_boundary=[];footmins=[]
    for i,q in enumerate(states):
        x,y,z=[float(q[k]) for k in ('x_m','y_m','height_m')];t=ts[i]
        centers=np.array([[float(q[l+'_center_'+a+'_m']) for a in 'xyz'] for l in LEGS]);radii=np.array([float(q[l+'_sphere_radius_m']) for l in LEGS]);np.testing.assert_allclose(radii,.022,rtol=0,atol=1e-7)
        boundary=not(-.95<x<6.95 and -1.25<y<1.25) or np.any(centers[:,0]<-1) or np.any(centers[:,0]>7) or np.any(centers[:,1]<-1.3) or np.any(centers[:,1]>1.3)
        fallen=float(q['base_clearance_m'])<.2 or max(abs(float(q['roll_deg'])),abs(float(q['pitch_deg'])))>45
        assert bool(boundary)==true(q['out_of_terrain']);assert fallen==true(q['physical_fallen'])
        independent_boundary.append(bool(boundary));footmins.append(float(np.min(centers[:,0]-radii)))
        fatal=fallen or boundary or true(q['engine_error'])
        if fatal and firstfatal is None:firstfatal=t
        crossed=x>finish and all(centers[:,0]-radii>finish) and not fatal
        if crossed:
            if firstall is None:firstall=t
            if pending is None:pending=t
            if t-pending>=.2-1e-8 and confirmed is None:confirmed=t
        else:pending=None
        quat=np.array(json.loads(q['quaternion_wxyz']));rotation=Rotation.from_quat(quat[[1,2,3,0]])
        for k,leg in enumerate(LEGS):
            joints=[float(q[leg+'_'+n+'_joint_position_rad']) for n in ('hip','thigh','calf')]
            expected=rotation.apply(kin.fk(leg,joints))+[x,y,z];maxfk=max(maxfk,float(np.linalg.norm(expected-centers[k])))
        supports=_surface(terrain['x'],terrain['y'],terrain['height_m'],centers[:,:2])
        np.testing.assert_allclose(supports,[float(q[l+'_terrain_height_m']) for l in LEGS],rtol=0,atol=1e-5)
    assert maxfk<2e-5
    c=result['completion'];assert c['first_all_feet_pass_s']==firstall
    for leg,record in c['first_each_foot_pass'].items():
        indices=[i for i,q in enumerate(states) if float(q[leg+'_center_x_m'])-float(q[leg+'_sphere_radius_m'])>finish]
        assert indices and abs(ts[indices[0]]-record['at_or_after_sim_s'])<1e-8
        if indices[0]:assert abs(ts[indices[0]-1]-record['previous_sim_s'])<1e-8
    if c['success']:
        assert confirmed is not None and abs(terminal-confirmed)<1e-8 and firstfatal is None
        assert c['reason']=='COURSE_COMPLETED'
    else:
        assert c['reason']=='OUT_OF_BOUNDS' and firstfatal==terminal and confirmed is None
    # Compare new first20s with the actual original20s physical trajectory.
    root=Path(__file__).resolve().parents[1];condition=result['args']['condition'];oldrun=root/'logs/rolling-native'/f"issue3-D13550-{result['evaluation_kind']}-c{condition}"
    old=rows(oldrun/'states.csv');common=[k for k in old[0] if k in states[0]]
    prefix_exact=all(all(a[k]==b[k] for k in common) for a,b in zip(old,states[:2001],strict=True))
    assert prefix_exact,'Existing controller/physics trajectory unexpectedly changed'
    oldresult=json.loads((oldrun/'result.json').read_text())
    for key in ('sim','rigid','robot_urdf_sha256','robot_dofs','ground_collision_geoms'):
        assert result['physical_build'][key]==oldresult['physical_build'][key]
    assert result['native_foot_geometry']==oldresult['native_foot_geometry']
    assert result['control']['kp_readback']==[20.]*12
    assert result['control']['kd_readback']==[1. if n=='RL_calf_joint' else .5 for n in result['control']['names']]
    limits={j.attrib['name']:j.find('limit').attrib for j in ET.parse(URDF).findall('joint') if j.find('limit') is not None}
    joint_ok=True;max_excursion=0.
    for q in states:
        for name in result['control']['names']:
            low=float(limits[name]['lower']);high=float(limits[name]['upper']);effort=float(limits[name]['effort'])
            actual=float(q[name+'_position_rad']);target=float(q[name+'_target_rad']);applied=float(q[name+'_qf_applied_Nm'])
            excursion=max(low-actual,actual-high,0.);max_excursion=max(max_excursion,excursion)
            joint_ok &= excursion<=.002 and abs(applied)<=effort+1e-4 and low+.12-1e-5<=target<=high-.12+1e-5
    assert bool(joint_ok)==result['new_run_safety']['joint_input_pass']
    contacts=[json.loads(l) for l in (run/'contacts.jsonl').read_text().splitlines()];nonfoot=[e for e in contacts if not e['foot']]
    assert len(nonfoot)==result['new_run_safety']['nonfoot_contact_points']
    calibrations=[json.loads(l) for l in (media/'camera-frame-map.jsonl').read_text().splitlines()]
    # Prove actual native START/FINISH colors in raw RGB, not merely debug-node creation.
    overhead=[q for q in calibrations if q['view']=='overhead'];gate_rgb={}
    for label,gx,record in [('START',0.,overhead[0]),('FINISH',finish,overhead[-1])]:
        rgb=np.asarray(Image.open(record['raw_png']).convert('RGB')).astype(float);K=np.asarray(record['intrinsics']);E=np.asarray(record['extrinsics']);count=0
        for gy in np.linspace(-1.,1.,21):
            local=E@np.array([gx,gy,.004,1.]);pixel=K@local[:3]
            if local[2]<=0:continue
            u,v=np.rint(pixel[:2]/pixel[2]).astype(int)
            if not(3<=u<637 and 3<=v<357):continue
            patch=rgb[v-3:v+4,u-3:u+4];red,green,blue=[patch[:,:,i] for i in range(3)]
            mask=(green>70)&(green>1.6*red)&(green>1.2*blue) if label=='START' else (red>70)&(red>1.6*green)&(red>1.6*blue)
            count+=int(mask.sum())
        gate_rgb[label]=dict(matching_native_rgb_pixels=count,visible=count>0)
    gate_visible=all(q['visible'] for q in gate_rgb.values())
    if result['visual_gates'].get('camera_visible_external_visual_meshes'):
        assert gate_visible,'Native visual gates still missing despite render fix'
    prior_v1=run.with_name(run.name.removesuffix('-v2')+'-v1')
    entire_physics_matches_prior_v1=None
    if run.name.endswith('-v2') and prior_v1.exists():
        entire_physics_matches_prior_v1=sha(run/'states.csv')==sha(prior_v1/'states.csv')
        assert entire_physics_matches_prior_v1,'Visual-only fix unexpectedly changed native physics'
    movies={};zrange={};baseline={};terminalmaps={}
    for view in ('side','oblique','overhead'):
        frames=[q for q in calibrations if q['view']==view];times=[q['simulation_time_s'] for q in frames]
        assert times[0]==0 and abs(times[-1]-terminal)<1e-8
        np.testing.assert_allclose(times[:-1],np.arange(len(times)-1)/25,rtol=0,atol=1e-8)
        assert times[-1]<=(len(times)-1)/25+1e-8
        cameraZ=[]
        for idx,record in enumerate(frames):
            assert record['frame']==idx and record['video_pts_s']==idx/25
            raw=media/'raw'/view/f'frame{idx:06d}.png';assert sha(raw)==record['raw_png_sha256']
            _verify_calibration(dict(record,true_90_side=True if view=='side' else None))
            E=np.array(record['extrinsics']);world=-E[:3,:3].T@E[:3,3]
            np.testing.assert_allclose(world,record['pos'],rtol=0,atol=1e-5);cameraZ.append(float(world[2]))
            state=states[round(record['simulation_time_s']*100)]
            np.testing.assert_allclose(record['base_position_m'],[float(state[k]) for k in ('x_m','y_m','height_m')],rtol=0,atol=1e-7)
        zrange[view]=[min(cameraZ),max(cameraZ)];assert np.ptp(cameraZ)<1e-6
        hud=[json.loads(l) for l in (media/f'{view}-hud-map.jsonl').read_text().splitlines()];assert len(hud)==len(frames)
        for f,h in zip(frames,hud,strict=True):
            assert h['baseline_y_px']==43.;K=np.array(f['intrinsics']);E=np.array(f['extrinsics'])
            for tick in h['world_ticks']+h['gate_markers']:
                local=E@np.r_[tick['world_xyz_m'],1];p=K@local[:3]
                if local[2]>0:assert abs(tick['hud_x_px']-(224+(p[0]/p[2]+.5)*1.3-.5))<1e-8
        timeline=rows(media/f'{view}-timeline.csv');assert len(timeline)==len(frames)+50
        assert all(abs(float(timeline[i]['simulation_time_s'])-t)<1e-8 for i,t in enumerate(times))
        assert all(q['simulation_time_s']=='' and q['kind']=='end_card' for q in timeline[len(frames):])
        terminalmaps[view]={k:timeline[len(frames)-1][k] for k in ('simulation_time_s','video_pts_s','kind')}
        for filename in (f'native-{view}-raw.mp4',f'course-{view}.mp4'):
            info=inspect_video(media/filename,decode=True);info['actual_pts']=verify_pts(media/filename,info['frames']);movies[filename]=info
            assert info['frames']==len(frames)+(50 if filename.startswith('course') else 0)
        reader=imageio.get_reader(media/f'course-{view}.mp4');ys=[];firstcard=None;card_mad=[]
        for idx,frame in enumerate(reader):
            if idx<len(frames):ys.append(40+int(frame[40:47,226:1053].mean(axis=2).mean(axis=1).argmin()))
            else:
                if firstcard is None:firstcard=frame.astype(float)
                card_mad.append(float(abs(frame.astype(float)-firstcard).mean()))
            if idx in (0,len(frames)//2,len(frames)-1,len(frames)):
                Image.fromarray(frame).save(media/f'qa-{view}-{idx:06d}.png')
        reader.close();assert max(ys)-min(ys)<=1;assert len(card_mad)==50 and max(card_mad)<.1
        baseline[view]=[min(ys),max(ys)]
    return dict(run=run.name,QA='PASS' if gate_visible else 'FAIL_NATIVE_GATES_MISSING',physics_camera_timing_QA='PASS',native_ground_gate_RGB=gate_rgb,entire_physics_matches_prior_v1=entire_physics_matches_prior_v1,course_success=c['success'],reason=c['reason'],terminal_sim_s=terminal,terminal_xyz_m=result['terminal_base_xyz_m'],first_all_feet_s=firstall,confirmed_s=confirmed,terminal_min_foot_trailing_x_m=footmins[-1],first20s_trajectory_exact=prefix_exact,max_independent_FK_error_m=maxfk,actual_camera_Z_range_m=zrange,decoded_HUD_baseline_Y_range_px=baseline,terminal_frame_mapping=terminalmaps,movies=movies,new_run_safety=result['new_run_safety'])


def main():
    p=argparse.ArgumentParser();p.add_argument('runs',type=Path,nargs='+');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    root=Path(__file__).resolve().parents[1]
    known={root/'logs/mixed-d/mixed128-lane-v3/policy_final.pt':'5d7fa7222067ff915942f2be546f9a9b3dcd6126b07eb3d7c8ea7fb4c05a4565',
        root/'assets/approved/heightfield.npz':'69979149fa5814316b7abea1b4ea01ccb12a0dfd6d36bfe72f55ce79d4071913',
        root.parent/'Physical-AI-Course-2026-Advanced1-Final-Assignment/logs/stage1/natural/training/slip20-margin012-64x1500/model_6500.pt':'c9bd93aa103db4e892623babff4de5c8da2cc7c0af5e31bcca389836738c0a2c',
        root/'logs/mixed-d/mixed128-contact-v4/policy_final.pt':'219c566e34ba832916bb7549cebb9eb989ad8d38f8ffd376ca53ed77f918e284',
        URDF:'4f306754e9b3d73930ac8362aa456eb8912f2e886665618e7eced9627c1704a4'}
    for path,digest in known.items():assert sha(path)==digest
    records=[audit(p.resolve()) for p in a.runs];protection=verify_preserved(json.loads((a.output/'source-before.json').read_text()))
    required={r['run'] for r in records if r['run'].endswith('-c2-v2') and r['QA']=='PASS'}
    required_complete={'issue5-D13550-FLAT-c2-v2','issue5-D13550-ROLLING_UNEVEN-c2-v2'}.issubset(required)
    report=dict(status='PASS_WITH_RETAINED_V1_VISUAL_FAILURES' if required_complete else 'REQUIRED_RUNS_INCOMPLETE',required_priority_runs_verified=required_complete,native_runs=len(records),PPO_updates=0,records=records,source_preservation=protection)
    (a.output/'independent-qa.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(QA=report['status'],required_priority_runs_verified=required_complete,runs=len(records),results=[{k:r[k] for k in ('run','QA','course_success','reason','terminal_sim_s')} for r in records],source_preservation=protection)))


if __name__=='__main__':main()
