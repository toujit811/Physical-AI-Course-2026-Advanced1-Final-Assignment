"""Full-course completion state machine, separate from historical20s gates.

No simulator imports or model control. Every decision consumes a real100Hz row.
"""
import copy
import math

LEGS=('FL','FR','RL','RR')


def outside_course_boundary(kind,position,foot=False,terrain_x_end=7.):
    """Keep existing Y/uneven guards; an infinite FLAT plane has no X edge."""
    x,y=position[:2]
    y_out=not(-1.3<=y<=1.3) if foot else not(-1.25<y<1.25)
    x_out=False if kind=='FLAT' else not(-1<=x<=terrain_x_end) if foot else not(-.95<x<terrain_x_end-.05)
    return bool(x_out or y_out)


def historical_reference(source,kind,condition):
    found=[r for r in source['results'] if r['kind']==kind and r['condition']==condition]
    if len(found)!=1:raise ValueError('Unique historical condition reference required')
    return copy.deepcopy(found[0])


def flag(value):
    if value is True or value=='True':return True
    if value is False or value=='False':return False
    raise ValueError('Missing physical boolean')


def summarize_safety(rows,contacts,control,names,excursion_limit=.002,terminal_verified=True):
    """Report unavailable measurements as unknown, including startup failures."""
    if not rows:
        return dict(measurements_available=False,verified_through_sim_s=None,
            physical_fall=None,boundary_excursion=None,nonfoot_contact_points=None,
            first_nonfoot_sim_s=None,joint_input_pass=None,max_joint_excursion_rad=None,max_FK_error_m=None)
    joint_ok=all(float(r['max_joint_excursion_rad'])<=excursion_limit for r in rows)
    if control is None:joint_ok=None
    else:
        for i,name in enumerate(names):
            low,high=control['joint_limits_rad'][name];effort=control['urdf_effort_limits'][i]
            joint_ok &= all(abs(float(r[name+'_qf_applied_Nm']))<=effort+1e-4 and low+.12-1e-5<=float(r[name+'_target_rad'])<=high-.12+1e-5 for r in rows)
    nonfoot=[e for e in contacts if not flag(e['foot'])]
    fallen=any(flag(r['physical_fallen']) for r in rows);outside=any(flag(r['out_of_terrain']) for r in rows)
    return dict(measurements_available=True,verified_through_sim_s=float(rows[-1]['time_s']),
        physical_fall=fallen if fallen or terminal_verified else None,
        boundary_excursion=outside if outside or terminal_verified else None,
        nonfoot_contact_points=len(nonfoot),first_nonfoot_sim_s=min((float(e['time_s']) for e in nonfoot),default=None),
        joint_input_pass=bool(joint_ok) if joint_ok is not None and (terminal_verified or not joint_ok) else None,
        max_joint_excursion_rad=max(float(r['max_joint_excursion_rad']) for r in rows),
        max_FK_error_m=max(float(r[leg+'_FK_error_m']) for r in rows for leg in LEGS))


