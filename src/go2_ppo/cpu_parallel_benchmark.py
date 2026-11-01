"""Isolated Mac CPU fixed-policy64/128 rollout benchmark. No PPO updates or model saves."""
import argparse,copy,hashlib,importlib.metadata,json,os,platform,resource,subprocess,sys,threading,time,traceback
from pathlib import Path
import numpy as np
import psutil
from .cpu_benchmark_metrics import vector_steps,speed

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'reports/cpu-64-128-benchmark-20261031'
LOGS=ROOT/'logs/cpu-64-128-benchmark-20261031'
CHECKPOINT=ROOT/'logs/stage1/natural/training/slip20-margin012-64x1500/model_6500.pt'
EXPECTED='c9bd93aa103db4e892623babff4de5c8da2cc7c0af5e31bcca389836738c0a2c'
ADOPTED=ROOT/'logs/stage1/e-joint-retest/evaluations/rlkd1-final-c2/config.json'

def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def dump(p,a):Path(p).write_text(json.dumps(a,indent=2,allow_nan=False))
def csvout(p,a):
    import csv
    if a:
        with Path(p).open('w') as f:
            w=csv.DictWriter(f,fieldnames=list(a[0]));w.writeheader();w.writerows(a)
def digest(value):
    import torch
    h=hashlib.sha256()
    def add(x):
        if isinstance(x,torch.Tensor):h.update(str((str(x.dtype),list(x.shape))).encode());h.update(x.detach().cpu().contiguous().numpy().tobytes())
        elif isinstance(x,dict):
            for k in sorted(x,key=str):h.update(str(k).encode());add(x[k])
        elif isinstance(x,(tuple,list)):
            for v in x:add(v)
        else:h.update(repr(x).encode())
    add(value);return h.hexdigest()

def system():
    return dict(time_unix=time.time(),cpu_count=psutil.cpu_count(),cpu_physical=psutil.cpu_count(logical=False),cpu_brand=subprocess.run(['sysctl','-n','machdep.cpu.brand_string'],capture_output=True,text=True).stdout.strip(),macos=platform.mac_ver()[0],machine=platform.machine(),memory=psutil.virtual_memory()._asdict(),swap=psutil.swap_memory()._asdict(),load_average=list(os.getloadavg()),vm_stat=subprocess.run(['vm_stat'],capture_output=True,text=True).stdout,swapusage=subprocess.run(['sysctl','vm.swapusage'],capture_output=True,text=True).stdout)

class Monitor:
    def __init__(self):self.rows=[];self.done=threading.Event();self.process=psutil.Process();self.start=0.;self.unsafe=None
    def sample(self):
        mem=psutil.virtual_memory();swap=psutil.swap_memory();cpu=self.process.cpu_percent();rss=self.process.memory_info().rss
        self.rows.append(dict(elapsed_s=time.perf_counter()-self.start,process_rss_bytes=rss,process_cpu_percent=cpu,system_cpu_percent=psutil.cpu_percent(),system_available_bytes=mem.available,system_used_bytes=mem.used,system_memory_percent=mem.percent,swap_used_bytes=swap.used,swap_in_bytes=swap.sin,swap_out_bytes=swap.sout,load1=os.getloadavg()[0]))
        if mem.available<4*1024**3:self.unsafe='System available memory below4GiB'
    def loop(self):
        while not self.done.wait(.25):self.sample()
    def begin(self):
        self.process.cpu_percent();psutil.cpu_percent();self.start=time.perf_counter();self.sample();self.thread=threading.Thread(target=self.loop,daemon=True);self.thread.start()
    def stop(self):self.done.set();self.thread.join();self.sample()

