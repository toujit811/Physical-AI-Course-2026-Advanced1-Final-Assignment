"""Full-course completion state machine, separate from historical20s gates.

No simulator imports or model control. Every decision consumes a real100Hz row.
"""
import copy
import math

LEGS=('FL','FR','RL','RR')


def historical_reference(source,kind,condition):
    found=[r for r in source['results'] if r['kind']==kind and r['condition']==condition]
    if len(found)!=1:raise ValueError('Unique historical condition reference required')
    return copy.deepcopy(found[0])


def flag(value):
    if value is True or value=='True':return True
    if value is False or value=='False':return False
    raise ValueError('Missing physical boolean')


class CourseTracker:
    def __init__(self,finish_x=6.4,confirmation_s=.2,max_sim_s=60.,stall_s=6.,stall_progress_m=.1):
        self.finish=float(finish_x);self.confirmation=float(confirmation_s)
        self.max_sim=float(max_sim_s);self.stall_s=float(stall_s);self.stall_progress=float(stall_progress_m)
        if not all(math.isfinite(v) for v in (self.finish,self.confirmation,self.max_sim,self.stall_s,self.stall_progress)) or min(self.confirmation,self.max_sim,self.stall_s)<=0:
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
            elif fall:self.stop('FALL',tm)
            elif outside:self.stop('OUT_OF_BOUNDS',tm)
            elif flag(row['fallen']):self.stop('STATE_ERROR',tm)
            if self.reason!='RUNNING':return self.summary()
            all_passed=x>self.finish and all(v>self.finish for v in trailing.values())
            if all_passed:
                if self.first_all is None:self.first_all=tm
                if self.pending is None:self.pending=tm
                if tm-self.pending>=self.confirmation-1e-8:self.stop('COURSE_COMPLETED',tm)
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
        return copy.deepcopy(dict(reason=self.reason,success=self.reason=='COURSE_COMPLETED',
            finish_x_m=self.finish,confirmation_s=self.confirmation,max_sim_s=self.max_sim,
            first_all_feet_pass_s=self.first_all,confirmation_start_s=self.pending,
            confirmed_at_sim_s=self.terminal if self.reason=='COURSE_COMPLETED' else None,
            terminal_sim_s=self.terminal,first_each_foot_pass=self.first_each,last_measurement=self.last,
            foot_predicate='all native sphere centre X minus radius > finish; base X > finish; continuous0.20s, no fall/boundary/solver/state error',
            error=getattr(self,'error',None)))
