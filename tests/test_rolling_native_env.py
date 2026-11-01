"""No native scenes: approved-grid wiring, controller bounds and 45D observations."""
import sys,unittest,os
os.environ.setdefault("NUMBA_CACHE_DIR","/private/tmp/rolling-native-env-numba")
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
import torch
from go2_ppo import rolling_native_env as env

class RollingNativeEnvTests(unittest.TestCase):
 def test_mm_terrain_wiring_preserves_samples_and_explicit_units(self):
  mm=np.arange(161*53,dtype=np.int16).reshape(161,53);t={'height_mm':mm,'height_m':mm.astype(float)*.001};s=env.terrain_options(t)
  self.assertIs(s['height_field'],mm);self.assertEqual(s['horizontal_scale'],.05);self.assertEqual(s['vertical_scale'],.001);self.assertEqual(s['pos'],(-1.,-1.3,0.))
  with self.assertRaises(ValueError):env.terrain_options({'height_mm':mm.astype(float)})
  with self.assertRaises(ValueError):env.terrain_options({'height_mm':mm.T})
 def test_camera_specs_are_three_native_views_and_true_side(self):
  specs=env.camera_options(-.4);self.assertEqual(set(specs),{'side','oblique','overhead'})
  for s in specs.values():self.assertEqual(s['res'],(640,360))
  s=specs['side'];self.assertEqual(s['pos'][0],s['lookat'][0]);self.assertEqual(s['pos'][2],s['lookat'][2]);self.assertEqual(s['up'],(0.,0.,1.));self.assertEqual(s['pos'][1],-3.)
 def test_quality_config_copies_and_preserves_initial_pose_and_substeps(self):
  c={'base_init_pos':[-.4,.02,.42],'base_init_quat':[1,0,0,0],'retest_substeps':8,'kp':20,'kd':.5};q=env.quality_configuration(c)
  self.assertEqual(c['base_init_pos'],q['base_init_pos']);self.assertEqual(q['retest_substeps'],8);self.assertNotIn('enforce_urdf_torques',c);self.assertTrue(q['enforce_urdf_torques']);self.assertTrue(q['clip_joint_targets_to_urdf']);self.assertEqual(q['joint_target_margin_rad'],.12)
  self.assertNotIn('retest_substeps',env.quality_configuration({'kp':20,'kd':.5}))
 def test_existing_observation_remains_45_dimensions_and_action_history(self):
  q=torch.arange(12).reshape(1,12).float();s=SimpleNamespace(base_ang_vel=torch.ones(1,3),projected_gravity=torch.ones(1,3),commands=torch.ones(1,3),commands_scale=torch.ones(3),dof_pos=q,default_dof_pos=torch.zeros(12),dof_vel=q+1,actions=q+2,obs_scales={'ang_vel':1,'dof_pos':1,'dof_vel':1})
  env._TerrainGo2Env._update_observation(s);self.assertEqual(tuple(s.obs_buf.shape),(1,45));torch.testing.assert_close(s.obs_buf[:,-12:],q+2)
 def test_bounded_actions_are_applied_without_mutating_caller(self):
  e=env.QualityEnv.__new__(env.QualityEnv);e.num_envs=1;e.device='cpu';e.env_cfg={'clip_joint_targets_to_urdf':True};e.action_lower=torch.full((12,),-.5);e.action_upper=torch.full((12,),.5);a=torch.ones(1,12)
  with patch.object(env._TerrainGo2Env,'step',lambda self,x:x):out=e.step(a)
  torch.testing.assert_close(out,torch.full((1,12),.5));torch.testing.assert_close(a,torch.ones(1,12))

if __name__=='__main__':unittest.main()
