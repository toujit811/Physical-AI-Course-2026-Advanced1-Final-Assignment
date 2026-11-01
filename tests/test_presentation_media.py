import unittest
import tempfile
from pathlib import Path
import numpy as np
from PIL import Image
from go2_ppo import presentation_media as m
from go2_ppo.presentation import analyse_trial
from test_presentation import samples,historical,camera


class PresentationMediaTests(unittest.TestCase):
    def test_api_is_present(self):
        self.assertTrue(all(callable(getattr(m,n,None)) for n in ('make_layout','compose','validate_frame')))

    def test_raw_image_is_preserved_and_fixed_hud_does_not_cover_it(self):
        rgb=np.random.default_rng(1).integers(0,256,(360,640,3),dtype=np.uint8)
        terrain={'x':np.array([-1.,7.]),'y':np.array([-1.3,1.3]),'height_m':np.zeros((2,2))}
        layout=m.make_layout(terrain)
        goal=analyse_trial(samples([0,1,2,4.1,4.2]),historical(),[])
        state=dict(x_m=0.,y_m=0.,height_m=.42,time_s=0.,physical_fallen=False,out_of_terrain=False)
        image,audit=m.compose(layout,rgb,'side',0.,state,goal,camera(), 'synthetic-test')
        expected=np.asarray(Image.fromarray(rgb).resize((832,468),Image.Resampling.LANCZOS))
        np.testing.assert_array_equal(np.asarray(image)[70:538,224:1056],expected)
        self.assertEqual(audit['baseline_y_px'],43.)

    def test_source_frame_mapping_rejects_wrong_time_hash_and_position(self):
        state=dict(x_m=0.,y_m=0.,height_m=.42)
        frame=dict(frame=0,view='side',simulation_time_s=0.,video_pts_s=0.,base_x_m=0.,base_y_m=0.,base_z_m=.42,raw_png_sha256='abc')
        cal=dict(frame=0,view='side',simulation_time_s=0.,video_pts_s=0.,base_position_m=[0.,0.,.42],raw_png_sha256='abc',**camera())
        m.validate_frame(frame,cal,state,'abc')
        for key,value in [('simulation_time_s',.01),('raw_png_sha256','bad'),('base_x_m',.1)]:
            bad=dict(frame);bad[key]=value
            with self.assertRaises(ValueError):m.validate_frame(bad,cal,state,'abc')

    def test_recorded_section_uses_real_approved_npz_z_m_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'heightfield.npz'
            x=np.array([-1.,7.]);y=np.array([-1.3,1.3]);z=np.array([[0.,.01],[.02,.03]])
            np.savez(path,x_m=x,y_m=y,z_m=z,slope_deg=np.zeros_like(z))
            terrain=dict(x=x,y=y,height_m=z)
            m.validate_terrain(terrain,'ROLLING_UNEVEN',path)
            terrain['height_m']=z+.001
            with self.assertRaises(ValueError):m.validate_terrain(terrain,'ROLLING_UNEVEN',path)
