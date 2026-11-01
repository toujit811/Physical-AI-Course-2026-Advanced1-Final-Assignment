"""Same-checkpoint FLAT/approved-rolling validation with unchanged historical gates."""
import argparse,json,copy,hashlib,shutil
from pathlib import Path
from types import SimpleNamespace
import numpy as np,torch
from . import rolling_native_evaluate as native
from . import rolling_native_env as native_env
from .rolling_approved_source import verify_heightfield
from .rolling_uneven_media import RollingUnevenRecorder
from .natural_metrics import assess
from .video_materials import sha
from .selection import claim_heldout_seed
from .evaluation_status import exit_code,recording_status,enforce_substep_safety

class EvaluationRecorder(RollingUnevenRecorder):
    def append(self,cameras,t,base_pos):
        x,y,z=base_pos;target=(x+.05,y,z-.15)
        cameras['side'].set_pose(pos=(target[0],y-.95,target[2]),lookat=target,up=(0,0,1))
        cameras['oblique'].set_pose(pos=(x+1.1,y-1.7,1.12),lookat=(x+.25,y,.2))
        cameras['overhead'].set_pose(pos=(3,0,5),lookat=(3,0,0),up=(0,1,0))
        return super().append(cameras,t,base_pos)
class NoRecorder:
    def __init__(self,*args,**kwargs):pass
    def append(self,*args,**kwargs):pass
    def close(self):pass

def main():
    p=argparse.ArgumentParser();p.add_argument('--checkpoint',required=True,type=Path);p.add_argument('--name',required=True);p.add_argument('--kind',choices=['FLAT','ROLLING_UNEVEN','HELDOUT'],required=True);p.add_argument('--condition',type=int,choices=range(3),default=2);p.add_argument('--record',action='store_true');p.add_argument('--heldout-seed',type=int);p.add_argument('--selection',type=Path);a=p.parse_args()
    torch.set_num_threads(4);checkpoint=a.checkpoint.resolve();native.PARENT=checkpoint;native.EXPECTED=sha(checkpoint);native.SOURCE=native.ROOT/'terrain/rolling_uneven/v1/heightfield.npz';original_source=verify_heightfield(native.SOURCE);terrain=original_source
    cls=native_env.QualityEnv;original_audit=native.terrain_audit
    if a.kind=='FLAT':
        terrain=copy.deepcopy(original_source);terrain['height_mm']=np.zeros_like(terrain['height_mm']);terrain['height_m']=np.zeros_like(terrain['height_m']);terrain['original_height_m']=np.zeros_like(terrain['original_height_m']);terrain['metadata'].update(kind='FLAT',surface='original URDF plane, z=0')
        class FlatEvaluationEnv(cls):
            def __init__(self,n,ec,oc,rc,cc,**kwargs):
                ec=copy.deepcopy(ec);ec['surface_kind']='FLAT';kwargs['terrain']=None;super().__init__(n,ec,oc,rc,cc,**kwargs)
                def analytic_height(xy):
                    xy=torch.as_tensor(xy,device=self.device);shape=(self.num_envs,) if xy.ndim==1 else (self.num_envs,xy.shape[0]) if xy.ndim==2 else xy.shape[:-1]
                    return torch.zeros(shape,device=self.device)
                self.ground.get_terrain_height=analytic_height
        native_env.QualityEnv=FlatEvaluationEnv
        def plane_audit(ground,t,run):
            result={'ground_class':type(ground).__name__,'analytic_plane_z_m':0.,'height_query_definition':'analytic z=0 plane, not a native Terrain query','actual_collision_geoms':[int(g.idx) for g in ground.geoms]};native.dump(run/'terrain-physics-check.json',result);return result
        native.terrain_audit=plane_audit
    elif a.kind=='HELDOUT':
        if a.selection is None or a.heldout_seed is None:raise ValueError('Frozen model selection and unused heldout seed required')
        cfg=json.loads((native.ROOT/'configs/training/mixed-d-v1.json').read_text())
        claim_heldout_seed(a.selection,checkpoint,a.heldout_seed,cfg['seeds']['heldout'])
        rng=np.random.default_rng(a.heldout_seed);terrain=copy.deepcopy(original_source);X,Y=np.meshgrid(terrain['x'],terrain['y'],indexing='ij');envelope=np.sin(np.pi*np.clip((X-.1)/6.4,0,1))**2;noise=.005*np.sin(2*np.pi*X/rng.uniform(2.4,3.2)+rng.uniform(0,2*np.pi))*np.cos(np.pi*Y/1.3+rng.uniform(-.4,.4));z=np.maximum(original_source['original_height_m']+noise*envelope,0);terrain['original_height_m']=z;terrain['height_mm']=np.rint(z/.001).astype(np.int16);terrain['height_m']=terrain['height_mm'].astype(float)*.001;terrain['metadata'].update(kind='HELDOUT_ROLLING_V1',seed=a.heldout_seed,source_sha256=hashlib.sha256(z.tobytes()).hexdigest(),parent_approved_source_sha256=original_source['metadata']['source_sha256'])
    native.verify_heightfield=lambda _:terrain
    native.RollingUnevenRecorder=EvaluationRecorder if a.record else NoRecorder
    args=SimpleNamespace(name=a.name,source=str(native.SOURCE),duration=20.,substeps=2,condition=a.condition,wall_cap=600.,pd_contact_probe=False,probe_x=None,probe_y=0.,recording_label='MODEL D / '+a.kind+' / '+checkpoint.name)
    status=native.run(args);run=native.ROOT/'logs/rolling-native'/a.name;path=run/'result.json';r=json.loads(path.read_text());r.update(mode='model_D_fixed_evaluation',evaluation_kind=a.kind,recording_performed=a.record,heldout=a.kind=='HELDOUT',approved_source=a.kind=='ROLLING_UNEVEN',source_definition=terrain['metadata'])
    r['args']['checkpoint']=str(checkpoint)
    for name in ('evaluate.py','training_env.py'):
        shutil.copy2(native.ROOT/'src/go2_ppo'/name,run/'source'/name)
        r['source_sha256s'][name]=sha(run/'source'/name)
    if a.kind=='FLAT' and r['status'] not in ('ERROR','TIMEOUT'):
        import csv
        rows=list(csv.DictReader((run/'controls.csv').open()));typed=[]
        for row in rows:
            converted={}
            for k,v in row.items():
                if v in ('True','False'):converted[k]=v=='True'
                else:
                    try:converted[k]=float(v)
                    except ValueError:converted[k]=v
            typed.append(converted)
        protocol=json.loads((native.ROOT/'configs/natural-gait.json').read_text());states=list(csv.DictReader((run/'states.csv').open()));metrics=enforce_substep_safety(assess(typed,protocol,r['control']),states);metrics['numeric_gates']['E'] &= r['numeric_gates']['joint_input'];metrics['numeric_gates']['B'] &= r['numeric_gates']['no_abnormal_contact'];metrics['numeric_pass']=all(metrics['numeric_gates'].values());r.update(metrics);r['status']='NUMERIC_PASS_VISUAL_PENDING' if metrics['numeric_pass'] else 'TASK_FAIL'
    meta_path=run/'native-media/recording-metadata.json'
    metadata=json.loads(meta_path.read_text()) if meta_path.exists() else None
    r.update(recording_status(a.record,r,metadata))
    path.write_text(json.dumps(r,indent=2,allow_nan=False)+'\n');print(json.dumps({k:r.get(k) for k in ('evaluation_kind','status','distance_m','duration_s','numeric_gates','recording_performed')}),flush=True);return exit_code(r)
if __name__=='__main__':raise SystemExit(main())
