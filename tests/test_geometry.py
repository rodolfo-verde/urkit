"""Tests for quaternion/rotation vector geometry helpers."""

from __future__ import annotations

import math

import pytest

from urkit.geometry import (
    orient_tcp,
    orient_tcp_down,
    quat_to_rotvec,
    quat_to_rpy,
    rpy_to_quat,
    rotvec_to_quat,
    _rotvec_to_matrix,
)


class TestRotvecToQuat:
    """Rotation vector to quaternion conversion."""

    def test_identity(self):
        q = rotvec_to_quat([0, 0, 0])
        assert abs(q[3] - 1.0) < 1e-10  # w = 1
        assert abs(q[0]) < 1e-10
        assert abs(q[1]) < 1e-10
        assert abs(q[2]) < 1e-10

    def test_180_degrees_x_axis(self):
        """180° rotation around X axis."""
        q = rotvec_to_quat([math.pi, 0, 0])
        assert abs(q[0] - 1.0) < 1e-10  # x = 1
        assert abs(q[1]) < 1e-10
        assert abs(q[2]) < 1e-10
        assert abs(q[3]) < 1e-10  # w = 0

    def test_90_degrees_z_axis(self):
        """90° rotation around Z axis."""
        q = rotvec_to_quat([0, 0, math.pi / 2])
        assert abs(q[0]) < 1e-10
        assert abs(q[1]) < 1e-10
        assert abs(q[2] - math.sin(math.pi / 4)) < 1e-10
        assert abs(q[3] - math.cos(math.pi / 4)) < 1e-10

    def test_roundtrip(self):
        """rotvec -> quat -> rotvec should be identity."""
        rv = [0.5, 0.3, 0.1]
        q = rotvec_to_quat(rv)
        back = quat_to_rotvec(q)
        for a, b in zip(rv, back):
            assert abs(a - b) < 1e-10


class TestQuatToRotvec:
    """Quaternion to rotation vector conversion."""

    def test_identity_quat(self):
        rv = quat_to_rotvec((0, 0, 0, 1))
        assert all(abs(v) < 1e-10 for v in rv)

    def test_roundtrip(self):
        """quat -> rotvec -> quat should be identity."""
        q = (0.7071, 0, 0, 0.7071)  # 90° around X
        rv = quat_to_rotvec(q)
        back = rotvec_to_quat(rv)
        for a, b in zip(q, back):
            assert abs(a - b) < 1e-5


class TestQuatToRpy:
    """Quaternion to RPY extraction."""

    def test_identity(self):
        roll, pitch, yaw = quat_to_rpy((0, 0, 0, 1))
        assert abs(roll) < 1e-10
        assert abs(pitch) < 1e-10
        assert abs(yaw) < 1e-10

    def test_90_deg_roll(self):
        """90° roll should give roll=pi/2."""
        q = rotvec_to_quat([math.pi / 2, 0, 0])
        roll, pitch, yaw = quat_to_rpy(q)
        assert abs(roll - math.pi / 2) < 1e-10
        assert abs(pitch) < 1e-10
        assert abs(yaw) < 1e-10

    def test_roundtrip(self):
        """rpy -> quat -> rpy should be identity."""
        r, p, y = 0.5, 0.3, 0.1
        q = rpy_to_quat(r, p, y)
        back_r, back_p, back_y = quat_to_rpy(q)
        assert abs(r - back_r) < 1e-10
        assert abs(p - back_p) < 1e-10
        assert abs(y - back_y) < 1e-10


class TestRpyToQuat:
    """RPY to quaternion conversion."""

    def test_zero_rpy(self):
        q = rpy_to_quat(0, 0, 0)
        assert abs(q[0]) < 1e-10
        assert abs(q[1]) < 1e-10
        assert abs(q[2]) < 1e-10
        assert abs(q[3] - 1.0) < 1e-10

    def test_180_roll(self):
        """180° roll -> known quaternion."""
        q = rpy_to_quat(math.pi, 0, 0)
        assert abs(q[0] - 1.0) < 1e-10
        assert abs(q[1]) < 1e-10
        assert abs(q[2]) < 1e-10
        assert abs(q[3]) < 1e-10


