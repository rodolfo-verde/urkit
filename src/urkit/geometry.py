"""Quaternion and rotation vector geometry helpers.

Conversion utilities for UR rotation vectors, quaternions, and
Roll-Pitch-Yaw angles. Uses the rxyz convention (same as UR
teach pendant and tf2). Also provides quaternion-based pose
transformation for frame-aware delta movements.
"""

from __future__ import annotations

import math
from enum import IntEnum


def rotvec_to_quat(rv: list[float]) -> tuple[float, float, float, float]:
    """Convert a rotation vector to a quaternion (x, y, z, w).

    Args:
        rv: Rotation vector [rx, ry, rz].

    Returns:
        Quaternion as (x, y, z, w).
    """
    ax, ay, az = rv
    angle = math.sqrt(ax * ax + ay * ay + az * az)
    if angle < 1e-10:
        return (0.0, 0.0, 0.0, 1.0)
    half_angle = angle / 2
    s = math.sin(half_angle) / angle
    return (s * ax, s * ay, s * az, math.cos(half_angle))


def quat_to_rotvec(q: tuple[float, float, float, float]) -> list[float]:
    """Convert a quaternion (x, y, z, w) to a rotation vector.

    Args:
        q: Quaternion (x, y, z, w).

    Returns:
        Rotation vector [rx, ry, rz].
    """
    x, y, z, w = q
    norm_xyz = math.sqrt(x * x + y * y + z * z)
    angle = 2 * math.atan2(norm_xyz, w)
    if norm_xyz < 1e-10:
        return [0.0, 0.0, 0.0]
    return [x / norm_xyz * angle, y / norm_xyz * angle, z / norm_xyz * angle]


def quat_to_rpy(q: tuple[float, float, float, float]) -> tuple[float, float, float]:
    """Extract Roll-Pitch-Yaw from a quaternion (rxyz convention).

    Args:
        q: Quaternion (x, y, z, w).

    Returns:
        (roll, pitch, yaw) in radians.
    """
    x, y, z, w = q
    roll = math.atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y))
    pitch = math.asin(min(1, max(-1, 2 * (w * y - z * x))))
    yaw = math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
    return roll, pitch, yaw


def rpy_to_quat(
    r: float, p: float, y: float
) -> tuple[float, float, float, float]:
    """Create a quaternion (x, y, z, w) from RPY angles (rxyz convention).

    Args:
        r: Roll angle in radians.
        p: Pitch angle in radians.
        y: Yaw angle in radians.

    Returns:
        Quaternion (x, y, z, w).
    """
    cr, sr = math.cos(r / 2), math.sin(r / 2)
    cp, sp = math.cos(p / 2), math.sin(p / 2)
    cy, sy = math.cos(y / 2), math.sin(y / 2)
    return (
        sr * cp * cy - cr * sp * sy,  # x
        cr * sp * cy + sr * cp * sy,  # y
        cr * cp * sy - sr * sp * cy,  # z
        cr * cp * cy + sr * sp * sy,  # w
    )


def orient_tcp_down(pose: list[float]) -> list[float]:
    """Orient TCP downward while preserving tool heading.

    Points the tool Z-axis straight down (base frame -Z) while
    preserving the tool's heading (X-axis direction projected to
    the XY plane). This avoids the ambiguity of RPY yaw at roll=π
    and produces a smooth, predictable orientation change.

    Matches the approach used in ur_bag_picking's orient_face_down.

    Args:
        pose: [x, y, z, rx, ry, rz] rotation vector pose.

    Returns:
        New pose with same position but TCP pointing downward.
    """
    pos = pose[:3]
    rv = pose[3:]

    # Current rotation matrix (columns are X, Y, Z axes)
    R = _rotvec_to_matrix(rv)

    # Target: Z points down
    z_new = [0.0, 0.0, -1.0]

    # Preserve heading: project current X axis to XY plane
    x_new = [R[0][0], R[1][0], 0.0]
    norm_x = math.sqrt(x_new[0] ** 2 + x_new[1] ** 2)

    if norm_x < 1e-6:
        # X is nearly vertical — use Y projection instead
        x_new = [0.0, 0.0, 0.0]
        y_new = [R[0][1], R[1][1], 0.0]
        norm_y = math.sqrt(y_new[0] ** 2 + y_new[1] ** 2)

        if norm_y < 1e-6:
            # Both vertical — fallback to roll=π
            return [pos[0], pos[1], pos[2], math.pi, 0.0, 0.0]

        y_new[0] /= norm_y
        y_new[1] /= norm_y
        # x = y cross z (right-hand rule: y × -z)
        x_new = [
            y_new[1] * z_new[2] - y_new[2] * z_new[1],
            y_new[2] * z_new[0] - y_new[0] * z_new[2],
            y_new[0] * z_new[1] - y_new[1] * z_new[0],
        ]
    else:
        x_new[0] /= norm_x
        x_new[1] /= norm_x
        # y = z cross x
        y_new = [
            z_new[1] * x_new[2] - z_new[2] * x_new[1],
            z_new[2] * x_new[0] - z_new[0] * x_new[2],
            z_new[0] * x_new[1] - z_new[1] * x_new[0],
        ]

    # Build rotation matrix from columns [x_new, y_new, z_new]
    R_new = [
        [x_new[0], y_new[0], z_new[0]],
        [x_new[1], y_new[1], z_new[1]],
        [x_new[2], y_new[2], z_new[2]],
    ]

    rv_target = _matrix_to_rotvec(R_new)

    return [pos[0], pos[1], pos[2], rv_target[0], rv_target[1], rv_target[2]]


