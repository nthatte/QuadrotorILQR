from src.quadrotor_ilqr_binding import QuadrotorILQR
import src.trajectory_pb2 as traj
import src.ilqr_options_pb2 as opts
import numpy as np
from scipy.spatial.transform import Rotation
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from mpl_toolkits import mplot3d
from stl import mesh
from enum import IntEnum
from copy import deepcopy


class IDX(IntEnum):
    time_s = 0
    translation_x_m = 1
    translation_y_m = 2
    translation_z_m = 3
    quaternion_w = 4
    quaternion_x = 5
    quaternion_y = 6
    quaternion_z = 7
    vel_translational_x_mps = 8
    vel_translational_y_mps = 9
    vel_translational_z_mps = 10
    vel_rotational_x_radps = 11
    vel_rotational_y_radps = 12
    vel_rotational_z_radps = 13
    control_0 = 14
    control_1 = 15
    control_2 = 16
    control_3 = 17


def extract_traj_array(trajectory: traj.QuadrotorTrajectory):
    out = np.zeros((len(trajectory.points), len(IDX)))
    extract_fcns = {
        IDX.time_s: lambda pt: pt.time_s,
        IDX.translation_x_m: lambda pt: pt.state.inertial_from_body.translation.c0,
        IDX.translation_y_m: lambda pt: pt.state.inertial_from_body.translation.c1,
        IDX.translation_z_m: lambda pt: pt.state.inertial_from_body.translation.c2,
        IDX.quaternion_w: lambda pt: pt.state.inertial_from_body.rotation.quaternion.c0,
        IDX.quaternion_x: lambda pt: pt.state.inertial_from_body.rotation.quaternion.c1,
        IDX.quaternion_y: lambda pt: pt.state.inertial_from_body.rotation.quaternion.c2,
        IDX.quaternion_z: lambda pt: pt.state.inertial_from_body.rotation.quaternion.c3,
        IDX.vel_translational_x_mps: lambda pt: pt.state.body_velocity.c0,
        IDX.vel_translational_y_mps: lambda pt: pt.state.body_velocity.c1,
        IDX.vel_translational_z_mps: lambda pt: pt.state.body_velocity.c2,
        IDX.vel_rotational_x_radps: lambda pt: pt.state.body_velocity.c3,
        IDX.vel_rotational_y_radps: lambda pt: pt.state.body_velocity.c4,
        IDX.vel_rotational_z_radps: lambda pt: pt.state.body_velocity.c5,
        IDX.control_0: lambda pt: pt.control.c0,
        IDX.control_1: lambda pt: pt.control.c1,
        IDX.control_2: lambda pt: pt.control.c2,
        IDX.control_3: lambda pt: pt.control.c3,
    }
    for field in IDX:
        out[:, field] = [extract_fcns[field](pt) for pt in trajectory.points]

    return out


def make_state(x_m=0.0, y_m=0.0, z_m=0.0):
    return traj.QuadrotorState(
        inertial_from_body=traj.SE3(
            translation=traj.Vec3(c0=x_m, c1=y_m, c2=z_m),
            rotation=traj.SO3(quaternion=traj.Vec4(c0=1, c1=0, c2=0, c3=0)),
        ),
        body_velocity=traj.Vec6(),
    )


def make_square_traj_pt(t_s, vel_mps, horizon_s):
    quarter_horizon_s = horizon_s / 4.0
    if t_s < quarter_horizon_s:
        return make_state(x_m=vel_mps * t_s, y_m=0.0)
    if t_s < 2.0 * quarter_horizon_s:
        return make_state(
            x_m=vel_mps * quarter_horizon_s, y_m=vel_mps * (t_s - quarter_horizon_s)
        )
    if t_s < 3.0 * quarter_horizon_s:
        return make_state(
            x_m=vel_mps * (3.0 * quarter_horizon_s - t_s),
            y_m=vel_mps * quarter_horizon_s,
        )
    return make_state(
        x_m=0.0,
        y_m=vel_mps * (4.0 * quarter_horizon_s - t_s),
    )


