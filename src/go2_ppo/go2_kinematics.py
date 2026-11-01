"""Installed-URDF Go2 geometry. No Genesis initialization or simulation.

Coordinates are base/trunk x forward, y left, z up. ``fk`` returns the foot
*collision sphere center* (2 mm offset from its link origin). Joint order is
hip, thigh, calf. Collision filtering is conservative: finite cylinders are
enclosed by capsules; boxes/spheres retain their URDF geometry. A clean result
certifies these conservative envelopes at a pose, not an entire motion.
"""
from __future__ import annotations
import importlib.util
from pathlib import Path
import math
import xml.etree.ElementTree as ET
import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation


def _v(element, key, default='0 0 0'):
    return np.fromstring(element.get(key,default) if element is not None else default,sep=' ')


def _rpy(v):
    x,y,z=v;cx,sx=np.cos(x),np.sin(x);cy,sy=np.cos(y),np.sin(y);cz,sz=np.cos(z),np.sin(z)
    return np.array([[cz*cy,cz*sy*sx-sz*cx,cz*sy*cx+sz*sx],[sz*cy,sz*sy*sx+cz*cx,sz*sy*cx-cz*sx],[-sy,cy*sx,cy*cx]])


def _axis_angle(axis,angle):
    axis=np.asarray(axis);x,y,z=axis;K=np.array([[0,-z,y],[z,0,-x],[-y,x,0]])
    return np.eye(3)+np.sin(angle)*K+(1-np.cos(angle))*(K@K)


def installed_urdf():
    spec=importlib.util.find_spec('genesis')
    if spec is None: raise FileNotFoundError('Genesis is not installed; supply urdf_path explicitly')
    return Path(spec.origin).parent/'assets/urdf/go2/urdf/go2.urdf'


