"""Offline presentation-only goal and saved-camera HUD calculations.

Standard library only. These functions never control a robot, change historical
gates, interpolate poses, or equate video PTS with simulation time.
"""
import copy
import math

FPS = 25
HUD_BASELINE_Y = 43.
RGB_ORIGIN = (224., 70.)
RGB_SCALE = 1.3


def _flag(value):
    if value is True or value == 'True': return True
    if value is False or value == 'False': return False
    raise ValueError('Missing or invalid recorded boolean')


def analyse_trial(states, result, contacts):
    """First *observed* 100Hz crossing; fatal event wins a same-time tie.

The crossing time is the upper sample of a saved bracket, not an invented exact
continuous crossing. No interpolation is needed. Nonfoot contacts, including
zero force, remain historical safety failures and never become a fall.
"""
    summary = dict(goal_distance_m=4., goal_reached=False, first_crossing_sample_s=None,
        crossing_bracket=None, end_reason='UNKNOWN', presentation_end_sim_s=None,
        start_x_m=None, goal_x_m=None, historical_numeric_pass=result.get('numeric_pass'),
        historical_numeric_gates=copy.deepcopy(result.get('numeric_gates')),
        historical_evaluation_sim_s=result.get('duration_s',result.get('terminal_sim_s')),
        historical_status=result.get('status'), F='USER_REVIEW_PENDING',
        nonfoot_events=copy.deepcopy([e for e in contacts if e.get('foot') is False]),
        errors=[], goal_is_presentation_only=True, arrival_time_definition='first observed 100Hz sample; exact crossing lies in saved bracket')
    try:
        typed=[]
        for row in states:
            q={k:float(row[k]) for k in ('time_s','x_m','y_m')}
            if not all(math.isfinite(v) for v in q.values()):raise ValueError('Nonfinite physical state')
            q.update({k:_flag(row[k]) for k in ('fallen','physical_fallen','out_of_terrain','unexpected_floor_contact')})
            typed.append(q)
        if not typed or abs(typed[0]['time_s'])>1e-8:raise ValueError('Missing initial state t=0')
        if any(abs(q['time_s']-i*.01)>1e-7 for i,q in enumerate(typed)):
            raise ValueError('Missing/nonuniform 100Hz physical states')
        summary.update(start_x_m=typed[0]['x_m'],goal_x_m=typed[0]['x_m']+4.,
                       recorded_end_sim_s=typed[-1]['time_s'])
        if result.get('numeric_pass') not in (True,False) or not isinstance(result.get('numeric_gates'),dict):
            raise ValueError('Missing historical numerical-gate result')
        crossing=next((i for i,q in enumerate(typed) if q['x_m']>=summary['goal_x_m']),None)
        fatal=None
        for i,q in enumerate(typed):
            reason='FALL' if q['physical_fallen'] else 'OUT_OF_BOUNDS' if q['out_of_terrain'] else 'UNKNOWN' if q['fallen'] else None
            if reason:fatal=(i,reason);break
        if result.get('status') in ('ERROR','TIMEOUT') or result.get('engine_error') is True:
            terminal=float(result.get('terminal_sim_s',typed[-1]['time_s']))
            idx=next((i for i,q in enumerate(typed) if q['time_s']>=terminal-1e-8),len(typed)-1)
            if fatal is None or idx<fatal[0]:fatal=(idx,'ENGINE_ERROR')
        if fatal and (crossing is None or fatal[0]<=crossing):end,reason=fatal
        elif crossing is not None:
            end,reason=crossing,'GOAL_REACHED';summary['goal_reached']=True
            summary['first_crossing_sample_s']=typed[end]['time_s']
            summary['crossing_bracket']={
                'before':{k:typed[end-1][k] for k in ('time_s','x_m')},
                'at_or_after':{k:typed[end][k] for k in ('time_s','x_m')}}
        else:end,reason=len(typed)-1,'RECORDING_ENDED_WITHOUT_GOAL'
        summary.update(end_reason=reason,presentation_end_sim_s=typed[end]['time_s'],
                       end_sample_x_m=typed[end]['x_m'],progress_at_end_sample_m=typed[end]['x_m']-summary['start_x_m'])
    except (KeyError,ValueError,TypeError) as error:
        summary['errors'].append(str(error))
    return summary


def select_frames(goal, frame_times):
    """Return real source indices through the first frame at/after cutoff."""
    times=[float(v) for v in frame_times]
    if not times or any(not math.isfinite(t) or abs(t-i/FPS)>1e-7 for i,t in enumerate(times)):
        raise ValueError('Exact preserved 25fps frame times starting at zero required')
    end=goal['presentation_end_sim_s']
    if end is None:raise ValueError('UNKNOWN physical timeline; cannot manufacture footage')
    last=next((i for i,t in enumerate(times) if t>=end-1e-8),None)
    if last is None:raise ValueError('No saved real frame at/after event; footage is missing')
    return list(range(last+1))


def timeline(frame_times, end_card_frames=50):
    """One real frame per original 25fps PTS, then 2s outside simulation."""
    times=[float(t) for t in frame_times]
    if not times or any(abs(t-i/FPS)>1e-7 for i,t in enumerate(times)):
        raise ValueError('Nonuniform source frame time')
    rows=[dict(output_frame=i,video_pts_s=i/FPS,kind='recorded_motion',simulation_time_s=t,
               frozen_at_sim_s=None,source_frame=i) for i,t in enumerate(times)]
    for _ in range(end_card_frames):
        i=len(rows);rows.append(dict(output_frame=i,video_pts_s=i/FPS,kind='end_card',
            simulation_time_s=None,frozen_at_sim_s=times[-1],source_frame=None))
    return rows


def ruler_ticks(calibration, values):
    """Project world (X,0,0) using actual K/E; only HUD Y is fixed.

    RGB is unmodified and resized with Pillow's pixel-centre convention. World
    elevation is not encoded by HUD Y and is shown in a separate physical section.
    """
    K=calibration['intrinsics'];E=calibration['extrinsics'];ticks=[]
    for x in values:
        world=[float(x),0.,0.,1.]
        local=[sum(a*b for a,b in zip(row,world)) for row in E[:3]]
        pixel=None
        if local[2]>1e-9:
            h=[sum(a*b for a,b in zip(row,local)) for row in K]
            pixel=[h[0]/h[2],h[1]/h[2]]
            if not all(math.isfinite(v) for v in pixel):raise ValueError('Nonfinite camera projection')
        ticks.append(dict(world_xyz_m=world[:3],native_pixel_xy=pixel,
            hud_x_px=RGB_ORIGIN[0]+(pixel[0]+.5)*RGB_SCALE-.5 if pixel is not None else None,
            hud_y_px=HUD_BASELINE_Y))
    return ticks
