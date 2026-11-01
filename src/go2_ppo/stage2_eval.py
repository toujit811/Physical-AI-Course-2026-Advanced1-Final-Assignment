"""Stage 1 quality experiments. Existing implementations and artifacts stay immutable."""
import argparse, copy, csv, datetime, hashlib, importlib.metadata, json, math
import os, pickle, platform, resource, shutil, subprocess, sys, time, traceback
from pathlib import Path
import numpy as np
import torch
import genesis as gs
from genesis.utils.geom import inv_quat, transform_by_quat
from .natural_metrics import assess, point_velocity
from .natural_rewards import contact_slip_cost
from .stage1_flat import flat_env_class, torque_setup
from .standing_metrics import tilt_degrees
from .stage2_env import Go2Env
from .stage2_terrain import generate, height_at
from .stage2_boundary import query_points
from rsl_rl.runners import OnPolicyRunner
from genesis.utils.misc import qd_to_torch

ROOT=Path(__file__).resolve().parents[2]
LEGS=("FL","FR","RL","RR")
PROTOCOL=ROOT/"configs/natural-gait.json"
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,obj):Path(p).write_text(json.dumps(obj,indent=2,allow_nan=False))
def make_run(kind,name):
    p=ROOT/"logs/stage2"/kind/name
    p.mkdir(parents=True,exist_ok=False)
    return p
def system_state():
    return {"load_average":os.getloadavg(),"cpu_seconds":time.process_time(),
            "peak_rss_bytes_macos":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "vm_stat":subprocess.run(["vm_stat"],capture_output=True,text=True).stdout,
            "swap":subprocess.run(["sysctl","vm.swapusage"],capture_output=True,text=True).stdout}
def provenance(run,args):
    sources=[Path(__file__),ROOT/"src/go2_ppo/stage2_env.py",ROOT/"src/go2_ppo/stage2_terrain.py",ROOT/"src/go2_ppo/stage2_boundary.py",ROOT/"configs/stage2-uneven.json",ROOT/"src/go2_ppo/natural_metrics.py",ROOT/"src/go2_ppo/natural_rewards.py",
             ROOT/"src/go2_ppo/stage1_flat.py",ROOT/"src/go2_ppo/standing_metrics.py",PROTOCOL]
    folder=run/"source";folder.mkdir()
    for s in sources:shutil.copy2(s,folder/s.name)
    return {"run_id":run.name,"timestamp_jst":datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat(),
            "stage":2,"terrain":args.terrain_kind,"algorithm":"PPO","backend":"cpu",
            "platform":platform.platform(),"machine":platform.machine(),"processor":platform.processor(),
            "python":sys.version,"versions":{p:importlib.metadata.version(p) for p in ("torch","genesis-world","rsl-rl-lib","numpy","tensorboard")},
            "source_sha256":{str(s.relative_to(ROOT)):sha(s) for s in sources},
            "git_status":subprocess.run(["git","status","--short","--branch"],cwd=ROOT,capture_output=True,text=True).stdout,
            "command":sys.argv,"arguments":vars(args),"system_before":system_state(),
            "protocol_sha256":sha(PROTOCOL),"observations":45,"actions":12,"control_hz":50,
            "substeps":args.substeps,"self_collision":False,
            "scope":"diagnostic" if args.duration<20 else "20s evaluation",
            "changes":{"rl_calf_kd":args.rl_kd,"action_latency":not args.no_latency,"physics_substeps":args.substeps},
            "learning_performed":False}

def feet(robot):
    result={}
    for leg in LEGS:
        geoms=[g for g in robot.geoms if g.link.name==leg+"_calf" and g.type==gs.GEOM_TYPE.SPHERE]
        if len(geoms)!=1:raise ValueError(f"{leg}: expected one merged foot sphere, got {len(geoms)}")
        result[leg]=geoms[0]
    return result

