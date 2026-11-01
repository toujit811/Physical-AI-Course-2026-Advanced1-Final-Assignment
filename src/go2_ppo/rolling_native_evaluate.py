"""Read-only model6500 baseline on SHA-verified rolling Terrain; no learning or heldout."""
import argparse,copy,csv,json,math,pickle,shutil,time,traceback
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
import torch,genesis as gs
from scipy.spatial.transform import Rotation
from rsl_rl.runners import OnPolicyRunner
from genesis.utils.misc import qd_to_torch
from genesis.utils.geom import inv_quat,transform_by_quat
from .rolling_approved_source import verify_heightfield
from .rolling_uneven_terrain import surface_height,save_audit
from .rolling_uneven_media import RollingUnevenRecorder
from .cpu_parallel_benchmark import Monitor,digest,system
from .video_materials import sha,csvout
from .standing_metrics import tilt_degrees
from .natural_metrics import assess,point_velocity
from .stage1_flat import torque_setup
from .go2_kinematics import Go2Kinematics
from .evaluation_status import enforce_substep_safety

ROOT=Path(__file__).resolve().parents[2]
PARENT=ROOT/'logs/stage1/natural/training/slip20-margin012-64x1500/model_6500.pt'
EXPECTED='c9bd93aa103db4e892623babff4de5c8da2cc7c0af5e31bcca389836738c0a2c'
SOURCE=ROOT/'reports/rolling-native-20261101/original-package/physicaai_uneven_preview/heightfield.npz'
LEGS=('FL','FR','RL','RR')
def dump(p,a):Path(p).write_text(json.dumps(a,indent=2,allow_nan=False)+'\n')