class TestOrientTcpDown:
    """TCP downward orientation."""

    def test_preserves_position(self):
        pose = [0.5, 0.3, 0.2, 0, 0, 0]
        result = orient_tcp_down(pose)
        assert result[0] == 0.5
        assert result[1] == 0.3
        assert result[2] == 0.2

    def test_z_axis_points_down(self):
        """Resulting tool Z-axis should point straight down in base frame."""
        pose = [0.5, 0.3, 0.2, 0, 0, 0]
        result = orient_tcp_down(pose)
        rv = result[3:]
        # For roll=π, Z-axis = (0, 0, -1)
        angle = math.sqrt(sum(v**2 for v in rv))
        if angle > 1e-10:
            az = rv[2] / angle
            c = math.cos(angle)
            oc = 1.0 - c
            # R[2][2] = c + az*az*oc — tool Z in base frame
            z_z = c + az * az * oc
            assert abs(z_z - (-1.0)) < 1e-10

    def test_minimal_rotation_angle(self):
        """Orient from yaw=0.5 to down should produce minimal rotation."""
        q = rpy_to_quat(0, 0, 0.5)
        rv = quat_to_rotvec(q)
        pose = [0.5, 0.3, 0.2, rv[0], rv[1], rv[2]]
        result = orient_tcp_down(pose)

        # The minimal rotation from Z=[0,0,1] to Z=[0,0,-1] is 180°
        result_angle = math.sqrt(sum(v**2 for v in result[3:]))
        assert abs(result_angle - math.pi) < 1e-10

    def test_handles_gimbal_lock(self):
        """Pitch=90° (gimbal lock) should still produce valid down orientation."""
        q = rpy_to_quat(0, math.pi / 2, 0.5)
        rv = quat_to_rotvec(q)
        pose = [0.5, 0.3, 0.2, rv[0], rv[1], rv[2]]
        result = orient_tcp_down(pose)
        # Should not crash, Z should point down
        assert len(result) == 6
        assert result[:3] == pose[:3]  # position preserved


class TestFullRoundtrip:
    """Full chain: rotvec -> quat -> rpy -> quat -> rotvec."""

    def test_various_angles(self):
        test_vectors = [
            [0, 0, 0],
            [math.pi / 6, 0, 0],
            [0, math.pi / 4, 0],
            [0, 0, math.pi / 3],
            [0.5, 0.3, 0.2],
            [1.0, 0.5, 0.3],
        ]
        for rv in test_vectors:
            q = rotvec_to_quat(rv)
            r, p, y = quat_to_rpy(q)
            q2 = rpy_to_quat(r, p, y)
            rv2 = quat_to_rotvec(q2)
            for a, b in zip(rv, rv2):
                assert abs(a - b) < 1e-10, f"Failed for {rv}"


