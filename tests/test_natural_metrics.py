import sys
import unittest
from pathlib import Path
from go2_ppo.natural_metrics import complete_swings, point_velocity, assess

class NaturalMeasurements(unittest.TestCase):
    def test_only_complete_swings_and_no_chatter_filter(self):
        # Starts airborne and ends airborne: both incomplete intervals are excluded.
        t=[2+i*.02 for i in range(10)]
        c=[False,True,False,True,False,False,True,True,False,False]
        h=[.1,0,.001,0,.01,.025,0,0,.1,.1]
        s=complete_swings(t,c,h)
        self.assertEqual(len(s),2)
        self.assertEqual(s[0]["peak_m"],.001)
        self.assertEqual(s[1]["peak_m"],.025)
        self.assertAlmostEqual(s[0]["duration_s"],.02)

    def test_rolling_sphere_contact_differs_from_center(self):
        v=point_velocity([.25,0,0],[0,12.5,0],[0,0,-.02])
        self.assertAlmostEqual(v[0],0)
        self.assertAlmostEqual(v[1],0)

    def test_rotating_contact_has_horizontal_slip(self):
        v=point_velocity([0,0,0],[0,0,2],[.1,0,0])
        self.assertAlmostEqual(v[1],.2)

    def test_early_fall_is_failed_not_nan_or_exception(self):
        rows=[]
        for t in [0,.02]:
            r={"time_s":t,"distance_m":0,"fallen":t>0,"height_m":.1,"roll_deg":60,
               "pitch_deg":0,"world_vx_m_s":0,"unexpected_floor_contact":False}
            for leg in ("FL","FR","RL","RR"):
                r.update({leg+"_contact":False,leg+"_clearance_m":0,leg+"_slip_m_s":0})
            rows.append(r)
        import json
        p=Path(__file__).resolve().parents[1]/"configs/natural-gait.json"
        result=assess(rows,json.loads(p.read_text()),{"joint_limits_rad":{}})
        self.assertFalse(result["numeric_pass"])
        self.assertFalse(result["numeric_gates"]["A"])
        self.assertFalse(result["numeric_gates"]["B"])
        json.dumps(result,allow_nan=False)

if __name__=="__main__":
    unittest.main()
