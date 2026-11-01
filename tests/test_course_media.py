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

    def test_advanced_but_unverified_scene_is_not_captured_with_previous_time(self):
        class Recorder:
            def capture(self,*a,**kw):raise AssertionError('Unverified physical scene must not be rendered')
        result=m.final_capture(Recorder(),{},[{'time_s':.02}],current_sim_s=.03)
        self.assertFalse(result['terminal_snapshot_verified'])
        self.assertEqual(result['last_verified_sim_s'],.02)
        self.assertEqual(result['terminal_physics_time_s'],.03)

    def test_no_initial_measurements_have_explicit_unavailable_terminal_evidence(self):
        result=m.final_capture(None,{},[],current_sim_s=0.)
        self.assertFalse(result['terminal_snapshot_verified'])
        self.assertIsNone(result['last_verified_sim_s'])

    def test_valid_state_without_recorder_is_not_a_verified_snapshot(self):
        result=m.final_capture(None,{},[{'time_s':.02}],current_sim_s=.02)
        self.assertFalse(result['terminal_snapshot_verified'])

    def test_partial_terminal_camera_set_is_not_reported_as_complete(self):
        class Recorder:
            records=[{'view':'side','simulation_time_s':.02}]
            def capture(self,*a,**kw):pass
        cameras={v:SimpleNamespace(set_pose=lambda **kw:None) for v in ('side','oblique','overhead')}
        state=dict(time_s=.02,x_m=0.,y_m=0.,height_m=.4)
        self.assertFalse(m.final_capture(Recorder(),cameras,[state],.02)['terminal_snapshot_verified'])

    def test_verified_terminal_capture_retains_actual_time_for_all_views(self):
        class Recorder:
            records=[]
            def capture(self,cameras,t,state,terminal):
                self.records=[{'view':v,'simulation_time_s':t} for v in cameras]
        cameras={v:SimpleNamespace(set_pose=lambda **kw:None) for v in ('side','oblique','overhead')}
        state=dict(time_s=.03,x_m=0.,y_m=0.,height_m=.4);rec=Recorder()
        result=m.final_capture(rec,cameras,[state],.03)
        self.assertTrue(result['terminal_snapshot_verified'])
        self.assertEqual({r['simulation_time_s'] for r in rec.records},{.03})
