"""Independent read-only audit of actual approved rolling-terrain native recordings.

No Genesis initialization, simulation, rendering, pose replay, learning, issue
writes or git operations. Media, terrain provenance, environment and model
verdicts are separate evidence layers; a valid movie cannot upgrade a failed model.
"""
from __future__ import annotations
import argparse
import csv
import json
import os
from pathlib import Path
import tempfile
import traceback
import numpy as np
from PIL import Image
os.environ.setdefault('MPLCONFIGDIR',str(Path(tempfile.gettempdir())/'physicaai-rolling-audit-mpl'))
from .video_materials import sha,inspect_video

ROOT=Path(__file__).resolve().parents[2]
APPROVED_SHA='69979149fa5814316b7abea1b4ea01ccb12a0dfd6d36bfe72f55ce79d4071913'
APPROVED_NPZ=ROOT/'reports/rolling-native-20261101/original-package/physicaai_uneven_preview/heightfield.npz'
VIEWS=('side','oblique','overhead')


def decision_layers(result):
    model=result.get('model_status',result.get('model_numeric_status',result.get('status','UNASSESSED')))
    if result.get('mode')=='pd_contact_probe':model='NOT_EVALUATED_CONTACT_ONLY'
    return {'raw_result_status':result.get('status','UNASSESSED'),
        'environment_status':result.get('environment_status',result.get('environment_verdict','UNASSESSED')),
        'model_status':model,
        'model_numeric_gates_as_recorded':result.get('numeric_gates'),
        'model_numeric_pass_as_recorded':result.get('numeric_pass')}


def verify_finite_rows(rows):
    for i,row in enumerate(rows):
        for key,value in row.items():
            if str(value).lower() in ('true','false'):continue
            if value is None or value=='':raise ValueError(f'Missing physical state value: row={i} {key}')
            parsed=json.loads(value) if isinstance(value,str) and value.startswith('[') else float(value)
            if not np.isfinite(np.asarray(parsed,dtype=float)).all():raise ValueError(f'Nonfinite physical state: row={i} {key}')
    return True


def _surface(x,y,height,points):
    points=np.asarray(points,dtype=float);px=np.clip(points[:,0],x[0],x[-1]);py=np.clip(points[:,1],y[0],y[-1])
    i=np.clip(np.searchsorted(x,px,side='right')-1,0,len(x)-2);j=np.clip(np.searchsorted(y,py,side='right')-1,0,len(y)-2)
    u=(px-x[i])/(x[i+1]-x[i]);v=(py-y[j])/(y[j+1]-y[j])
    # Native Terrain facets use the anti-diagonal, not a bilinear saddle patch.
    a,b,c,d=height[i,j],height[i+1,j],height[i,j+1],height[i+1,j+1]
    return np.where(u+v<=1,a+(b-a)*u+(c-a)*v,d+(c-d)*(1-u)+(b-d)*(1-v))


