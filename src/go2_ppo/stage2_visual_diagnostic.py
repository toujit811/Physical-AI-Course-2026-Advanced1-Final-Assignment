"""Read-only Stage2 XY diagnosis. No simulator, policy, terrain or gate mutation."""
import csv, hashlib, json, math
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LightSource, Normalize

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'reports/stage2-visual-diagnostic-20261030'
LEGS=('FL','FR','RL','RR')
BOUNDS=(-1.,7.,-1.,1.)
CM_RANGE=(-1.2,4.)

def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()

def dump(p,obj):Path(p).write_text(json.dumps(obj,indent=2,allow_nan=False))
def csvout(p,records):
    if not records:return
    with Path(p).open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in records for k in r)));w.writeheader();w.writerows(records)
def rawrows(p):
    with Path(p).open() as f:return list(csv.DictReader(f))

def signed_margins(x,y,bounds=BOUNDS):
    lo,hi,bottom,top=bounds
    return dict(x_min=x-lo,x_max=hi-x,y_min=y-bottom,y_max=top-y)

def yaw_angle(q):
    w,x,y,z=q
    return math.atan2(2*(w*z+x*y),1-2*(y*y+z*z))

def velocity_components(vx,vy,yaw):
    return vx*math.cos(yaw)+vy*math.sin(yaw),-vx*math.sin(yaw)+vy*math.cos(yaw)

def first_negative(times,margins):
    for i,(t,m) in enumerate(zip(times,margins)):
        if m<0:return dict(time_s=float(t),previous_time_s=float(times[i-1]) if i else None,margin_m=float(m))
    return None

def texture_rgb(height):
    """Image rows run from +Y to -Y; texture UV(0,0) is terrain(-X,-Y)."""
    import matplotlib as mpl
    v=Normalize(*CM_RANGE)(np.asarray(height).T[::-1]*100)
    return np.round(mpl.colormaps['viridis'](v)[:,:,:3]*255).astype(np.uint8)

def terrain_graphs(run,folder):
    a=np.load(run/'terrain.npz');x,y,h=a['x'],a['y'],a['height_m']
    meta=json.loads((run/'terrain.json').read_text())
    fig,ax=plt.subplots(2,1,figsize=(12,6),layout='constrained')
    im=ax[0].pcolormesh(x,y,h.T*100,cmap='viridis',vmin=CM_RANGE[0],vmax=CM_RANGE[1],shading='auto')
    fig.colorbar(im,ax=ax[0],label='Actual elevation [cm], no height scaling')
    ax[0].set(xlabel='World X [m]',ylabel='World Y [m]',aspect='equal',title=run.name+' | original height array')
    for c in meta['components']:
        ax[0].axvspan(c['start_m'],c['end_m'],alpha=.10,color={'bumps':'blue','slope':'orange','low_step':'red'}[c['kind']])
        ax[0].text((c['start_m']+c['end_m'])/2,.75,c['kind'],fontsize=8,ha='center')
    ax[1].plot(x,h[:,np.argmin(abs(y))]*100,color='black');ax[1].grid(alpha=.25)
    ax[1].set(xlabel='World X [m]',ylabel='Actual z [cm]',title='Centerline profile (axes have different units)')
    fig.savefig(folder/'heightmap-cm.png',dpi=140);plt.close(fig)
    fig,ax=plt.subplots(figsize=(6.4,3.4),layout='constrained')
    image=LightSource(azdeg=315,altdeg=15).shade(h.T,cmap=plt.colormaps['viridis'],norm=Normalize(*np.array(CM_RANGE)/100),vert_exag=1,dx=.025,dy=.025,blend_mode='soft')
    ax.imshow(image,origin='lower',extent=(x[0],x[-1],y[0],y[-1]),aspect='equal')
    fig.colorbar(plt.cm.ScalarMappable(norm=Normalize(*CM_RANGE),cmap='viridis'),ax=ax,label='Actual height [cm]')
    ax.set(xlabel='World X [m]',ylabel='World Y [m]',title='Top-down hillshade; vertical exaggeration = 1')
    fig.savefig(folder/'terrain-legend.png',dpi=140);plt.close(fig)
    from PIL import Image
    Image.fromarray(texture_rgb(h)).save(folder/'height-texture.png')

