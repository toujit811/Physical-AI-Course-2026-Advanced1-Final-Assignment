"""Stage 0 measurement rules; no simulator or learning dependency."""
import math
import statistics


def tilt_degrees(quaternion_wxyz):
    w, x, y, z = quaternion_wxyz
    norm = math.sqrt(w*w+x*x+y*y+z*z)
    if not math.isfinite(norm) or norm == 0:
        raise ValueError("Invalid base quaternion")
    w, x, y, z = (q/norm for q in (w,x,y,z))
    return (math.degrees(math.atan2(2*(w*x+y*z), 1-2*(x*x+y*y))),
            math.degrees(math.asin(max(-1, min(1, 2*(w*y-z*x))))))


def fallen(height, roll, pitch, minimum_height, angle_limit):
    return height < minimum_height or abs(roll) > angle_limit or abs(pitch) > angle_limit


def summarize(rows, config):
    if not rows:
        return {"standing_passed": False, "reason": "no measurements"}
    tail = [r for r in rows if r["time_s"] >= config["duration_s"]-config["tail_s"]]
    if not tail:
        tail = rows[-1:]
    complete = rows[-1]["time_s"] >= config["duration_s"] - 1e-8
    result = {
        "completed_simulation_s": rows[-1]["time_s"], "samples": len(rows),
        "height_min_m": min(r["height_m"] for r in rows),
        "height_max_m": max(r["height_m"] for r in rows),
        "roll_abs_max_deg": max(abs(r["roll_deg"]) for r in rows),
        "pitch_abs_max_deg": max(abs(r["pitch_deg"]) for r in rows),
        "ever_fallen": any(r["fallen"] for r in rows),
        "tail_height_mean_m": statistics.mean(r["height_m"] for r in tail),
        "tail_height_std_m": statistics.pstdev(r["height_m"] for r in tail),
        "tail_joint_error_max_rad": max(r["joint_error_max_rad"] for r in tail),
        "tail_mean_support_feet": statistics.mean(r["support_feet"] for r in tail),
    }
    result["standing_passed"] = bool(
        complete and not result["ever_fallen"]
        and result["tail_height_std_m"] <= config["max_tail_height_std_m"]
        and result["tail_joint_error_max_rad"] <= config["max_joint_error_rad"]
        and result["tail_mean_support_feet"] >= config["min_mean_support_feet"])
    return result