def audit_physics(run,result):
    """Check native evidence identities; preserve the evaluator's numeric gates."""
    from scipy.spatial.transform import Rotation
    from .go2_kinematics import Go2Kinematics
    run=Path(run)
    mode=result.get('mode','fixed_policy6500_baseline')
    if mode=='fixed_policy6500_baseline' and result.get('policy_evaluation') is not True:
        raise ValueError('Fixed-model baseline must declare policy_evaluation true')
    if mode=='pd_contact_probe' and result.get('policy_evaluation') is not False:
        raise ValueError('PD contact-only probe must not claim a policy evaluation')
    if result.get('approved_source') is not True or result.get('robot_count')!=1:
        raise ValueError('Actual approved terrain and exactly one live Go2 must be declared')
    if result.get('source_sha256')!=APPROVED_SHA:raise ValueError('Physical run does not identify the exact approved source SHA')
    frozen=result.get('source_sha256s',{})
    if not frozen:raise ValueError('Native evaluator/environment frozen source hashes are missing')
    for name,digest in frozen.items():
        if sha(run/'source'/name)!=digest:raise ValueError(f'Frozen native evaluator/environment source changed: {name}')
    if not (run/'states.csv').exists():return {'status':'UNASSESSED','reason':'states.csv not yet available'}
    with (run/'states.csv').open() as f:states=list(csv.DictReader(f))
    with (run/'controls.csv').open() as f:controls=list(csv.DictReader(f))
    if not states or not controls:raise ValueError('Empty native state/control evidence')
    verify_finite_rows(states);verify_finite_rows(controls)
    times=np.array([float(r['time_s']) for r in states]);dt=float(np.median(np.diff(times))) if len(times)>1 else None
    if times[0]!=0 or (len(times)>1 and (np.any(np.diff(times)<=0) or np.max(abs(np.diff(times)-dt))>1e-8)):
        raise ValueError('Physical-state times are not continuous from initial t=0')
    control_times=np.array([float(r['time_s']) for r in controls])
    if control_times[0]!=0 or (len(controls)>1 and np.max(abs(np.diff(control_times)-.02))>1e-8):raise ValueError('Control times differ from 0.02s inference cadence')
    if abs(times[-1]-float(result['terminal_sim_s']))>1e-7:raise ValueError('Saved physical terminal time differs from result')
    if result.get('rows',len(states))!=len(states) or result.get('control_samples',len(controls))!=len(controls):raise ValueError('Physical sample counts differ from result')
    with np.load(run/'native-media/terrain-input.npz',allow_pickle=False) as terrain:
        x,y,h=(terrain[k].copy() for k in ('x','y','height_m'))
    base=np.array([[float(r[k]) for k in ('x_m','y_m','height_m')] for r in states])
    quats=np.array([json.loads(r['quaternion_wxyz']) for r in states]);rotation=Rotation.from_quat(quats[:,[1,2,3,0]])
    kin=Go2Kinematics();fk_errors={};support_errors={};radius_errors={};clearance_errors={}
    if result.get('physical_build',{}).get('robot_urdf_sha256')!=sha(kin.urdf_path):
        raise ValueError('Native robot source is not the installed actual Go2 URDF used for independent FK')
    indexed={round(float(r['time_s']),8):r for r in states}
    with (run/'native-media/camera-frame-map.jsonl').open() as f:
        for line in f:
            frame=json.loads(line);row=indexed.get(round(float(frame['simulation_time_s']),8))
            if row is None:raise ValueError('Native camera frame has no matching actual physics state time')
            np.testing.assert_allclose(frame['base_position_m'],[float(row[k]) for k in ('x_m','y_m','height_m')],rtol=0,atol=1e-6)
    for leg in ('FL','FR','RL','RR'):
        q=np.array([[float(r[f'{leg}_{part}_joint_position_rad']) for part in ('hip','thigh','calf')] for r in states])
        centers=np.array([[float(r[f'{leg}_center_{a}_m']) for a in 'xyz'] for r in states])
        error=np.linalg.norm(rotation.apply(kin.fk(leg,q))+base-centers,axis=1);fk_errors[leg]=float(error.max())
        if fk_errors[leg]>=1e-4:raise ValueError(f'Independent URDF FK fails native {leg} foot centers')
        reported=np.array([float(r[f'{leg}_FK_error_m']) for r in states])
        if np.max(abs(error-reported))>1e-6:raise ValueError('Reported FK error differs from independent recomputation')
        support=np.array([float(r[f'{leg}_terrain_height_m']) for r in states]);wanted=_surface(x,y,h,centers[:,:2])
        support_errors[leg]=float(np.max(abs(support-wanted)))
        if support_errors[leg]>1e-5:raise ValueError('Foot support query differs from approved quantized terrain')
        bottom=np.array([float(r[f'{leg}_bottom_z_m']) for r in states]);clearance=np.array([float(r[f'{leg}_clearance_m']) for r in states])
        radius_errors[leg]=float(np.max(abs(centers[:,2]-bottom-kin.foot_radius[leg])))
        clearance_errors[leg]=float(np.max(abs(clearance-(bottom-support))))
        if radius_errors[leg]>1e-6 or clearance_errors[leg]>1e-7:raise ValueError('Native foot radius/clearance identity fails')
    with (run/'contacts.jsonl').open() as f:contacts=[json.loads(line) for line in f if line.strip()]
    ground=set(result.get('physical_build',{}).get('ground_collision_geoms',[]));positive=nonflat=upward=0;point_error=0.;force_ids=set()
    for event in contacts:
        p=np.asarray(event['position_m'],dtype=float);force=np.asarray(event['force_on_robot_N'],dtype=float)
        if p.shape!=(3,) or force.shape!=(3,) or not np.isfinite(np.r_[p,force,event['native_support_z_m'],event['penetration_m']]).all():raise ValueError('Nonfinite native terrain contact')
        if ground and event['terrain_geom'] not in ground:raise ValueError('Contact names an unexpected terrain geometry')
        if bool(event['foot'])!=(event['part'] in ('FL','FR','RL','RR')):raise ValueError('Native foot/contact-part identity disagrees')
        loaded=bool(np.linalg.norm(force)>1e-6)
        if loaded!=bool(event['positive_force']):raise ValueError('Contact positive-force flag differs from actual force vector')
        if dt is not None and abs(event['contact_geometry_time_s']-max(0,event['time_s']-dt))>1e-7:raise ValueError('Contact geometry time lag differs from actual physics dt')
        wanted=float(_surface(x,y,h,p[None,:2])[0]);error=abs(wanted-float(event['native_support_z_m']));point_error=max(point_error,error)
        if error>1e-5:raise ValueError('Actual contact-point support differs from approved terrain')
        if abs(float(event['point_surface_difference_m'])-(p[2]-event['native_support_z_m']))>1e-8:raise ValueError('Contact surface difference identity fails')
        if event['foot'] and loaded:
            positive+=1;force_ids.add(event['robot_geom']);nonflat+=int(event['native_support_z_m']>.001)
            upward+=int(event['native_support_z_m']>.001 and force[2]>1e-6)
    for key,wanted in [('actual_positive_foot_terrain_contacts',positive),('positive_foot_contact_on_nonflat',nonflat)]:
        if key in result and int(result[key])!=wanted:raise ValueError(f'Native contact aggregate mismatch: {key}')
    build=result.get('physical_build',{})
    if build and (build.get('entities')!=2 or build.get('robot_dofs')!=18 or build.get('ground_only') is not True):raise ValueError('Scene must contain exactly one native Terrain and one actual Go2')
    for key in ('actor_unchanged','optimizer_unchanged','checkpoint_file_unchanged'):
        if result.get(key) is not True:raise ValueError(f'Fixed-model/no-training evidence missing or false: {key}')
    check=run/'terrain-physics-check.json';native_check=json.loads(check.read_text()) if check.exists() else None
    if native_check and (native_check['integer_heightfield_max_error']!=0 or max(native_check['metre_readback_max_error_m'],native_check['query_max_error_m'])>1e-5):raise ValueError('Native heightfield integer/metre/query audit failed')
    return {'status':'PASS','mode':mode,'policy_evaluation':bool(result.get('policy_evaluation')),
        'contact_probe_is_not_locomotion_or_standing_acceptance':mode=='pd_contact_probe',
        'physical_state_rows':len(states),'control_rows':len(controls),'physics_dt_s':dt,'control_dt_s':.02,
        'all_saved_state_control_contact_values_finite':True,'independent_URDF_FK_max_errors_m':fk_errors,
        'foot_native_support_max_errors_m':support_errors,'foot_radius_identity_max_errors_m':radius_errors,
        'foot_clearance_identity_max_errors_m':clearance_errors,'contact_count':len(contacts),
        'actual_positive_force_foot_terrain_contacts':positive,'positive_force_foot_contacts_above_1mm':nonflat,
        'upward_loaded_foot_contacts_above_1mm':upward,'loaded_native_foot_geom_ids':sorted(force_ids),
        'contact_native_support_max_error_m':point_error,'native_terrain_readback':native_check,
        'actor_optimizer_checkpoint_unchanged':True,'scene_one_native_terrain_one_actual_Go2':bool(build),
        'all_native_evaluator_environment_frozen_source_hashes_verified':True,
        'native_camera_current_X_marker_matches_actual_physics_base_positions':True,
        'installed_actual_Go2_URDF_sha256_verified':True,
        'numeric_gate_definitions_changed':False,'recording_initial_state_time_s':float(times[0]),
        'source_sha256':{p.name:sha(p) for p in (run/'states.csv',run/'controls.csv',run/'contacts.jsonl')}}