class QualityEnv(flat_env_class(Go2Env)):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.foot_geoms=feet(self.robot)
        margin=self.env_cfg.get("joint_target_margin_rad",0.)
        audit=torque_setup(self,self.env_cfg,gs)
        lim=[audit["joint_limits_rad"][n] for n in self.cfg["joint_names"]]
        lower=torch.tensor([x[0]+margin for x in lim],device=self.device)
        upper=torch.tensor([x[1]-margin for x in lim],device=self.device)
        self.action_lower=(lower-self.default_dof_pos)/self.cfg["action_scale"]
        self.action_upper=(upper-self.default_dof_pos)/self.cfg["action_scale"]
        self.robot.set_dofs_kv([1.0],[self.robot.get_joint("RL_calf_joint").dof_start])
    def step(self,actions):
        self._terrain_outside=torch.zeros((self.num_envs,),dtype=torch.bool,device=self.device)
        return super().step(actions)
    def _surface_for_reward(self,xy):
        data=self.ground_data
        bounded,outside=query_points(xy,(float(data["x"][0]),float(data["x"][-1]),float(data["y"][0]),float(data["y"][-1])))
        self._terrain_outside |= outside
        return self.ground.get_terrain_height(bounded)
    def _reward_foot_clearance(self):
        # No prescribed phase or gait: PPO chooses which legs to swing and when.
        if not hasattr(self,"foot_geoms"):self.foot_geoms=feet(self.robot)
        centers=torch.stack([g.get_pos() for g in self.foot_geoms.values()],dim=1)
        surface=self._surface_for_reward(centers[:,:,:2]) if self.ground_data is not None else torch.zeros_like(centers[:,:,2])
        h=centers[:,:,2]-.022-surface
        target=self.reward_cfg["clearance_target_m"]
        return (torch.exp(-torch.square((h-target)/.02))*(h>.004)).sum(dim=1)
    def _reward_base_height(self):
        surface=self._surface_for_reward(self.base_pos[:,:2,None].transpose(1,2)).squeeze(-1) if self.ground_data is not None else 0.
        return torch.square(self.base_pos[:,2]-surface-self.reward_cfg["base_height_target"])
    def _reward_stance_slip(self):
        contact=self.robot.get_contacts(is_padded=True)
        ids=torch.tensor([g.idx for g in self.foot_geoms.values()],device=self.device)
        links=[g.link.idx-self.robot.link_start for g in self.foot_geoms.values()]
        a=contact["geom_a"];b=contact["geom_b"]
        mask=((a[:,:,None]==ids)|(b[:,:,None]==ids)) & contact["valid_mask"][:,:,None]
        mask=mask & ((a<self.robot.geom_start)|(b<self.robot.geom_start))[:,:,None]
        return contact_slip_cost(self.robot.get_links_pos(links),self.robot.get_links_vel(links),
                                 self.robot.get_links_ang(links),contact["position"],mask)

def load_cfg(checkpoint):
    with (checkpoint.parent/"cfgs.pkl").open("rb") as f:return copy.deepcopy(pickle.load(f))