class CourseTracker:
    def __init__(self,finish_x=6.4,confirmation_s=.2,max_sim_s=60.,stall_s=6.,stall_progress_m=.1,post_goal_s=0.):
        self.finish=float(finish_x);self.confirmation=float(confirmation_s)
        self.max_sim=float(max_sim_s);self.stall_s=float(stall_s);self.stall_progress=float(stall_progress_m)
        self.post_goal=float(post_goal_s);self.goal_at=None;self.post_events={}
        if not math.isfinite(self.post_goal) or self.post_goal<0 or (self.post_goal and self.confirmation):
            raise ValueError('Post-goal recording requires immediate goal and finite nonnegative duration')
        if not all(math.isfinite(v) for v in (self.finish,self.confirmation,self.max_sim,self.stall_s,self.stall_progress)) or self.confirmation<0 or min(self.max_sim,self.stall_s)<=0:
            raise ValueError('Invalid course configuration')
        self.rows=[];self.pending=None;self.first_all=None;self.first_each={};self.reason='RUNNING';self.terminal=None;self.last=None

    def stop(self,reason,tm):
        if self.reason=='RUNNING':self.reason=reason;self.terminal=float(tm)

    def update(self,row):
        if self.reason!='RUNNING':raise ValueError('No physics samples allowed after terminal event')
        try:
            tm=float(row['time_s']);x=float(row['x_m']);values=[tm,x]
            trailing={leg:float(row[leg+'_center_x_m'])-float(row[leg+'_sphere_radius_m']) for leg in LEGS}
            values.extend(trailing.values())
            values.extend(float(row[k]) for k in ('y_m','height_m','roll_deg','pitch_deg'))
            if not all(math.isfinite(v) for v in values):raise ValueError('Nonfinite measured state')
            if abs(tm-len(self.rows)*.01)>1e-7:raise ValueError('Nonuniform or missing100Hz sample')
            fall=flag(row['physical_fallen']);outside=flag(row['out_of_terrain']);engine=flag(row['engine_error'])
            flag(row['fallen']);flag(row['unexpected_floor_contact'])
            q=dict(time_s=tm,x_m=x,trailing_x_m=trailing,physical_fallen=fall,out_of_terrain=outside)
            self.rows.append(q);self.last=q
            for leg,fx in trailing.items():
                if fx>self.finish and leg not in self.first_each:
                    previous=self.rows[-2] if len(self.rows)>1 else None
                    self.first_each[leg]=dict(at_or_after_sim_s=tm,trailing_x_m=fx,
                        previous_sim_s=previous['time_s'] if previous else None,
                        previous_trailing_x_m=previous['trailing_x_m'][leg] if previous else None)
            if engine:self.stop('ENGINE_ERROR',tm)
            elif self.goal_at is not None and self.post_goal:
                # Continue actual physics for the requested tail, retaining all
                # safety observations. This neither extends nor edits terrain.
                if fall:self.post_events.setdefault('FALL',tm)
                if outside:self.post_events.setdefault('OUT_OF_BOUNDS',tm)
                if flag(row['fallen']) and not (fall or outside):self.stop('STATE_ERROR',tm)
                if self.reason=='RUNNING' and tm-self.goal_at>=self.post_goal-1e-8:self.stop('POST_GOAL_RECORDED',tm)
                return self.summary()
            elif fall:self.stop('FALL',tm)
            elif outside:self.stop('OUT_OF_BOUNDS',tm)
            elif flag(row['fallen']):self.stop('STATE_ERROR',tm)
            if self.reason!='RUNNING':return self.summary()
            all_passed=(self.confirmation==0 or x>self.finish) and all(v>self.finish for v in trailing.values())
            if all_passed:
                if self.first_all is None:self.first_all=tm
                if self.pending is None:self.pending=tm
                if tm-self.pending>=self.confirmation-1e-8:
                    self.goal_at=tm
                    if not self.post_goal:self.stop('COURSE_COMPLETED',tm)
            else:self.pending=None
            if self.reason=='RUNNING' and tm>=self.max_sim-1e-8:self.stop('TIMEOUT_NOT_REACHED',tm)
            window=round(self.stall_s/.01)
            if self.reason=='RUNNING' and len(self.rows)>window and x-self.rows[-1-window]['x_m']<self.stall_progress:
                self.stop('STALLED_NOT_REACHED',tm)
        except (ValueError,KeyError,TypeError) as error:
            self.stop('STATE_ERROR',self.last['time_s'] if self.last else 0.)
            self.error=str(error)
        return self.summary()

    def summary(self):
        return copy.deepcopy(dict(reason=self.reason,success=self.reason in ('COURSE_COMPLETED','POST_GOAL_RECORDED'),
            goal_achieved=self.goal_at is not None,goal_sim_s=self.goal_at,post_goal_requested_s=self.post_goal,
            post_goal_recorded_s=(round(self.last['time_s']-self.goal_at,8) if self.last and self.goal_at is not None else 0.),
            post_goal_first_events_s=self.post_events,
            finish_x_m=self.finish,confirmation_s=self.confirmation,max_sim_s=self.max_sim,
            first_all_feet_pass_s=self.first_all,confirmation_start_s=self.pending,
            confirmed_at_sim_s=self.goal_at,
            terminal_sim_s=self.terminal,first_each_foot_pass=self.first_each,last_measurement=self.last,
            foot_predicate='all four native foot sphere trailing extents X > finish; immediate goal' if self.confirmation==0 else 'all native sphere centre X minus radius > finish; base X > finish; continuous0.20s, no fall/boundary/solver/state error',
            error=getattr(self,'error',None)))