def _project(points,K,E):
    camera=(np.c_[points,np.ones(len(points))]@E.T)[:,:3]
    output=np.full((len(points),2),np.nan);positive=camera[:,2]>1e-9
    pixels=camera@K.T;output[positive]=pixels[positive,:2]/pixels[positive,2,None]
    return output


def verify_world_ticks(record,tolerance=1e-5):
    """Recompute projected metric geometry rather than trust saved pixel claims."""
    K=np.asarray(record['intrinsics'],dtype=float);E=np.asarray(record['extrinsics'],dtype=float)
    maximum=0.
    for tick in record['world_ticks']:
        world=np.asarray(tick['world_xyz_m'],dtype=float)[None]
        expected=_project(world,K,E)[0];top=_project(world+[0,0,.015],K,E)[0]
        visible=np.isfinite(expected).all() and np.isfinite(top).all()
        if not visible:
            if tick['native_pixel_xy'] is not None:raise ValueError('Behind-camera tick claims finite native pixels')
            continue
        for key,want in [('native_pixel_xy',expected),('native_tick_top_xy',top),('annotated_pixel_xy',expected*1.3+[224,70])]:
            if tick.get(key) is None:raise ValueError(f'Visible world tick lacks {key}')
            actual=np.asarray(tick[key],dtype=float)
            if actual.shape!=(2,) or not np.isfinite(actual).all():raise ValueError('Invalid recorded tick pixels')
            error=float(np.max(abs(actual-want)));maximum=max(maximum,error)
            if error>tolerance:raise ValueError(f'World-distance tick projection changed: {key} error={error}')
    return maximum