def evaluate(args):
    import imageio.v2 as imageio
    run=make_run("evaluations",args.name)
    report=provenance(run,args);started=time.monotonic();writers={};rows=[];recorder=None
    subrows=[];subfile=None
    checkpoint=Path(args.checkpoint).resolve();initial_sha=sha(checkpoint)
    cfg=json.loads(PROTOCOL.read_text());s2=json.loads((ROOT/"configs/stage2-uneven.json").read_text()); terrain_data=generate(args.terrain_kind,args.terrain_seed,s2)
    condition=(cfg["initial_conditions"]+[{"seed":2104,"roll_deg":.2,"pitch_deg":-.2,"y_m":-.02},{"seed":2105,"roll_deg":-.2,"pitch_deg":-.1,"y_m":.02}])[args.condition]
    report.update(checkpoint=str(checkpoint),checkpoint_sha256=initial_sha,condition=condition,
                  initial_frame_saved_before_physics=False,status="initializing")
    report["terrain_seed"]=args.terrain_seed
    report["stage2_config_sha256"]=sha(ROOT/"configs/stage2-uneven.json")
    report["terrain_height_sha256"]=hashlib.sha256(terrain_data["height_m"].tobytes()).hexdigest()
    np.savez_compressed(run/"terrain.npz",x=terrain_data["x"],y=terrain_data["y"],height_m=terrain_data["height_m"])
    dump(run/"terrain.json",terrain_data["metadata"])
    dump(run/"provenance.json",report)
    try:
        env_cfg,obs_cfg,reward_cfg,command_cfg,train_cfg=load_cfg(checkpoint)
        reward_cfg["reward_scales"]={}
        env_cfg["episode_length_s"]=cfg["duration_s"]
        env_cfg["retest_substeps"]=args.substeps
        for axis in ("roll","pitch"):env_cfg["termination_if_"+axis+"_greater_than"]=cfg["fall_angle_deg"]
        command_cfg["lin_vel_x_range"]=[cfg["command_velocity_m_s"]]*2
        gs.init(backend=gs.cpu,precision="32",seed=condition["seed"],logging_level="warning")
        env=QualityEnv(1,env_cfg,obs_cfg,reward_cfg,command_cfg,auto_reset=False,record=True,terrain=None if args.terrain_kind=="FLAT" else terrain_data)
        env.simulate_action_latency=not args.no_latency
        if args.rl_kd is not None:
            env.robot.set_dofs_kv([args.rl_kd],[env.robot.get_joint("RL_calf_joint").dof_start])
        control=torque_setup(env,env_cfg,gs); foot=env.foot_geoms
        control["simulator_joint_limits_rad"]=[x.tolist() for x in env.robot.get_dofs_limit(env.motors_dof_idx.tolist())]
        if args.terrain_kind!="FLAT":
            points=np.array([[0,0],[.9,.1],[1.7,-.1],[2.8,.05],[3.5,0]],dtype=np.float32)
            native=env.ground.get_terrain_height(points).reshape(-1).cpu().numpy()
            expected=height_at(terrain_data,points[:,0],points[:,1])
            readback_error=float(np.max(np.abs(env.ground.terrain_hf-terrain_data["height_m"])))
            query_error=float(np.max(np.abs(native-expected)))
            if readback_error>1e-6 or query_error>1e-5:raise ValueError("Terrain physics/query mismatch")
            dump(run/"terrain-physics-check.json",{"height_grid_readback_max_error_m":readback_error,"native_query_max_error_m":query_error,
                "points_xy_m":points.tolist(),"native_heights_m":native.tolist(),"collision":True,"visualization":True,
                "ground_entity":type(env.ground).__name__,"rendered_in_initial_frame":True})
        dump(run/"config.json",{"protocol":cfg,"effective_cfgs":[env_cfg,obs_cfg,reward_cfg,command_cfg,train_cfg],
              "condition":condition,"control_audit":control,"training":False,"stage2_protocol":s2,"terrain":terrain_data["metadata"],
              "feet":{k:{"geom_idx":g.idx,"link_idx":g.link.idx,"link_name":g.link.name,"radius_m":float(g.data[0])} for k,g in foot.items()},
              "robot_geoms":[{"idx":g.idx,"link":g.link.name,"type":str(g.type)} for g in env.robot.geoms],
              "foot_contact_source":"actual sphere-plane contact geom IDs, solver contact point and world link twist"})
        runner=OnPolicyRunner(env,copy.deepcopy(train_cfg),str(run),device=gs.device)
        runner.load(str(checkpoint));policy=runner.get_inference_policy(device=gs.device)
        with torch.inference_mode():
            env.reset()
            qpos=env.robot.get_qpos().clone()
            rr=math.radians(condition["roll_deg"])/2;pp=math.radians(condition["pitch_deg"])/2
            quat=[math.cos(rr)*math.cos(pp),math.sin(rr)*math.cos(pp),math.cos(rr)*math.sin(pp),-math.sin(rr)*math.sin(pp)]
            qpos[:,1]+=condition["y_m"];qpos[:,3:7]=torch.tensor(quat,device=gs.device)
            env.robot.set_qpos(qpos,zero_velocity=True,skip_forward=False)
            env.base_pos.copy_(env.robot.get_pos());env.base_quat.copy_(env.robot.get_quat())
            env.projected_gravity.copy_(transform_by_quat(env.global_gravity,inv_quat(env.base_quat)))
            env.dof_pos.copy_(env.robot.get_dofs_position(env.motors_dof_idx));env._update_observation()
            obs=env.get_observations();x0=env.robot.get_pos()[0,0].item()
            from .standard_recording import StandardRecorder,set_recording_cameras
            recorder=StandardRecorder(run,None if args.terrain_kind=="FLAT" else terrain_data,args.terrain_seed if args.terrain_kind!="FLAT" else None);writers=recorder.writers
            frames=0
            def frame():
                nonlocal frames
                p=env.robot.get_pos()[0].tolist()
                cameras={"oblique":env.camera,"side":env.side_camera};set_recording_cameras(cameras,p)
                for view,cam in cameras.items():
                    rgb,*_=cam.render(force_render=True);recorder.append(view,rgb,cam,frames/25,p)
                frames+=1
            frame();report["initial_frame_saved_before_physics"]=True
            names=env_cfg["joint_names"];indices=env.motors_dof_idx.tolist()
            raw_actions=[0.]*12;bounded_actions=[0.]*12;executed_actions=[0.]*12
            current_targets=env.default_dof_pos.tolist()
            subfile=(run/"substeps.csv").open("w")
            subtotal=0;subtable=None
            original_substep=env.scene.rigid_solver.substep
            def observed_substep(f):
                nonlocal subtotal,subtable
                original_substep(f)
                subtotal+=1
                solver=env.scene.rigid_solver
                t=subtotal*env.dt/args.substeps
                q=env.robot.get_dofs_position(indices)[0].tolist()
                qd=env.robot.get_dofs_velocity(indices)[0].tolist()
                pd=env.robot.get_dofs_control_force(indices)[0].tolist()
                applied=qd_to_torch(solver.dyn_state.dofs.qf_applied,transpose=True,copy=True)[0,indices].tolist()
                actuator=solver.get_dofs_actuator_force()[0,indices].tolist()
                internal=env.robot.get_dofs_force(indices)[0].tolist()
                acceleration=env.robot.get_dofs_acc(indices)[0].tolist()
                base=env.robot.get_qpos()[0,:7].tolist()
                rr,pp=tilt_degrees(base[3:7])
                row={"time_s":t,"height_m":base[2],"roll_deg":rr,"pitch_deg":pp}
                for i,n in enumerate(names):
                    row[n+"_position_rad"]=q[i];row[n+"_velocity_rad_s"]=qd[i]
                    row[n+"_target_rad"]=current_targets[i]
                    row[n+"_pd_post_Nm"]=pd[i];row[n+"_qf_applied_Nm"]=applied[i]
                    row[n+"_actuator_output_Nm"]=actuator[i];row[n+"_internal_force_Nm"]=internal[i]
                    row[n+"_acc_rad_s2"]=acceleration[i]
                contact=env.robot.get_contacts()
                ga=contact["geom_a"].reshape(-1).tolist();gb=contact["geom_b"].reshape(-1).tolist()
                pts=contact["position"].reshape(-1,3).tolist();normals=contact["normal"].reshape(-1,3).tolist()
                fa=contact["force_a"].reshape(-1,3).tolist();fb=contact["force_b"].reshape(-1,3).tolist()
                valid=contact["valid_mask"].reshape(-1).tolist()
                entries=[]
                penetrations=contact["penetration"].reshape(-1).tolist()
                for a,b,pt,normal,forcea,forceb,ok,depth in zip(ga,gb,pts,normals,fa,fb,valid,penetrations):
                    if ok:
                        entries.append({"geom_a":a,"geom_b":b,"position":pt,"normal_a_b_raw":normal,
                                        "force_on_robot_N":forcea if a>=env.robot.geom_start else forceb,"penetration_m":depth})
                row["contacts_json"]=json.dumps(entries)
                for leg,g in foot.items():
                    active=[e for e in entries if g.idx in (e["geom_a"],e["geom_b"])]
                    row[leg+"_contact"]=bool(active)
                    row[leg+"_floor_fz_N"]=sum(e["force_on_robot_N"][2] for e in active)
                if not all(math.isfinite(x) for x in q+qd+pd+applied+actuator+internal):
                    raise FloatingPointError("Nonfinite substep state/force")
                if subtable is None:
                    subtable=csv.DictWriter(subfile,fieldnames=list(row));subtable.writeheader()
                subtable.writerow(row);subfile.flush();subrows.append(row)
            env.scene.rigid_solver.substep=observed_substep
            def measure(t,targets):
                p=env.robot.get_pos()[0].tolist();vel=env.robot.get_vel()[0].tolist()
                quat=env.robot.get_quat()[0].tolist();roll,pitch=tilt_degrees(quat)
                row={"time_s":t,"x_m":p[0],"y_m":p[1],"height_m":p[2],"distance_m":p[0]-x0,
                     "roll_deg":roll,"pitch_deg":pitch,"quaternion_wxyz":json.dumps(quat),"world_vx_m_s":vel[0],
                     "command_vx_m_s":.25,"unexpected_floor_contact":False,
                     "fallen":p[2]<cfg["minimum_base_height_m"] or max(abs(roll),abs(pitch))>cfg["fall_angle_deg"]}
                row["ground_height_m"]=float(height_at(terrain_data,p[0],p[1]))
                row["base_clearance_m"]=p[2]-row["ground_height_m"]
                row["fallen"]=row["base_clearance_m"]<s2["minimum_base_clearance_m"] or max(abs(roll),abs(pitch))>s2["fall_angle_deg"]
                row["out_of_terrain"]=not (-.95<p[0]<6.95 and -.95<p[1]<.95) if args.terrain_kind!="FLAT" else False
                row["fallen"]=row["fallen"] or row["out_of_terrain"]
                q=env.robot.get_dofs_position(indices)[0].tolist();qd=env.robot.get_dofs_velocity(indices)[0].tolist()
                tau=env.robot.get_dofs_control_force(indices)[0].tolist()
                for i,n in enumerate(names):
                    row[n+"_position_rad"]=q[i];row[n+"_velocity_rad_s"]=qd[i];row[n+"_control_Nm"]=tau[i];row[n+"_target_rad"]=targets[i]
                    row[n+"_raw_action"]=raw_actions[i];row[n+"_bounded_action"]=bounded_actions[i]
                    row[n+"_executed_action"]=executed_actions[i]
                if not all(math.isfinite(x) for x in p+vel+quat+q+qd+tau+targets):raise FloatingPointError("nonfinite state/target")
                origins=env.robot.get_links_pos()[0].tolist();vlinks=env.robot.get_links_vel()[0].tolist()
                omega=env.robot.get_links_ang()[0].tolist()
                contacts=env.robot.get_contacts(); pairs={leg:[] for leg in LEGS}
                ga=contacts["geom_a"].reshape(-1).tolist();gb=contacts["geom_b"].reshape(-1).tolist()
                pts=contacts["position"].reshape(-1,3).tolist()
                valid=contacts.get("valid_mask",torch.ones_like(contacts["geom_a"],dtype=torch.bool)).reshape(-1).tolist()
                known={g.idx:leg for leg,g in foot.items()}
                for a,b,pt,ok in zip(ga,gb,pts,valid):
                    if not ok:continue
                    if a<env.robot.geom_start:robotgeom=b
                    elif b<env.robot.geom_start:robotgeom=a
                    else:continue
                    if robotgeom in known:pairs[known[robotgeom]].append(pt)
                    else:row["unexpected_floor_contact"]=True
                for leg,g in foot.items():
                    center=g.get_pos()[0].tolist();idx=g.link.idx-env.robot.link_start
                    rcenter=[center[i]-origins[idx][i] for i in range(3)]
                    center_vel=point_velocity(vlinks[idx],omega[idx],rcenter)
                    speeds=[];offsets=[]
                    for pt in pairs[leg]:
                        velocity=point_velocity(vlinks[idx],omega[idx],[pt[i]-origins[idx][i] for i in range(3)])
                        speeds.append(math.hypot(*velocity[:2]));offsets.append(math.dist(pt,center))
                    row[leg+"_contact"]=bool(speeds)
                    row[leg+"_clearance_m"]=center[2]-float(g.data[0])
                    row[leg+"_terrain_height_m"]=float(height_at(terrain_data,center[0],center[1]))
                    outside=args.terrain_kind!="FLAT" and not (-1<=center[0]<=7 and -1<=center[1]<=1)
                    row[leg+"_outside_terrain"]=outside
                    row["out_of_terrain"]=row["out_of_terrain"] or outside
                    row["fallen"]=row["fallen"] or outside
                    row[leg+"_bottom_z_m"]=center[2]-float(g.data[0])
                    row[leg+"_clearance_m"]-=row[leg+"_terrain_height_m"]
                    row[leg+"_slip_m_s"]=sum(speeds)/len(speeds) if speeds else 0.
                    row[leg+"_center_speed_m_s"]=math.hypot(*center_vel[:2])
                    row[leg+"_contact_radius_m"]=sum(offsets)/len(offsets) if offsets else 0.
                    row[leg+"_contact_count"]=len(speeds)
                    row[leg+"_contact_points_json"]=json.dumps(pairs[leg])
                    for i,axis in enumerate("xyz"):
                        row[leg+"_center_"+axis+"_m"]=center[i]
                        row[leg+"_center_v"+axis+"_m_s"]=center_vel[i]
                        row[leg+"_link_"+axis+"_m"]=origins[idx][i]
                        row[leg+"_link_v"+axis+"_m_s"]=vlinks[idx][i]
                        row[leg+"_link_w"+axis+"_rad_s"]=omega[idx][i]
                return row
            rows.append(measure(0,env.default_dof_pos.tolist()))
            with (run/"measurements.csv").open("w") as f:
                table=csv.DictWriter(f,fieldnames=list(rows[0]));table.writeheader();table.writerow(rows[0]);f.flush()
                for step in range(1,int(args.duration/env.dt)+1):
                    actions=policy(obs)
                    if not torch.isfinite(actions).all():raise FloatingPointError("nonfinite policy")
                    raw_actions=actions[0].tolist()
                    bounded_actions=torch.maximum(env.action_lower,torch.minimum(actions,env.action_upper))[0].tolist()
                    executed=env.last_actions if env.simulate_action_latency else torch.maximum(env.action_lower,torch.minimum(actions,env.action_upper))
                    executed_actions=executed[0].tolist()
                    targets=(executed*env_cfg["action_scale"]+env.default_dof_pos)[0].tolist()
                    current_targets=targets
                    obs,_,_,_=env.step(actions)
                    if step%2==0:frame()
                    row=measure(step*env.dt,targets);rows.append(row);table.writerow(row);f.flush()
                    if bool(env.engine_errors.any()):raise RuntimeError("physics engine error")
                    if row["fallen"]:break
            metrics=assess(rows,cfg,control)
            sub_excess={}
            for n,(lo,hi) in control["joint_limits_rad"].items():
                worst=max(subrows,key=lambda r:max(lo-r[n+"_position_rad"],r[n+"_position_rad"]-hi,0.))
                sub_excess[n]={"max_excursion_rad":max(lo-worst[n+"_position_rad"],worst[n+"_position_rad"]-hi,0.),
                               "time_s":worst["time_s"]}
            extended_E=all(v["max_excursion_rad"]<=cfg["actual_joint_excursion_max_rad"] for v in sub_excess.values())
            metrics["control_sample_gates"]=copy.deepcopy(metrics["numeric_gates"])
            metrics["substep_joint_excursions"]=sub_excess
            metrics["substep_E_pass"]=extended_E
            input_peaks={n:max(abs(r[n+"_qf_applied_Nm"]) for r in subrows) for n in names}
            sub_torques_ok=all(input_peaks[n]<=control["urdf_effort_limits"][i]+1e-4 for i,n in enumerate(names))
            metrics["substep_input_torque_max_Nm"]=input_peaks
            metrics["substep_input_torque_pass"]=sub_torques_ok
            metrics["numeric_gates"]["E"]=metrics["numeric_gates"]["E"] and extended_E and sub_torques_ok
            foot_ids={g.idx for g in foot.values()}
            nonfoot_events=[{"time_s":r["time_s"],"contact":e} for r in subrows
                            for e in json.loads(r["contacts_json"])
                            if (e["geom_a"] if e["geom_a"]>=env.robot.geom_start else e["geom_b"]) not in foot_ids]
            metrics["substep_nonfoot_contact_count"]=len(nonfoot_events)
            metrics["substep_nonfoot_contact_events"]=nonfoot_events
            if args.terrain_kind=="FLAT":
                metrics["numeric_gates"]["B"]=metrics["numeric_gates"]["B"] and not nonfoot_events
            metrics["numeric_pass"]=all(metrics["numeric_gates"].values())
            if args.terrain_kind!="FLAT":
                metrics["flat_formula_reference_not_gates"]=metrics["numeric_gates"]
                settled=[r for r in rows if r["time_s"]>=2]
                tilt_ok=bool(settled) and all(max(abs(r["roll_deg"]),abs(r["pitch_deg"]))<=s2["dangerous_tilt_abs_deg"] for r in rows)
                tilt_ok=tilt_ok and all(math.sqrt(sum(r[k]**2 for r in settled)/len(settled))<=s2["dangerous_tilt_rms_deg"] for k in ("roll_deg","pitch_deg"))
                gates={"progress":metrics["numeric_gates"]["A"],"joint_input":metrics["numeric_gates"]["E"],
                       "posture":bool(tilt_ok),"no_abnormal_contact":not nonfoot_events and not any(r["unexpected_floor_contact"] for r in rows)}
                metrics["numeric_gates"]=gates;metrics["numeric_pass"]=all(gates.values())
                metrics["relative_base_height_std_m"]=float(np.std([r["base_clearance_m"] for r in settled])) if settled else None
            report.update(metrics,status="numeric-pass-visual-pending" if metrics["numeric_pass"] else "failed",
                          frames_per_video=frames,samples=len(rows),initial_state_qpos=qpos[0].tolist())
    except BaseException as e:
        report.update(status="error",error_type=type(e).__name__,error=str(e))
        (run/"error.txt").write_text(traceback.format_exc());traceback.print_exc()
    finally:
        if subfile is not None:subfile.close()
        if recorder is not None:recorder.save()
        videos=[]
        for view,writer in writers.items():
            writer.close()
            p=run/(view+"-incomplete.mp4")
            if p.exists():
                final=run/(view+"-"+report["status"]+".mp4");p.rename(final);videos.append(str(final.relative_to(ROOT)))
        report.update(videos=videos,wall_seconds=time.monotonic()-started,system_after=system_state(),
                      policy_hash_unchanged=sha(checkpoint)==initial_sha,protocol_hash_unchanged=sha(PROTOCOL)==report["protocol_sha256"])
        dump(run/"result.json",report)
        print(json.dumps({k:report.get(k) for k in ("run_id","status","numeric_gates","distance_m","error")}),flush=True)
    return 0 if report.get("numeric_pass") else 1

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--name",required=True);p.add_argument("--checkpoint",required=True)
    p.add_argument("--condition",type=int,choices=range(5),default=2)
    p.add_argument("--duration",type=float,default=20.)
    p.add_argument("--substeps",type=int,default=2)
    p.add_argument("--no-latency",action="store_true")
    p.add_argument("--rl-kd",type=float,default=1.0)
    p.add_argument("--terrain-kind",choices=("FLAT","BUMPS","SLOPE","STEPS","COMPOUND"),default="FLAT")
    p.add_argument("--terrain-seed",type=int,default=41001)
    args=p.parse_args()
    raise SystemExit(evaluate(args))