class Go2Kinematics:
    legs=('FL','FR','RL','RR')
    def __init__(self,urdf_path=None):
        self.urdf_path=Path(urdf_path) if urdf_path else installed_urdf()
        self.root=ET.parse(self.urdf_path).getroot()
        self.links={e.get('name'):e for e in self.root.findall('link')}
        self.joints={};self.children={};self.parent={}
        for e in self.root.findall('joint'):
            origin=e.find('origin');limit=e.find('limit');name=e.get('name')
            j={'name':name,'type':e.get('type'),'parent':e.find('parent').get('link'),'child':e.find('child').get('link'),'xyz':_v(origin,'xyz'),'rpy':_v(origin,'rpy'),'axis':_v(e.find('axis'),'xyz'),'lower':float(limit.get('lower')) if limit is not None else None,'upper':float(limit.get('upper')) if limit is not None else None,'effort':float(limit.get('effort')) if limit is not None else None,'velocity':float(limit.get('velocity')) if limit is not None else None}
            self.joints[name]=j;self.children.setdefault(j['parent'],[]).append(j);self.parent[j['child']]=j
        self.chains={leg:[self.joints[f'{leg}_{part}_joint'] for part in ('hip','thigh','calf','foot')] for leg in self.legs}
        self.foot_radius={leg:float(self.links[f'{leg}_foot'].find('collision/geometry/sphere').get('radius')) for leg in self.legs}
        self.foot_offset={leg:_v(self.links[f'{leg}_foot'].find('collision/origin'),'xyz') for leg in self.legs}
        for leg,chain in self.chains.items():
            if any(np.linalg.norm(j['rpy']) for j in chain) or not np.allclose([j['axis'] for j in chain[:3]],[[1,0,0],[0,1,0],[0,1,0]]):
                raise ValueError('Optimized FK requires installed Go2 chain convention; URDF differs')
        self.total_mass=sum(float(e.find('inertial/mass').get('value')) for e in self.links.values() if e.find('inertial/mass') is not None)

    def bounds(self,leg,margin=0.):
        if margin<0:raise ValueError('margin must be nonnegative')
        lo=np.array([j['lower']+margin for j in self.chains[leg][:3]]);hi=np.array([j['upper']-margin for j in self.chains[leg][:3]])
        if np.any(lo>=hi):raise ValueError('margin leaves an empty joint interval')
        return lo,hi

    def within_limits(self,leg,q,margin=0.):
        lo,hi=self.bounds(leg,margin);q=np.asarray(q)
        return bool(np.all(np.isfinite(q)) and np.all(q>=lo-1e-10) and np.all(q<=hi+1e-10))

    def fk(self,leg,q,collision_center=True):
        """Vectorized exact chain FK; q shape (...,3), output (...,3)."""
        q=np.asarray(q,dtype=float)
        if q.shape[-1]!=3 or not np.all(np.isfinite(q)):raise ValueError('q must contain three finite joint angles')
        a,b,c=np.moveaxis(q,-1,0);chain=self.chains[leg]
        # URDF joint translations, followed by local-axis rotations.
        end=chain[3]['xyz']+(self.foot_offset[leg] if collision_center else 0)
        ce,se=np.cos(b+c),np.sin(b+c);cb,sb=np.cos(b),np.sin(b)
        d=chain[2]['xyz'];h=chain[1]['xyz']
        x=h[0]+cb*d[0]+sb*d[2]+ce*end[0]+se*end[2]
        y=h[1]+d[1]+end[1]+np.zeros_like(a)
        z=h[2]-sb*d[0]+cb*d[2]-se*end[0]+ce*end[2]
        ca,sa=np.cos(a),np.sin(a)
        return np.stack([x,ca*y-sa*z,sa*y+ca*z],axis=-1)+chain[0]['xyz']

    def fk_link(self,leg,q):return self.fk(leg,q,collision_center=False)

    def fk_reference(self,leg,q):
        """Independent homogeneous-transform evaluation using SciPy rotations."""
        T=np.eye(4)
        for j,angle in zip(self.chains[leg],list(q)+[0.]):
            O=np.eye(4);O[:3,:3]=Rotation.from_euler('xyz',j['rpy']).as_matrix();O[:3,3]=j['xyz']
            A=np.eye(4)
            if j['type']!='fixed':A[:3,:3]=Rotation.from_rotvec(j['axis']*angle).as_matrix()
            T=T@O@A
        return (T@np.r_[self.foot_offset[leg],1])[:3]

    def transforms(self,q_by_leg):
        angles={f'{leg}_{part}_joint':float(q_by_leg[leg][i]) for leg in self.legs for i,part in enumerate(('hip','thigh','calf'))}
        result={'base':(np.eye(3),np.zeros(3))}
        todo=['base']
        while todo:
            parent=todo.pop();R,p=result[parent]
            for j in self.children.get(parent,[]):
                Rj=_rpy(j['rpy']);child_R=R@Rj
                if j['type']!='fixed':child_R=child_R@_axis_angle(j['axis'],angles[j['name']])
                result[j['child']]=(child_R,p+R@j['xyz']);todo.append(j['child'])
        return result

    def jacobian(self,leg,q):
        q=np.asarray(q,dtype=float);R=np.eye(3);p=np.zeros(3);axes=[];origins=[]
        for j,a in zip(self.chains[leg][:3],q):
            p=p+R@j['xyz'];R=R@_rpy(j['rpy']);axes.append(R@j['axis']);origins.append(p.copy());R=R@_axis_angle(j['axis'],a)
        foot=self.fk(leg,q)
        return np.column_stack([np.cross(axis,foot-origin) for axis,origin in zip(axes,origins)])

    def ik(self,leg,target,margin=.12,seed=None,tolerance=1e-6,nearest=True):
        """Enumerate exact hip/elbow branches; bounded least squares on failure.

        Successful solutions are selected nearest the supplied seed. A returned
        pose does not certify a continuous path from the seed to that pose.
        """
        lo,hi=self.bounds(leg,margin);target=np.asarray(target,dtype=float)
        if target.shape!=(3,) or not np.all(np.isfinite(target)):raise ValueError('target must be finite xyz')
        chain=self.chains[leg];v=target-chain[0]['xyz'];offset=chain[1]['xyz'];end=chain[3]['xyz']+self.foot_offset[leg]
        # This exact planar reduction uses only verified URDF translations.
        if not (np.allclose(offset[[0,2]],0) and np.allclose(chain[2]['xyz'][:2],0) and abs(end[1])<1e-14):
            raise ValueError('Analytic IK requires the installed Go2 planar link offsets')
        radius=np.hypot(v[1],v[2]);solutions=[]
        if radius>=abs(offset[1])-1e-12 and radius>1e-14:
            phi=np.arctan2(v[2],v[1]);alpha=np.arccos(np.clip(offset[1]/radius,-1,1))
            l1=-chain[2]['xyz'][2];l2=np.hypot(end[0],end[2]);delta=np.arctan2(-end[0],-end[2])
            for hip0 in [phi-alpha,phi+alpha]:
                for turns in [-1,0,1]:
                    hip=hip0+turns*2*np.pi
                    if not lo[0]-1e-10<=hip<=hi[0]+1e-10:continue
                    local_z=-np.sin(hip)*v[1]+np.cos(hip)*v[2];u=-local_z;w=-v[0]
                    cosine=(u*u+w*w-l1*l1-l2*l2)/(2*l1*l2)
                    if not -1-1e-10<=cosine<=1+1e-10:continue
                    for elbow in [-np.arccos(np.clip(cosine,-1,1)),np.arccos(np.clip(cosine,-1,1))]:
                        calf=elbow-delta;thigh0=np.arctan2(w,u)-np.arctan2(l2*np.sin(elbow),l1+l2*np.cos(elbow))
                        for thigh_turns in [-1,0,1]:
                            q=np.array([hip,thigh0+thigh_turns*2*np.pi,calf])
                            if self.within_limits(leg,q,margin):
                                residual=float(np.linalg.norm(self.fk_reference(leg,q)-target))
                                if residual<=tolerance:solutions.append((q,residual))
        if solutions:
            preferred=np.asarray(seed) if seed is not None else np.array([0.,.8 if leg[0]=='F' else 1.,-1.5])
            q,residual=min(solutions,key=lambda qr:np.linalg.norm(qr[0]-preferred))
            return {'q':q.tolist(),'residual_m':residual,'success':True,'method':'analytic_all_branches','solution_count':len(solutions)}
        if not nearest:
            q=np.clip(np.asarray(seed) if seed is not None else (lo+hi)/2,lo,hi)
            return {'q':q.tolist(),'residual_m':float(np.linalg.norm(self.fk_reference(leg,q)-target)),'success':False,'method':'analytic_unreachable_no_projection','solution_count':0}
        seeds=[(lo+hi)/2,np.array([0.,.8 if leg[0]=='F' else 1.,-1.5]),lo+.15*(hi-lo),lo+.85*(hi-lo)]
        if seed is not None:seeds.insert(0,np.asarray(seed))
        best=None
        for s in seeds:
            fit=least_squares(lambda q:self.fk(leg,q)-target,np.clip(s,lo+1e-10,hi-1e-10),jac=lambda q:self.jacobian(leg,q),bounds=(lo,hi),gtol=1e-12,ftol=1e-12,xtol=1e-12,max_nfev=150)
            residual=float(np.linalg.norm(self.fk_reference(leg,fit.x)-target))
            if best is None or residual<best['residual_m']:best={'q':fit.x.tolist(),'residual_m':residual,'success':bool(residual<=tolerance and self.within_limits(leg,fit.x,margin))}
            if best['success']:break
        return best

    def center_of_mass(self,q_by_leg):
        transforms=self.transforms(q_by_leg);weighted=np.zeros(3)
        for name,link in self.links.items():
            inertial=link.find('inertial')
            if inertial is not None:
                R,p=transforms[name];weighted+=float(inertial.find('mass').get('value'))*(p+R@_v(inertial.find('origin'),'xyz'))
        return weighted/self.total_mass

    def static_torques(self,q_by_leg,normal_forces,body_rpy=(0,0,0),gravity=9.81):
        """Actuator torque from subtree weight and vertical point-foot forces.

        These are static equilibrium demands, without PD tracking, motor thermal
        limits, tangential contact force, acceleration, or impact contributions.
        A force dict contains world-up normal force in N for each stance leg.
        """
        transforms=self.transforms(q_by_leg);B=_rpy(body_rpy);result={}
        for leg in self.legs:
            values=[]
            for joint in self.chains[leg][:3]:
                R,p=transforms[joint['child']];axis=B@R@joint['axis'];origin=B@p
                moment=np.zeros(3);descendants=[];todo=[joint['child']]
                while todo:
                    name=todo.pop();descendants.append(name);todo.extend(j['child'] for j in self.children.get(name,[]))
                for name in descendants:
                    inertial=self.links[name].find('inertial')
                    if inertial is not None:
                        Rl,pl=transforms[name];mass=float(inertial.find('mass').get('value'))
                        point=B@(pl+Rl@_v(inertial.find('origin'),'xyz'))
                        moment+=np.cross(point-origin,[0,0,-mass*gravity])
                point=B@self.fk(leg,q_by_leg[leg]);moment+=np.cross(point-origin,[0,0,float(normal_forces.get(leg,0.))])
                values.append(float(-axis@moment))
            result[leg]=values
        return result

    def collision_shapes(self,q_by_leg,body_position=(0,0,0),body_rpy=(0,0,0)):
        transforms=self.transforms(q_by_leg);B=_rpy(body_rpy);bp=np.asarray(body_position);shapes=[]
        for name,link in self.links.items():
            R,p=transforms[name]
            for e in link.findall('collision'):
                origin=e.find('origin');C=B@R@_rpy(_v(origin,'rpy'));center=bp+B@(p+R@_v(origin,'xyz'));g=e.find('geometry')[0]
                s={'link':name,'center':center,'rotation':C,'foot':name.endswith('_foot')}
                if g.tag=='box':s.update(kind='box',half=_v(g,'size')/2)
                elif g.tag=='sphere':s.update(kind='capsule',radius=float(g.get('radius')),a=center,b=center)
                elif g.tag=='cylinder':
                    d=C[:,2]*float(g.get('length'))/2;s.update(kind='capsule',radius=float(g.get('radius')),a=center-d,b=center+d)
                else:raise ValueError(f'Unsupported collision primitive {g.tag}')
                shapes.append(s)
        return shapes

    def collision_bounds(self,q_by_leg,body_position=(0,0,0),body_rpy=(0,0,0),ground_z=0.,tolerance=1e-8):
        """Enclosing-capsule filter, direct adjacent-link pairs excluded.

        ``possible_self_collision`` means envelope overlap (may be false positive).
        Ground cylinder capsules over-approximate true cylinder by end hemispheres.
        No contact dynamics, friction, swept volumes, or terrain-edge test is implied.
        """
        shapes=self.collision_shapes(q_by_leg,body_position,body_rpy);pairs=[];ground=[];foot_ground=[]
        def rigid_root(name):
            while name in self.parent and self.parent[name]['type']=='fixed':name=self.parent[name]['parent']
            return name
        for i,a in enumerate(shapes):
            if a['kind']=='box':bottom=a['center'][2]-np.sum(np.abs(a['rotation'][2])*a['half'])
            else:bottom=min(a['a'][2],a['b'][2])-a['radius']
            if bottom<ground_z-tolerance:(foot_ground if a['foot'] else ground).append({'link':a['link'],'bottom_z_m':float(bottom)})
            for b in shapes[i+1:]:
                an,bn=a['link'],b['link']
                if rigid_root(an)==rigid_root(bn):continue
                if (an in self.parent and self.parent[an]['parent']==bn) or (bn in self.parent and self.parent[bn]['parent']==an):continue
                if _shape_overlap(a,b,tolerance):pairs.append([an,bn])
        return {'possible_self_collision':bool(pairs),'self_pairs':pairs,'nonfoot_ground_collision':bool(ground),'nonfoot_ground':ground,'foot_ground_collision':bool(foot_ground),'foot_ground':foot_ground,'method':'URDF OBBs and cylinder-enclosing capsules; adjacent links and fixed rigid groups excluded'}


