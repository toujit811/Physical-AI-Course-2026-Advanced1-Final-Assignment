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
from .nature_env import Go2Env
from rsl_rl.runners import OnPolicyRunner

ROOT=Path(__file__).resolve().parents[2]
LEGS=("FL","FR","RL","RR")
PROTOCOL=ROOT/"configs/natural-gait.json"
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,obj):Path(p).write_text(json.dumps(obj,indent=2,allow_nan=False))
def make_run(kind,name):
    p=ROOT/"logs/stage1/natural"/kind/name
    p.mkdir(parents=True,exist_ok=False)
    return p
def system_state():
    return {"load_average":os.getloadavg(),"cpu_seconds":time.process_time(),
            "peak_rss_bytes_macos":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "vm_stat":subprocess.run(["vm_stat"],capture_output=True,text=True).stdout,
            "swap":subprocess.run(["sysctl","vm.swapusage"],capture_output=True,text=True).stdout}
def provenance(run,args):
    sources=[Path(__file__),ROOT/"src/go2_ppo/nature_env.py",ROOT/"src/go2_ppo/natural_metrics.py",ROOT/"src/go2_ppo/natural_rewards.py",
             ROOT/"src/go2_ppo/stage1_flat.py",ROOT/"src/go2_ppo/standing_metrics.py",PROTOCOL]
    folder=run/"source";folder.mkdir()
    for s in sources:shutil.copy2(s,folder/s.name)
    return {"run_id":run.name,"timestamp_jst":datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat(),
            "stage":1,"terrain":"FLAT","algorithm":"PPO","backend":"cpu",
            "platform":platform.platform(),"machine":platform.machine(),"processor":platform.processor(),
            "python":sys.version,"versions":{p:importlib.metadata.version(p) for p in ("torch","genesis-world","rsl-rl-lib","numpy","tensorboard")},
            "source_sha256":{str(s.relative_to(ROOT)):sha(s) for s in sources},
            "git_status":subprocess.run(["git","status","--short","--branch"],cwd=ROOT,capture_output=True,text=True).stdout,
            "command":sys.argv,"arguments":vars(args),"system_before":system_state(),
            "protocol_sha256":sha(PROTOCOL),"observations":45,"actions":12,"control_hz":50,
            "substeps":2,"self_collision":False}

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
    def _reward_foot_clearance(self):
        # No prescribed phase or gait: PPO chooses which legs to swing and when.
        if not hasattr(self,"foot_geoms"):self.foot_geoms=feet(self.robot)
        h=torch.stack([g.get_pos()[:,2]-float(g.data[0]) for g in self.foot_geoms.values()],dim=1)
        target=self.reward_cfg["clearance_target_m"]
        return (torch.exp(-torch.square((h-target)/.02))*(h>.004)).sum(dim=1)
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
    checkpoint=Path(args.checkpoint).resolve();initial_sha=sha(checkpoint)
    cfg=json.loads(PROTOCOL.read_text());condition=cfg["initial_conditions"][args.condition]
    report.update(checkpoint=str(checkpoint),checkpoint_sha256=initial_sha,condition=condition,
                  initial_frame_saved_before_physics=False,status="initializing")
    dump(run/"provenance.json",report)
    try:
        env_cfg,obs_cfg,reward_cfg,command_cfg,train_cfg=load_cfg(checkpoint)
        reward_cfg["reward_scales"]={}
        env_cfg["episode_length_s"]=cfg["duration_s"]
        for axis in ("roll","pitch"):env_cfg["termination_if_"+axis+"_greater_than"]=cfg["fall_angle_deg"]
        command_cfg["lin_vel_x_range"]=[cfg["command_velocity_m_s"]]*2
        gs.init(backend=gs.cpu,precision="32",seed=condition["seed"],logging_level="warning")
        env=QualityEnv(1,env_cfg,obs_cfg,reward_cfg,command_cfg,auto_reset=False,record=True)
        control=torque_setup(env,env_cfg,gs); foot=env.foot_geoms
        dump(run/"config.json",{"protocol":cfg,"effective_cfgs":[env_cfg,obs_cfg,reward_cfg,command_cfg,train_cfg],
              "condition":condition,"control_audit":control,"training":False,
              "feet":{k:{"geom_idx":g.idx,"link_idx":g.link.idx,"link_name":g.link.name,"radius_m":float(g.data[0])} for k,g in foot.items()},
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
            recorder=StandardRecorder(run,None,None);writers=recorder.writers
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
            def measure(t,targets):
                p=env.robot.get_pos()[0].tolist();vel=env.robot.get_vel()[0].tolist()
                quat=env.robot.get_quat()[0].tolist();roll,pitch=tilt_degrees(quat)
                row={"time_s":t,"x_m":p[0],"y_m":p[1],"height_m":p[2],"distance_m":p[0]-x0,
                     "roll_deg":roll,"pitch_deg":pitch,"quaternion_wxyz":json.dumps(quat),"world_vx_m_s":vel[0],
                     "command_vx_m_s":.25,"unexpected_floor_contact":False,
                     "fallen":p[2]<cfg["minimum_base_height_m"] or max(abs(roll),abs(pitch))>cfg["fall_angle_deg"]}
                q=env.robot.get_dofs_position(indices)[0].tolist();qd=env.robot.get_dofs_velocity(indices)[0].tolist()
                tau=env.robot.get_dofs_control_force(indices)[0].tolist()
                for i,n in enumerate(names):
                    row[n+"_position_rad"]=q[i];row[n+"_velocity_rad_s"]=qd[i];row[n+"_control_Nm"]=tau[i];row[n+"_target_rad"]=targets[i]
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
                for step in range(1,int(cfg["duration_s"]/env.dt)+1):
                    actions=policy(obs)
                    if not torch.isfinite(actions).all():raise FloatingPointError("nonfinite policy")
                    executed=env.last_actions if env.simulate_action_latency else torch.maximum(env.action_lower,torch.minimum(actions,env.action_upper))
                    targets=(executed*env_cfg["action_scale"]+env.default_dof_pos)[0].tolist()
                    obs,_,_,_=env.step(actions)
                    if step%2==0:frame()
                    row=measure(step*env.dt,targets);rows.append(row);table.writerow(row);f.flush()
                    if bool(env.engine_errors.any()):raise RuntimeError("physics engine error")
                    if row["fallen"]:break
            metrics=assess(rows,cfg,control)
            report.update(metrics,status="numeric-pass-visual-pending" if metrics["numeric_pass"] else "failed",
                          frames_per_video=frames,samples=len(rows),initial_state_qpos=qpos[0].tolist())
    except BaseException as e:
        report.update(status="error",error_type=type(e).__name__,error=str(e))
        (run/"error.txt").write_text(traceback.format_exc());traceback.print_exc()
    finally:
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

def train(args):
    run=make_run("training",args.name);report=provenance(run,args);started=time.monotonic()
    checkpoint=Path(args.checkpoint).resolve()
    env_cfg,obs_cfg,reward_cfg,command_cfg,train_cfg=load_cfg(checkpoint)
    env_cfg.update(joint_target_margin_rad=args.margin,enforce_urdf_torques=True,clip_joint_targets_to_urdf=True)
    reward_cfg["clearance_target_m"]=args.clearance_target
    reward_cfg["reward_scales"]["foot_clearance"]=args.clearance_weight
    if args.slip_weight:reward_cfg["reward_scales"]["stance_slip"]=-args.slip_weight
    command_cfg["lin_vel_x_range"]=[.25,.25]
    train_cfg.update(save_interval=250,run_name=args.name)
    cfgs=[env_cfg,obs_cfg,reward_cfg,command_cfg,train_cfg]
    dump(run/"configs.json",cfgs)
    with (run/"cfgs.pkl").open("wb") as f:pickle.dump(cfgs,f)
    report.update(parent_checkpoint=str(checkpoint),parent_sha256=sha(checkpoint),seed=args.seed,num_envs=args.num_envs,
                  iterations=args.iterations,total_env_steps=args.iterations*args.num_envs*24,
                  rollout_steps=24,rollout_batch=args.num_envs*24,minibatch_size=args.num_envs*24//4,
                  gradient_updates=args.iterations*5*4,missing_metrics={"KL":"PPO internal adaptive KL not returned by rsl_rl5.0",
                  "clip_fraction":"not returned by rsl_rl5.0","training_stance_slip":"measured exactly in separate recorded eval, not all training envs",
                  "training_swing_success":"measured in recorded eval; per-iteration foot height is only a final-step batch snapshot"})
    dump(run/"provenance.json",report)
    try:
        gs.init(backend=gs.cpu,precision="32",seed=args.seed,logging_level="warning")
        env=QualityEnv(args.num_envs,env_cfg,obs_cfg,copy.deepcopy(reward_cfg),command_cfg)
        report["control_audit"]=torque_setup(env,env_cfg,gs)
        runner=OnPolicyRunner(env,copy.deepcopy(train_cfg),str(run),device=gs.device);runner.load(str(checkpoint))
        original=runner.logger.log;history=[]
        def log_iteration(**kw):
            row={k:kw[k] for k in ("it","collect_time","learn_time","learning_rate")}
            row.update({k:float(v) for k,v in kw["loss_dict"].items()})
            row["action_std"]=kw["action_std"].mean().item()
            row["batch_speed_rmse_m_s"]=torch.square(env.base_lin_vel[:,0]-.25).mean().sqrt().item()
            row["batch_height_std_m"]=env.base_pos[:,2].std().item()
            row["batch_done_fraction"]=env.reset_buf.float().mean().item()
            row["batch_foot_clearance_mean_m"]=torch.stack([g.get_pos()[:,2]-float(g.data[0]) for g in env.foot_geoms.values()]).mean().item()
            row["peak_rss_bytes_macos"]=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            row["load_average_1min"]=os.getloadavg()[0]
            if not all(math.isfinite(float(v)) for v in row.values()):raise FloatingPointError("nonfinite PPO metrics")
            history.append(row)
            with (run/"iteration-metrics.jsonl").open("a") as f:f.write(json.dumps(row)+"\n")
            original(**kw)
        runner.logger.log=log_iteration
        begin=runner.current_learning_iteration
        runner.learn(num_learning_iterations=args.iterations,init_at_random_ep_len=True)
        model=run/f"model_{runner.current_learning_iteration}.pt"
        report.update(status="trained_not_evaluated",checkpoint=str(model.relative_to(ROOT)),checkpoint_sha256=sha(model),
                      start_iteration=begin,end_iteration=runner.current_learning_iteration,
                      collection_seconds=sum(r["collect_time"] for r in history),update_seconds=sum(r["learn_time"] for r in history))
        if runner.logger.writer:runner.logger.writer.flush()
    except BaseException as e:
        report.update(status="error",error_type=type(e).__name__,error=str(e))
        (run/"error.txt").write_text(traceback.format_exc());raise
    finally:
        report.update(wall_seconds=time.monotonic()-started,system_after=system_state(),parent_hash_unchanged=sha(checkpoint)==report["parent_sha256"])
        dump(run/"provenance.json",report);print(json.dumps(report),flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("mode",choices=("eval","eval-set","train"))
    p.add_argument("--name",required=True);p.add_argument("--checkpoint",required=True)
    p.add_argument("--condition",type=int,choices=(0,1,2),default=0)
    p.add_argument("--seed",type=int,default=3101);p.add_argument("--num-envs",type=int,default=64)
    p.add_argument("--iterations",type=int,default=1500);p.add_argument("--margin",type=float,default=.06)
    p.add_argument("--clearance-target",type=float,default=.04);p.add_argument("--clearance-weight",type=float,default=.5)
    p.add_argument("--slip-weight",type=float,default=0.)
    args=p.parse_args()
    if args.mode=="eval":return evaluate(args)
    if args.mode=="train":train(args);return 0
    group=make_run("evaluation-sets",args.name);results=[]
    for condition in range(3):
        name=args.name+f"-c{condition}"
        command=[sys.executable,__file__,"eval","--name",name,"--checkpoint",args.checkpoint,"--condition",str(condition)]
        with (group/f"c{condition}.log").open("w") as out:
            result=subprocess.run(command,stdout=out,stderr=subprocess.STDOUT)
        resultfile=ROOT/"logs/stage1/natural/evaluations"/name/"result.json"
        results.append(json.loads(resultfile.read_text()) if resultfile.exists() else {"status":"process_error","returncode":result.returncode})
        print(name,results[-1]["status"],results[-1].get("numeric_gates"),flush=True)
    dump(group/"results.json",results)
    numeric=all(r.get("numeric_pass",False) for r in results)
    dump(group/"summary.json",{"numeric_all_three_pass":numeric,"visual_gate":"unreviewed","gate_G_distinct_initial_qpos":len({json.dumps(r.get("initial_state_qpos")) for r in results})==3,
                            "status":"FAIL" if not numeric else "PENDING_VISUAL_REVIEW"})
    return 0 if numeric else 1
if __name__=="__main__":raise SystemExit(main())
