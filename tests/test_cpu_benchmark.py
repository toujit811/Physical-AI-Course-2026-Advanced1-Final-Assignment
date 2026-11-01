import sys,unittest
from pathlib import Path
from go2_ppo.cpu_benchmark_metrics import vector_steps,speed,paired_improvement,summarize

class EqualWorkTests(unittest.TestCase):
    def test_equal_experience_has_different_vector_steps(self):
        self.assertEqual(vector_steps(196608,64),3072);self.assertEqual(vector_steps(196608,128),1536)
        self.assertEqual(vector_steps(196608,64)*64,vector_steps(196608,128)*128)
    def test_rejects_non_equal_batch_or_unrequested_scale(self):
        for n,t in [(256,196608),(64,1000),(128,0)]:
            with self.assertRaises(ValueError):vector_steps(t,n)
    def test_env_steps_per_second_is_not_vector_steps_per_second(self):self.assertEqual(speed(196608,8),24576)
    def test_paired_changes_and_uncertainty(self):
        a=paired_improvement([(100,110),(100,120),(100,130)])
        self.assertAlmostEqual(a['mean'],20);self.assertAlmostEqual(a['sd'],10);self.assertLess(a['ci95_lower_percent'],5)
        self.assertAlmostEqual(summarize([10,10,10])['cv_percent'],0)

if __name__=='__main__':unittest.main()
