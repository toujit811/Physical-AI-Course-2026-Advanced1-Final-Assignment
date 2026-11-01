"""Actual full-state PPO continuation; one policy, two native Scenes, no implicit evaluation."""
import argparse,copy,json,pickle,time,traceback,hashlib,os,shutil
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
import torch,genesis as gs
from torch.utils.tensorboard import SummaryWriter
from rsl_rl.runners import OnPolicyRunner
from .training_env import build_mixed
from .cpu_parallel_benchmark import Monitor,digest
from .training_constraints import check_native_errors,apply_ppo_overrides,progress_metadata,rollout_reward_metrics

ROOT=Path(__file__).resolve().parents[2]
EXPECTED='c9bd93aa103db4e892623babff4de5c8da2cc7c0af5e31bcca389836738c0a2c'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,a):Path(p).write_text(json.dumps(a,indent=2,allow_nan=False)+'\n')
def parameter_hash(model):return digest(dict(model.named_parameters()))
def synchronize_lr(alg):
    rates=[float(g['lr']) for g in alg.optimizer.param_groups]
    if not rates or not all(np.isfinite(rates)) or min(rates)<=0 or len(set(rates))!=1:raise ValueError('Unsupported restored optimizer learning rates')
    alg.learning_rate=rates[0];return rates[0]
def full_load(runner,path):
    runner.load(str(path),strict=True,map_location='cpu');s=torch.load(path,weights_only=False,map_location='cpu');a=runner.alg
    audit={k:digest(getattr(a,attr).state_dict())==digest(s[key]) for k,attr,key in (('actor_exact','actor','actor_state_dict'),('critic_exact','critic','critic_state_dict'),('optimizer_exact','optimizer','optimizer_state_dict'))};audit.update(iteration=runner.current_learning_iteration,learning_rate=synchronize_lr(a),optimizer_slots=len(a.optimizer.state),adam_steps=sorted(set(float(v['step']) for v in a.optimizer.state.values() if 'step' in v)))
    if not all(audit[k] for k in ('actor_exact','critic_exact','optimizer_exact')):raise ValueError('Full-state resume mismatch')
    return audit,s

def reset_audit(env):
    report={}
    for kind,e in zip(('FLAT','ROLLING_UNEVEN'),env.groups):
        old=e.robot.get_qpos().clone();mask=torch.zeros(e.num_envs,dtype=torch.bool,device=e.device);mask[0]=True;e._reset_idx(mask);now=e.robot.get_qpos();unchanged=bool(torch.equal(old[1:],now[1:]));q=e.robot.get_dofs_position(e.motors_dof_idx);obs_q=e.dof_pos;match=bool(torch.allclose(q[0],obs_q[0],atol=1e-6));report[kind]={'nonreset_pose_exact':unchanged,'reset_policy_joint_observation_matches_native':match,'reset_pose_finite':bool(torch.isfinite(now).all()),'reset_contacts_cleared':not bool(e.robot.get_contacts(is_padded=True)['valid_mask'][0].any())}
        if not all(report[kind].values()):raise ValueError('Native partial reset audit failed '+kind+': '+json.dumps(report[kind]))
    return report