# ------------------------------------------------------------------
# Quaternion algebra helpers
# ------------------------------------------------------------------


def _quat_multiply(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    """Multiply two quaternions (Hamilton product).

    Returns a * b, where both are (x, y, z, w).
    """
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    )


def _quat_conjugate(
    q: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    """Return the conjugate of a quaternion (x, y, z, w) -> (-x, -y, -z, w)."""
    x, y, z, w = q
    return (-x, -y, -z, w)


def _quat_rotate_vector(
    q: tuple[float, float, float, float],
    v: list[float],
) -> list[float]:
    """Rotate a 3D vector by a quaternion.

    Uses the q * v * q_conj formula, where v is treated as a pure
    quaternion (0, vx, vy, vz).

    Args:
        q: Rotation quaternion (x, y, z, w).
        v: 3D vector [vx, vy, vz].

    Returns:
        Rotated vector [vx', vy', vz'].
    """
    # Convert vector to pure quaternion
    vq = (v[0], v[1], v[2], 0.0)
    # q * v * q_conj
    result = _quat_multiply(q, vq)
    result = _quat_multiply(result, _quat_conjugate(q))
    return [result[0], result[1], result[2]]


# ------------------------------------------------------------------
# Frame of reference for delta movements
# ------------------------------------------------------------------


class MoveFrame(IntEnum):
    """Coordinate frame for relative (delta) movements.

    Controls how delta vectors are interpreted during ``move_relative()`` and offsets.
    - ``BASE`` — Delta is expressed in the robot's base frame.
      Pressing +X always moves along the base X axis.
    - ``TOOL`` — Delta is expressed in the TCP (tool) frame.
      Pressing +X moves along the tool's local X axis, regardless
      of how the robot is oriented.
    """

    BASE = 0
    TOOL = 1


# ------------------------------------------------------------------
# Matrix helpers for pose composition (matches robot_mover /
# point_recording.cpp Eigen::Isometry3d approach)
# ------------------------------------------------------------------


def _rotvec_to_matrix(rv: list[float]) -> list[list[float]]:
    """Convert a rotation vector to a 3x3 rotation matrix (Rodrigues formula).

    Args:
        rv: Rotation vector [rx, ry, rz].

    Returns:
        3x3 rotation matrix as nested lists.
    """
    ax, ay, az = rv
    angle = math.sqrt(ax * ax + ay * ay + az * az)

    if angle < 1e-10:
        return [[1, 0, 0], [0, 1, 0], [0, 0, 1]]

    s = math.sin(angle)
    c = math.cos(angle)
    oc = 1.0 - c
    sx, sy, sz = ax / angle, ay / angle, az / angle

    return [
        [
            c + sx * sx * oc,
            sx * sy * oc - sz * s,
            sx * sz * oc + sy * s,
        ],
        [
            sy * sx * oc + sz * s,
            c + sy * sy * oc,
            sy * sz * oc - sx * s,
        ],
        [
            sz * sx * oc - sy * s,
            sz * sy * oc + sx * s,
            c + sz * sz * oc,
        ],
    ]


def _matrix_to_rotvec(m: list[list[float]]) -> list[float]:
    """Convert a 3x3 rotation matrix to a rotation vector.

    Uses the closed-form arccos trace method. Handles identity,
    180°, and general cases.
    """
    # Trace: m[0][0] + m[1][1] + m[2][2]
    tr = m[0][0] + m[1][1] + m[2][2]

    if tr > 3 - 1e-10:
        # Identity
        return [0.0, 0.0, 0.0]

    if tr < -1 + 1e-10:
        # 180° rotation — extract axis from rotation matrix
        # For angle=π: R[k][k] = 2*k_k^2 - 1  =>  k_k = sqrt((R[k][k]+1)/2)
        # Off-diagonal: R[i][j] + R[j][i] = 4*k_i*k_j  =>  k_i = sum / (4*k_j)
        # rotvec = axis * π
        if m[0][0] >= m[1][1] and m[0][0] >= m[2][2]:
            k0 = math.sqrt((m[0][0] + 1) / 2)
            k1 = (m[0][1] + m[1][0]) / (4 * k0) if k0 > 1e-15 else 0.0
            k2 = (m[0][2] + m[2][0]) / (4 * k0) if k0 > 1e-15 else 0.0
        elif m[1][1] >= m[0][0] and m[1][1] >= m[2][2]:
            k1 = math.sqrt((m[1][1] + 1) / 2)
            k0 = (m[0][1] + m[1][0]) / (4 * k1) if k1 > 1e-15 else 0.0
            k2 = (m[1][2] + m[2][1]) / (4 * k1) if k1 > 1e-15 else 0.0
        else:
            k2 = math.sqrt((m[2][2] + 1) / 2)
            k0 = (m[0][2] + m[2][0]) / (4 * k2) if k2 > 1e-15 else 0.0
            k1 = (m[1][2] + m[2][1]) / (4 * k2) if k2 > 1e-15 else 0.0
        return [k0 * math.pi, k1 * math.pi, k2 * math.pi]

    # General case
    angle = math.acos(max(-1, min(1, (tr - 1) / 2)))
    if angle < 1e-10:
        return [0.0, 0.0, 0.0]
    s = math.sin(angle)
    return [
        (m[2][1] - m[1][2]) / (2 * s) * angle,
        (m[0][2] - m[2][0]) / (2 * s) * angle,
        (m[1][0] - m[0][1]) / (2 * s) * angle,
    ]


def _mat_vec_mul(m: list[list[float]], v: list[float]) -> list[float]:
    """Multiply a 3x3 matrix by a 3-element vector."""
    return [
        m[0][0] * v[0] + m[0][1] * v[1] + m[0][2] * v[2],
        m[1][0] * v[0] + m[1][1] * v[1] + m[1][2] * v[2],
        m[2][0] * v[0] + m[2][1] * v[1] + m[2][2] * v[2],
    ]


def _mat_mul(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    """Multiply two 3x3 matrices."""
    return [
        [
            a[0][0]*b[0][0] + a[0][1]*b[1][0] + a[0][2]*b[2][0],
            a[0][0]*b[0][1] + a[0][1]*b[1][1] + a[0][2]*b[2][1],
            a[0][0]*b[0][2] + a[0][1]*b[1][2] + a[0][2]*b[2][2],
        ],
        [
            a[1][0]*b[0][0] + a[1][1]*b[1][0] + a[1][2]*b[2][0],
            a[1][0]*b[0][1] + a[1][1]*b[1][1] + a[1][2]*b[2][1],
            a[1][0]*b[0][2] + a[1][1]*b[1][2] + a[1][2]*b[2][2],
        ],
        [
            a[2][0]*b[0][0] + a[2][1]*b[1][0] + a[2][2]*b[2][0],
            a[2][0]*b[0][1] + a[2][1]*b[1][1] + a[2][2]*b[2][1],
            a[2][0]*b[0][2] + a[2][1]*b[1][2] + a[2][2]*b[2][2],
        ],
    ]


# ------------------------------------------------------------------
# Pose transformation
# ------------------------------------------------------------------


def transform_pose_delta(
    pose: list[float],
    delta: list[float],
    frame: MoveFrame = MoveFrame.BASE,
) -> list[float]:
    """Compute a target pose by applying a delta to the current pose.

    Uses full matrix composition (matching robot_mover's
    Eigen::Isometry3d and point_recording.cpp) — the rotation is
    composed as a 3x3 matrix, then converted back to rotvec. This
    avoids rotvec wrapping when the cumulative rotation exceeds π.

    Args:
        pose: Current TCP pose [x, y, z, rx, ry, rz].
        delta: Delta [dx, dy, dz, droll, dpitch, dyaw].
        frame: Coordinate frame for interpreting the delta.

    Returns:
        Target pose [x, y, z, rx, ry, rz].
    """
    R = _rotvec_to_matrix(pose[3:])

    # Angular delta as a rotation matrix (axis-angle → Rodrigues)
    dr = math.sqrt(delta[3] ** 2 + delta[4] ** 2 + delta[5] ** 2)
    if dr < 1e-10:
        R_delta = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
    else:
        ax = delta[3] / dr
        ay = delta[4] / dr
        az = delta[5] / dr
        s = math.sin(dr)
        c = math.cos(dr)
        oc = 1.0 - c
        R_delta = [
            [c + ax*ax*oc, ax*ay*oc - az*s, ax*az*oc + ay*s],
            [ay*ax*oc + az*s, c + ay*ay*oc, ay*az*oc - ax*s],
            [az*ax*oc - ay*s, az*ay*oc + ax*s, c + az*az*oc],
        ]

    if frame == MoveFrame.BASE:
        # Base frame: add linear delta directly, pre-multiply rotation
        new_pos = [pose[0] + delta[0], pose[1] + delta[1], pose[2] + delta[2]]
        R_new = _mat_mul(R_delta, R)
    else:
        # TOOL frame: rotate linear delta by current orientation,
        # post-multiply rotation (matches robot_mover Eigen approach)
        rotated_linear = _mat_vec_mul(R, delta[:3])
        new_pos = [
            pose[0] + rotated_linear[0],
            pose[1] + rotated_linear[1],
            pose[2] + rotated_linear[2],
        ]
        R_new = _mat_mul(R, R_delta)

    new_rot = _matrix_to_rotvec(R_new)
    return [new_pos[0], new_pos[1], new_pos[2], new_rot[0], new_rot[1], new_rot[2]]