def diagnose(run):
    folder=OUT/'diagnosis'/run.name;folder.mkdir(parents=True,exist_ok=False)
    rows=rawrows(run/'measurements.csv');sub=rawrows(run/'substeps.csv')
    t=np.array([float(r['time_s']) for r in rows]);value=lambda k:np.array([float(r[k]) for r in rows])
    x=value('x_m');y=value('y_m');yaw=np.array([yaw_angle(json.loads(r['quaternion_wxyz'])) for r in rows])
    # Interval-average finite differences, not a new instantaneous velocity sensor.
    vx_fd=np.gradient(x,t);vy_fd=np.gradient(y,t)
    body=np.array([velocity_components(a,b,c) for a,b,c in zip(vx_fd,vy_fd,yaw)])
    targets={'base':(x,y)}
    targets.update({leg:(value(leg+'_center_x_m'),value(leg+'_center_y_m')) for leg in LEGS})
    exports=[];exits={};margins={};data=[]
    for tag,(xx,yy) in targets.items():
        m=[signed_margins(float(a),float(b)) for a,b in zip(xx,yy)]
        margins[tag]=np.array([min(v.values()) for v in m])
        exits[tag]=first_negative(t,margins[tag])
        if exits[tag]:
            i=next(i for i,v in enumerate(margins[tag]) if v<0)
            exits[tag].update(edge=min(m[i],key=m[i].get),x_m=float(xx[i]),y_m=float(yy[i]),base_x_m=float(x[i]),base_y_m=float(y[i]),yaw_deg=math.degrees(yaw[i]))
        for i in range(len(t)):
            exports.append(dict(time_s=float(t[i]),object=tag,x_m=float(xx[i]),y_m=float(yy[i]),**{k+'_margin_m':v for k,v in m[i].items()},min_margin_m=float(margins[tag][i])))
    base_eval=np.minimum.reduce((x+.95,6.95-x,y+.95,.95-y))
    eval_exit=first_negative(t,base_eval)
    for i in range(len(t)):
        data.append(dict(time_s=float(t[i]),base_x_m=float(x[i]),base_y_m=float(y[i]),yaw_deg=math.degrees(yaw[i]),
                         world_vx_saved_m_s=float(rows[i]['world_vx_m_s']),world_vx_fd_m_s=float(vx_fd[i]),world_vy_fd_m_s=float(vy_fd[i]),
                         body_forward_fd_m_s=float(body[i,0]),body_lateral_fd_m_s=float(body[i,1]),
                         command_body_vx_m_s=float(rows[i]['command_vx_m_s']),command_body_vy_m_s=0.,command_yaw_rate_rad_s=0.,
                         heading_forward_vy_m_s=float(body[i,0]*math.sin(yaw[i])),body_lateral_world_vy_m_s=float(body[i,1]*math.cos(yaw[i])),
                         base_eval_min_margin_m=float(base_eval[i]),base_physical_min_margin_m=float(margins['base'][i]),
                         min_foot_center_margin_m=float(min(margins[k][i] for k in LEGS))))
    contacts=[]
    for r in sub:
        for e in json.loads(r['contacts_json']):
            a,b,c=e['position'];m=signed_margins(a,b)
            contacts.append(dict(time_s=float(r['time_s']),geom_a=e['geom_a'],geom_b=e['geom_b'],x_m=a,y_m=b,z_m=c,
                                 min_margin_m=min(m.values()),force_norm_N=float(np.linalg.norm(e['force_on_robot_N']))))
    csvout(folder/'xy-margins-50hz.csv',exports);csvout(folder/'yaw-velocity-50hz.csv',data);csvout(folder/'contact-margins-100hz.csv',contacts)
    subfirst=next((r for r in contacts if r['min_margin_m']<0),None)
    sorted_exits=sorted([dict(object=k,**v) for k,v in exits.items() if v],key=lambda z:z['time_s'])
    heading_dy=float(np.trapezoid(body[:,0]*np.sin(yaw),t));lateral_dy=float(np.trapezoid(body[:,1]*np.cos(yaw),t))
    envelope=np.array([max(abs(targets[k][1][i]-y[i]) for k in LEGS) for i in range(len(t))])
    first=sorted_exits[0] if sorted_exits else None
    result=dict(run_id=run.name,duration_s=float(t[-1]),base_start_xy_m=[float(x[0]),float(y[0])],base_end_xy_m=[float(x[-1]),float(y[-1])],
        delta_x_m=float(x[-1]-x[0]),delta_y_m=float(y[-1]-y[0]),final_yaw_deg=float(math.degrees(yaw[-1])),max_abs_yaw_deg=float(np.degrees(abs(yaw)).max()),
        max_abs_body_y_m=float(abs(y).max()),max_foot_offset_from_base_y_m=float(envelope.max()),
        centered_observed_gait_margin_y_m=float(1-envelope.max()),first_physical_center_exit=first,all_center_exits=exits,
        first_base_evaluation_margin_exit=eval_exit,first_contact_point_outside=subfirst,
        dy_from_heading_forward_component_m=heading_dy,dy_from_body_lateral_component_m=lateral_dy,
        decomposition_sum_error_m=float(heading_dy+lateral_dy-(y[-1]-y[0])),
        original_result_unchanged=True,original_result_sha256=sha(run/'result.json'),height_npz_sha256=sha(run/'terrain.npz'),
        limits='XY and yaw sampled at 50Hz (20ms); 100Hz supplies contact positions/joints only. First exit lies between previous_time_s and time_s; no interpolation is presented as observed. Finite-difference velocities are averages. Centered gait envelope is diagnostic, not a counterfactual policy test.',
        attribution='Observed lateral/heading drift reaches Y edge' if first and first['edge'].startswith('y_') else ('No physical center exit observed' if not first else 'Observed X-edge exit'),
        causal_limit='Kinematic decomposition cannot identify a unique RL reward/control cause or prove that a wider domain would pass. Current width and displaced path jointly determine the exit; no domain change was tested.')
    dump(folder/'diagnosis.json',result)
    a=np.load(run/'terrain.npz')
    fig,ax=plt.subplots(5,1,figsize=(13,15),layout='constrained')
    im=ax[0].pcolormesh(a['x'],a['y'],a['height_m'].T*100,cmap='viridis',vmin=CM_RANGE[0],vmax=CM_RANGE[1],shading='auto')
    fig.colorbar(im,ax=ax[0],label='Actual height [cm]')
    ax[0].plot(x,y,'k',label='base',lw=2)
    colors=('tab:red','tab:blue','tab:orange','tab:purple')
    for leg,color in zip(LEGS,colors):ax[0].plot(*targets[leg],color=color,label=leg,lw=.7)
    for k in range(0,len(t),100):
        ax[0].annotate(f'{t[k]:.0f}s',(x[k],y[k]),fontsize=8)
        ax[0].arrow(x[k],y[k],.2*math.cos(yaw[k]),.2*math.sin(yaw[k]),width=.003,color='black')
    ax[0].plot([-1,7,7,-1,-1],[-1,-1,1,1,-1],color='red',ls='--',label='physical domain')
    ax[0].plot([-.95,6.95,6.95,-.95,-.95],[-.95,-.95,.95,.95,-.95],color='grey',ls=':',label='base eval margin')
    ax[0].set(xlabel='World X [m]',ylabel='World Y [m]',aspect='equal');ax[0].legend(ncol=7,fontsize=8)
    for tag in targets:ax[1].plot(t,margins[tag],label=tag,lw=.8)
    ax[1].plot(t,base_eval,'--',label='base eval margin');ax[1].axhline(0,color='red');ax[1].set_ylabel('Signed nearest margin [m]');ax[1].legend(ncol=6)
    ax[2].plot(t,np.degrees(yaw),label='yaw');ax[2].set_ylabel('Yaw [deg]');ax[2].legend()
    ax[3].plot(t,vy_fd,label='world vy (finite difference)');ax[3].plot(t,body[:,1],label='body lateral (finite difference)');ax[3].axhline(0,color='black',ls=':');ax[3].set_ylabel('Lateral velocity [m/s]');ax[3].legend()
    ax[4].plot(t,body[:,0]*np.sin(yaw),label='forward along heading -> world vy');ax[4].plot(t,body[:,1]*np.cos(yaw),label='body lateral -> world vy');ax[4].set(xlabel='Observed time [s]',ylabel='World vy components [m/s]');ax[4].legend()
    if first:
        for q in ax[1:]:q.axvline(first['time_s'],color='red',ls='--',label='first foot/base exit')
        ax[0].scatter(first['x_m'],first['y_m'],marker='x',s=80,color='red')
    for q in ax[1:]:q.grid(alpha=.25)
    fig.suptitle(run.name+' | saved trajectory only; arrows = commanded body-forward direction')
    fig.savefig(folder/'boundary-diagnosis.png',dpi=130);plt.close(fig)
    terrain_graphs(run,folder)
    return result

def main():
    (OUT/'diagnosis').mkdir(exist_ok=True)
    result=[]
    for run in sorted((ROOT/'logs/stage2/evaluations').iterdir()):
        if not (run/'result.json').exists():continue
        d=json.loads((run/'result.json').read_text())
        if d.get('terrain')=='FLAT' or 'numeric_gates' not in d:continue
        print('Diagnose',run.name,flush=True);result.append(diagnose(run))
    dump(OUT/'boundary-summary.json',result)
    csvout(OUT/'boundary-summary.csv',[{**{k:v for k,v in r.items() if not isinstance(v,(dict,list))},
        'first_center_exit_time_s':(r['first_physical_center_exit'] or {}).get('time_s'),
        'first_center_exit_object':(r['first_physical_center_exit'] or {}).get('object'),
        'first_center_exit_edge':(r['first_physical_center_exit'] or {}).get('edge')} for r in result])
    print('Diagnosed',len(result),'existing runs')

if __name__=='__main__':main()