def audit_terrain(media,approved_npz=APPROVED_NPZ):
    media=Path(media);metadata=json.loads((media/'recording-metadata.json').read_text())
    if sha(approved_npz)!=APPROVED_SHA:raise ValueError('Approved source NPZ SHA256 mismatch')
    with np.load(approved_npz,allow_pickle=False) as source:
        sx,sy,original=(source[key].copy() for key in ('x_m','y_m','z_m'))
    with np.load(media/'terrain-input.npz',allow_pickle=False) as saved:
        x,y,height=(saved[key].copy() for key in ('x','y','height_m'))
    if height.shape!=(len(x),len(y)) or height.shape!=(161,53):raise ValueError('Native terrain array is not X rows / Y columns 161x53')
    np.testing.assert_allclose(x,sx,rtol=0,atol=1e-12);np.testing.assert_allclose(y,sy,rtol=0,atol=1e-12)
    quantized=np.rint(original/.001)*.001
    np.testing.assert_allclose(height,quantized,rtol=0,atol=1e-8)
    if metadata['terrain_array_order']!='height_m[x_index,y_index]':raise ValueError('Recorded native terrain axis order changed')
    if sha(media/'terrain-input.npz')!=metadata['terrain_input_sha256']:raise ValueError('Captured terrain input changed')
    if sha(media/'viridis-lut.npy')!=metadata['viridis_lut_sha256']:raise ValueError('Frozen viridis LUT changed')
    np.testing.assert_allclose(metadata['absolute_world_z_color_range_m'],[0,.20],rtol=0,atol=0)
    from matplotlib import colormaps
    wanted=np.rint(colormaps['viridis'](np.arange(256)/255)[:,:3]*255).astype(np.uint8)
    np.testing.assert_array_equal(np.load(media/'viridis-lut.npy',allow_pickle=False),wanted)
    profile=np.array([np.interp(0,y,row) for row in height])
    exaggeration=float(metadata['section_vertical_display_exaggeration'])
    if exaggeration<=0 or abs(metadata['section_z_pixels_per_metre']/metadata['section_x_pixels_per_metre']-exaggeration)>1e-10:
        raise ValueError('Section vertical exaggeration disclosure differs from its calibration')
    if profile.min()<metadata['section_world_z_display_m'][0]-1e-9 or profile.max()>metadata['section_world_z_display_m'][1]+1e-9:
        raise ValueError('Saved section display range clips the actual Y=0 profile')
    return {'approved_npz':str(Path(approved_npz).resolve()),'approved_sha256':APPROVED_SHA,
        'native_axis_order':'X rows / Y columns','grid_shape':list(height.shape),
        'original_to_quantized_max_error_m':float(np.max(abs(original-height))),
        'captured_to_expected_quantized_max_error_m':float(np.max(abs(height-quantized))),
        'original_height_range_m':[float(original.min()),float(original.max())],
        'captured_height_range_m':[float(height.min()),float(height.max())],
        'absolute_viridis_range_m':[0,.20],'viridis_lut_verified':True,
        'section_vertical_exaggeration_verified':exaggeration,'y0_profile_range_m':[float(profile.min()),float(profile.max())]},x,profile


