"""Isolated Stage2 Go2 environment for the verified rolling height field.

Only terrain wiring and recording cameras differ from the existing Stage2 base.
No terrain generation, Genesis initialization, policy loading or training occurs
on import. The caller must verify approved source hashes before construction.
"""
import copy
import numpy as np
from .stage1_flat import flat_env_class,torque_setup
from .stage2_boundary import query_points
from .natural_rewards import contact_slip_cost


def terrain_options(terrain):
    if not isinstance(terrain,dict) or 'height_mm' not in terrain:
        raise ValueError('Verified terrain with integer millimetre samples is required')
    mm=np.asarray(terrain['height_mm'])
    if mm.shape!=(161,53) or mm.dtype!=np.int16:
        raise ValueError('Native rolling terrain requires161x53 int16 millimetres')
    if 'height_m' in terrain:
        h=np.asarray(terrain['height_m'])
        if h.shape!=mm.shape or not np.isfinite(h).all() or not np.allclose(h,mm.astype(float)*.001,rtol=0,atol=1e-12):
            raise ValueError('Metre and millimetre height fields disagree')
    return dict(height_field=terrain['height_mm'],horizontal_scale=.05,vertical_scale=.001,pos=(-1.,-1.3,0.))


def camera_options(x):
    return dict(
        side=dict(res=(640,360),pos=(x,-3.,.3),lookat=(x,0.,.3),up=(0.,0.,1.),fov=60,GUI=False),
        oblique=dict(res=(640,360),pos=(x+2.,-3.,2.),lookat=(x,0.,.3),up=(0.,0.,1.),fov=55,GUI=False),
        overhead=dict(res=(640,360),pos=(x,0.,5.),lookat=(x,0.,0.),up=(0.,1.,0.),fov=55,GUI=False))


def quality_configuration(env_cfg):
    cfg=copy.deepcopy(env_cfg)
    cfg['clip_joint_targets_to_urdf']=True
    cfg['enforce_urdf_torques']=True
    cfg.setdefault('joint_target_margin_rad',.12)
    return cfg

import math

import torch
from tensordict import TensorDict

import genesis as gs
from genesis.utils.geom import quat_to_xyz, transform_by_quat, inv_quat, transform_quat_by_quat


def gs_rand(lower, upper, batch_shape):
    assert lower.shape == upper.shape
    return (upper - lower) * torch.rand(size=(*batch_shape, *lower.shape), dtype=gs.tc_float, device=gs.device) + lower


