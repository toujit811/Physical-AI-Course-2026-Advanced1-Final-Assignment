import sys,unittest
from pathlib import Path
import numpy as np
from go2_ppo.xz_colour import height_rgb,normalised_indices,colour_panel,lut_rgb
from go2_ppo.xz_profile import plot_pixels
from go2_ppo.stage2_visual_diagnostic import texture_rgb

class ElevationColourTests(unittest.TestCase):
    def test_lut_matches_existing_terrain_source_at_every_height_bin(self):
        h=np.linspace(-.012,.04,2049,dtype=np.float32)
        np.testing.assert_array_equal(height_rgb(h),texture_rgb(h[:,None])[0])
        np.testing.assert_array_equal(height_rgb(h),lut_rgb()[normalised_indices(h)[1]])
    def test_flat_zero_is_same_rgb_and_visible_on_contour(self):
        x=np.linspace(-1,7,321);z=np.zeros_like(x);im=np.asarray(colour_panel(x,z,None));_,y=plot_pixels(0,0)
        np.testing.assert_array_equal(im[int(y),300:1100,:],np.broadcast_to(height_rgb(np.array(0.)),(800,3)))
    def test_height_range_is_fixed_not_scaled_per_trial(self):
        sample=np.array([0.,.01,.025],np.float32)
        alone=height_rgb(sample);larger=height_rgb(np.r_[-.012,sample,.04])[1:4]
        np.testing.assert_array_equal(alone,larger)
        self.assertEqual(normalised_indices(np.array([-.012,.04],np.float32))[1].tolist(),[0,255])
    def test_profile_has_many_colours_for_nonflat_heights(self):
        x=np.array([-1.,1.,3.,7.]);z=np.array([0.,-.01,.025,0.])
        im=np.asarray(colour_panel(x,z,41001))
        self.assertGreater(len(np.unique(height_rgb(z),axis=0)),2)
        self.assertGreater(len(np.unique(im[562:668,94:1250].reshape(-1,3),axis=0)),30)

if __name__=='__main__':unittest.main()
