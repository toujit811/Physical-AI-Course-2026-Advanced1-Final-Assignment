"""Units and equal-experience comparisons for the isolated CPU benchmark."""
import math,statistics

def vector_steps(total_env_steps,num_envs):
    if num_envs not in [64,128] or total_env_steps<=0 or total_env_steps%(num_envs*24):raise ValueError('Use64/128 and a whole24-step rollout batch')
    return total_env_steps//num_envs

def speed(total_env_steps,seconds):
    if seconds<=0:raise ValueError('Nonpositive timed interval')
    return total_env_steps/seconds

def summarize(values):
    x=list(map(float,values));m=statistics.mean(x);sd=statistics.stdev(x) if len(x)>1 else 0.
    return dict(n=len(x),mean=m,median=statistics.median(x),sd=sd,cv_percent=100*sd/m if m>0 else None,minimum=min(x),maximum=max(x))

def paired_improvement(pairs):
    improvements=[100*(b/a-1) for a,b in pairs];s=summarize(improvements)
    # Student-t95% CI for three paired observations; descriptive, not broad quality proof.
    half=4.3026527299*s['sd']/math.sqrt(s['n']) if s['n']==3 else None
    s.update(pair_percent=improvements,ci95_lower_percent=s['mean']-half if half is not None else None,ci95_upper_percent=s['mean']+half if half is not None else None)
    return s
