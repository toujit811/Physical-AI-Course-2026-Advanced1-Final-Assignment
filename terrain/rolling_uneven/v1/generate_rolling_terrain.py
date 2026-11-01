"""Offline 3D rolling-terrain concept for the PhysicaAI Genesis Go2 assignment.

This script only creates static mesh + previews. It does not change the Mac
repository or run a Genesis collision/robot test.
"""
from pathlib import Path
import json
import numpy as np
from scipy.interpolate import PchipInterpolator
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

OUT = Path(__file__).resolve().parent
X0, X1 = -1.0, 7.0
Y0, Y1 = -1.30, 1.30
NX, NY = 161, 53
BOTTOM_Z = -0.20

X_KNOT = np.array([-1.0, -0.6, 0.0, 0.45, 1.1, 1.6, 2.15, 2.6,
                   3.18, 3.65, 4.25, 4.9, 5.5, 6.1, 6.6, 7.0])
Z_KNOT = np.array([0.0, 0.0, 0.0, 0.025, 0.09, 0.05, 0.125, 0.078,
                   0.175, 0.135, 0.05, 0.125, 0.08, 0.025, 0.0, 0.0])

def heights(x, y):
    """x and y are broadcast-compatible NumPy arrays; returns physical Z [m]."""
    lateral_shift = (0.10*np.sin(np.pi*y/1.3)
                     + 0.06*np.sin(2*np.pi*y/2.7+0.4))
    centerline = PchipInterpolator(X_KNOT, Z_KNOT)(np.clip(x-lateral_shift, X0, X1))
    e1 = np.clip((x - 0.1)/1.0, 0.0, 1.0)
    e2 = np.clip((6.5 - x)/1.0, 0.0, 1.0)
    smoothstep = lambda t: t*t*(3.0 - 2.0*t)
    envelope = smoothstep(e1) * smoothstep(e2)
    lateral = (0.012*np.sin((x-0.2)*2*np.pi/2.7)*np.cos(np.pi*y/1.3)
               +0.007*np.cos((x-0.8)*2*np.pi/1.5)*np.sin(np.pi*y/0.95))
    local_hills = (0.009*np.exp(-((x-3.4)/0.55)**2-((y-0.35)/0.65)**2)
                   -0.007*np.exp(-((x-4.2)/0.62)**2-((y+0.40)/0.58)**2))
    return np.maximum(centerline + (lateral+local_hills)*envelope, 0.0)*envelope


def save_closed_obj(path, x, y, z):
    """Write a watertight mesh with top heightfield, sides, and flat bottom."""
    nx, ny = z.shape
    n = nx * ny
    def idx(i,j): return i*ny+j+1
    def bid(i,j): return idx(i,j)+n
    with path.open('w', encoding='utf-8') as f:
        f.write('# PhysicaAI rolling terrain prototype. Units: meters, Z up.\n')
        f.write('# Static geometry only; Genesis collision not yet validated.\n')
        f.write('o rolling_uneven_terrain\n')
        for i in range(nx):
            for j in range(ny):
                f.write(f'v {x[i]:.8f} {y[j]:.8f} {z[i,j]:.8f}\n')
        for i in range(nx):
            for j in range(ny):
                f.write(f'v {x[i]:.8f} {y[j]:.8f} {BOTTOM_Z:.8f}\n')
        # top (+Z) and bottom (-Z)
        for i in range(nx-1):
            for j in range(ny-1):
                a,b,c,d=idx(i,j),idx(i+1,j),idx(i,j+1),idx(i+1,j+1)
                f.write(f'f {a} {b} {c}\nf {b} {d} {c}\n')
                A,B,C,D=bid(i,j),bid(i+1,j),bid(i,j+1),bid(i+1,j+1)
                f.write(f'f {C} {B} {A}\nf {C} {D} {B}\n')
        edges=[]
        for i in range(nx-1): edges.append(((i,0),(i+1,0)))
        for j in range(ny-1): edges.append(((nx-1,j),(nx-1,j+1)))
        for i in range(nx-1,0,-1): edges.append(((i,ny-1),(i-1,ny-1)))
        for j in range(ny-1,0,-1): edges.append(((0,j),(0,j-1)))
        for (i,j),(k,l) in edges:
            u,v=idx(i,j),idx(k,l)
            bu,bv=bid(i,j),bid(k,l)
            f.write(f'f {u} {bu} {v}\nf {v} {bu} {bv}\n')
    return {"vertices": n*2, "top_triangles": 2*(nx-1)*(ny-1),
            "total_triangles": 4*(nx-1)*(ny-1)+2*len(edges)}


