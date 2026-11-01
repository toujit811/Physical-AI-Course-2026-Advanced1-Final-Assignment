"""Pure measurements for the immutable, project-specific natural-gait gate."""
import math

def point_velocity(v, omega, r):
    return [v[0]+omega[1]*r[2]-omega[2]*r[1],
            v[1]+omega[2]*r[0]-omega[0]*r[2],
            v[2]+omega[0]*r[1]-omega[1]*r[0]]

def complete_swings(times, contacts, heights):
    swings=[]
    start=None
    for i in range(1,len(times)):
        if contacts[i-1] and not contacts[i]:
            start=i
        elif not contacts[i-1] and contacts[i] and start is not None:
            swings.append({"start_s":times[start], "end_s":times[i],
                           "duration_s":times[i]-times[start], "peak_m":max(heights[start:i])})
            start=None
    return swings

def assess(rows, protocol, audit):
    import numpy as np
    t=np.array([r["time_s"] for r in rows])
    settled=t>=protocol["settle_s"]
    def values(k):return np.array([r[k] for r in rows])
    end=rows[-1]
    A=end["time_s"]>=protocol["duration_s"]-1e-8 and end["distance_m"]>=protocol["target_distance_m"] and not any(r["fallen"] for r in rows)
    stability={"height_std_m":float(values("height_m")[settled].std()) if settled.any() else None}
    B=bool(settled.any()) and stability["height_std_m"]<=protocol["height_std_max_m"]
    for axis in ("roll","pitch"):
        x=values(axis+"_deg")[settled]
        stability[axis+"_rms_deg"]=float(np.sqrt(np.mean(x*x))) if len(x) else None
        stability[axis+"_abs_max_deg"]=float(np.max(np.abs(x))) if len(x) else None
        B=B and bool(len(x)) and stability[axis+"_rms_deg"]<=protocol["tilt_rms_max_deg"] and stability[axis+"_abs_max_deg"]<=protocol["tilt_abs_max_deg"]
    stability["unexpected_floor_contact"]=any(r["unexpected_floor_contact"] for r in rows)
    B=B and not stability["unexpected_floor_contact"]
    legs={}
    C=D=True
    for leg in ("FL","FR","RL","RR"):
        contacts=values(leg+"_contact").astype(bool)
        height=values(leg+"_clearance_m")
        swings=complete_swings(t[settled].tolist(),contacts[settled].tolist(),height[settled].tolist())
        passed=sum(s["peak_m"]>=protocol["swing_height_min_m"] for s in swings)
        ratio=passed/len(swings) if swings else 0.
        speeds=values(leg+"_slip_m_s")[settled&contacts]
        median=float(np.median(speeds)) if len(speeds) else None
        C=C and len(swings)>=protocol["swing_count_min"] and ratio>=protocol["swing_passing_fraction"]
        D=D and median is not None and median<=protocol["stance_slip_median_max_m_s"]
        # Keep all chatter and label its duration; no threshold-based deletion.
        legs[leg]={"swing_count":len(swings),"swing_height_pass_fraction":ratio,
                   "swing_peak_max_m":max((s["peak_m"] for s in swings),default=None),
                   "swings":swings,"stance_slip_median_m_s":median,
                   "stance_samples":len(speeds),
                   "stance_movement_m":float(np.sum(speeds)*.02),
                   "stance_duration_s":len(speeds)*.02,
                   "contact_transitions":int(np.count_nonzero(contacts[1:]!=contacts[:-1]))}
    joints={}
    E=True
    for n,limits in audit["joint_limits_rad"].items():
        q=values(n+"_position_rad"); target=values(n+"_target_rad");torque=values(n+"_control_Nm")
        excess=np.maximum(np.maximum(limits[0]-q,q-limits[1]),0)
        target_excess=np.maximum(np.maximum(limits[0]-target,target-limits[1]),0)
        i=audit["names"].index(n);limit=audit["urdf_effort_limits"][i]
        peak=float(np.max(excess)); tar=float(np.max(target_excess));tau=float(np.max(np.abs(torque)))
        E=E and peak<=protocol["actual_joint_excursion_max_rad"] and tar<=1e-7 and tau<=limit+1e-4
        joints[n]={"actual_excursion_rad":peak,"target_excursion_rad":tar,"max_torque_Nm":tau,
                   "max_excursion_time_s":float(t[int(np.argmax(excess))])}
    return {"numeric_gates":{"A":bool(A),"B":bool(B),"C":bool(C),"D":bool(D),"E":bool(E)},
            "numeric_pass":bool(A and B and C and D and E),"visual_gate_F":"requires human review of both unedited videos",
            "stability":stability,"legs":legs,"joints":joints,"distance_m":end["distance_m"],
            "duration_s":end["time_s"],"mean_speed_m_s":end["distance_m"]/end["time_s"] if end["time_s"] else 0,
            "tracking_rmse_m_s":float(np.sqrt(np.mean((values("world_vx_m_s")-.25)**2)))}