class TestOrientTcp:
    """TCP orientation in arbitrary directions (minimal relative rotation)."""

    def test_preserves_position(self):
        pose = [0.5, 0.3, 0.2, 0, 0, 0]
        result = orient_tcp(pose, [1, 0, 0])
        assert result[0] == 0.5
        assert result[1] == 0.3
        assert result[2] == 0.2

    def test_z_points_along_target(self):
        """Tool Z-axis should point along the target direction."""
        pose = [0.5, 0.3, 0.2, 0, 0, 0]
        result = orient_tcp(pose, [1, 0, 0])
        R = _rotvec_to_matrix(result[3:])
        z = [R[i][2] for i in range(3)]
        assert abs(z[0] - 1.0) < 1e-10
        assert abs(z[1]) < 1e-10
        assert abs(z[2]) < 1e-10

    def test_z_points_along_neg_y(self):
        pose = [0.5, 0.3, 0.2, 0, 0, 0]
        result = orient_tcp(pose, [0, -1, 0])
        R = _rotvec_to_matrix(result[3:])
        z = [R[i][2] for i in range(3)]
        assert abs(z[0]) < 1e-10
        assert abs(z[1] - (-1.0)) < 1e-10
        assert abs(z[2]) < 1e-10

    def test_minimal_rotation_non_180(self):
        """Z up (yaw=30°) → +X: delta should be 90°, not 120°."""
        q = rpy_to_quat(0, 0, math.radians(30))
        rv = quat_to_rotvec(q)
        pose = [0.5, 0.3, 0.2, rv[0], rv[1], rv[2]]
        result = orient_tcp(pose, [1, 0, 0])
        # Compute delta rotation: R_delta = R_new @ R_curr^T
        R_curr = _rotvec_to_matrix(pose[3:])
        R_new = _rotvec_to_matrix(result[3:])
        # Transpose of R_curr (since it's orthogonal, inverse = transpose)
        R_curr_T = [[R_curr[0][0], R_curr[1][0], R_curr[2][0]],
                    [R_curr[0][1], R_curr[1][1], R_curr[2][1]],
                    [R_curr[0][2], R_curr[1][2], R_curr[2][2]]]
        R_delta = [
            [sum(R_new[i][k] * R_curr_T[k][j] for k in range(3)) for j in range(3)]
            for i in range(3)
        ]
        trace = R_delta[0][0] + R_delta[1][1] + R_delta[2][2]
        delta_angle = math.acos(max(-1, min(1, (trace - 1) / 2)))
        # Minimal rotation from [0,0,1] to [1,0,0] is 90°
        assert abs(delta_angle - math.pi / 2) < 1e-10, f"delta_angle={delta_angle}"

    def test_already_aligned_returns_unchanged(self):
        """If Z already points along target, pose should be unchanged."""
        pose = [0.5, 0.3, 0.2, 0, 0, 0]
        result = orient_tcp(pose, [0, 0, 1])
        assert result[3:] == pose[3:]

    def test_180_degree_flip(self):
        """Z up → Z down should give a valid 180° rotation."""
        pose = [0.5, 0.3, 0.2, 0, 0, 0]
        result = orient_tcp(pose, [0, 0, -1])
        angle = math.sqrt(sum(v**2 for v in result[3:]))
        assert abs(angle - math.pi) < 1e-10
        R = _rotvec_to_matrix(result[3:])
        z = [R[i][2] for i in range(3)]
        assert abs(z[0]) < 1e-10
        assert abs(z[1]) < 1e-10
        assert abs(z[2] - (-1.0)) < 1e-10

    def test_raises_on_zero_direction(self):
        pose = [0.5, 0.3, 0.2, 0, 0, 0]
        with pytest.raises(ValueError):
            orient_tcp(pose, [0, 0, 0])

    def test_various_starting_poses(self):
        """Multiple starting orientations should all produce valid results."""
        targets = [[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]]
        for roll in [0, math.radians(45), math.radians(90)]:
            for pitch in [0, math.radians(-30), math.radians(60)]:
                for yaw in [0, math.radians(30)]:
                    q = rpy_to_quat(roll, pitch, yaw)
                    rv = quat_to_rotvec(q)
                    pose = [0.5, 0.3, 0.2, rv[0], rv[1], rv[2]]
                    for target in targets:
                        result = orient_tcp(pose, target)
                        # Verify Z points along target
                        R = _rotvec_to_matrix(result[3:])
                        z = [R[i][2] for i in range(3)]
                        norm_t = math.sqrt(target[0]**2 + target[1]**2 + target[2]**2)
                        t = [target[i]/norm_t for i in range(3)]
                        dot = z[0]*t[0] + z[1]*t[1] + z[2]*t[2]
                        assert abs(dot - 1.0) < 1e-10, (
                            f"Z not aligned: roll={roll}, pitch={pitch}, "
                            f"yaw={yaw}, target={target}"
                        )
                        # Verify rotation matrix is proper (det = 1)
                        det = (
                            R[0][0]*(R[1][1]*R[2][2] - R[1][2]*R[2][1])
                            - R[0][1]*(R[1][0]*R[2][2] - R[1][2]*R[2][0])
                            + R[0][2]*(R[1][0]*R[2][1] - R[1][1]*R[2][0])
                        )
                        assert abs(det - 1.0) < 1e-10
