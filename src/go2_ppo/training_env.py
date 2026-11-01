"""Versioned mixed-training additions; controller and approved evaluation source preserved."""
import copy,torch
from .rolling_native_env import QualityEnv
from .mixed_core import MixedVecEnv
from .rolling_approved_source import verify_heightfield
from .training_constraints import joint_guard_cost

class TrainingEnv(QualityEnv):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self.reset_events=torch.zeros(self.num_envs,dtype=torch.long,device=self.device);self.training_episode_stats={'ended':0,'ended_x_sum':0.,'completed_at_least3m':0,'max_terminal_x_m':0.}
    def _reset_idx(self,envs_idx=None):
        if envs_idx is not None and hasattr(self,'training_episode_stats') and bool(envs_idx.any()):
            x=self.base_pos[envs_idx,0];length=self.episode_length_buf[envs_idx];s=self.training_episode_stats;s['ended']+=int(envs_idx.sum());s['ended_x_sum']+=float(x.sum());s['completed_at_least3m']+=int(((x>=3)&(length>=999)).sum());s['max_terminal_x_m']=max(s['max_terminal_x_m'],float(x.max()))
        super()._reset_idx(envs_idx)
        # Native qpos was reset, but skip_forward left joint-position readback stale.
        self.robot.set_qpos(self.init_qpos,envs_idx=envs_idx,zero_velocity=True,skip_forward=False)
        if envs_idx is None:self.dof_pos.copy_(self.default_dof_pos)
        else:torch.where(envs_idx[:,None],self.default_dof_pos,self.dof_pos,out=self.dof_pos)
        if hasattr(self,'reset_events'):
            if envs_idx is None:self.reset_events+=1
            else:self.reset_events+=envs_idx.long()
    def _reward_world_tracking(self):
        velocity=self.robot.get_vel();return torch.exp(-(velocity[:,0]-.25).square()/.1)
    def _reward_lateral_drift(self):return self.robot.get_vel()[:,1].square()+.2*self.base_pos[:,1].square()
    def _reward_heading(self):return torch.atan2(2*(self.base_quat[:,0]*self.base_quat[:,3]+self.base_quat[:,1]*self.base_quat[:,2]),1-2*(self.base_quat[:,2].square()+self.base_quat[:,3].square())).square()
    def _reward_upright(self):return self.projected_gravity[:,:2].square().sum(-1)
    def _reward_nonfoot(self):
        c=self.robot.get_contacts(is_padded=True);ids=torch.tensor([g.idx for g in self.foot_geoms.values()],device=self.device);a,b=c['geom_a'],c['geom_b'];isfoot=((a[:,:,None]==ids)|(b[:,:,None]==ids)).any(-1);ground=(a<self.robot.geom_start)|(b<self.robot.geom_start)
        return (c['valid_mask']&ground&~isfoot).any(-1).float()
    def _reward_joint_limit(self):
        lo,hi=self.robot.get_dofs_limit(self.motors_dof_idx)
        return joint_guard_cost(self.dof_pos,lo,hi,self.env_cfg.get('training_joint_guard_margin_rad',0.))

def build_mixed(num_envs,cfgs,terrain_path,training_cfg):
    if num_envs<4 or num_envs%2:raise ValueError('Even number>=4 required')
    ec,oc,rc,cc,_=copy.deepcopy(cfgs);ec.update(kp=20.,kd=.5,retest_substeps=2,episode_length_s=20.,termination_if_roll_greater_than=45.,termination_if_pitch_greater_than=45.,clip_joint_targets_to_urdf=True,enforce_urdf_torques=True,joint_target_margin_rad=.12);cc.update(lin_vel_x_range=[.25,.25],lin_vel_y_range=[0.,0.],ang_vel_range=[0.,0.]);rc['reward_scales'].update(training_cfg['additional_reward_scales'])
    ec['training_joint_guard_margin_rad']=training_cfg.get('joint_guard_margin_rad',0.)
    terrain=verify_heightfield(terrain_path);groups=[]
    for kind,data in (('FLAT',None),('ROLLING_UNEVEN',terrain)):
        child_ec=copy.deepcopy(ec);child_ec['surface_kind']=kind
        groups.append(TrainingEnv(num_envs//2,child_ec,copy.deepcopy(oc),copy.deepcopy(rc),copy.deepcopy(cc),terrain=data,auto_reset=True,record=False))
    env=MixedVecEnv(*groups);env.cfg.update(training_reward_version=training_cfg['reward_version'],additional_reward_scales=training_cfg['additional_reward_scales']);return env,[ec,oc,rc,cc,copy.deepcopy(cfgs[4])]