def _verify_calibration(record):
    K=np.asarray(record['intrinsics'],dtype=float);E=np.asarray(record['extrinsics'],dtype=float)
    if K.shape!=(3,3) or E.shape!=(4,4) or not np.isfinite(K).all() or not np.isfinite(E).all():raise ValueError('Invalid native camera matrices')
    R=E[:3,:3];np.testing.assert_allclose(R@R.T,np.eye(3),rtol=0,atol=1e-4)
    np.testing.assert_allclose(E[3],[0,0,0,1],rtol=0,atol=1e-7)
    if abs(np.linalg.det(R)-1)>1e-4:raise ValueError('Native camera extrinsics are not a rigid transform')
    if record['view']=='side':
        side=abs(E[2,0])<1e-5 and abs(E[2,2])<1e-5 and abs(abs(E[2,1])-1)<1e-5
        upright=abs(E[1,0])<1e-5 and abs(E[1,1])<1e-5 and abs(E[1,2]+1)<1e-5
        if not side or not upright or record.get('true_90_side') is not True:raise ValueError('Side camera is not actual upright 90-degree side')
    expected_f=180/np.tan(np.deg2rad(float(record['fov_deg'])/2))
    np.testing.assert_allclose([K[0,0],K[1,1]],[expected_f,expected_f],rtol=2e-5,atol=1e-5)
    np.testing.assert_allclose([K[0,2],K[1,2]],[320,180],rtol=0,atol=1e-5)


def audit_media(run,approved_npz=APPROVED_NPZ):
    """Audit ONE completed run; no physics result schema is required for media QA."""
    run=Path(run);media=run/'native-media';metadata=json.loads((media/'recording-metadata.json').read_text())
    terrain,x,profile=audit_terrain(media,approved_npz)
    if sha(media/'source/rolling_uneven_media.py')!=metadata['source_sha256']:raise ValueError('Frozen native recorder source differs from metadata')
    if metadata['pose_replay'] or metadata['interpolated_poses'] or metadata['new_physics_steps_by_recorder']!=0:raise ValueError('Recording is not direct native camera capture')
    with (media/'frame-map.csv').open() as handle:rows=list(csv.DictReader(handle))
    calibrations=[json.loads(line) for line in (media/'camera-frame-map.jsonl').read_text().splitlines()]
    counts={view:0 for view in VIEWS};max_tick_error=0.;side_count=0
    tick_x=np.arange(np.ceil(x[0]*2)/2,x[-1]+1e-9,.5)
    for row,record in zip(rows,calibrations,strict=True):
        frame=int(row['frame']);view=row['view']
        if view not in counts or frame!=counts[view]:raise ValueError('Native frame sequence is not contiguous per view')
        if record['view']!=view or int(record['frame'])!=frame:raise ValueError('Camera calibration/frame identity differs')
        for key in ('simulation_time_s','video_pts_s'):
            if abs(float(row[key])-frame/25)>1e-6 or abs(float(record[key])-float(row[key]))>1e-6:raise ValueError('Native frame timestamp/PTS mismatch')
        np.testing.assert_allclose([float(row[k]) for k in ('base_x_m','base_y_m','base_z_m')],record['base_position_m'],rtol=0,atol=1e-7)
        if sha(row['raw_png'])!=row['raw_png_sha256'] or record['raw_png_sha256']!=row['raw_png_sha256']:raise ValueError('Native raw PNG/calibration hash mismatch')
        with Image.open(row['raw_png']) as image:
            if image.size!=(640,360) or image.mode!='RGB':raise ValueError('Raw native image is not unchanged RGB640x360')
        _verify_calibration(record);max_tick_error=max(max_tick_error,verify_world_ticks(record))
        points=np.asarray([tick['world_xyz_m'] for tick in record['world_ticks']])
        np.testing.assert_allclose(points[:,0],tick_x,rtol=0,atol=1e-9)
        np.testing.assert_allclose(points[:,1],0,rtol=0,atol=1e-12)
        np.testing.assert_allclose(points[:,2],np.interp(tick_x,x,profile)+.002,rtol=0,atol=1e-9)
        counts[view]+=1;side_count+=int(view=='side')
    if not rows or len(set(counts.values()))!=1 or list(counts.values())[0]!=metadata['frames_per_view']:raise ValueError('Native camera frame counts differ')
    if metadata['true_90_side_frames_verified']!=side_count:raise ValueError('Reported true-side frame count differs from actual matrices')
    movies={}
    for view,count in counts.items():
        for suffix in ('','-raw'):
            path=media/f'native-{view}{suffix}.mp4';info=inspect_video(path,decode=True)
            if info['frames']!=count:raise ValueError('Full decoded movie count differs from native raw frames')
            movies[path.name]=info
    result=json.loads((run/'result.json').read_text()) if (run/'result.json').exists() else {}
    try:physics=audit_physics(run,result)
    except Exception as exc:physics={'status':'FAIL','audit_error':repr(exc),'audit_traceback':traceback.format_exc()}
    return {'run':str(run.resolve()),'media_integrity_status':'PASS',**decision_layers(result),
        'terrain_source':terrain,'raw_png_count':len(rows),'frames_per_view':counts,'all_videos_fully_decoded':True,
        'all_raw_hashes_verified':True,'all_frame_times_and_pts_exact_25fps':True,
        'all_per_frame_camera_matrices_verified':True,'actual_true_90_side_frames':side_count,
        'world_tick_max_projection_error_pixels':max_tick_error,'world_ticks_sample_actual_y0_heights':True,
        'frozen_recorder_source_verified':True,'movies':movies,
        'physics_analysis_status':physics['status'],'physics_analysis':physics,
        'source_sha256':{name:sha(media/name) for name in ('recording-metadata.json','frame-map.csv','camera-frame-map.jsonl','terrain-input.npz','viridis-lut.npy')}}