class _TerrainGo2Env:
    def __init__(self, num_envs, env_cfg, obs_cfg, reward_cfg, command_cfg, show_viewer=False,
                 terrain=None, auto_reset=True, record=False, static_obstacles=None, dynamic_obstacles=None):
        if (terrain is None and env_cfg.get('surface_kind')!='FLAT') or static_obstacles or dynamic_obstacles:
            raise ValueError('Rolling native environment requires its terrain and no additional obstacles')
        if terrain is not None:terrain_options(terrain)
        self.auto_reset = auto_reset
        self.num_envs: int = num_envs
        self.num_actions = env_cfg["num_actions"]
        self.cfg = env_cfg
        self.num_commands = command_cfg["num_commands"]
        self.device = gs.device

        self.simulate_action_latency = True  # there is a 1 step latency on real robot
        self.dt = 0.02  # control frequency on real robot is 50hz
        self.max_episode_length = math.ceil(env_cfg["episode_length_s"] / self.dt)

        self.env_cfg = env_cfg
        self.obs_cfg = obs_cfg
        self.reward_cfg = reward_cfg
        self.command_cfg = command_cfg

        self.obs_scales: dict[str, float] = obs_cfg["obs_scales"]
        self.reward_scales: dict[str, float] = reward_cfg["reward_scales"]

        self.scene = gs.Scene(
            sim_options=gs.options.SimOptions(
                dt=self.dt,
                substeps=env_cfg.get("retest_substeps", 2),
            ),
            rigid_options=gs.options.RigidOptions(
                enable_self_collision=False,
                # For this locomotion policy, there are usually no more than 20 collision pairs. Setting a low value
                # can save memory. Violating this condition will raise an exception.
                max_collision_pairs=env_cfg.get('collision_pair_limit',128 if terrain or static_obstacles or dynamic_obstacles else 20),
                tolerance=1e-5,
            ),
            vis_options=gs.options.VisOptions(
                rendered_envs_idx=[0],
            ),
            viewer_options=gs.options.ViewerOptions(
                camera_pos=(2.0, 0.0, 2.5),
                camera_lookat=(0.0, 0.0, 0.5),
                camera_fov=40,
            ),
            show_viewer=show_viewer,
        )

        self.ground_data = terrain
        from .rolling_uneven_media import viridis_rgb
        if terrain is not None:
            spec=terrain_options(terrain);texture=viridis_rgb(np.asarray(terrain['height_m']).T[::-1])
            self.ground=self.scene.add_entity(gs.morphs.Terrain(**spec),material=gs.materials.Rigid(friction=1.0),surface=gs.surfaces.Default(diffuse_texture=gs.textures.ImageTexture(image_array=texture),roughness=1.0))
        else:
            self.ground=self.scene.add_entity(gs.morphs.URDF(file='urdf/plane/plane.urdf',fixed=True),material=gs.materials.Rigid(friction=1.0),surface=gs.surfaces.Default(color=tuple(viridis_rgb(0.).astype(float)/255)))
        self.static_obstacles = []

        self.robot = self.scene.add_entity(
            gs.morphs.URDF(
                file="urdf/go2/urdf/go2.urdf",
                pos=self.env_cfg["base_init_pos"],
                quat=self.env_cfg["base_init_quat"],
            ),
        )

        self.dynamic_obstacles = []
        self.camera = self.side_camera = self.overhead_camera = None
        if record:
            specs = camera_options(float(self.env_cfg["base_init_pos"][0]))
            self.side_camera = self.scene.add_camera(**specs['side'])
            self.camera = self.scene.add_camera(**specs['oblique'])
            self.overhead_camera = self.scene.add_camera(**specs['overhead'])
        self.scene.build(n_envs=num_envs)

        # names to indices
        self.motors_dof_idx = torch.tensor(
            [self.robot.get_joint(name).dof_start for name in self.env_cfg["joint_names"]],
            dtype=gs.tc_int,
            device=gs.device,
        )
        self.actions_dof_idx = torch.argsort(self.motors_dof_idx)

        # PD control parameters
        self.robot.set_dofs_kp([self.env_cfg["kp"]] * self.num_actions, self.motors_dof_idx)
        self.robot.set_dofs_kv([self.env_cfg["kd"]] * self.num_actions, self.motors_dof_idx)

        # Define global gravity direction vector
        self.global_gravity = torch.tensor([0.0, 0.0, -1.0], dtype=gs.tc_float, device=gs.device)

        # Initial state
        self.init_base_pos = torch.tensor(self.env_cfg["base_init_pos"], dtype=gs.tc_float, device=gs.device)
        self.init_base_quat = torch.tensor(self.env_cfg["base_init_quat"], dtype=gs.tc_float, device=gs.device)
        self.inv_base_init_quat = inv_quat(self.init_base_quat)
        self.init_dof_pos = torch.tensor(
            [self.env_cfg["default_joint_angles"][joint.name] for joint in self.robot.joints[1:]],
            dtype=gs.tc_float,
            device=gs.device,
        )
        self.init_qpos = torch.concatenate((self.init_base_pos, self.init_base_quat, self.init_dof_pos))
        self.init_projected_gravity = transform_by_quat(self.global_gravity, self.inv_base_init_quat)

        # initialize buffers
        self.base_lin_vel = torch.empty((self.num_envs, 3), dtype=gs.tc_float, device=gs.device)
        self.base_ang_vel = torch.empty((self.num_envs, 3), dtype=gs.tc_float, device=gs.device)
        self.projected_gravity = torch.empty((self.num_envs, 3), dtype=gs.tc_float, device=gs.device)
        self.rew_buf = torch.empty((self.num_envs,), dtype=gs.tc_float, device=gs.device)
        self.reset_buf = torch.ones((self.num_envs,), dtype=gs.tc_bool, device=gs.device)
        self.episode_length_buf = torch.empty((self.num_envs,), dtype=gs.tc_int, device=gs.device)
        self.commands = torch.empty((self.num_envs, self.num_commands), dtype=gs.tc_float, device=gs.device)
        self.commands_scale = torch.tensor(
            [self.obs_scales["lin_vel"], self.obs_scales["lin_vel"], self.obs_scales["ang_vel"]],
            device=gs.device,
            dtype=gs.tc_float,
        )
        self.commands_limits: tuple[torch.Tensor, torch.Tensor] = tuple(
            torch.tensor(values, dtype=gs.tc_float, device=gs.device)
            for values in zip(
                self.command_cfg["lin_vel_x_range"],
                self.command_cfg["lin_vel_y_range"],
                self.command_cfg["ang_vel_range"],
            )
        )
        self.actions = torch.zeros((self.num_envs, self.num_actions), dtype=gs.tc_float, device=gs.device)
        self.last_actions = torch.zeros_like(self.actions)
        self.dof_pos = torch.empty_like(self.actions)
        self.dof_vel = torch.empty_like(self.actions)
        self.last_dof_vel = torch.zeros_like(self.actions)
        self.base_pos = torch.empty((self.num_envs, 3), dtype=gs.tc_float, device=gs.device)
        self.base_quat = torch.empty((self.num_envs, 4), dtype=gs.tc_float, device=gs.device)
        self.base_euler = torch.empty((self.num_envs, 3), dtype=gs.tc_float, device=gs.device)
        self.default_dof_pos = torch.tensor(
            [self.env_cfg["default_joint_angles"][name] for name in self.env_cfg["joint_names"]],
            dtype=gs.tc_float,
            device=gs.device,
        )
        self.extras = dict()  # extra information for logging

        # prepare reward functions and multiply reward scales by dt
        self.reward_functions, self.episode_sums = dict(), dict()
        for name in self.reward_scales.keys():
            self.reward_scales[name] *= self.dt
            self.reward_functions[name] = getattr(self, "_reward_" + name)
            self.episode_sums[name] = torch.zeros((self.num_envs,), dtype=gs.tc_float, device=gs.device)

        self.reset()

    def _resample_commands(self, envs_idx):
        commands = gs_rand(*self.commands_limits, (self.num_envs,))
        if envs_idx is None:
            self.commands.copy_(commands)
        else:
            torch.where(envs_idx[:, None], commands, self.commands, out=self.commands)

    def step(self, actions):
        self.actions = torch.clip(actions, -self.env_cfg["clip_actions"], self.env_cfg["clip_actions"])
        exec_actions = self.last_actions if self.simulate_action_latency else self.actions
        target_dof_pos = exec_actions * self.env_cfg["action_scale"] + self.default_dof_pos
        self.robot.control_dofs_position(target_dof_pos[:, self.actions_dof_idx], slice(6, 18))
        self.scene.step()

        # update buffers
        self.episode_length_buf += 1
        self.base_pos = self.robot.get_pos()
        self.base_quat = self.robot.get_quat()
        self.base_euler = quat_to_xyz(
            transform_quat_by_quat(self.inv_base_init_quat, self.base_quat), rpy=True, degrees=True
        )
        inv_base_quat = inv_quat(self.base_quat)
        self.base_lin_vel = transform_by_quat(self.robot.get_vel(), inv_base_quat)
        self.base_ang_vel = transform_by_quat(self.robot.get_ang(), inv_base_quat)
        self.projected_gravity = transform_by_quat(self.global_gravity, inv_base_quat)
        self.dof_pos = self.robot.get_dofs_position(self.motors_dof_idx)
        self.dof_vel = self.robot.get_dofs_velocity(self.motors_dof_idx)

        # compute reward
        self.rew_buf.zero_()
        for name, reward_func in self.reward_functions.items():
            rew = reward_func() * self.reward_scales[name]
            self.rew_buf += rew
            self.episode_sums[name] += rew

        self._resample_commands(self.episode_length_buf % int(self.env_cfg["resampling_time_s"] / self.dt) == 0)

        # check termination and reset
        self.reset_buf = self.episode_length_buf > self.max_episode_length
        self.reset_buf |= torch.abs(self.base_euler[:, 1]) > self.env_cfg["termination_if_pitch_greater_than"]
        self.reset_buf |= torch.abs(self.base_euler[:, 0]) > self.env_cfg["termination_if_roll_greater_than"]
        self.engine_errors = self.scene.rigid_solver.get_error_envs_mask()
        self.reset_buf |= self.engine_errors
        if self.ground_data is not None and hasattr(self,"_terrain_outside"):
            self.reset_buf |= self._terrain_outside

        # Compute timeout
        self.extras["time_outs"] = (self.episode_length_buf > self.max_episode_length).to(dtype=gs.tc_float)

        # Reset environment if necessary
        if self.auto_reset:
            self._reset_idx(self.reset_buf)

        # update observations
        self._update_observation()

        self.last_actions.copy_(self.actions)
        self.last_dof_vel.copy_(self.dof_vel)

        return self.get_observations(), self.rew_buf, self.reset_buf, self.extras

    def get_observations(self):
        return TensorDict({"policy": self.obs_buf}, batch_size=[self.num_envs])

    def _reset_idx(self, envs_idx=None):
        # reset state
        self.robot.set_qpos(self.init_qpos, envs_idx=envs_idx, zero_velocity=True, skip_forward=True)

        # reset buffers
        if envs_idx is None:
            self.base_pos.copy_(self.init_base_pos)
            self.base_quat.copy_(self.init_base_quat)
            self.projected_gravity.copy_(self.init_projected_gravity)
            self.dof_pos.copy_(self.init_dof_pos)
            self.base_lin_vel.zero_()
            self.base_ang_vel.zero_()
            self.dof_vel.zero_()
            self.actions.zero_()
            self.last_actions.zero_()
            self.last_dof_vel.zero_()
            self.episode_length_buf.zero_()
            self.reset_buf.fill_(True)
        else:
            torch.where(envs_idx[:, None], self.init_base_pos, self.base_pos, out=self.base_pos)
            torch.where(envs_idx[:, None], self.init_base_quat, self.base_quat, out=self.base_quat)
            torch.where(
                envs_idx[:, None], self.init_projected_gravity, self.projected_gravity, out=self.projected_gravity
            )
            torch.where(envs_idx[:, None], self.init_dof_pos, self.dof_pos, out=self.dof_pos)
            self.base_lin_vel.masked_fill_(envs_idx[:, None], 0.0)
            self.base_ang_vel.masked_fill_(envs_idx[:, None], 0.0)
            self.dof_vel.masked_fill_(envs_idx[:, None], 0.0)
            self.actions.masked_fill_(envs_idx[:, None], 0.0)
            self.last_actions.masked_fill_(envs_idx[:, None], 0.0)
            self.last_dof_vel.masked_fill_(envs_idx[:, None], 0.0)
            self.episode_length_buf.masked_fill_(envs_idx, 0)
            self.reset_buf.masked_fill_(envs_idx, True)

        # fill extras
        n_envs = envs_idx.sum() if envs_idx is not None else self.num_envs
        self.extras["episode"] = {}
        for key, value in self.episode_sums.items():
            if envs_idx is None:
                mean = value.mean()
            else:
                mean = torch.where(n_envs > 0, value[envs_idx].sum() / n_envs, 0.0)
            self.extras["episode"]["rew_" + key] = mean / self.env_cfg["episode_length_s"]
            if envs_idx is None:
                value.zero_()
            else:
                value.masked_fill_(envs_idx, 0.0)

        # random sample command upon reset
        self._resample_commands(envs_idx)

    def _update_observation(self):
        self.obs_buf = torch.concatenate(
            (
                self.base_ang_vel * self.obs_scales["ang_vel"],  # 3
                self.projected_gravity,  # 3
                self.commands * self.commands_scale,  # 3
                (self.dof_pos - self.default_dof_pos) * self.obs_scales["dof_pos"],  # 12
                self.dof_vel * self.obs_scales["dof_vel"],  # 12
                self.actions,  # 12
            ),
            dim=-1,
        )

    def reset(self):
        self._reset_idx()
        self._update_observation()
        return self.get_observations()

    # Reward functions.
    def _reward_tracking_lin_vel(self):
        # Tracking of linear velocity commands (xy axes)
        lin_vel_error = torch.sum(torch.square(self.commands[:, :2] - self.base_lin_vel[:, :2]), dim=1)
        return torch.exp(-lin_vel_error / self.reward_cfg["tracking_sigma"])

    def _reward_tracking_ang_vel(self):
        # Tracking of angular velocity commands (yaw)
        ang_vel_error = torch.square(self.commands[:, 2] - self.base_ang_vel[:, 2])
        return torch.exp(-ang_vel_error / self.reward_cfg["tracking_sigma"])

    def _reward_lin_vel_z(self):
        # Penalize z axis base linear velocity
        return torch.square(self.base_lin_vel[:, 2])

    def _reward_action_rate(self):
        # Penalize changes in actions
        return torch.sum(torch.square(self.last_actions - self.actions), dim=1)

    def _reward_similar_to_default(self):
        # Penalize joint poses far away from default pose
        return torch.sum(torch.abs(self.dof_pos - self.default_dof_pos), dim=1)

    def _reward_base_height(self):
        # Penalize base height away from target
        return torch.square(self.base_pos[:, 2] - self.reward_cfg["base_height_target"])