def main():
    dt_s = 0.1
    horizon_s = 4.0
    time_s = np.arange(0, horizon_s, dt_s)
    vel_mps = 10
    desired_traj = traj.QuadrotorTrajectory(
        points=[
            traj.QuadrotorTrajectoryPoint(
                time_s=t_s,
                state=make_square_traj_pt(t_s, vel_mps, horizon_s),
                control=traj.Vec4(),
            )
            for t_s in time_s
        ]
    )

    options = opts.ILQROptions(
        line_search_params=opts.LineSearchParams(
            step_update=0.5,
            desired_reduction_frac=0.5,
            max_iters=100,
        ),
        convergence_criteria=opts.ConvergenceCriteria(
            rtol=1e-12,
            atol=1e-12,
            max_iters=100,
        ),
    )

    mass_kg = 1.0
    inertia = np.eye(3)
    arm_length_m = 1.0
    torque_to_thrust_ratio_m = 0.0
    g_mpss = 9.81
    Q = np.diag(np.concatenate((100 * np.ones(6), np.zeros(6))))
    R = np.eye(4)

    ilqr = QuadrotorILQR(
        mass_kg,
        inertia,
        arm_length_m,
        torque_to_thrust_ratio_m,
        g_mpss,
        Q,
        R,
        desired_traj,
        dt_s,
        options,
    )
    opt_traj = ilqr.solve(desired_traj)

    desired_traj_array = extract_traj_array(desired_traj)
    opt_traj_array = extract_traj_array(opt_traj)

    fig, ax = plt.subplots(1, 1)
    ax.plot(
        desired_traj_array[:, IDX.translation_x_m],
        desired_traj_array[:, IDX.translation_y_m],
        label="desired",
    )
    ax.plot(
        opt_traj_array[:, IDX.translation_x_m],
        opt_traj_array[:, IDX.translation_y_m],
        label="optimized",
    )
    ax.set_xlabel("x translation [m]")
    ax.set_ylabel("y translation [m]")

    fig, ax = plt.subplots(3, 1, sharex=True)
    ax[0].plot(
        desired_traj_array[:, IDX.time_s],
        desired_traj_array[:, IDX.translation_x_m],
        label="desired",
    )
    ax[0].plot(
        opt_traj_array[:, IDX.time_s],
        opt_traj_array[:, IDX.translation_x_m],
        label="optimized",
    )
    ax[0].legend()
    ax[0].set_ylabel("x translation [m]")

    ax[1].plot(
        desired_traj_array[:, IDX.time_s],
        desired_traj_array[:, IDX.translation_y_m],
        label="desired",
    )
    ax[1].plot(
        opt_traj_array[:, IDX.time_s],
        opt_traj_array[:, IDX.translation_y_m],
        label="optimized",
    )
    ax[1].legend()
    ax[1].set_ylabel("y translation [m]")

    ax[2].plot(
        desired_traj_array[:, IDX.time_s],
        desired_traj_array[:, IDX.control_0 : IDX.control_3 + 1],
        label="desired",
    )
    ax[2].plot(
        opt_traj_array[:, IDX.time_s],
        opt_traj_array[:, IDX.control_0 : IDX.control_3 + 1],
        label="optimized",
    )
    ax[2].legend()
    ax[2].set_ylabel("control")

    fig.align_ylabels()
    ax[-1].set_xlabel("time [s]")

    fig, ax = plt.subplots(1, 1, subplot_kw={"projection": "3d"})
    orig_quad_mesh = mesh.Mesh.from_file("quad_simple_scaled.stl")
    orig_quad_mesh.rotate([1.0, 0.0, 0.0], np.pi / 2.0)
    orig_quad_mesh.rotate([0.0, 0.0, 1.0], np.pi)
    collection = ax.add_collection3d(
        mplot3d.art3d.Poly3DCollection(orig_quad_mesh.vectors)
    )

    # set equal aspect ratio
    scale = desired_traj_array[
        :, IDX.translation_x_m : IDX.translation_z_m + 1
    ].flatten()
    ax.auto_scale_xyz(scale, scale, scale)

    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.set_zlabel("z")

    def anim_init():
        return (collection,)

    def anim_update(traj_pt):
        quaternion_scalar_first = traj_pt.state.inertial_from_body.rotation.quaternion
        quaternion_scalar_last = np.array(
            [
                quaternion_scalar_first.c1,
                quaternion_scalar_first.c2,
                quaternion_scalar_first.c3,
                quaternion_scalar_first.c0,
            ]
        )
        rot = Rotation.from_quat(quaternion_scalar_last)
        translation = np.array(
            [
                traj_pt.state.inertial_from_body.translation.c0,
                traj_pt.state.inertial_from_body.translation.c1,
                traj_pt.state.inertial_from_body.translation.c2,
            ]
        )

        transform = np.eye(4)
        transform[0:3, 0:3] = rot.as_matrix()
        transform[0:3, 3] = translation

        quad_mesh = deepcopy(orig_quad_mesh)
        quad_mesh.transform(transform)
        collection.set_verts(quad_mesh.vectors)
        return (collection,)

    ani = animation.FuncAnimation(
        fig, anim_update, frames=opt_traj.points, init_func=anim_init, blit=False
    )

    plt.show()


if __name__ == "__main__":
    main()