def main():
    x=np.linspace(X0,X1,NX); y=np.linspace(Y0,Y1,NY)
    X,Y=np.meshgrid(x,y,indexing='ij')
    Z=heights(X,Y)
    gx, gy=np.gradient(Z,x,y,edge_order=2)
    slope=np.rad2deg(np.arctan(np.hypot(gx,gy)))
    active = (X>=0.5)&(X<=6.0)&(np.abs(Y)<=0.75)
    center = NY//2
    metrics={
        "status":"geometry_preview_only__no_genesis_native_verification",
        "length_x_m":X1-X0,"width_y_m":Y1-Y0,"grid_nx":NX,"grid_ny":NY,
        "height_min_m":float(np.min(Z)),"height_max_m":float(np.max(Z)),
        "centerline_max_height_m":float(np.max(Z[:,center])),
        "active_foot_region_x_m":[0.5,6.0],"active_foot_region_abs_y_m":0.75,
        "active_region_median_slope_deg":float(np.median(slope[active])),
        "active_region_p95_slope_deg":float(np.percentile(slope[active],95)),
        "active_region_max_slope_deg":float(np.max(slope[active])),
        "active_region_fraction_over_10deg":float(np.mean(slope[active]>10)),
        "slope_max_whole_mesh_deg":float(np.max(slope)),
        "observations":45,"new_sensors":False,
        "ppo_training_executed":False,"genesis_robot_trajectory_executed":False,
        "notes":"Continuously shaped slopes, zero-height approach and exit, no vertical steps. Steep sections are local. All figures use simulated geometry, not native Genesis output."
    }
    mesh_info=save_closed_obj(OUT/'uneven_rolling_terrain.obj',x,y,Z)
    metrics.update(mesh_info)
    (OUT/'terrain_metrics.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    np.savetxt(OUT/'centerline_x_z.csv',np.column_stack([x,Z[:,center]]),delimiter=',',header='x_m,z_m',comments='')
    np.savez_compressed(OUT/'heightfield.npz',x_m=x,y_m=y,z_m=Z,slope_deg=slope)

    # Preview image: visually exaggerate only the rendered vertical axis.
    fig=plt.figure(figsize=(11.5,5.4),dpi=150)
    ax=fig.add_subplot(111,projection='3d')
    stride=max(1,NX//95)
    ax.plot_surface(X[::stride,::2],Y[::stride,::2],Z[::stride,::2],
                    cmap='terrain', linewidth=0,alpha=.97,antialiased=True)
    ax.plot(x,np.zeros_like(x),Z[:,center]+.003,linewidth=1.5)
    ax.set_xlabel('Forward X [m]',labelpad=8)
    ax.set_ylabel('Lateral Y [m]',labelpad=8)
    ax.set_zlabel('Height Z [m]',labelpad=8)
    ax.set_zlim(0,.24)
    ax.view_init(elev=28,azim=-65)
    ax.set_box_aspect((8,2.6,1.2))
    ax.set_title('Rolling uneven terrain — geometry preview (Z visually exaggerated)',pad=12)
    fig.tight_layout()
    fig.savefig(OUT/'terrain_perspective.png',bbox_inches='tight')
    plt.close(fig)

    fig,ax=plt.subplots(figsize=(12,3.5),dpi=150)
    ax.plot(x,Z[:,center],linewidth=2)
    ax.axhline(0,linewidth=.8)
    ax.set_xlim(X0,X1);ax.set_ylim(-.01,.24)
    ax.set_xlabel('Forward X [m]');ax.set_ylabel('Ground height Z [m]')
    ax.set_title('Centerline X-Z profile (physical meters; no artificial steps)')
    ax.grid(alpha=.3)
    fig.tight_layout()
    fig.savefig(OUT/'terrain_centerline.png',bbox_inches='tight')
    plt.close(fig)

    fig,ax=plt.subplots(figsize=(10,4),dpi=150)
    c=ax.contourf(X,Y,Z,levels=18,cmap='terrain')
    fig.colorbar(c,ax=ax,label='Ground Z [m]')
    ax.axhline(0,linewidth=1)
    ax.axhline(.75,linestyle='--',linewidth=.8)
    ax.axhline(-.75,linestyle='--',linewidth=.8)
    ax.set_xlabel('Forward X [m]');ax.set_ylabel('Lateral Y [m]')
    ax.set_title('Top-down elevation (dashed lines = sampled foot region)')
    fig.tight_layout();fig.savefig(OUT/'terrain_topdown.png',bbox_inches='tight')
    plt.close(fig)
    print(json.dumps(metrics,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