LEGS=("FL","FR","RL","RR")

def feet(robot):
    result={}
    for leg in LEGS:
        geoms=[g for g in robot.geoms if g.link.name==leg+"_calf" and g.type==gs.GEOM_TYPE.SPHERE]
        if len(geoms)!=1:raise ValueError(f"{leg}: expected one merged foot sphere, got {len(geoms)}")
        result[leg]=geoms[0]
    return result

class QualityEnv(flat_env_class(_TerrainGo2Env)):
    def __init__(self,num_envs,env_cfg,obs_cfg,reward_cfg,command_cfg,show_viewer=False,
                 terrain=None,auto_reset=False,record=False,static_obstacles=None,dynamic_obstacles=None):
        super().__init__(num_envs,quality_configuration(env_cfg),obs_cfg,reward_cfg,command_cfg,
                         show_viewer=show_viewer,terrain=terrain,auto_reset=auto_reset,record=record,
                         static_obstacles=static_obstacles,dynamic_obstacles=dynamic_obstacles)
        self.foot_geoms=feet(self.robot)
        margin=self.env_cfg.get("joint_target_margin_rad",0.)
        audit=torque_setup(self,self.env_cfg,gs)
        self.control_audit=audit
        lim=[audit["joint_limits_rad"][n] for n in self.cfg["joint_names"]]
        lower=torch.tensor([x[0]+margin for x in lim],device=self.device)
        upper=torch.tensor([x[1]-margin for x in lim],device=self.device)
        self.action_lower=(lower-self.default_dof_pos)/self.cfg["action_scale"]
        self.action_upper=(upper-self.default_dof_pos)/self.cfg["action_scale"]
        self.robot.set_dofs_kv([1.0],[self.robot.get_joint("RL_calf_joint").dof_start])
        self.control_audit["kd_readback"]=self.robot.get_dofs_kv(self.motors_dof_idx).tolist()
    def step(self,actions):
        self._terrain_outside=torch.zeros((self.num_envs,),dtype=torch.bool,device=self.device)
        return super().step(actions)
    def _surface_for_reward(self,xy):
        data=self.ground_data
        bounded,outside=query_points(xy,(float(data["x"][0]),float(data["x"][-1]),float(data["y"][0]),float(data["y"][-1])))
        self._terrain_outside |= outside
        return self.ground.get_terrain_height(bounded)
    def _reward_foot_clearance(self):
        # No prescribed phase or gait: PPO chooses which legs to swing and when.
        if not hasattr(self,"foot_geoms"):self.foot_geoms=feet(self.robot)
        centers=torch.stack([g.get_pos() for g in self.foot_geoms.values()],dim=1)
        surface=self._surface_for_reward(centers[:,:,:2]) if self.ground_data is not None else torch.zeros_like(centers[:,:,2])
        h=centers[:,:,2]-.022-surface
        target=self.reward_cfg["clearance_target_m"]
        return (torch.exp(-torch.square((h-target)/.02))*(h>.004)).sum(dim=1)
    def _reward_base_height(self):
        surface=self._surface_for_reward(self.base_pos[:,:2,None].transpose(1,2)).squeeze(-1) if self.ground_data is not None else 0.
        return torch.square(self.base_pos[:,2]-surface-self.reward_cfg["base_height_target"])
    def _reward_stance_slip(self):
        contact=self.robot.get_contacts(is_padded=True)
        ids=torch.tensor([g.idx for g in self.foot_geoms.values()],device=self.device)
        links=[g.link.idx-self.robot.link_start for g in self.foot_geoms.values()]
        a=contact["geom_a"];b=contact["geom_b"]
        mask=((a[:,:,None]==ids)|(b[:,:,None]==ids)) & contact["valid_mask"][:,:,None]
        mask=mask & ((a<self.robot.geom_start)|(b<self.robot.geom_start))[:,:,None]
        return contact_slip_cost(self.robot.get_links_pos(links),self.robot.get_links_vel(links),
                                 self.robot.get_links_ang(links),contact["position"],mask)


# Public convenience alias; both names use the same bounded quality environment.
Go2Env = QualityEnv
