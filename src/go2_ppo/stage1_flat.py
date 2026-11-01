"""Stage 1 only: immutable-policy FLAT evaluation or flat-ground PPO training."""
import argparse
import copy
import csv
import hashlib
import importlib.metadata
import json
import math
import pickle
import resource
import sys
import time
import traceback
import xml.etree.ElementTree as ET
from pathlib import Path
from .standing_metrics import tilt_degrees
from .walking_metrics import classify

ROOT = Path(__file__).resolve().parents[2]
from .run_paths import create_run_dir


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def flat_env_class(base_class):
    # Keep the shared upstream environment and all other stages untouched.
    class BoundedFlatEnv(base_class):
        def step(self, actions):
            if self.env_cfg.get("clip_joint_targets_to_urdf", False):
                import torch
                if not hasattr(self,"action_lower"):
                    import genesis as gs
                    tree=ET.parse(Path(gs.__file__).parent/"assets/urdf/go2/urdf/go2.urdf").getroot()
                    limits={j.attrib["name"]:j.find("limit").attrib for j in tree.findall("joint")
                            if j.find("limit") is not None}
                    lower=torch.tensor([float(limits[n]["lower"]) for n in self.cfg["joint_names"]],
                                       device=self.device,dtype=self.default_dof_pos.dtype)
                    upper=torch.tensor([float(limits[n]["upper"]) for n in self.cfg["joint_names"]],
                                       device=self.device,dtype=self.default_dof_pos.dtype)
                    self.action_lower=(lower-self.default_dof_pos)/self.cfg["action_scale"]
                    self.action_upper=(upper-self.default_dof_pos)/self.cfg["action_scale"]
                actions=torch.maximum(self.action_lower,torch.minimum(actions,self.action_upper))
            return super().step(actions)
    return BoundedFlatEnv


def torque_setup(env, env_cfg, gs):
    tree = ET.parse(Path(gs.__file__).parent / "assets/urdf/go2/urdf/go2.urdf").getroot()
    joints = {j.attrib["name"]: j for j in tree.findall("joint")}
    indices = env.motors_dof_idx.tolist()
    efforts = [float(joints[n].find("limit").attrib["effort"]) for n in env_cfg["joint_names"]]
    before = [p.tolist() for p in env.robot.get_dofs_force_range(indices)]
    if env_cfg.get("enforce_urdf_torques", False):
        env.robot.set_dofs_force_range([-x for x in efforts], efforts, indices)
    return {"names": env_cfg["joint_names"], "dof_indices": indices,
            "joint_limits_rad": {n: [float(joints[n].find("limit").attrib[k])
                                     for k in ("lower","upper")] for n in env_cfg["joint_names"]},
            "urdf_effort_limits": efforts, "force_ranges_before": before,
            "force_ranges_used": [p.tolist() for p in env.robot.get_dofs_force_range(indices)],
            "kp_readback": env.robot.get_dofs_kp(indices).tolist(),
            "kd_readback": env.robot.get_dofs_kv(indices).tolist()}


