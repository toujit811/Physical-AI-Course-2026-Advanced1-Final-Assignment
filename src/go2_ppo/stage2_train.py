"""Bounded Stage2 PPO curriculum, fixed 64-env controller, separate terrain seeds."""
import argparse,copy,csv,hashlib,json,math,pickle,resource,shutil,time
from pathlib import Path
import torch
import genesis as gs
from rsl_rl.runners import OnPolicyRunner
from . import stage2_eval as se
from .stage2_terrain import generate
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--name",required=True);p.add_argument("--checkpoint",required=True)
    p.add_argument("--terrain-kind",choices=("BUMPS","SLOPE","STEPS","COMPOUND"),required=True)
    p.add_argument("--terrain-seed",type=int,required=True);p.add_argument("--seed",type=int,default=51001)
    args=p.parse_args();args.substeps=2;args.duration=20.;args.rl_kd=1.;args.no_latency=False
    cfg=json.loads((se.ROOT/"configs/stage2-uneven.json").read_text())
    assert args.terrain_seed in cfg["training_seeds"]
    run=se.make_run("training",args.name);start=time.monotonic()
    report=se.provenance(run,args);report.update(scope="training",learning_performed=True,algorithm="PPO")
    shutil.copy2(__file__,run/"source"/Path(__file__).name)
    report["source_sha256"]["src/go2_ppo/stage2_train.py"]=se.sha(__file__)
    parent=Path(args.checkpoint).resolve();initial=se.sha(parent)
    ec,oc,rc,cc,tc=se.load_cfg(parent)
    ec.update(enforce_urdf_torques=True,clip_joint_targets_to_urdf=True,joint_target_margin_rad=.12,retest_substeps=2,kp=20.,kd=.5)
    rc["terrain_relative_heights"]=True;cc["lin_vel_x_range"]=[.25,.25];tc.update(run_name=args.name,save_interval=250)
    ec["terrain_boundary_policy"]="Immediate terminal/reset when base or foot XY leaves physical terrain; terminal height rewards query nearest edge, physical terrain is not extended; nonfinite states raise."
    terrain=generate(args.terrain_kind,args.terrain_seed,cfg)
    import numpy as np
    np.savez_compressed(run/"terrain.npz",x=terrain["x"],y=terrain["y"],height_m=terrain["height_m"])
    se.dump(run/"terrain.json",terrain["metadata"])
    se.dump(run/"configs.json",[ec,oc,rc,cc,tc])
    with (run/"cfgs.pkl").open("wb") as f:pickle.dump([ec,oc,rc,cc,tc],f)
    report.update(parent_checkpoint=str(parent),parent_sha256=initial,num_envs=64,iterations=cfg["iterations_per_curriculum_stage"],
        rollout_steps=24,batch_size=1536,minibatch_size=384,num_minibatches=4,epochs=5,
        total_env_steps=64*24*cfg["iterations_per_curriculum_stage"],gradient_updates=20*cfg["iterations_per_curriculum_stage"],
        missing_metrics={"KL":"not returned by rsl_rl5.0","clip_fraction":"not returned","training_contact_slip_full_metrics":"exact quality from separate recorded evaluation; snapshots are not episode success rates"})
    se.dump(run/"provenance.json",report)
    try:
        gs.init(backend=gs.cpu,precision="32",seed=args.seed,logging_level="warning")
        env=se.QualityEnv(64,ec,oc,copy.deepcopy(rc),cc,terrain=terrain)
        for reward_name,reward_function in list(env.reward_functions.items()):
            def monitored_reward(fn=reward_function,name=reward_name):
                value=fn()
                if not torch.isfinite(value).all():
                    centers=torch.stack([g.get_pos() for g in env.foot_geoms.values()],dim=1)
                    surface=env.ground.get_terrain_height(centers[:,:,:2])
                    se.dump(run/"nonfinite-reward-diagnostic.json",{
                        "reward":name,"nonfinite_envs":(~torch.isfinite(value)).nonzero().reshape(-1).tolist(),
                        "base_pos":env.robot.get_pos().tolist(),"foot_centers":centers.tolist(),
                        "native_surface_finite":torch.isfinite(surface).tolist(),
                        "foot_xy_min":centers[:,:,:2].amin(dim=(0,1)).tolist(),"foot_xy_max":centers[:,:,:2].amax(dim=(0,1)).tolist()})
                    raise FloatingPointError("Nonfinite reward "+name)
                return value
            env.reward_functions[reward_name]=monitored_reward
        report["control_audit"]=se.torque_setup(env,ec,gs)
        runner=OnPolicyRunner(env,copy.deepcopy(tc),str(run),device=gs.device);runner.load(str(parent))
        history=[];original=runner.logger.log
        def log(**kw):
            row={k:kw[k] for k in ("it","collect_time","learn_time","learning_rate")}
            row.update({k:float(v) for k,v in kw["loss_dict"].items()})
            row.update(action_std=kw["action_std"].mean().item(),batch_speed_rmse=torch.square(env.base_lin_vel[:,0]-.25).mean().sqrt().item(),
                batch_done_fraction=env.reset_buf.float().mean().item(),max_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
            if not all(math.isfinite(float(v)) for v in row.values()):raise FloatingPointError("Nonfinite training metric")
            history.append(row)
            with (run/"iterations.jsonl").open("a") as f:f.write(json.dumps(row)+"\n")
            original(**kw)
        runner.logger.log=log
        begin=runner.current_learning_iteration
        runner.learn(num_learning_iterations=cfg["iterations_per_curriculum_stage"],init_at_random_ep_len=True)
        model=run/"policy_final.pt";runner.save(str(model))
        if runner.logger.writer:runner.logger.writer.flush()
        report.update(status="trained_not_evaluated",checkpoint=str(model.relative_to(se.ROOT)),checkpoint_sha256=se.sha(model),
            start_iteration=begin,end_iteration=runner.current_learning_iteration,logged_iterations=len(history),
            rollout_seconds=sum(r["collect_time"] for r in history),update_seconds=sum(r["learn_time"] for r in history))
    except BaseException as e:
        import traceback
        report.update(status="error",error=str(e));(run/"error.txt").write_text(traceback.format_exc());raise
    finally:
        report.update(wall_seconds=time.monotonic()-start,system_after=se.system_state(),parent_hash_unchanged=se.sha(parent)==initial)
        se.dump(run/"provenance.json",report);print(json.dumps(report),flush=True)
if __name__=="__main__":main()