def audit_all(run_root,output,approved_npz=APPROVED_NPZ):
    run_root,output=Path(run_root),Path(output)
    if output.exists():raise FileExistsError(output)
    runs={}
    for run in sorted(p for p in run_root.iterdir() if p.is_dir()):
        try:
            runs[run.name]=audit_media(run,approved_npz);print(f'Full rolling native audit PASS: {run.name}',flush=True)
        except Exception as exc:
            result=json.loads((run/'result.json').read_text()) if (run/'result.json').exists() else {}
            runs[run.name]={'media_integrity_status':'FAIL',**decision_layers(result),
                'audit_error':repr(exc),'audit_traceback':traceback.format_exc()}
            print(f'Rolling native audit FAIL: {run.name}: {exc}',flush=True)
    passed=bool(runs) and all(run['media_integrity_status']=='PASS' for run in runs.values())
    physics_status='FAIL' if any(run.get('physics_analysis_status')=='FAIL' for run in runs.values()) else (
        'PASS' if runs and all(run.get('physics_analysis_status')=='PASS' for run in runs.values()) else 'UNASSESSED')
    audit={'kind':'independent approved-terrain native recording audit','media_integrity_status':'PASS' if passed else 'FAIL',
        'physics_evidence_status':physics_status,
        'audit_script_sha256':sha(Path(__file__)),'new_native_simulations':0,'new_native_rendering':False,
        'runs':runs,'fully_decoded_video_count':sum(len(run.get('movies',{})) for run in runs.values()),
        'verified_raw_png_count':sum(run.get('raw_png_count',0) for run in runs.values()),
        'verdict_note':'Media PASS verifies recording integrity and approved terrain input; it does not establish environment or model numeric PASS.'}
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(audit,indent=2,allow_nan=False)+'\n')
    return audit


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-root',required=True,type=Path);parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--approved-npz',type=Path,default=APPROVED_NPZ)
    args=parser.parse_args();report=audit_all(args.run_root,args.output,args.approved_npz)
    raise SystemExit(0 if report['media_integrity_status']=='PASS' and report['physics_evidence_status']!='FAIL' else 2)
