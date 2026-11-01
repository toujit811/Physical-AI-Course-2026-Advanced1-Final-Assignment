import unittest,torch
from tensordict import TensorDict
from go2_ppo.mixed_core import MixedVecEnv

class Child:
    def __init__(self,n,value):
        self.num_envs=n;self.num_actions=12;self.device='cpu';self.cfg={};self.max_episode_length=1000;self.episode_length_buf=torch.zeros(n,dtype=torch.long);self.value=value
    def get_observations(self):return TensorDict({'policy':torch.full((self.num_envs,45),float(self.value))},[self.num_envs])
    def reset(self):self.episode_length_buf.zero_();return self.get_observations()
    def step(self,a):
        self.last=a.clone();self.episode_length_buf+=1
        return self.get_observations(),torch.full((self.num_envs,),float(self.value)),torch.full((self.num_envs,),self.value==2),{'time_outs':torch.full((self.num_envs,),float(self.value==2))}

class MixedTests(unittest.TestCase):
    def test_split_actions_join_observations_rewards_dones_and_timeouts(self):
        a,b=Child(2,1),Child(2,2);e=MixedVecEnv(a,b);actions=torch.arange(48).reshape(4,12);o,r,d,x=e.step(actions)
        self.assertEqual(tuple(o['policy'].shape),(4,45));torch.testing.assert_close(a.last,actions[:2]);torch.testing.assert_close(b.last,actions[2:]);self.assertEqual(r.tolist(),[1,1,2,2]);self.assertEqual(d.tolist(),[False,False,True,True]);self.assertEqual(x['time_outs'].tolist(),[0,0,1,1]);self.assertEqual(e.environment_steps,{'FLAT':2,'ROLLING_UNEVEN':2})
    def test_episode_counter_replacement_is_forwarded_to_each_child(self):
        a,b=Child(2,1),Child(2,2);e=MixedVecEnv(a,b);e.episode_length_buf=torch.tensor([1,2,8,9]);self.assertEqual(a.episode_length_buf.tolist(),[1,2]);self.assertEqual(b.episode_length_buf.tolist(),[8,9]);self.assertEqual(e.episode_length_buf.tolist(),[1,2,8,9])
    def test_unequal_halves_and_wrong_action_shape_are_rejected(self):
        with self.assertRaises(ValueError):MixedVecEnv(Child(2,1),Child(3,2))
        e=MixedVecEnv(Child(2,1),Child(2,2))
        with self.assertRaises(ValueError):e.step(torch.zeros(3,12))

if __name__=='__main__':unittest.main()