def evaluate(args):
    import imageio.v2 as imageio
    import torch
    import genesis as gs
    from rsl_rl.runners import OnPolicyRunner
    from go2_env import Go2Env
    checkpoint = Path(args.checkpoint).resolve()
    cfg = json.loads((ROOT / "configs/stage1-flat.json").read_text())
    run = create_run_dir(ROOT / "logs/stage1/evaluations", args.name)
    report = {"status": "initializing", "seed": args.seed, "policy_sha256": digest(checkpoint),
              "checkpoint": str(checkpoint), "video": None, "physics_steps": 0,
              "initial_frame_saved_before_physics": False, "stage": 1, "terrain": "FLAT"}
    started = time.monotonic()
    rows, writer = [], None
    video = run / "walking-incomplete.mp4"
    try:
        with (checkpoint.parent / "cfgs.pkl").open("rb") as f:
            env_cfg, obs_cfg, reward_cfg, command_cfg, train_cfg = pickle.load(f)
        source_cfgs = copy.deepcopy([env_cfg, obs_cfg, reward_cfg, command_cfg, train_cfg])
        env_cfg["episode_length_s"] = cfg["duration_s"]
        env_cfg["termination_if_roll_greater_than"] = cfg["fall_angle_deg"]
        env_cfg["termination_if_pitch_greater_than"] = cfg["fall_angle_deg"]
        reward_cfg["reward_scales"] = {}
        command_cfg["lin_vel_x_range"] = [cfg["command_velocity_m_s"]]*2
        gs.init(backend=gs.cpu, precision="32", seed=args.seed, logging_level="warning")
        env = flat_env_class(Go2Env)(1, env_cfg, obs_cfg, reward_cfg, command_cfg, auto_reset=False, record=True)
        audit = torque_setup(env, env_cfg, gs)
        runner = OnPolicyRunner(env, copy.deepcopy(train_cfg), str(run), device=gs.device)
        runner.load(str(checkpoint))
        policy = runner.get_inference_policy(device=gs.device)
        (run / "config.json").write_text(json.dumps({
            "protocol": cfg, "source_cfgs": source_cfgs,
            "effective_cfgs": [env_cfg, obs_cfg, reward_cfg, command_cfg, train_cfg],
            "control_audit": audit, "source_sha256": digest(__file__),
            "training": False, "seed":args.seed, "checkpoint_sha256":report["policy_sha256"],
            "observation_dim":45, "action_dim":12, "control_hz":50,
            "camera":"tracking robot, real-time 1x", "contact_proxy":"calf includes merged fixed foot"
        },indent=2))
        with torch.inference_mode():
            obs = env.reset()
            assert tuple(obs["policy"].shape)==(1,45)
            # Forward kinematics refresh only; preserve state before the first physics step.
            env.robot.set_qpos(env.robot.get_qpos(), zero_velocity=False, skip_forward=False)
            x0 = env.robot.get_pos().reshape(-1)[0].item()
            writer = imageio.get_writer(str(video),fps=cfg["fps"],codec="libx264",macro_block_size=2)
            def frame():
                p=env.robot.get_pos().reshape(-1).tolist()
                env.camera.set_pose(pos=(p[0]+1.8,p[1]-1.8,1.0),lookat=(p[0]+.2,p[1],.25))
                rgb,*_=env.camera.render()
                if rgb.ndim==4:
                    rgb=rgb[0]
                writer.append_data(rgb)
            frame()
            report["initial_frame_saved_before_physics"]=True
            frames=1
            names=env_cfg["joint_names"]
            indices=env.motors_dof_idx.tolist()
            calf_links={leg:env.robot.get_link(leg+"_calf") for leg in ("FL","FR","RL","RR")}
            def measure(t, actions, targets):
                p=env.robot.get_pos().reshape(-1).tolist()
                velocity=env.robot.get_vel().reshape(-1).tolist()
                quaternion=env.robot.get_quat().reshape(-1).tolist()
                roll,pitch=tilt_degrees(quaternion)
                w,qx,qy,qz=quaternion
                yaw=math.degrees(math.atan2(2*(w*qz+qx*qy),1-2*(qy*qy+qz*qz)))
                q=env.robot.get_dofs_position(indices).reshape(-1).tolist()
                qd=env.robot.get_dofs_velocity(indices).reshape(-1).tolist()
                motor=env.robot.get_dofs_control_force(indices).reshape(-1).tolist()
                if not all(math.isfinite(x) for x in p+velocity+q+qd+motor+[roll,pitch]):
                    raise FloatingPointError("Non-finite state")
                contact=env.robot.get_contacts()
                a,b=contact["link_a"],contact["link_b"]
                if "valid_mask" in contact:
                    a,b=a[contact["valid_mask"]],b[contact["valid_mask"]]
                touched=set(a.reshape(-1).tolist()+b.reshape(-1).tolist())
                # FLAT has exactly one fixed plane, added before the robot.
                row={"time_s":t,"x_m":p[0],"y_m":p[1],"height_m":p[2],"forward_distance_m":p[0]-x0,
                     "world_vx_m_s":velocity[0],"command_vx_m_s":cfg["command_velocity_m_s"],
                     "tracking_error_m_s":velocity[0]-cfg["command_velocity_m_s"],
                     "roll_deg":roll,"pitch_deg":pitch,"yaw_deg":yaw,
                     "quaternion_wxyz":json.dumps(quaternion),
                     "fallen":p[2]<cfg["minimum_base_height_m"] or max(abs(roll),abs(pitch))>cfg["fall_angle_deg"],
                     "base_floor_contact":env.robot.get_link("base").idx in touched}
                row["fallen"] = row["fallen"] or row["base_floor_contact"]
                for i,n in enumerate(names):
                    row[n+"_position_rad"]=q[i];row[n+"_velocity_rad_s"]=qd[i]
                    row[n+"_control_Nm"]=motor[i];row[n+"_action"]=float(actions[i])
                    row[n+"_target_rad"]=float(targets[i])
                    row[n+"_joint_error_rad"]=float(targets[i])-q[i]
                for leg,link in calf_links.items():
                    row[leg+"_calf_floor_contact"]=link.idx in touched
                    row[leg+"_calf_z_m"]=link.get_pos().reshape(-1)[2].item()
                return row
            rows.append(measure(0,[0]*12,env.default_dof_pos.tolist()))
            with (run/"measurements.csv").open("w") as out:
                table=csv.DictWriter(out,fieldnames=list(rows[0]));table.writeheader();table.writerow(rows[0])
                for step in range(1,1001):
                    actions=policy(obs)
                    if not torch.isfinite(actions).all():
                        raise FloatingPointError("Non-finite policy actions")
                    executed=env.last_actions if env.simulate_action_latency else actions
                    targets=(executed*env_cfg["action_scale"]+env.default_dof_pos).reshape(-1).tolist()
                    obs,rews,dones,extras=env.step(actions)
                    report["physics_steps"]=step
                    if step%2==0:
                        frame();frames+=1
                    row=measure(step*env.dt,actions.reshape(-1).tolist(),targets)
                    rows.append(row);table.writerow(row)
                    if bool(env.engine_errors.any()):
                        raise RuntimeError("Engine error mask")
                    if row["fallen"]:
                        break
        writer.close();writer=None
        end=rows[-1]
        report.update(status=classify(end["time_s"],end["forward_distance_m"],
                      any(r["fallen"] for r in rows),False,cfg),
            elapsed_simulation_s=end["time_s"],distance_m=end["forward_distance_m"],
            mean_speed_m_s=end["forward_distance_m"]/end["time_s"] if end["time_s"] else 0,
            velocity_tracking_rmse_m_s=math.sqrt(sum(r["tracking_error_m_s"]**2 for r in rows)/len(rows)),
            ever_fallen=any(r["fallen"] for r in rows),frames=frames,samples=len(rows),
            max_abs_roll_deg=max(abs(r["roll_deg"]) for r in rows),
            max_abs_pitch_deg=max(abs(r["pitch_deg"]) for r in rows),
            minimum_height_m=min(r["height_m"] for r in rows),
            contact_transitions={leg:sum(rows[i][leg+"_calf_floor_contact"]!=rows[i-1][leg+"_calf_floor_contact"]
                                for i in range(1,len(rows))) for leg in calf_links},
            policy_hash_unchanged=digest(checkpoint)==report["policy_sha256"])
        if not report["policy_hash_unchanged"]:
            raise RuntimeError("Policy checkpoint changed during evaluation")
    except BaseException as error:
        report.update(status="engine_error",error_type=type(error).__name__,error=str(error))
        (run/"error.txt").write_text(traceback.format_exc());traceback.print_exc()
    finally:
        if writer is not None:
            writer.close()
        if video.exists() and video.stat().st_size:
            dest=run/("walking-"+report["status"]+".mp4");video.rename(dest)
            report["video"]=str(dest.relative_to(ROOT))
        report["wall_seconds"]=time.monotonic()-started
        report["run_directory"]=str(run.relative_to(ROOT))
        (run/"result.json").write_text(json.dumps(report,indent=2))
        print(json.dumps(report,indent=2),flush=True)
    return 0 if report["status"]=="passed" else 1


