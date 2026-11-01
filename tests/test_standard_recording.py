import sys,unittest
from pathlib import Path
import numpy as np
from go2_ppo import standard_recording as s

class StandardRecordingTests(unittest.TestCase):
    def setUp(self):self.assertTrue(callable(getattr(s,'section_raster',None)),'Common standard recording feature absent')
    def test_same_pixel_z_same_colour_across_x_inside_real_surface(self):
        x=np.linspace(-1,7,321);z=np.interp(x,[-1,1,3,7],[0,-.01,.025,0]);a=s.section_raster(x,z)
        from go2_ppo.xz_colour import height_rgb
        for row in [20,80,100]:
            mask=a['mask'][row];expected=height_rgb(np.array(a['pixel_z_m'][row]));np.testing.assert_array_equal(a['rgb'][row,mask],np.broadcast_to(expected,(mask.sum(),3)))
        self.assertTrue((a['mask'].sum(axis=0)>0).all())
    def test_fill_excludes_air_above_contour(self):
        x=np.linspace(-1,7,321);z=np.zeros_like(x);a=s.section_raster(x,z)
        self.assertFalse(a['mask'][a['pixel_z_m']>0].any());self.assertTrue(a['mask'][a['pixel_z_m']<0].all())
    def test_negative_depth_and_colour_clamping_keep_fixed_global_lut(self):
        from go2_ppo.xz_colour import height_rgb
        np.testing.assert_array_equal(height_rgb(np.array(-.015)),height_rgb(np.array(-.012)))
        a=s.section_raster(np.array([-1.,7.]),np.array([-.01,.025]));self.assertEqual(a['rgb'].shape,(107,1157,3))
    def test_default_shared_configuration_and_flat_zero(self):
        cfg=s.load_standard();self.assertEqual(cfg['minor_tick_m'],.5);self.assertEqual(cfg['viridis_z_cm'],[-1.2,4.])
        t=s.VideoTemplate();self.assertEqual(float(np.max(abs(t.z))),0.);self.assertEqual(t.definition['physical_height_multiplier'],1.)
    def test_common_recorder_two_views_real_saved_frames_and_preserves_clean(self):
        import tempfile
        from PIL import Image
        from go2_ppo.video_materials import inspect_video
        camera=self.camera_fixture();rgb=np.full((360,640,3),128,dtype=np.uint8)
        with tempfile.TemporaryDirectory() as td:
            r=s.StandardRecorder(td)
            try:
                for i in range(3):
                    for view in ['side','oblique']:
                        r.append(view,rgb,camera,i/25,[i*.01,0.,.3])
                        np.testing.assert_array_equal(rgb,np.array(Image.open(Path(td)/('raw-'+view)/f'{i:06d}.png')))
                r.save()
            finally:
                for w in r.writers.values():w.close()
            for name in r.writers:self.assertEqual(inspect_video(Path(td)/(name+'-incomplete.mp4'))['frames'],3)
            self.assertEqual(len(r.records),6);self.assertEqual(len(r.cameras),6)
    @staticmethod
    def camera_fixture():
        from types import SimpleNamespace
        E=np.array([[1,0,0,0],[0,0,-1,.3],[0,1,0,3],[0,0,0,1]],dtype=float)
        return SimpleNamespace(intrinsics=np.array([[600,0,320],[0,600,180],[0,0,1]]),extrinsics=E,transform=np.linalg.inv(E)@np.diag([1,-1,-1,1]))
    def test_steep_terrain_fill_audit_separates_surface_stroke_and_zero_line(self):
        t=s.VideoTemplate()
        self.assertTrue(hasattr(t,'audit_mask'),'Fill audit must distinguish contour/zero symbols')
        from go2_ppo.xz_colour import height_rgb
        from go2_ppo.xz_profile import RECT
        l,top,right,b=map(int,RECT);a=np.array(t.background)[top:b+1,l:right+1]
        for row,z in enumerate(t.raster['pixel_z_m']):
            pixels=a[row,t.audit_mask[row]];np.testing.assert_array_equal(pixels,np.broadcast_to(height_rgb(np.array(z)),pixels.shape))
    def test_recorder_video_pts_starts_zero_when_source_clip_starts_later(self):
        import tempfile,json
        from types import SimpleNamespace
        from PIL import Image
        camera=self.camera_fixture()
        with tempfile.TemporaryDirectory() as td:
            r=s.StandardRecorder(td)
            try:
                r.append('side',np.full((360,640,3),128,dtype=np.uint8),camera,7.12,[0.,.01,.3])
                self.assertEqual(r.records[0]['source_time_s'],7.12);self.assertEqual(r.records[0]['video_pts_s'],0.)
                self.assertTrue((Path(td)/'raw-side/000000.png').exists())
            finally:
                for w in r.writers.values():w.close()

if __name__=='__main__':unittest.main()