def _segment_distance(a,b,c,d):
    # Convex quadratic over the unit square; include interior solution and edges.
    u=b-a;v=d-c;w=a-c;A=np.dot(u,u);B=np.dot(u,v);C=np.dot(v,v);D=np.dot(u,w);E=np.dot(v,w)
    candidates=[];det=A*C-B*B
    if det>1e-20:
        s=(B*E-C*D)/det;t=(A*E-B*D)/det
        if 0<=s<=1 and 0<=t<=1:candidates.append((s,t))
    for s in [0.,1.]:candidates.append((s,float(np.clip((E+B*s)/C,0,1)) if C>1e-20 else 0.))
    for t in [0.,1.]:candidates.append((float(np.clip((B*t-D)/A,0,1)) if A>1e-20 else 0.,t))
    return min(np.linalg.norm(w+s*u-t*v) for s,t in candidates)


def _segment_box_distance(a,b,box):
    a=box['rotation'].T@(a-box['center']);b=box['rotation'].T@(b-box['center']);v=b-a;h=box['half']
    knots=[0.,1.]
    for i in range(3):
        if abs(v[i])>1e-20:
            knots.extend(float(t) for t in [(-h[i]-a[i])/v[i],(h[i]-a[i])/v[i]] if 0<t<1)
    knots=sorted(set(knots));candidates=knots[:]
    for lo,hi in zip(knots[:-1],knots[1:]):
        mid=(lo+hi)/2;point=a+mid*v;active=np.abs(point)>h
        va=v[active];offset=a[active]-np.sign(point[active])*h[active]
        if va@va>1e-20:candidates.append(float(np.clip(-(offset@va)/(va@va),lo,hi)))
    return min(np.linalg.norm(np.maximum(np.abs(a+t*v)-h,0)) for t in candidates)