def main():
    p=argparse.ArgumentParser();p.add_argument('--name',required=True);p.add_argument('--checkpoint',required=True,type=Path);p.add_argument('--num-envs',type=int,default=64);p.add_argument('--iterations',type=int,default=300);p.add_argument('--save-every',type=int,default=100);p.add_argument('--max-wall-seconds',type=float,default=3600);p.add_argument('--seed',type=int,default=62001);p.add_argument('--threads',type=int,default=4);p.add_argument('--reset-check',action='store_true');a=p.parse_args()
    cfg_path=Path(os.environ.get('GO2_TRAINING_CONFIG',ROOT/'configs/training/mixed-d-v1.json'))
    cfg=json.loads(cfg_path.read_text())
    if a.seed not in cfg['seeds']['train']:raise ValueError('Seed not allocated for training')
    parent=a.checkpoint.resolve();parent_sha=sha(parent)
    if parent.name=='model_6500.pt' and parent_sha!=EXPECTED:raise ValueError('Original checkpoint hash mismatch')
    run=ROOT/'logs/mixed-d'/a.name;run.mkdir(parents=True,exist_ok=False);start=time.monotonic();rows=[];monitor=Monitor();writer=None;runner=None;env=None;completed=0;optimizer_steps=0;result={'started_at_utc':datetime.now(timezone.utc).isoformat(),'status':'initializing','name':a.name,'args':{**vars(a),'checkpoint':str(parent)},'parent_sha256':parent_sha,'learning_performed':False,'heldout':False};dump(run/'result.json',result)
    (run/'source').mkdir()
    for source in (ROOT/'src/go2_ppo').glob('*.py'):shutil.copy2(source,run/'source'/source.name)
    result['approved_terrain_sha256']=sha(ROOT/'terrain/rolling_uneven/v1/heightfield.npz')
    try:
        torch.set_num_threads(a.threads);torch.manual_seed(a.seed);np.random.seed(a.seed);gs.init(backend=gs.cpu,precision='32',seed=a.seed,logging_level='warning');monitor.begin()
        cfgs=copy.deepcopy(pickle.load((parent.parent/'cfgs.pkl').open('rb')));env,effective=build_mixed(a.num_envs,cfgs,ROOT/'terrain/rolling_uneven/v1/heightfield.npz',cfg)
        effective[4]['run_name']=a.name
        effective[4]=apply_ppo_overrides(effective[4],cfg.get('ppo_overrides',{}))
        with (run/'cfgs.pkl').open('wb') as f:pickle.dump(effective,f)
        dump(run/'configs.json',effective);dump(run/'training-config.json',cfg)
        runner=OnPolicyRunner(env,copy.deepcopy(effective[4]),None,device=gs.device);audit,saved=full_load(runner,parent);dump(run/'resume-audit.json',audit);alg=runner.alg;begin=int(runner.current_learning_iteration);actor0=parameter_hash(alg.actor);critic0=parameter_hash(alg.critic)
        result.update(initial_resume=audit,start_iteration=begin,observations=45,actions=12,num_envs=a.num_envs,sampler=env.cfg,thread_count=torch.get_num_threads(),source_sha256={str(x.relative_to(ROOT)):sha(x) for x in (ROOT/'src/go2_ppo').glob('*.py')})
        result['status']='TRAINING';dump(run/'result.json',result)
        with torch.inference_mode():
            env.reset()
            if a.reset_check:
                policy=runner.get_inference_policy(device=gs.device)
                for _ in range(12):env.step(policy(env.get_observations()))
                dump(run/'native-reset-audit.json',reset_audit(env))
            obs=env.reset();env.environment_steps={'FLAT':0,'ROLLING_UNEVEN':0}
        alg.train_mode();writer=SummaryWriter(str(run/'tensorboard'));original_step=alg.optimizer.step;gradient={'actor_nonzero_steps':0,'critic_nonzero_steps':0,'actor_max_norm':0.,'critic_max_norm':0.}
        def checked_step(*args,**kwargs):
            nonlocal optimizer_steps
            for key,model in (('actor',alg.actor),('critic',alg.critic)):
                norm=0.
                for param in model.parameters():
                    if param.grad is None:continue
                    g=param.grad.detach()
                    if not torch.isfinite(g).all():raise FloatingPointError('Nonfinite '+key+' gradient')
                    norm+=float(g.square().sum())
                norm=norm**.5;gradient[key+'_nonzero_steps']+=int(norm>0);gradient[key+'_max_norm']=max(gradient[key+'_max_norm'],norm)
            optimizer_steps+=1;return original_step(*args,**kwargs)
        alg.optimizer.step=checked_step
        parent_cumulative=int((saved.get('infos') or {}).get('cumulative_mixed_env_steps',0))
        def save_checkpoint(label):
            payload=alg.save();payload.update(iter=begin+completed,infos={'parent_sha256':parent_sha,'completed_updates_this_run':completed,'cumulative_mixed_env_steps':parent_cumulative+sum(env.environment_steps.values()),'environment_steps_this_run':dict(env.environment_steps),'reward_version':cfg['reward_version'],'training_seed':a.seed,'optimizer_step_calls':optimizer_steps});path=run/label;torch.save(payload,path);return path
        for i in range(a.iterations):
            if monitor.unsafe:raise RuntimeError(monitor.unsafe)
            if time.monotonic()-start>a.max_wall_seconds:break
            collection=time.monotonic();reward_samples=[]
            with torch.inference_mode():
                for _ in range(24):
                    actions=alg.act(obs);obs,rewards,dones,extras=env.step(actions)
                    check_native_errors(env.groups)
                    reward_samples.append(rewards.detach().clone())
                    if not(torch.isfinite(obs['policy']).all() and torch.isfinite(rewards).all()):raise FloatingPointError('Nonfinite rollout')
                    alg.process_env_step(obs,rewards,dones,extras)
                alg.compute_returns(obs)
            collect_s=time.monotonic()-collection;up=time.monotonic();loss=alg.update();update_s=time.monotonic()-up;completed+=1;runner.current_learning_iteration=begin+completed
            row={'completed_updates':completed,'iteration':begin+completed,'collect_s':collect_s,'update_s':update_s,'env_steps_s':a.num_envs*24/(collect_s+update_s),'learning_rate':float(alg.learning_rate),'optimizer_steps':optimizer_steps,'process_peak_rss_bytes':max(x['process_rss_bytes'] for x in monitor.rows),**{k:float(v) for k,v in loss.items()}}
            row.update(rollout_reward_metrics(torch.stack(reward_samples)))
            for kind,e in zip(('FLAT','ROLLING_UNEVEN'),env.groups):row.update({kind+'_mean_x_m':float(e.base_pos[:,0].mean()),kind+'_mean_abs_y_m':float(e.base_pos[:,1].abs().mean()),kind+'_reset_events':int(e.reset_events.sum())})
            for kind,e in zip(('FLAT','ROLLING_UNEVEN'),env.groups):
                for key,value in e.training_episode_stats.items():row[kind+'_episodes_'+key]=value
            if not all(np.isfinite(v) for v in row.values()):raise FloatingPointError('Nonfinite PPO losses/metrics')
            rows.append(row)
            with (run/'iterations.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
            for key,value in row.items():writer.add_scalar(key,value,begin+completed)
            if completed==1 or completed%10==0:print(json.dumps(row),flush=True)
            if completed%a.save_every==0:save_checkpoint('model_'+str(begin+completed)+'.pt');writer.flush()
        if not completed:raise RuntimeError('No actual PPO updates')
        model=save_checkpoint('policy_final.pt');alg.optimizer.step=original_step
        changed_actor=parameter_hash(alg.actor)!=actor0;changed_critic=parameter_hash(alg.critic)!=critic0
        if not(changed_actor and changed_critic and gradient['actor_nonzero_steps'] and gradient['critic_nonzero_steps']):raise RuntimeError('No genuine actor/critic parameter update')
        expected_steps=completed*effective[4]['algorithm']['num_learning_epochs']*effective[4]['algorithm']['num_mini_batches'];assert optimizer_steps==expected_steps
        before_reload={k:digest(getattr(alg,k).state_dict()) for k in ('actor','critic','optimizer')};fresh=OnPolicyRunner(env,copy.deepcopy(effective[4]),None,device=gs.device);readback,_=full_load(fresh,model);assert all(digest(getattr(fresh.alg,k).state_dict())==v for k,v in before_reload.items());assert fresh.current_learning_iteration==begin+completed
        dump(run/'roundtrip-audit.json',readback)
        result.update(status='TRAINED_NOT_EVALUATED',learning_performed=True,completed_updates=completed,end_iteration=begin+completed,actual_env_steps=sum(env.environment_steps.values()),environment_steps=env.environment_steps,cumulative_mixed_env_steps=parent_cumulative+sum(env.environment_steps.values()),optimizer_step_calls=optimizer_steps,gradient_audit=gradient,actor_parameters_changed=changed_actor,critic_parameters_changed=changed_critic,checkpoint=str(model),checkpoint_sha256=sha(model),full_state_roundtrip_exact=True,wall_limit_reached=completed<a.iterations)
    except BaseException as exc:result.update(status='ERROR',reason=str(exc),traceback=traceback.format_exc());print(result['traceback'],flush=True)
    finally:
        if writer:writer.flush();writer.close()
        if hasattr(monitor,'thread'):monitor.stop()
        from .video_materials import csvout
        csvout(run/'iterations.csv',rows);csvout(run/'resources.csv',monitor.rows);result.update(progress_metadata(a.num_envs,completed,env.environment_steps if env is not None else {},optimizer_steps));result.update(wall_seconds=time.monotonic()-start,parent_unchanged=sha(parent)==parent_sha,completed_updates=completed);dump(run/'result.json',result);print(json.dumps({k:result.get(k) for k in ('status','name','reason','completed_updates','actual_env_steps','optimizer_step_calls','wall_seconds','checkpoint','parent_unchanged')}),flush=True)
    return int(result['status']=='ERROR')
if __name__=='__main__':raise SystemExit(main())
