"""Isolated new native full-course run; historical20s evaluator stays immutable."""
import argparse,copy,csv,json,math,pickle,shutil,time,traceback
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
import torch,genesis as gs
from scipy.spatial.transform import Rotation
from rsl_rl.runners import OnPolicyRunner
from genesis.utils.misc import qd_to_torch
from genesis.utils.geom import inv_quat,transform_by_quat
from .rolling_approved_source import verify_heightfield,extend_flat_runout
from .rolling_uneven_terrain import surface_height,save_audit
from .rolling_uneven_media import RollingUnevenRecorder
from .cpu_parallel_benchmark import Monitor,digest,system
from .video_materials import sha,csvout
from .standing_metrics import tilt_degrees
from .natural_metrics import assess,point_velocity
from .stage1_flat import torque_setup
from .go2_kinematics import Go2Kinematics
from .evaluation_status import enforce_substep_safety
from .course_completion import CourseTracker,historical_reference,summarize_safety,outside_course_boundary
from .course_media import CourseRecorder,camera_poses,show_gate_in_native_camera,final_capture

class CourseStop(Exception):
    """Stop immediately after the measured terminal native substep."""
    pass

ROOT=Path(__file__).resolve().parents[2]
PARENT=ROOT/'logs/mixed-d/mixed128-lane-v3/policy_final.pt'
EXPECTED='5d7fa7222067ff915942f2be546f9a9b3dcd6126b07eb3d7c8ea7fb4c05a4565'
SOURCE=ROOT/'assets/approved/heightfield.npz'
LEGS=('FL','FR','RL','RR')
def dump(p,a):Path(p).write_text(json.dumps(a,indent=2,allow_nan=False)+'\n')

def terrain_audit(ground,t,run):
    raw=np.asarray(ground.geoms[0].metadata['height_field']);readback=ground.terrain_hf
    if hasattr(readback,'cpu'):readback=readback.cpu().numpy()
    r={'integer_heightfield_max_error':float(np.max(abs(raw-t['height_mm']))),'metre_readback_max_error_m':float(np.max(abs(np.asarray(readback)-t['height_m'])))}
    X,Y=np.meshgrid(t['x'],t['y'],indexing='ij')
    points=np.concatenate([np.column_stack([X.ravel(),Y.ravel()])]+[np.column_stack([(X[:-1,:-1]+u*.05).ravel(),(Y[:-1,:-1]+v*.05).ravel()]) for u,v in ((.2,.3),(.8,.7))]).astype(np.float32)
    native=ground.get_terrain_height(torch.tensor(points,device=gs.device)).reshape(-1).cpu().numpy();expected=surface_height(t,np.clip(points[:,0],float(t['x'][0]),float(t['x'][-1])),np.clip(points[:,1],-1.3,1.3))
    if not np.isfinite(np.r_[native,expected]).all():raise FloatingPointError('Nonfinite terrain audit')
    error=native-expected;r.update(query_points=len(points),query_max_error_m=float(abs(error).max()),native_terrain_class=type(ground).__name__,origin_m=[-1,-1.3,0],horizontal_scale_m=.05,vertical_scale_m=.001)
    if r['integer_heightfield_max_error']!=0 or max(r['metre_readback_max_error_m'],r['query_max_error_m'])>1e-5:raise ValueError('Native source/query mismatch')
    csvout(run/'terrain-readback.csv',[dict(x_m=float(p[0]),y_m=float(p[1]),expected_z_m=float(e),native_z_m=float(n),difference_m=float(d)) for p,e,n,d in zip(points,expected,native,error)])
    # Numerical slopes use the same finite-difference convention as the source.
    gx,gy=np.gradient(np.asarray(readback),t['x'],t['y'],edge_order=2);s=np.rad2deg(np.arctan(np.hypot(gx,gy)));sx,sy=np.gradient(t['original_height_m'],t['x'],t['y'],edge_order=2);original=np.rad2deg(np.arctan(np.hypot(sx,sy)))
    r['quantization_slope_max_difference_deg']=float(abs(s-original).max())
    csvout(run/'terrain-slopes.csv',[dict(x_m=float(x),y_m=float(y),original_slope_deg=float(a),quantized_native_slope_deg=float(b),difference_deg=float(b-a)) for x,y,a,b in zip(X.ravel(),Y.ravel(),original.ravel(),s.ravel())]);dump(run/'terrain-physics-check.json',r);return r

