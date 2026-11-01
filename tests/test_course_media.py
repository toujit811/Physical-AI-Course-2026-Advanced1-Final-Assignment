import unittest
from types import SimpleNamespace
from go2_ppo import course_media as m


class CourseMediaTests(unittest.TestCase):
    def test_api(self):self.assertTrue(all(callable(getattr(m,n,None)) for n in ('camera_poses','course_timeline','CourseRecorder')))

    def test_camera_world_z_does_not_follow_robot_height(self):
        a=m.camera_poses([0,0,.3]);b=m.camera_poses([6,.2,.5])
        for view in ('side','oblique','overhead'):
            self.assertEqual(a[view]['pos'][2],b[view]['pos'][2])
            self.assertEqual(a[view]['lookat'][2],b[view]['lookat'][2])
        self.assertEqual(a['side']['pos'][0],a['side']['lookat'][0])
        self.assertEqual(a['side']['pos'][2],a['side']['lookat'][2])

    def test_no_source_frames_cut_and_offgrid_terminal_snapshot_is_explicit(self):
        t=m.course_timeline([0,.04,.07])
        self.assertEqual(len(t),53);self.assertEqual(t[2]['simulation_time_s'],.07)
        self.assertEqual(t[2]['video_pts_s'],.08);self.assertEqual(t[2]['kind'],'terminal_real_snapshot')
        self.assertIsNone(t[3]['simulation_time_s']);self.assertEqual(t[3]['video_pts_s'],.12)
        with self.assertRaises(ValueError):m.course_timeline([0,.04,.03])

    def test_an_interior_missing_25fps_frame_cannot_be_hidden(self):
        with self.assertRaises(ValueError):m.course_timeline([0,.08,.12])

    def test_last_snapshot_cannot_hide_a_missing_scheduled_frame(self):
        with self.assertRaises(ValueError):m.course_timeline([0,.08])

    def test_visual_gate_is_not_filtered_out_by_native_camera_marker_filter(self):
        mesh=SimpleNamespace(is_marker=True)
        self.assertIs(m.show_gate_in_native_camera(mesh),mesh)
        self.assertFalse(mesh.is_marker)
        with self.assertRaises(TypeError):m.show_gate_in_native_camera(object())
