import sys,unittest
from pathlib import Path
import torch
from go2_ppo.natural_rewards import contact_slip_cost

class SlipRewardTests(unittest.TestCase):
    def test_rolling_contact_and_airborne_are_not_penalized(self):
        origin=torch.tensor([[[0.,0.,.02],[1.,0.,.02]]])
        vel=torch.tensor([[[.25,0.,0.],[50.,0.,0.]]])
        omega=torch.tensor([[[0.,12.5,0.],[0.,0.,0.]]])
        points=torch.tensor([[[0.,0.,0.],[1.,0.,0.]]])
        mask=torch.tensor([[[True,False],[False,False]]])
        self.assertAlmostEqual(contact_slip_cost(origin,vel,omega,points,mask).item(),0)
    def test_translation_at_actual_contact_costs_squared_slip(self):
        origin=torch.zeros((1,1,3));v=torch.tensor([[[.1,0.,0.]]]);w=torch.zeros_like(v)
        points=torch.zeros((1,2,3));mask=torch.tensor([[[True],[True]]])
        self.assertAlmostEqual(contact_slip_cost(origin,v,w,points,mask).item(),.01,places=6)
    def test_invalid_padded_contacts_do_not_propagate_nan(self):
        origin=torch.zeros((1,1,3));points=torch.full((1,1,3),float("nan"))
        self.assertEqual(contact_slip_cost(origin,origin,origin,points,torch.zeros((1,1,1),dtype=torch.bool)).item(),0)
if __name__=="__main__":unittest.main()