def worker(a):
    run=LOGS/f'{a.phase}-{a.trial}-n{a.num_envs}-seed{a.seed}';run.mkdir(parents=True,exist_ok=False)
    report=dict(status='initializing',phase=a.phase,trial=a.trial,num_envs=a.num_envs,seed=a.seed,total_env_steps=a.steps,vector_steps=vector_steps(a.steps,a.num_envs),rollout_length=24,rollout_blocks=a.steps//(a.num_envs*24),warmup_vector_steps=96,checkpoint=str(CHECKPOINT),checkpoint_sha256=sha(CHECKPOINT),command=sys.argv,system_before=system(),missing_metrics={})
    dump(run/'provenance.json',report);start=time.perf_counter();monitor=None
    try:
        if sys.platform!='darwin' or platform.machine()!='arm64':raise RuntimeError('Expected local Apple Silicon Mac')
        assert report['checkpoint_sha256']==EXPECTED
        import torch,genesis as gs
        from rsl_rl.runners import OnPolicyRunner
        from .natural_gait import QualityEnv,torque_setup
        training=json.loads((CHECKPOINT.parent/'configs.json').read_text());adopted=json.loads(ADOPTED.read_text())
        ec=copy.deepcopy(adopted['effective_cfgs'][0]);oc=copy.deepcopy(training[1]);rc=copy.deepcopy(training[2]);cc=copy.deepcopy(training[3]);tc=copy.deepcopy(training[4])
        cfgs=[ec,oc,rc,cc,tc];dump(run/'configs.json',cfgs);report['configs_sha256']=sha(run/'configs.json')
        report['thread_settings']=dict(torch_intraop=torch.get_num_threads(),torch_interop=torch.get_num_interop_threads(),environment={k:os.environ.get(k) for k in ['OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','NUMBA_NUM_THREADS']})
        report['versions']={k:importlib.metadata.version(k) for k in ['genesis-world','torch','rsl-rl-lib','psutil']}
        torch.manual_seed(a.seed);np.random.seed(a.seed);gs.init(backend=gs.cpu,precision='32',seed=a.seed,logging_level='warning')
        env=QualityEnv(a.num_envs,ec,oc,rc,cc,record=False)
        ids=env.motors_dof_idx.tolist();rl_id=env.robot.get_joint('RL_calf_joint').dof_start;env.robot.set_dofs_kv([1.],[rl_id]);control=torque_setup(env,ec,gs)
        # torque_setup must retain the adopted override; audit actual readback.
        env.robot.set_dofs_kv([1.],[rl_id]);control['kd_readback']=env.robot.get_dofs_kv(ids).tolist()
        expected_kd=adopted['control_audit']['kd_readback'];assert control['kd_readback']==expected_kd
        report['control_audit']=control
        report['physical_build']=dict(sim=env.scene.options.sim.model_dump(mode='json'),rigid=env.scene.options.rigid.model_dump(mode='json'),collision_entities=len(env.scene.rigid_solver.entities),robot_urdf_sha256=sha(Path(gs.__file__).parent/'assets/urdf/go2/urdf/go2.urdf'))
        runner=OnPolicyRunner(env,copy.deepcopy(tc),str(run/'unused-runner-log'),device=gs.device);runner.load(str(CHECKPOINT),map_location='cpu')
        saved=torch.load(CHECKPOINT,weights_only=False,map_location='cpu');alg=runner.alg
        resume=dict(checkpoint_keys=list(saved),iteration=runner.current_learning_iteration,checkpoint_iteration=saved['iter'],actor_state_exact=digest(alg.actor.state_dict())==digest(saved['actor_state_dict']),critic_state_exact=digest(alg.critic.state_dict())==digest(saved['critic_state_dict']),optimizer_state_exact=digest(alg.optimizer.state_dict())==digest(saved['optimizer_state_dict']),optimizer_slots=len(alg.optimizer.state),optimizer_loaded_lr=[g['lr'] for g in alg.optimizer.param_groups],configured_learning_rate=tc['algorithm']['learning_rate'],fresh_storage_actions_shape=list(alg.storage.actions.shape),fresh_storage_observation_batch=list(alg.storage.observations.batch_size),storage_initial_step=int(alg.storage.step))
        assert all(resume[k] for k in ['actor_state_exact','critic_state_exact','optimizer_state_exact'])
        assert resume['fresh_storage_actions_shape']==[24,a.num_envs,12] and resume['fresh_storage_observation_batch']==[24,a.num_envs] and resume['storage_initial_step']==0
        dump(run/'resume-audit.json',resume);report['resume_audit']=resume
        policy=runner.get_inference_policy(device='cpu');actor_before=digest(alg.actor.state_dict());optimizer_before=digest(alg.optimizer.state_dict());cpu=psutil.Process()
        with torch.inference_mode():
            obs=env.reset();warm=time.perf_counter()
            for _ in range(96):obs,rew,done,extra=env.step(policy(obs))
            report['warmup_seconds']=time.perf_counter()-warm
            torch.manual_seed(a.seed);obs=env.reset();initial=env.robot.get_qpos().clone()
            assert obs['policy'].shape==(a.num_envs,45) and torch.isfinite(initial).all()
            report['initial_state']=dict(shape=list(initial.shape),minimum_height=float(initial[:,2].min()),maximum_height=float(initial[:,2].max()),qpos_sha256=digest(initial))
            report['startup_and_warmup_seconds']=time.perf_counter()-start;dump(run/'ready.json',report)
            monitor=Monitor();monitor.begin();cpu0=cpu.cpu_times();timer=time.perf_counter();resetflags=0
            for step in range(report['vector_steps']):
                actions=policy(obs)
                if not torch.isfinite(actions).all():raise FloatingPointError('Nonfinite fixed policy actions')
                obs,rew,done,extra=env.step(actions)
                if not torch.isfinite(obs['policy']).all() or not torch.isfinite(rew).all():raise FloatingPointError('Nonfinite simulation outputs')
                if bool(env.engine_errors.any()):raise RuntimeError('Genesis engine error')
                resetflags+=int(done.sum())
                if monitor.unsafe:raise MemoryError(monitor.unsafe)
            seconds=time.perf_counter()-timer;cpu1=cpu.cpu_times();monitor.stop()
            final=env.robot.get_qpos();assert torch.isfinite(final).all()
            report.update(status='passed',wall_seconds=seconds,env_steps_per_second=speed(a.steps,seconds),vector_steps_per_second=report['vector_steps']/seconds,process_cpu_seconds=(cpu1.user+cpu1.system-cpu0.user-cpu0.system),process_cpu_percent_from_times=100*(cpu1.user+cpu1.system-cpu0.user-cpu0.system)/seconds,reset_flag_count=resetflags,final_state_sha256=digest(final),nonfinite_count=0,engine_error_count=0,actor_unchanged=digest(alg.actor.state_dict())==actor_before,optimizer_unchanged=digest(alg.optimizer.state_dict())==optimizer_before,checkpoint_unchanged=sha(CHECKPOINT)==EXPECTED,storage_step_after=int(alg.storage.step),peak_rss_process_lifetime_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
            assert report['actor_unchanged'] and report['optimizer_unchanged'] and report['checkpoint_unchanged'] and report['storage_step_after']==0
        sample=monitor.rows;csvout(run/'resources.csv',sample)
        report.update(resource_sample_count=len(sample),peak_rss_measured_bytes=max(r['process_rss_bytes'] for r in sample),mean_rss_measured_bytes=float(np.mean([r['process_rss_bytes'] for r in sample])),minimum_system_available_bytes=min(r['system_available_bytes'] for r in sample),maximum_system_memory_percent=max(r['system_memory_percent'] for r in sample),maximum_swap_bytes=max(r['swap_used_bytes'] for r in sample),swap_growth_bytes=sample[-1]['swap_used_bytes']-sample[0]['swap_used_bytes'],mean_process_cpu_percent=float(np.mean([r['process_cpu_percent'] for r in sample[1:]])),mean_system_cpu_percent=float(np.mean([r['system_cpu_percent'] for r in sample[1:]])),system_after=system(),ppo_updates=0,policy_mode='deterministic actor evaluation; original training rewards/observations/resets; no returns/SGD/storage filling')
    except BaseException as e:
        if monitor is not None and hasattr(monitor,'thread') and monitor.thread.is_alive():monitor.stop()
        if monitor is not None:csvout(run/'resources-partial.csv',monitor.rows)
        report.update(status='error',error_type=type(e).__name__,error=str(e),traceback=traceback.format_exc());(run/'error.txt').write_text(report['traceback']);raise
    finally:
        report['process_elapsed_seconds']=time.perf_counter()-start;report['checkpoint_unchanged']=sha(CHECKPOINT)==EXPECTED;dump(run/'result.json',report)
        print(json.dumps({k:report.get(k) for k in ['phase','trial','num_envs','status','wall_seconds','env_steps_per_second','startup_and_warmup_seconds','error']}),flush=True)

def controller():
    LOGS.mkdir(exist_ok=False);dump(OUT/'host-before.json',system());commands=[];results=[]
    schedule=[('preflight',0,64,7100,12288),('preflight',0,128,7100,12288)]+[('measure',pair,n,7100+pair,196608) for pair,ns in [(1,[64,128]),(2,[128,64]),(3,[64,128])] for n in ns]
    dump(OUT/'schedule.json',[dict(phase=p,trial=i,num_envs=n,seed=s,total_env_steps=t) for p,i,n,s,t in schedule])
    for phase,trial,n,seed,steps in schedule:
        cmd=[sys.executable,str(Path(__file__).resolve()),'--worker','--phase',phase,'--trial',str(trial),'--num-envs',str(n),'--seed',str(seed),'--steps',str(steps)]
        commands.append(cmd);dump(OUT/'commands.json',commands);log=OUT/f'{phase}-{trial}-n{n}.log';print('START',phase,trial,n,flush=True)
        with log.open('w') as f:
            try:process=subprocess.run(cmd,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,timeout=1200)
            except subprocess.TimeoutExpired:dump(OUT/'controller-error.json',dict(error='worker timeout1200s',command=cmd));raise
        result_path=LOGS/f'{phase}-{trial}-n{n}-seed{seed}'/'result.json';r=json.loads(result_path.read_text()) if result_path.exists() else dict(status='process_error',returncode=process.returncode)
        results.append(r);dump(OUT/'completed-results.json',results)
        if process.returncode or r['status']!='passed':raise RuntimeError(f'Abort after {phase} N{n}: worker failure; preserve all logs')
        print('DONE',phase,trial,n,round(r['env_steps_per_second'],1),'envsteps/s',flush=True)
    dump(OUT/'host-after.json',system());print('ALL8 workers passed; benchmark measurements complete',flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--worker',action='store_true');p.add_argument('--phase',choices=['preflight','measure']);p.add_argument('--trial',type=int);p.add_argument('--num-envs',type=int,choices=[64,128]);p.add_argument('--seed',type=int);p.add_argument('--steps',type=int);a=p.parse_args()
    if a.worker:worker(a)
    else:controller()
