"""One policy-facing VecEnv over two independent native Scenes."""
import torch
class MixedVecEnv:
    def __init__(self,flat,rolling):
        if flat.num_envs!=rolling.num_envs:raise ValueError('Initial sampler must have equal50:50 groups')
        self.flat,self.rolling=flat,rolling;self.groups=(flat,rolling);self.half=flat.num_envs;self.num_envs=2*self.half;self.num_actions=12;self.device=flat.device;self.cfg={'sampler':'two_native_scenes_50:50','observation_dimension':45};self.max_episode_length=flat.max_episode_length;self.environment_steps={'FLAT':0,'ROLLING_UNEVEN':0}
    @property
    def episode_length_buf(self):return torch.cat([e.episode_length_buf for e in self.groups])
    @episode_length_buf.setter
    def episode_length_buf(self,value):
        if tuple(value.shape)!=(self.num_envs,):raise ValueError('Episode counter shape')
        for e,v in zip(self.groups,value.split(self.half)):e.episode_length_buf.copy_(v)
    def get_observations(self):return torch.cat([e.get_observations() for e in self.groups],dim=0)
    def reset(self):
        for e in self.groups:e.reset()
        return self.get_observations()
    def step(self,actions):
        if tuple(actions.shape)!=(self.num_envs,12):raise ValueError('Action shape')
        transitions=[e.step(a) for e,a in zip(self.groups,actions.split(self.half))];obs=torch.cat([r[0] for r in transitions],dim=0);reward=torch.cat([r[1] for r in transitions]);done=torch.cat([r[2] for r in transitions]);extras={'time_outs':torch.cat([r[3]['time_outs'] for r in transitions])}
        for kind,e,r in zip(self.environment_steps,self.groups,transitions):
            self.environment_steps[kind]+=e.num_envs
            for key,value in r[3].get('episode',{}).items():extras.setdefault('episode',{})[kind+'/'+key]=value
        return obs,reward,done,extras
