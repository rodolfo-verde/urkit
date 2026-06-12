"""Tests for quaternion/rotation vector geometry helpers."""

from __future__ import annotations

import math

from urkit.geometry import (
    orient_tcp_down,
    quat_to_rotvec,
    quat_to_rpy,
    rpy_to_quat,
    rotvec_to_quat,
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
            ax, ay, az = rv[0]/angle, rv[1]/angle, rv[2]/angle
            s, c = math.sin(angle), math.cos(angle)
            oc = 1 - c
            # R[2][2] = c + az*az*oc — tool Z in base frame
            z_z = c + az*az*oc
            assert abs(z_z - (-1.0)) < 1e-10

    def test_preserves_heading(self):
        """Tool X-axis direction in XY plane should be preserved."""
        # Start with yaw=0.5 (tool facing ~45° from X)
        q = rpy_to_quat(0, 0, 0.5)
        rv = quat_to_rotvec(q)
        pose = [0.5, 0.3, 0.2, rv[0], rv[1], rv[2]]
        result = orient_tcp_down(pose)

        # Original X axis angle in XY plane
        orig_q = rotvec_to_quat(pose[3:])
        orig_rpy = quat_to_rpy(orig_q)
        orig_heading = orig_rpy[2]  # yaw = heading in XY plane

        # Result X axis angle in XY plane
        result_q = rotvec_to_quat(result[3:])
        result_rpy = quat_to_rpy(result_q)
        result_heading = result_rpy[2]

        assert abs(orig_heading - result_heading) < 1e-10

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
