import json,csv,hashlib
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation
from go2_ppo.go2_kinematics import Go2Kinematics
from go2_ppo.rolling_approved_source import verify_heightfield
from go2_ppo.rolling_native_audit import _surface
C=Path(__file__).resolve().parents[1];k=Go2Kinematics();terrain=verify_heightfield(C/'assets/approved/heightfield.npz');angle=np.arange(128)*2*np.pi/128;zz=np.linspace(-.015,.015,17);local=np.array([[.0155*np.cos(a),.0155*np.sin(a),z] for z in zz for a in angle]);out=[]
for cond,tm in [(0,15.31),(1,14.68)]:
 d=C/f'logs/rolling-native/validation-D13550-ROLLING_UNEVEN-c{cond}';rows=list(csv.DictReader((d/'states.csv').open()));near=[r for r in rows if abs(float(r['time_s'])-tm)<.031]
 for r in near:
  qs={leg:[float(r[f'{leg}_{j}_joint_position_rad']) for j in ['hip','thigh','calf']] for leg in k.legs};R,p=k.transforms(qs)['FL_calflower1'];quat=np.array(json.loads(r['quaternion_wxyz']));B=Rotation.from_quat(quat[[1,2,3,0]]).as_matrix();base=np.array([float(r[a]) for a in ['x_m','y_m','height_m']]);points=(local@R.T+p)@B.T+base;support=_surface(terrain['x'],terrain['y'],terrain['height_m'],points[:,:2]);gap=points[:,2]-support;idx=int(np.argmin(gap));v={'condition':cond,'time_s':float(r['time_s']),'URDF_link':'FL_calflower1','native_merged_link':'FL_calf','native_geom':9,'sampled_cylinder_min_vertical_gap_m':float(gap[idx]),'min_point_world_m':points[idx].tolist(),'FL_foot_clearance_m':float(r['FL_clearance_m']),'FL_contact':r['FL_contact'],'FL_positive_contact':r['FL_positive_force_contact'],'roll_deg':float(r['roll_deg']),'pitch_deg':float(r['pitch_deg']),'q':[float(r[f'FL_{j}_joint_position_rad']) for j in ['hip','thigh','calf']],'qdot':[float(r[f'FL_{j}_joint_velocity_rad_s']) for j in ['hip','thigh','calf']],'target':[float(r[f'FL_{j}_joint_target_rad']) for j in ['hip','thigh','calf']]};out.append(v)
r={'method':'Independent URDF fixed-joint transforms + actual recorded body quaternion,128angularx17axial finite-cylinder surface samples, native anti-diagonal quantized terrain. Not an exact continuous collision proof.','physics_dt_s':.01,'control_dt_s':.02,'contact_pose_lag_s':.01,'records':out};(C/('reports/generated/issue3-diagnostic-'+__import__('datetime').datetime.now().strftime('%Y%m%d-%H%M%S')+'.json')).write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