def terrain_audit(ground,t,run):
    raw=np.asarray(ground.geoms[0].metadata['height_field']);readback=ground.terrain_hf
    if hasattr(readback,'cpu'):readback=readback.cpu().numpy()
    r={'integer_heightfield_max_error':float(np.max(abs(raw-t['height_mm']))),'metre_readback_max_error_m':float(np.max(abs(np.asarray(readback)-t['height_m'])))}
    X,Y=np.meshgrid(t['x'],t['y'],indexing='ij')
    points=np.concatenate([np.column_stack([X.ravel(),Y.ravel()])]+[np.column_stack([(X[:-1,:-1]+u*.05).ravel(),(Y[:-1,:-1]+v*.05).ravel()]) for u,v in ((.2,.3),(.8,.7))]).astype(np.float32)
    native=ground.get_terrain_height(torch.tensor(points,device=gs.device)).reshape(-1).cpu().numpy();expected=surface_height(t,np.clip(points[:,0],-1,7),np.clip(points[:,1],-1.3,1.3))
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
    run=ROOT/'logs/rolling-native'/a.name;run.mkdir(parents=True,exist_ok=False)
    t['provenance']={'label':getattr(a,'recording_label','APPROVED ROLLING UNEVEN / LIVE Go2 / FIXED MODEL6500'),'source_sha256':t['metadata']['source_sha256']}
    save_audit(t,run);source=run/'source';source.mkdir()
    for module in (ROOT/'src/go2_ppo').glob('*.py'):
        shutil.copy2(module,source/module.name)
    for name in ('stage2-uneven.json','natural-gait.json'):shutil.copy2(ROOT/'configs'/name,source/name)
    started=time.monotonic();monitor=Monitor();monitor.begin();rec=None;runner=None;solver=None;original_step=None;actor0=opt0=None
    rows=[];controls=[];contacts=[];current=0.;step_times=[];subcount=0;fallen=False;outside=False
    result={'started_at_utc':datetime.now(timezone.utc).isoformat(),'run_id':a.name,'status':'initializing','mode':'pd_contact_probe' if a.pd_contact_probe else 'fixed_policy6500_baseline','approved_source':True,'source_sha256':t['metadata']['source_sha256'],'robot_count':1,'policy_evaluation':not a.pd_contact_probe,'learning_performed':False,'heldout':False,'checkpoint_sha256':EXPECTED,'args':vars(a),'visual_gate_F':'requires user review of all three native videos','source_sha256s':{p.name:sha(p) for p in source.iterdir()}}
    dump(run/'result.json',result)
    try:
        with (PARENT.parent/'cfgs.pkl').open('rb') as f:ec,oc,rc,cc,tc=copy.deepcopy(pickle.load(f))
        protocol=json.loads((ROOT/'configs/natural-gait.json').read_text());s2=json.loads((ROOT/'configs/stage2-uneven.json').read_text());condition=protocol['initial_conditions'][a.condition]
        ec.update(episode_length_s=a.duration,retest_substeps=a.substeps,termination_if_roll_greater_than=45.,termination_if_pitch_greater_than=45.,joint_target_margin_rad=.12,enforce_urdf_torques=True,clip_joint_targets_to_urdf=True)
        rc['reward_scales']={};cc.update(lin_vel_x_range=[.25,.25],lin_vel_y_range=[0.,0.],ang_vel_range=[0.,0.])
        if a.pd_contact_probe:
            if a.probe_x is None:raise ValueError('Explicit probe X required; never reinterpret probe placement as locomotion')
            ec['base_init_pos']=[a.probe_x,a.probe_y,float(surface_height(t,a.probe_x,a.probe_y))+.42]
            t['provenance']['label']='APPROVED TERRAIN / LIVE Go2 PD CONTACT PROBE / NO POLICY ROLLOUT'
        gs.init(backend=gs.cpu,precision='32',seed=condition['seed'],logging_level='warning')
        build=time.monotonic();env=QualityEnv(1,ec,oc,rc,cc,terrain=t,record=True,auto_reset=False);result['build_seconds']=time.monotonic()-build
        solver=env.scene.rigid_solver;robot=env.robot;indices=env.motors_dof_idx.tolist();names=ec['joint_names'];ground=env.ground
        assert robot.dof_start==0 and robot.n_dofs==18
        control=torque_setup(env,ec,gs);assert control['kp_readback']==[20.]*12;assert control['kd_readback']==[1. if n=='RL_calf_joint' else .5 for n in names]
        control['native_joint_limits_readback_rad']=[v.tolist() for v in robot.get_dofs_limit(indices)]
        result['native_foot_geometry']={leg:{'geom_id':g.idx,'link_name':g.link.name,'link_id':g.link.idx,'sphere_radius_m':float(g.data[0])} for leg,g in env.foot_geoms.items()}
        native_vertices=ground.get_verts().reshape(-1,3).cpu().numpy();np.savez_compressed(run/'native-terrain-vertices.npz',vertices_world_m=native_vertices)
        result['native_terrain_vertices_count']=len(native_vertices)
        result['terrain_audit']=terrain_audit(ground,t,run);result['physical_build']={'entities':len(solver.entities),'robot_urdf_sha256':sha(Path(gs.__file__).parent/'assets/urdf/go2/urdf/go2.urdf'),'sim':env.scene.options.sim.model_dump(mode='json'),'rigid':env.scene.options.rigid.model_dump(mode='json'),'robot_dofs':int(robot.n_dofs),'ground_collision_geoms':[g.idx for g in ground.geoms],'ground_only':len(solver.entities)==2,'substep_dt_s':float(solver._substep_dt)}
        if len(solver.entities)!=2:raise ValueError('Expected exactly one Terrain and one Go2; no underlaid ground')
        dump(run/'config.json',{'effective_cfgs':[ec,oc,rc,cc,tc],'condition':condition,'old_uneven_protocol':s2,'flat_reference_protocol':protocol,'control':control,'terrain':t['metadata']})
        runner=OnPolicyRunner(env,copy.deepcopy(tc),str(run/'inference-only'),device=gs.device);runner.load(str(PARENT));policy=runner.get_inference_policy(device=gs.device)
        actor0=digest(runner.alg.actor.state_dict());opt0=digest(runner.alg.optimizer.state_dict())
        cameras={'side':env.side_camera,'oblique':env.camera,'overhead':env.overhead_camera};rec=RollingUnevenRecorder(run/'native-media',t)
        feet=env.foot_geoms;footids={g.idx:leg for leg,g in feet.items()};robotids={g.idx:g.link.name for g in robot.geoms};groundids={g.idx for g in ground.geoms};kin=Go2Kinematics();dt=env.dt/a.substeps;targets=env.default_dof_pos[0].cpu().numpy() if env.default_dof_pos.ndim==2 else env.default_dof_pos.cpu().numpy()
        initial_x=0.;limitarray=np.array([control['joint_limits_rad'][n] for n in names])
        def measure(tm):
            nonlocal current,fallen,outside
            current=tm;p=robot.get_pos()[0].cpu().numpy();quat=robot.get_quat()[0].cpu().numpy();vel=robot.get_vel()[0].cpu().numpy();q=robot.get_dofs_position(indices)[0].cpu().numpy();qv=robot.get_dofs_velocity(indices)[0].cpu().numpy();tau=robot.get_dofs_control_force(indices)[0].cpu().numpy();applied=qd_to_torch(solver.dyn_state.dofs.qf_applied,transpose=True,copy=True)[0,indices].cpu().numpy()
            if not np.isfinite(np.r_[p,quat,vel,q,qv,tau,applied,targets]).all():raise FloatingPointError('Nonfinite robot state/control')
            roll,pitch=tilt_degrees(quat);outside_now=env.ground_data is not None and not(-.95<p[0]<6.95 and -1.25<p[1]<1.25);outside|=outside_now;support=float(ground.get_terrain_height(torch.tensor(np.clip(p[:2],[-1,-1.3],[7,1.3]),device=gs.device)).reshape(-1)[0]);isfall=p[2]-support<s2['minimum_base_clearance_m'] or max(abs(roll),abs(pitch))>s2['fall_angle_deg'];fallen|=bool(isfall)
            row={'time_s':tm,'x_m':float(p[0]),'y_m':float(p[1]),'height_m':float(p[2]),'distance_m':float(p[0]-initial_x),'roll_deg':roll,'pitch_deg':pitch,'ground_height_m':support,'base_clearance_m':float(p[2]-support),'world_vx_m_s':float(vel[0]),'fallen':bool(isfall or outside_now),'physical_fallen':bool(isfall),'out_of_terrain':bool(outside_now),'unexpected_floor_contact':False,'quaternion_wxyz':json.dumps(quat.tolist())}
            for i,n in enumerate(names):
                for suffix,value in (('position_rad',q[i]),('velocity_rad_s',qv[i]),('control_Nm',tau[i]),('qf_applied_Nm',applied[i]),('target_rad',targets[i])):row[n+'_'+suffix]=float(value)
            contact=robot.get_contacts();pairs={leg:[] for leg in LEGS};loaded={leg:[] for leg in LEGS};valid=contact['valid_mask'].reshape(-1).cpu().numpy()
            for a0,b0,point,fa,fb,pen,ok in zip(contact['geom_a'].reshape(-1),contact['geom_b'].reshape(-1),contact['position'].reshape(-1,3),contact['force_a'].reshape(-1,3),contact['force_b'].reshape(-1,3),contact['penetration'].reshape(-1),valid):
                if not ok:continue
                ga,gb=int(a0),int(b0);me,other=(ga,gb) if ga in robotids else (gb,ga)
                if other not in groundids or me not in robotids:continue
                pt=point.cpu().numpy();force=(fa if me==ga else fb).cpu().numpy();leg=footids.get(me);positive=bool(np.linalg.norm(force)>1e-6);z=float(ground.get_terrain_height(torch.tensor(np.clip(pt[:2],[-1,-1.3],[7,1.3]),device=gs.device)).reshape(-1)[0])
                if not np.isfinite(np.r_[pt,force,float(pen),z]).all():raise FloatingPointError('Nonfinite contact')
                contacts.append({'time_s':tm,'contact_geometry_time_s':max(0,tm-dt),'robot_geom':me,'terrain_geom':other,'part':leg or robotids[me],'foot':leg is not None,'positive_force':positive,'position_m':pt.tolist(),'force_on_robot_N':force.tolist(),'penetration_m':float(pen),'native_support_z_m':z,'point_surface_difference_m':float(pt[2]-z)})
                if leg:pairs[leg].append(pt);loaded[leg].append(positive)
                else:row['unexpected_floor_contact']=True
            origins=robot.get_links_pos()[0].cpu().numpy();lv=robot.get_links_vel()[0].cpu().numpy();omega=robot.get_links_ang()[0].cpu().numpy();rot=Rotation.from_quat(quat[[1,2,3,0]])
            for leg,g in feet.items():
                center=g.get_pos()[0].cpu().numpy();idx=g.link.idx-robot.link_start;vpoint=point_velocity(lv[idx],omega[idx],center-origins[idx]);speeds=[math.hypot(*point_velocity(lv[idx],omega[idx],pt-origins[idx])[:2]) for pt in pairs[leg]];foutside=env.ground_data is not None and not(-1<=center[0]<=7 and -1.3<=center[1]<=1.3);row['out_of_terrain']|=foutside;row['fallen']|=foutside
                height=float(ground.get_terrain_height(torch.tensor(np.clip(center[:2],[-1,-1.3],[7,1.3]),device=gs.device)).reshape(-1)[0]);bottom=float(center[2]-float(g.data[0]));fq=[q[names.index(leg+'_'+j+'_joint')] for j in ('hip','thigh','calf')];fk=rot.apply(kin.fk(leg,fq))+p
                row.update({leg+'_contact':bool(pairs[leg]),leg+'_positive_force_contact':any(loaded[leg]),leg+'_clearance_m':bottom-height,leg+'_terrain_height_m':height,leg+'_bottom_z_m':bottom,leg+'_slip_m_s':float(np.mean(speeds)) if speeds else 0.,leg+'_center_speed_m_s':math.hypot(*vpoint[:2]),leg+'_FK_error_m':float(np.linalg.norm(fk-center))})
                for i,axis in enumerate('xyz'):row[leg+'_center_'+axis+'_m']=float(center[i])
            fallen|=row['fallen'];outside|=row['out_of_terrain']
            row['max_joint_excursion_rad']=float(np.maximum(np.maximum(limitarray[:,0]-q,q-limitarray[:,1]),0).max());rows.append(row)
            if abs(tm*25-round(tm*25))<1e-7:
                cameras['side'].set_pose(pos=(p[0]+.2,-3.,.32),lookat=(p[0]+.2,0.,.32),up=(0,0,1));cameras['oblique'].set_pose(pos=(p[0]+1.1,p[1]-1.7,1.12),lookat=(p[0]+.25,p[1],.20));cameras['overhead'].set_pose(pos=(p[0]+.5,0,5.),lookat=(p[0]+.5,0,0),up=(0,1,0));rec.append(cameras,tm,p)
            return row
        with torch.inference_mode():
            obs=env.reset();qpos=robot.get_qpos().clone();rr=math.radians(condition['roll_deg'])/2;pp=math.radians(condition['pitch_deg'])/2;qpos[:,1]+=condition['y_m'];qpos[:,3:7]=torch.tensor([math.cos(rr)*math.cos(pp),math.sin(rr)*math.cos(pp),math.cos(rr)*math.sin(pp),-math.sin(rr)*math.sin(pp)],device=gs.device);robot.set_qpos(qpos,zero_velocity=True,skip_forward=False)
            env.base_pos.copy_(robot.get_pos());env.base_quat.copy_(robot.get_quat());env.projected_gravity.copy_(transform_by_quat(env.global_gravity,inv_quat(env.base_quat)));env.dof_pos.copy_(robot.get_dofs_position(indices));env._update_observation();obs=env.get_observations();initial_x=float(robot.get_pos()[0,0]);result['initial_qpos']=robot.get_qpos()[0].tolist();assert tuple(obs['policy'].shape)==(1,45)
            measure(0.);controls.append(rows[-1]);result['recording_started_before_first_physics_step']=True;original_step=solver.substep
            def observed(f):
                nonlocal subcount
                original_step(f);subcount+=1;measure(subcount*dt)
            solver.substep=observed
            for step in range(1,round(a.duration/.02)+1):
                if fallen or outside:break
                if time.monotonic()-started>a.wall_cap:raise TimeoutError('Run wall cap')
                if monitor.unsafe:raise RuntimeError(monitor.unsafe)
                action=torch.zeros_like(env.actions) if a.pd_contact_probe else policy(obs)
                if not torch.isfinite(action).all():raise FloatingPointError('Nonfinite policy action')
                bounded=torch.maximum(env.action_lower,torch.minimum(action,env.action_upper));executed=env.last_actions if env.simulate_action_latency else bounded;targets=(executed*ec['action_scale']+env.default_dof_pos)[0].cpu().numpy();before=time.monotonic();obs,_,_,_=env.step(action);step_times.append(time.monotonic()-before);controls.append(rows[-1])
                if bool(env.engine_errors.any()):raise RuntimeError('Native solver error')
                if step%50==0:print(json.dumps({'time_s':current,'x_m':rows[-1]['x_m'],'base_clearance_m':rows[-1]['base_clearance_m'],'roll_deg':rows[-1]['roll_deg'],'pitch_deg':rows[-1]['pitch_deg'],'wall_s':time.monotonic()-started}),flush=True)
                if fallen or outside:break
            metrics=enforce_substep_safety(assess(controls,protocol,control),rows);result['flat_formula_reference_not_acceptance']=copy.deepcopy(metrics['numeric_gates']);settled=[r for r in controls if r['time_s']>=2]
            posture=bool(settled) and max(max(abs(r['roll_deg']),abs(r['pitch_deg'])) for r in controls)<=s2['dangerous_tilt_abs_deg'] and all(math.sqrt(np.mean([r[k]**2 for r in settled]))<=s2['dangerous_tilt_rms_deg'] for k in ('roll_deg','pitch_deg'))
            E=metrics['numeric_gates']['E'] and all(r['max_joint_excursion_rad']<=s2['joint_excursion_limit_rad'] for r in rows) and all(max(abs(r[n+'_qf_applied_Nm']) for r in rows)<=control['urdf_effort_limits'][i]+1e-4 for i,n in enumerate(names))
            gates={'progress':metrics['numeric_gates']['A'],'joint_input':bool(E),'posture':bool(posture),'no_abnormal_contact':not any(r['unexpected_floor_contact'] for r in rows)};result.update(metrics);result.update(numeric_gates=gates,numeric_pass=all(gates.values()),status='NUMERIC_PASS_VISUAL_PENDING' if all(gates.values()) else 'TASK_FAIL',environment_status='PASS',control=control,max_substep_joint_excursion_rad=max(r['max_joint_excursion_rad'] for r in rows),max_FK_error_m=max(r[leg+'_FK_error_m'] for r in rows for leg in LEGS),actual_positive_foot_terrain_contacts=sum(e['foot'] and e['positive_force'] for e in contacts),positive_foot_contact_on_nonflat=sum(e['foot'] and e['positive_force'] and e['native_support_z_m']>.001 for e in contacts))
            result['visual_gate_F']='requires user review of all three direct native videos'
            result['termination_reason']=metrics['substep_safety']['termination_reason']
            result['physical_fall_observed']=any(r['physical_fallen'] for r in rows)
            result['positive_foot_contacts_by_leg']={leg:sum(e['part']==leg and e['foot'] and e['positive_force'] for e in contacts) for leg in LEGS}
            if a.pd_contact_probe:
                result.update(status='CONTACT_OBSERVED' if result['actual_positive_foot_terrain_contacts'] else 'CONTACT_UNCONFIRMED',baseline_gate_reference_not_applicable=gates,numeric_gates=None,numeric_pass=None,probe_is_not_locomotion_or_standing_acceptance=True)
    except Exception as e:result.update(status='TIMEOUT' if isinstance(e,TimeoutError) else 'ERROR',reason=str(e),traceback=traceback.format_exc());print(result['traceback'],flush=True)
    finally:
        if solver is not None and original_step is not None:solver.substep=original_step
        if rec:
            try:rec.close()
            except Exception as e:result['recording_error']=repr(e)
        monitor.stop();csvout(run/'states.csv',rows);csvout(run/'controls.csv',controls);csvout(run/'resources.csv',monitor.rows)
        with (run/'contacts.jsonl').open('w') as f:
            for event in contacts:f.write(json.dumps(event,allow_nan=False)+'\n')
        if runner is not None and actor0 is not None:result.update(actor_unchanged=digest(runner.alg.actor.state_dict())==actor0,optimizer_unchanged=digest(runner.alg.optimizer.state_dict())==opt0)
        result.update(terminal_sim_s=current,wall_seconds=time.monotonic()-started,checkpoint_file_unchanged=sha(PARENT)==EXPECTED,rows=len(rows),control_samples=len(controls),peak_rss_bytes=max(r['process_rss_bytes'] for r in monitor.rows),step_median_s=float(np.median(step_times)) if step_times else None,step_p95_s=float(np.percentile(step_times,95)) if step_times else None,engine_error=False if result['status']!='ERROR' else None)
        dump(run/'result.json',result);print(json.dumps({k:result.get(k) for k in ('run_id','status','reason','terminal_sim_s','distance_m','numeric_gates','actual_positive_foot_terrain_contacts','positive_foot_contact_on_nonflat','wall_seconds')}),flush=True)
    return int(result['status']=='ERROR')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--name',required=True);p.add_argument('--source',default=str(SOURCE));p.add_argument('--duration',type=float,default=20.);p.add_argument('--substeps',type=int,default=2);p.add_argument('--condition',type=int,choices=range(3),default=2);p.add_argument('--wall-cap',type=float,default=600);p.add_argument('--pd-contact-probe',action='store_true');p.add_argument('--probe-x',type=float);p.add_argument('--probe-y',type=float,default=0.);raise SystemExit(run(p.parse_args()))