def run(a):
    t=verify_heightfield(a.source);assert sha(PARENT)==EXPECTED
    from .rolling_native_env import QualityEnv
    run=ROOT/'logs/course-native'/a.name;run.mkdir(parents=True,exist_ok=False)
    original_t=copy.deepcopy(t)
    active=np.flatnonzero(np.max(t['height_m'],axis=1)>0);finish=float(t['x'][active[-1]+1])
    assert abs(finish-6.4)<1e-8
    runout_end=getattr(a,'runout_end_x',None)
    if runout_end is not None:
        if a.kind!='ROLLING_UNEVEN':raise ValueError('Runout extension is only for the finite uneven course')
        t=extend_flat_runout(t,runout_end)
    terrain_end=float(t['x'][-1])
    paired=getattr(a,'paired',False);post_goal=getattr(a,'post_goal_seconds',3.) if paired else 0.
    tracker=CourseTracker(finish_x=finish,confirmation_s=0. if a.raw_only or paired else .2,post_goal_s=post_goal)
    old_reference=historical_reference(json.loads((ROOT/'reports/issue3-results.json').read_text()),a.kind,a.condition)
    if a.kind=='FLAT':
        t=copy.deepcopy(t);t['height_mm']=np.zeros_like(t['height_mm']);t['height_m']=np.zeros_like(t['height_m']);t['original_height_m']=np.zeros_like(t['original_height_m']);t['metadata']['kind']='FLAT'
    goal_config=dict(finish_x_m=finish,approved_last_nonzero_x_m=float(original_t['x'][active[-1]]),first_flat_exit_x_m=finish,terrain_x_bounds=None if a.kind=='FLAT' else [-1,terrain_end],runout_extension=t['metadata'].get('runout_extension'),foot_test='native sphere centre X minus radius > finish',confirmation_s=tracker.confirmation,max_sim_s=60.,stall_window_s=6.,stall_progress_m=.1,raw_only=a.raw_only)
    goal_config.update(paired_standard=paired,post_goal_recording_s=post_goal,post_goal_safety_observations='logged, no early cut; engine/state/resource/wall errors still stop' if paired else None)
    dump(run/'course-config.json',goal_config)
    t['provenance']={'label':'NEW NATIVE FULL COURSE / '+a.kind+' / D13550','source_sha256':t['metadata']['source_sha256']}
    save_audit(t,run);source=run/'source';source.mkdir()
    for module in (ROOT/'src/go2_ppo').glob('*.py'):
        shutil.copy2(module,source/module.name)
    for name in ('stage2-uneven.json','natural-gait.json'):shutil.copy2(ROOT/'configs'/name,source/name)
    started=time.monotonic();monitor=Monitor();monitor.begin();rec=None;runner=None;solver=None;original_step=None;actor0=opt0=None;control=None;names=[];cameras={}
    rows=[];controls=[];contacts=[];current=0.;step_times=[];subcount=0;fallen=False;outside=False
    result={'started_at_utc':datetime.now(timezone.utc).isoformat(),'run_id':a.name,'status':'initializing','mode':'new_native_course_completion','approved_source':True,'source_sha256':t['metadata']['source_sha256'],'robot_count':1,'policy_evaluation':True,'learning_performed':False,'heldout':False,'checkpoint_sha256':EXPECTED,'args':vars(a),'evaluation_kind':a.kind,'course_config':goal_config,'PPO_updates':0,'start_x_m':0.,'old_20s_gates_redefined':False,'historical_c2_numeric_pass':True,'visual_gate_F':'requires user review of all three native videos','source_sha256s':{p.name:sha(p) for p in source.iterdir()}}
    dump(run/'result.json',result)
    result.update(historical_numeric_pass=old_reference['numeric_pass'],historical_condition=a.condition,historical_reference_source='reports/issue3-results.json',historical_reference_sha256=sha(ROOT/'reports/issue3-results.json'))
    try:
        with (PARENT.parent/'cfgs.pkl').open('rb') as f:ec,oc,rc,cc,tc=copy.deepcopy(pickle.load(f))
        protocol=json.loads((ROOT/'configs/natural-gait.json').read_text());s2=json.loads((ROOT/'configs/stage2-uneven.json').read_text());condition=protocol['initial_conditions'][a.condition]
        ec.update(episode_length_s=60.02,retest_substeps=a.substeps,termination_if_roll_greater_than=45.,termination_if_pitch_greater_than=45.,joint_target_margin_rad=.12,enforce_urdf_torques=True,clip_joint_targets_to_urdf=True)
        rc['reward_scales']={};cc.update(lin_vel_x_range=[.25,.25],lin_vel_y_range=[0.,0.],ang_vel_range=[0.,0.])
        if a.kind=='FLAT':ec['surface_kind']='FLAT'
        gs.init(backend=gs.cpu,precision='32',seed=condition['seed'],logging_level='warning')
        build=time.monotonic();env=QualityEnv(1,ec,oc,rc,cc,terrain=t if a.kind!='FLAT' else None,record=True,auto_reset=False)
        if a.kind=='FLAT':
            def flat_height(xy):
                xy=torch.as_tensor(xy,device=gs.device);return torch.zeros(xy.shape[:-1],device=gs.device)
            env.ground.get_terrain_height=flat_height
        result['build_seconds']=time.monotonic()-build
        solver=env.scene.rigid_solver;robot=env.robot;indices=env.motors_dof_idx.tolist();names=ec['joint_names'];ground=env.ground
        assert robot.dof_start==0 and robot.n_dofs==18
        control=torque_setup(env,ec,gs);assert control['kp_readback']==[20.]*12;assert control['kd_readback']==[1. if n=='RL_calf_joint' else .5 for n in names]
        control['native_joint_limits_readback_rad']=[v.tolist() for v in robot.get_dofs_limit(indices)]
        result['native_foot_geometry']={leg:{'geom_id':g.idx,'link_name':g.link.name,'link_id':g.link.idx,'sphere_radius_m':float(g.data[0])} for leg,g in env.foot_geoms.items()}
        native_vertices=ground.get_verts().reshape(-1,3).cpu().numpy();np.savez_compressed(run/'native-terrain-vertices.npz',vertices_world_m=native_vertices)
        result['native_terrain_vertices_count']=len(native_vertices)
        result['terrain_audit']=terrain_audit(ground,t,run) if a.kind!='FLAT' else {'analytic_plane_z_m':0.,'class':type(ground).__name__};result['physical_build']={'entities':len(solver.entities),'robot_urdf_sha256':sha(Path(gs.__file__).parent/'assets/urdf/go2/urdf/go2.urdf'),'sim':env.scene.options.sim.model_dump(mode='json'),'rigid':env.scene.options.rigid.model_dump(mode='json'),'robot_dofs':int(robot.n_dofs),'ground_collision_geoms':[g.idx for g in ground.geoms],'ground_only':len(solver.entities)==2,'substep_dt_s':float(solver._substep_dt)}
        if len(solver.entities)!=2:raise ValueError('Expected exactly one Terrain and one Go2; no underlaid ground')
        dump(run/'config.json',{'effective_cfgs':[ec,oc,rc,cc,tc],'condition':condition,'old_uneven_protocol':s2,'flat_reference_protocol':protocol,'control':control,'terrain':t['metadata']})
        # Native debug visual lines are not collision entities.
        entities_before=len(solver.entities);marker_nodes=[]
        for gx,color in ((0.,(0.,.9,.3,1.)),(finish,(1.,.1,.1,1.))):
            ys=np.linspace(-1.23,1.23,51);zs=surface_height(t,np.full(len(ys),gx),ys)+.004
            for i in range(len(ys)-1):marker_nodes.append(show_gate_in_native_camera(env.scene.draw_debug_line((gx,float(ys[i]),float(zs[i])),(gx,float(ys[i+1]),float(zs[i+1])),radius=.004,color=color)))
        assert len(solver.entities)==entities_before==2
        result['visual_gates']={'native_debug_segments':len(marker_nodes),'camera_visible_external_visual_meshes':sum(not node.is_marker for node in marker_nodes),'collision_entities_before':entities_before,'collision_entities_after':len(solver.entities),'no_collision_entities_added':True,'start_x_m':0.,'finish_x_m':finish}
        runner=OnPolicyRunner(env,copy.deepcopy(tc),str(run/'inference-only'),device=gs.device);runner.load(str(PARENT));policy=runner.get_inference_policy(device=gs.device)
        actor0=digest(runner.alg.actor.state_dict());opt0=digest(runner.alg.optimizer.state_dict())
        cameras={'side':env.side_camera,'oblique':env.camera,'overhead':env.overhead_camera};rec=CourseRecorder(run/'native-media',t)
        feet=env.foot_geoms;footids={g.idx:leg for leg,g in feet.items()};robotids={g.idx:g.link.name for g in robot.geoms};groundids={g.idx for g in ground.geoms};kin=Go2Kinematics();dt=env.dt/a.substeps;targets=env.default_dof_pos[0].cpu().numpy() if env.default_dof_pos.ndim==2 else env.default_dof_pos.cpu().numpy()
        initial_x=0.;limitarray=np.array([control['joint_limits_rad'][n] for n in names])
        def measure(tm):
            nonlocal current,fallen,outside
            current=tm;p=robot.get_pos()[0].cpu().numpy();quat=robot.get_quat()[0].cpu().numpy();vel=robot.get_vel()[0].cpu().numpy();q=robot.get_dofs_position(indices)[0].cpu().numpy();qv=robot.get_dofs_velocity(indices)[0].cpu().numpy();tau=robot.get_dofs_control_force(indices)[0].cpu().numpy();applied=qd_to_torch(solver.dyn_state.dofs.qf_applied,transpose=True,copy=True)[0,indices].cpu().numpy()
            if not np.isfinite(np.r_[p,quat,vel,q,qv,tau,applied,targets]).all():raise FloatingPointError('Nonfinite robot state/control')
            roll,pitch=tilt_degrees(quat);outside_now=outside_course_boundary(a.kind,p,terrain_x_end=terrain_end);outside|=outside_now;support=float(ground.get_terrain_height(torch.tensor(np.clip(p[:2],[-1,-1.3],[terrain_end,1.3]),device=gs.device)).reshape(-1)[0]);isfall=p[2]-support<s2['minimum_base_clearance_m'] or max(abs(roll),abs(pitch))>s2['fall_angle_deg'];fallen|=bool(isfall)
            row={'time_s':tm,'x_m':float(p[0]),'y_m':float(p[1]),'height_m':float(p[2]),'distance_m':float(p[0]-initial_x),'roll_deg':roll,'pitch_deg':pitch,'ground_height_m':support,'base_clearance_m':float(p[2]-support),'world_vx_m_s':float(vel[0]),'fallen':bool(isfall or outside_now),'physical_fallen':bool(isfall),'out_of_terrain':bool(outside_now),'unexpected_floor_contact':False,'quaternion_wxyz':json.dumps(quat.tolist())}
            for i,n in enumerate(names):
                for suffix,value in (('position_rad',q[i]),('velocity_rad_s',qv[i]),('control_Nm',tau[i]),('qf_applied_Nm',applied[i]),('target_rad',targets[i])):row[n+'_'+suffix]=float(value)
            contact=robot.get_contacts();pairs={leg:[] for leg in LEGS};loaded={leg:[] for leg in LEGS};valid=contact['valid_mask'].reshape(-1).cpu().numpy()
            for a0,b0,point,fa,fb,pen,ok in zip(contact['geom_a'].reshape(-1),contact['geom_b'].reshape(-1),contact['position'].reshape(-1,3),contact['force_a'].reshape(-1,3),contact['force_b'].reshape(-1,3),contact['penetration'].reshape(-1),valid):
                if not ok:continue
                ga,gb=int(a0),int(b0);me,other=(ga,gb) if ga in robotids else (gb,ga)
                if other not in groundids or me not in robotids:continue
                pt=point.cpu().numpy();force=(fa if me==ga else fb).cpu().numpy();leg=footids.get(me);positive=bool(np.linalg.norm(force)>1e-6);z=float(ground.get_terrain_height(torch.tensor(np.clip(pt[:2],[-1,-1.3],[terrain_end,1.3]),device=gs.device)).reshape(-1)[0])
                if not np.isfinite(np.r_[pt,force,float(pen),z]).all():raise FloatingPointError('Nonfinite contact')
                contacts.append({'time_s':tm,'contact_geometry_time_s':max(0,tm-dt),'robot_geom':me,'terrain_geom':other,'part':leg or robotids[me],'foot':leg is not None,'positive_force':positive,'position_m':pt.tolist(),'force_on_robot_N':force.tolist(),'penetration_m':float(pen),'native_support_z_m':z,'point_surface_difference_m':float(pt[2]-z)})
                if leg:pairs[leg].append(pt);loaded[leg].append(positive)
                else:row['unexpected_floor_contact']=True
            origins=robot.get_links_pos()[0].cpu().numpy();lv=robot.get_links_vel()[0].cpu().numpy();omega=robot.get_links_ang()[0].cpu().numpy();rot=Rotation.from_quat(quat[[1,2,3,0]])
            for leg,g in feet.items():
                center=g.get_pos()[0].cpu().numpy();idx=g.link.idx-robot.link_start;vpoint=point_velocity(lv[idx],omega[idx],center-origins[idx]);speeds=[math.hypot(*point_velocity(lv[idx],omega[idx],pt-origins[idx])[:2]) for pt in pairs[leg]];foutside=outside_course_boundary(a.kind,center,foot=True,terrain_x_end=terrain_end);row['out_of_terrain']|=foutside;row['fallen']|=foutside
                height=float(ground.get_terrain_height(torch.tensor(np.clip(center[:2],[-1,-1.3],[terrain_end,1.3]),device=gs.device)).reshape(-1)[0]);bottom=float(center[2]-float(g.data[0]));fq=[q[names.index(leg+'_'+j+'_joint')] for j in ('hip','thigh','calf')];fk=rot.apply(kin.fk(leg,fq))+p
                row.update({leg+'_contact':bool(pairs[leg]),leg+'_positive_force_contact':any(loaded[leg]),leg+'_clearance_m':bottom-height,leg+'_terrain_height_m':height,leg+'_bottom_z_m':bottom,leg+'_slip_m_s':float(np.mean(speeds)) if speeds else 0.,leg+'_center_speed_m_s':math.hypot(*vpoint[:2]),leg+'_FK_error_m':float(np.linalg.norm(fk-center))})
                row[leg+'_sphere_radius_m']=float(g.data[0])
                for i,axis in enumerate('xyz'):row[leg+'_center_'+axis+'_m']=float(center[i])
            fallen|=row['fallen'];outside|=row['out_of_terrain']
            row['max_joint_excursion_rad']=float(np.maximum(np.maximum(limitarray[:,0]-q,q-limitarray[:,1]),0).max())
            row['engine_error']=bool(solver.get_error_envs_mask().any())
            rows.append(row)
            tracker.update(row)
            if abs(tm*25-round(tm*25))<1e-7 or tracker.reason!='RUNNING':
                for view,pose in camera_poses(p).items():cameras[view].set_pose(**pose)
                rec.capture(cameras,tm,row,terminal=tracker.reason!='RUNNING')
            if tracker.reason!='RUNNING':raise CourseStop(tracker.reason)
            return row
        with torch.inference_mode():
            obs=env.reset();qpos=robot.get_qpos().clone();rr=math.radians(condition['roll_deg'])/2;pp=math.radians(condition['pitch_deg'])/2;qpos[:,1]+=condition['y_m'];qpos[:,3:7]=torch.tensor([math.cos(rr)*math.cos(pp),math.sin(rr)*math.cos(pp),math.cos(rr)*math.sin(pp),-math.sin(rr)*math.sin(pp)],device=gs.device);robot.set_qpos(qpos,zero_velocity=True,skip_forward=False)
            env.base_pos.copy_(robot.get_pos());env.base_quat.copy_(robot.get_quat());env.projected_gravity.copy_(transform_by_quat(env.global_gravity,inv_quat(env.base_quat)));env.dof_pos.copy_(robot.get_dofs_position(indices));env._update_observation();obs=env.get_observations();initial_x=float(robot.get_pos()[0,0]);result['initial_qpos']=robot.get_qpos()[0].tolist();assert tuple(obs['policy'].shape)==(1,45)
            measure(0.);controls.append(rows[-1]);result['recording_started_before_first_physics_step']=True;original_step=solver.substep
            def observed(f):
                nonlocal subcount
                original_step(f);subcount+=1;measure(subcount*dt)
            solver.substep=observed
            for step in range(1,3002):
                if time.monotonic()-started>a.wall_cap:
                    tracker.stop('WALL_TIMEOUT_NOT_REACHED',current);raise CourseStop(tracker.reason)
                if monitor.unsafe:
                    tracker.stop('RESOURCE_LIMIT',current);raise CourseStop(tracker.reason)
                action=policy(obs)
                if not torch.isfinite(action).all():raise FloatingPointError('Nonfinite policy action')
                bounded=torch.maximum(env.action_lower,torch.minimum(action,env.action_upper));executed=env.last_actions if env.simulate_action_latency else bounded;targets=(executed*ec['action_scale']+env.default_dof_pos)[0].cpu().numpy();before=time.monotonic()
                obs,_,_,_=env.step(action);step_times.append(time.monotonic()-before);controls.append(rows[-1])
                if not torch.isfinite(obs['policy']).all():raise FloatingPointError('Nonfinite policy observation')
                if step%100==0:print(json.dumps({'time_s':current,'x_m':rows[-1]['x_m'],'y_m':rows[-1]['y_m'],'min_foot_trailing_x_m':tracker.last['trailing_x_m'],'reason':tracker.reason,'wall_s':time.monotonic()-started}),flush=True)
            if tracker.reason=='RUNNING':tracker.stop('TIMEOUT_NOT_REACHED',current)
    except CourseStop:
        pass
    except Exception as e:
        tracker.stop('STATE_ERROR' if isinstance(e,FloatingPointError) else 'ENGINE_ERROR',current)
        result.update(error=str(e),traceback=traceback.format_exc());print(result['traceback'],flush=True)
    finally:
        if solver is not None and original_step is not None:solver.substep=original_step
        terminal_verified=bool(rows) and abs(float(rows[-1]['time_s'])-current)<1e-8
        try:result['terminal_evidence']=final_capture(rec,cameras,rows,current)
        except Exception as e:result['terminal_recording_error']=repr(e)
        if rec:
            try:rec.close()
            except Exception as e:result['recording_error']=repr(e)
        monitor.stop();csvout(run/'states.csv',rows);csvout(run/'controls.csv',controls);csvout(run/'resources.csv',monitor.rows)
        with (run/'contacts.jsonl').open('w') as f:
            for event in contacts:f.write(json.dumps(event,allow_nan=False)+'\n')
        if runner is not None and actor0 is not None:result.update(actor_unchanged=digest(runner.alg.actor.state_dict())==actor0,optimizer_unchanged=digest(runner.alg.optimizer.state_dict())==opt0)
        completion=tracker.summary()
        safety=summarize_safety(rows,contacts,control,names,terminal_verified=terminal_verified)
        safety['engine_error']=completion['reason'] in ('ENGINE_ERROR','STATE_ERROR')
        result.update(status='COURSE_COMPLETED' if completion['success'] else 'NOT_COMPLETED',completion=completion,new_run_safety=safety,terminal_sim_s=current,distance_m=rows[-1]['distance_m'] if terminal_verified else None,distance_at_last_verified_sample_m=rows[-1]['distance_m'] if rows else None,terminal_base_xyz_m=[rows[-1][k] for k in ('x_m','y_m','height_m')] if terminal_verified else None,wall_seconds=time.monotonic()-started,checkpoint_file_unchanged=sha(PARENT)==EXPECTED,rows=len(rows),control_samples=len(controls),peak_rss_bytes=max((r['process_rss_bytes'] for r in monitor.rows),default=None),step_median_s=float(np.median(step_times)) if step_times else None,step_p95_s=float(np.percentile(step_times,95)) if step_times else None,engine_error=safety['engine_error'],control=control if runner is not None else None)
        dump(run/'result.json',result)
        if rec and rows and terminal_verified and result.get('terminal_evidence',{}).get('terminal_snapshot_verified'):
            try:result['videos']=rec.validate_raw() if a.raw_only else rec.present(result,rows,end_card_frames=0 if paired else 50,standard_subdir='standard-final' if paired else None)
            except Exception as e:result['presentation_error']=repr(e);result['presentation_traceback']=traceback.format_exc();print(result['presentation_traceback'],flush=True)
        elif rec:result['presentation_error']='UNAVAILABLE_TERMINAL_MEASUREMENT; preserved last verified raw frames only'
        result['total_wall_including_media_s']=time.monotonic()-started
        dump(run/'result.json',result);print(json.dumps({k:result.get(k) for k in ('run_id','status','terminal_sim_s','distance_m','new_run_safety','total_wall_including_media_s','presentation_error')}),flush=True)
    return 1 if result.get('presentation_error') or result.get('recording_error') or result.get('terminal_recording_error') or result.get('engine_error') else 0 if completion['success'] else 2

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--name',required=True);p.add_argument('--source',default=str(SOURCE));p.add_argument('--kind',required=True,choices=['FLAT','ROLLING_UNEVEN']);p.add_argument('--condition',type=int,default=2,choices=range(3));p.add_argument('--substeps',type=int,default=2,choices=[2]);p.add_argument('--wall-cap',type=float,default=900.);p.add_argument('--raw-only',action='store_true')
    p.add_argument('--paired',action='store_true',help='same-run raw + standard, no cards, immediate goal plus actual post-goal capture');p.add_argument('--post-goal-seconds',type=float,default=3.)
    p.add_argument('--runout-end-x',type=float,help='append a physical flat exit to the approved uneven heightfield; keep its core and FINISH unchanged')
    args=p.parse_args()
    if args.paired and args.raw_only:p.error('--paired and --raw-only are mutually exclusive')
    torch.set_num_threads(4);raise SystemExit(run(args))
