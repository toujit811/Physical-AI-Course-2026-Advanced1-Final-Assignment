import sys,unittest
from pathlib import Path
import numpy as np
from go2_ppo.xz_profile import extract_profile,side_metrics,project_points,plot_pixels,elevation_extrema,framing_bounds

class XZTests(unittest.TestCase):
    def test_close_side_camera_clips_drifted_foot_but_wider_fixed_distance_fits(self):
        K=np.array([[672.,0.,320.],[0.,672.,180.],[0.,0.,1.]])
        points=np.array([[-.65,-.94,0.],[.6,-.94,.6]])
        def at(y):
            T=np.array([[1,0,0,.2],[0,0,-1,y],[0,1,0,.3],[0,0,0,1.]])
            E=T.copy();E[:3,1:3]*=-1
            return framing_bounds(points,K,np.linalg.inv(E),(640,360))
        self.assertFalse(at(-2.)['inside'])
        self.assertTrue(at(-3.)['inside'])
    def test_height_depth_extents_and_flat_positive_zero(self):
        ext=elevation_extrema(np.array([-.011,.025]))
        self.assertAlmostEqual(ext['height_cm'],2.5);self.assertAlmostEqual(ext['depth_cm'],1.1)
        flat=elevation_extrema(np.zeros(3))
        self.assertEqual(flat,{'height_cm':0.,'depth_cm':0.})
        self.assertFalse(np.signbit(flat['depth_cm']))
    def test_flat_is_exact_zero_everywhere(self):
        t={'x':np.linspace(-1,7,321),'y':np.linspace(-1,1,81),'height_m':np.zeros((321,81),np.float32)}
        x,z=extract_profile(t,0.)
        np.testing.assert_array_equal(x,t['x']);np.testing.assert_array_equal(z,np.zeros_like(x))
    def test_triangle_diagonal_kink_is_not_faked_by_linear_grid_only(self):
        t={'x':np.array([0.,1.]),'y':np.array([0.,1.]),'height_m':np.array([[0.,0.],[0.,1.]])}
        x,z=extract_profile(t,.25)
        np.testing.assert_allclose(x,[0.,.75,1.]);np.testing.assert_allclose(z,[0.,0.,.25])
    def test_negative_depth_and_fixed_y_are_preserved(self):
        t={'x':np.array([0.,1.,2.]),'y':np.array([-1.,0.,1.]),'height_m':np.array([[0,-.01,.01],[0,.02,.04],[0,0,.02]])}
        x,z=extract_profile(t,0.)
        np.testing.assert_allclose(z,[-.01,.02,0.])
        self.assertNotEqual(z[1],t['height_m'][1,2])
    def test_true_side_basis_is_horizontal_and_projects_zero_plane_horizontally(self):
        T=np.array([[1,0,0,1.],[0,0,-1,-2.],[0,1,0,.3],[0,0,0,1.]])
        m=side_metrics(T);self.assertEqual(m['tilt_deg'],0.);self.assertEqual(m['angle_to_world_x_deg'],90.)
        E=T.copy();E[:3,1:3]*=-1;E=np.linalg.inv(E)
        uv=project_points(np.array([[0.,0.,0.],[1.,0.,0.],[2.,0.,0.]]),np.array([[300.,0.,320.],[0.,300.,180.],[0.,0.,1.]]),E)
        self.assertEqual(np.ptp(uv[:,1]),0.)
        self.assertTrue(np.all(np.diff(uv[:,0])>0))
    def test_plot_units_and_zero_line(self):
        px,pz=plot_pixels(np.array([-1.,7.]),np.array([0.,0.]))
        np.testing.assert_allclose(px,[94.,1250.]);self.assertEqual(pz[0],pz[1])

if __name__=='__main__':unittest.main()
