import sys,unittest
from pathlib import Path
import torch
from go2_ppo.stage2_boundary import query_points
class BoundaryTests(unittest.TestCase):
    def test_foot_outside_ends_environment_while_inside_unchanged(self):
        points=torch.tensor([[[0.,0.],[1.,1.03473]],[[.2,.3],[.5,-.2]]])
        bounded,outside=query_points(points,(-1.,7.,-1.,1.))
        self.assertEqual(outside.tolist(),[True,False])
        self.assertLessEqual(bounded[0,1,1].item(),1.)
        self.assertTrue(torch.equal(bounded[1],points[1]))
        self.assertGreater(points[0,1,1].item(),1.)
    def test_nonfinite_state_is_not_hidden(self):
        with self.assertRaises(FloatingPointError):
            query_points(torch.tensor([[[float("nan"),0.]]]),(-1.,7.,-1.,1.))
if __name__=="__main__":unittest.main()