def _shape_overlap(a,b,tol=1e-8):
    if a['kind']=='capsule' and b['kind']=='capsule':return _segment_distance(a['a'],a['b'],b['a'],b['b'])<a['radius']+b['radius']-tol
    if a['kind']=='box' and b['kind']=='capsule':a,b=b,a
    if a['kind']=='capsule':return _segment_box_distance(a['a'],a['b'],b)<a['radius']-tol
    # OBB separating-axis test, including all nine edge cross products.
    delta=b['center']-a['center'];axes=[*a['rotation'].T,*b['rotation'].T]
    axes.extend(np.cross(x,y) for x in a['rotation'].T for y in b['rotation'].T)
    for axis in axes:
        norm=np.linalg.norm(axis)
        if norm<1e-12:continue
        axis=axis/norm;ra=np.sum(np.abs(a['rotation'].T@axis)*a['half']);rb=np.sum(np.abs(b['rotation'].T@axis)*b['half'])
        if abs(axis@delta)>=ra+rb-tol:return False
    return True


def support_triangle(contacts,com,mass,gravity=9.81):
    """Horizontal support/vertical normal force bound; no frictional dynamics."""
    xy=np.asarray(contacts,dtype=float)[:,:2];p=np.asarray(com,dtype=float)[:2]
    if xy.shape!=(3,2):raise ValueError('Exactly three support contacts required')
    A=np.vstack([xy.T,np.ones(3)])
    if abs(np.linalg.det(A))<1e-12:return {'inside':False,'margin_m':float('-inf'),'barycentric':None,'normal_forces_N':None}
    w=np.linalg.solve(A,np.r_[p,1]);orientation=np.sign(np.linalg.det(A));margins=[]
    for a,b in zip(xy,np.roll(xy,-1,axis=0)):
        e=b-a;cross=e[0]*(p[1]-a[1])-e[1]*(p[0]-a[0]);margins.append(float(orientation*cross/np.linalg.norm(e)))
    inside=bool(np.all(w>=-1e-10))
    return {'inside':inside,'margin_m':min(margins),'barycentric':w.tolist(),'normal_forces_N':(mass*gravity*w).tolist() if inside else None}