def train(args):
    import torch
    import genesis as gs
    from rsl_rl.runners import OnPolicyRunner
    from go2_env import Go2Env
    from go2_train import get_cfgs,get_train_cfg
    run=create_run_dir(ROOT/"logs/stage1/training",args.name)
    if args.resume:
        with (Path(args.resume).parent/"cfgs.pkl").open("rb") as f:
            env_cfg,obs_cfg,reward_cfg,command_cfg,train_cfg=pickle.load(f)
    else:
        env_cfg,obs_cfg,reward_cfg,command_cfg=get_cfgs()
        train_cfg=get_train_cfg(args.name)
    command_cfg["lin_vel_x_range"]=[.25,.25]
    # Stage 0's kp=40 is deliberately not adopted into the trained policy.
    env_cfg["enforce_urdf_torques"]=True
    env_cfg["kp"]=20.0
    if args.bound_targets:
        env_cfg["clip_joint_targets_to_urdf"]=True
    train_cfg["save_interval"]=250
    train_cfg["run_name"]=args.name
    report={"stage":1,"terrain":"FLAT","seed":args.seed,"num_envs":args.num_envs,
            "iterations":args.iterations,"status":"started","command_m_s":.25,
            "backend":"cpu","observation_dim":45,"action_dim":12,"control_hz":50,
            "versions":{p:importlib.metadata.version(p) for p in ("torch","genesis-world","rsl-rl-lib")},
            "source_sha256":digest(__file__)}
    started=time.monotonic()
    try:
        with (run/"cfgs.pkl").open("wb") as out:
            pickle.dump([env_cfg,obs_cfg,reward_cfg,command_cfg,train_cfg],out)
        (run/"configs.json").write_text(json.dumps([env_cfg,obs_cfg,reward_cfg,command_cfg,train_cfg],indent=2))
        gs.init(backend=gs.cpu,precision="32",seed=args.seed,logging_level="warning")
        env=flat_env_class(Go2Env)(args.num_envs,env_cfg,obs_cfg,reward_cfg,command_cfg)
        report["control_audit"]=torque_setup(env,env_cfg,gs)
        runner=OnPolicyRunner(env,train_cfg,str(run),device=gs.device)
        if args.resume:
            runner.load(args.resume)
            report["parent_checkpoint"]=str(Path(args.resume).resolve())
            report["parent_sha256"]=digest(args.resume)
        begin=runner.current_learning_iteration
        runner.learn(num_learning_iterations=args.iterations,init_at_random_ep_len=True)
        checkpoint=run/f"model_{runner.current_learning_iteration}.pt"
        report.update(status="trained_not_evaluated",checkpoint=str(checkpoint.relative_to(ROOT)),
                      checkpoint_sha256=digest(checkpoint),start_iteration=begin,
                      end_iteration=runner.current_learning_iteration,
                      max_rss_bytes_macos=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    except BaseException as error:
        report.update(status="error",error_type=type(error).__name__,error=str(error))
        (run/"error.txt").write_text(traceback.format_exc());raise
    finally:
        report["wall_seconds"]=time.monotonic()-started
        (run/"provenance.json").write_text(json.dumps(report,indent=2))
        print(json.dumps(report,indent=2),flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("mode",choices=("eval","train"))
    p.add_argument("--name",required=True)
    p.add_argument("--checkpoint")
    p.add_argument("--seed",type=int,default=1001)
    p.add_argument("--iterations",type=int,default=5)
    p.add_argument("--num-envs",type=int,default=16)
    p.add_argument("--resume")
    p.add_argument("--bound-targets",action="store_true")
    args=p.parse_args()
    if args.mode=="eval" and not args.checkpoint: p.error("--checkpoint required")
    if args.mode=="train" and (args.iterations<1 or args.num_envs<4): p.error("Positive iterations and >=4 environments required")
    if args.mode=="eval": raise SystemExit(evaluate(args))
    train(args)
