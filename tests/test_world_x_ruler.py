import sys,unittest
from pathlib import Path
import numpy as np
from go2_ppo import world_x_ruler as ruler

def camera(x):
    return dict(side_intrinsics=[[600,0,320],[0,600,180],[0,0,1]],side_extrinsics=[[1,0,0,-x],[0,0,-1,.3],[0,1,0,3],[0,0,0,1]])

class WorldXRulerTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(all(callable(getattr(ruler,n,None)) for n in ['project_x','motion','tick_values','is_major','crossings','lower_axis']),'World-coordinate ruler feature is absent')
    def test_projection_includes_pixel_center_resize(self):
        uv=ruler.project_x(np.array([0.,.5,1.]),camera(.2))
        np.testing.assert_allclose(uv[:,0],[588.15,718.15,848.15],atol=1e-12)
        np.testing.assert_allclose(uv[:,1],np.full(3,356.15),atol=1e-12)
    def test_world_tick_flows_left_when_camera_advances_and_right_on_reverse(self):
        a=ruler.project_x(np.array([0.,1.]),camera(.2));b=ruler.project_x(np.array([0.,1.]),camera(.7))
        np.testing.assert_allclose(b[:,0]-a[:,0],[-130.,-130.],atol=1e-12)
        np.testing.assert_allclose(a[:,0]-b[:,0],[130.,130.],atol=1e-12)
    def test_world_position_is_distinct_from_nonzero_start_displacement(self):
        v=ruler.motion(1.7,1.2,1.6)
        self.assertEqual(v['world_x_m'],1.7);self.assertAlmostEqual(v['delta_x_m'],.5)
        self.assertEqual(v['direction'],'forward');self.assertEqual(ruler.motion(1.5,1.2,1.6)['direction'],'backward')
    def test_half_metre_ticks_and_integer_major_labels_are_world_values(self):
        ticks=ruler.tick_values();np.testing.assert_allclose(np.diff(ticks),.5)
        self.assertEqual([x for x in ticks if ruler.is_major(x)],list(range(-1,8)))
    def test_crossing_is_bracketed_and_interpolation_is_labelled(self):
        events=ruler.crossings([0.,.02,.04],[1.2,1.6,1.4],[1.5])
        self.assertEqual([e['direction'] for e in events],['forward','backward'])
        self.assertAlmostEqual(events[0]['linear_estimate_s'],.015)
        self.assertEqual(events[0]['bracket_start_s'],0.);self.assertEqual(events[0]['bracket_end_s'],.02)
    def test_lower_half_ticks_leave_elevation_contour_and_fill_untouched(self):
        from go2_ppo.xz_colour import colour_panel
        from go2_ppo.xz_profile import plot_pixels
        x=np.linspace(-1,7,321);z=np.zeros_like(x);before=np.asarray(colour_panel(x,z,None));after=np.asarray(ruler.lower_axis(colour_panel(x,z,None)))
        np.testing.assert_array_equal(before[562:668],after[562:668])
        xx,_=plot_pixels(.5,0);self.assertFalse(np.array_equal(before[670,int(xx)],after[670,int(xx)]))

if __name__=='__main__':unittest.main()
