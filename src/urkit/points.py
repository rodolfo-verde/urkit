"""Named point storage with SQLite backend."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from urkit.exceptions import PointError
from urkit.geometry import MoveFrame, transform_pose_delta


@dataclass(frozen=True, slots=True)
class Point:
    """A robot waypoint stored as a TCP pose.

    Stores the TCP pose (from ``getActualTCPPose()``). The UR controller
    interprets the stored pose in whatever TCP frame is active at playback
    time, making points tool-agnostic by design.

    Returned by Points attribute/subscript access. Pass directly
    to URRobot.move_to(). Points loaded from the database carry a
    name; ad-hoc points created via ``from_pose()`` have an empty name.

    Fields:
        name: Point name (key in the database, empty string for ad-hoc points).
        pose: TCP pose [x, y, z, rx, ry, rz] in meters/radians.
    """

    name: str
    pose: list[float]

    def with_offset(
        self,
        offset: list[float],
        frame: MoveFrame = MoveFrame.BASE,
    ) -> "Point":
        """Return a new Point with the offset applied to the pose.

        Args:
            offset: [dx, dy, dz, droll, dpitch, dyaw].
            frame: Coordinate frame for interpreting the offset
                (``MoveFrame.BASE`` or ``MoveFrame.TOOL``).

        Returns:
            New Point with offset applied to the pose.
        """
        if len(offset) != 6:
            raise PointError(
                f"Offset must have 6 values, got {len(offset)}."
            )
        return Point(
            name=self.name,
            pose=transform_pose_delta(self.pose, offset, frame),
        )

    def with_name(self, name: str) -> "Point":
        """Return a copy of this point with a new name."""
        return Point(name=name, pose=list(self.pose))

    @classmethod
    def from_pose(cls, pose: list[float], name: str = "") -> "Point":
        """Create a Point from a raw pose.

        Use for one-off moves where a named point isn't needed.

        Args:
            pose: [x, y, z, rx, ry, rz].
            name: Optional name (empty string by default).

        Returns:
            Point with the given pose.
        """
        if len(pose) != 6:
            raise PointError(
                f"Pose must have 6 values [x, y, z, rx, ry, rz], got {len(pose)}."
            )
        return cls(name=name, pose=list(pose))


def _init_db(conn: sqlite3.Connection) -> None:
    """Create the points table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS points (
            name TEXT PRIMARY KEY,
            pose TEXT NOT NULL
        )
    """)
    conn.commit()


def _serialize(v: list[float]) -> str:
    return json.dumps([float(x) for x in v])


def _deserialize(s: str) -> list[float]:
    return json.loads(s)


class Points:
    """SQLite-backed named waypoint database.

    Args:
        path: Path to the SQLite file.

    Example:
        >>> points = Points("points.db")
        >>> point = Point(name="pick", pose=[0.5, 0, 0.3, 0, 0, 0])
        >>> points.save(point)
        >>> pose = points.load("pick")
    """

    def __init__(self, path: str | Path) -> None:
        if str(path) == ":memory:":
            self._path = Path(":memory:")
            self._conn = sqlite3.connect(":memory:")
        else:
            self._path = Path(path).resolve()
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self._path))
        _init_db(self._conn)

    def _close(self) -> None:
        if hasattr(self, "_conn") and self._conn:
            self._conn.close()

    def __enter__(self) -> Points:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        self._close()
        return False

    def __del__(self) -> None:
        self._close()

    def save(self, point: Point) -> None:
        """Save a named point (overwrites if it already exists).

        Raises:
            PointError: If name is empty or pose doesn't have 6 values.
        """
        if not point.name:
            raise PointError("Point name must not be empty.")
        if len(point.pose) != 6:
            raise PointError(
                f"Pose must have 6 values [x, y, z, rx, ry, rz], got {len(point.pose)}."
            )

        self._conn.execute(
            "INSERT OR REPLACE INTO points (name, pose) VALUES (?, ?)",
            (point.name, _serialize(point.pose)),
        )
        self._conn.commit()

    def _find(self, name: str) -> Point:
        """Look up a point by name. Raises KeyError if not found."""
        row = self._conn.execute(
            "SELECT pose FROM points WHERE name = ?", (name,)
        ).fetchone()
        if row is None:
            raise KeyError(name)
        return Point(name=name, pose=_deserialize(row[0]))

    def delete(self, name: str) -> None:
        """Delete a named point. Raises KeyError if not found."""
        cursor = self._conn.execute(
            "DELETE FROM points WHERE name = ?", (name,)
        )
        if cursor.rowcount == 0:
            raise KeyError(name)
        self._conn.commit()

    def rename(self, old: str, new: str) -> None:
        """Rename a point. Raises KeyError if the old name does not exist,
        or PointError if the new name already exists."""
        try:
            point = self._find(old)
        except KeyError:
            raise KeyError(old) from None

        if new in self:
            raise PointError(
                f"Point '{new}' already exists. Use delete() first to remove it."
            )

        self._conn.execute(
            "INSERT INTO points (name, pose) VALUES (?, ?)",
            (new, _serialize(point.pose)),
        )
        self._conn.execute("DELETE FROM points WHERE name = ?", (old,))
        self._conn.commit()

    def list(self) -> list[str]:
        """List all saved point names (sorted)."""
        rows = self._conn.execute(
            "SELECT name FROM points ORDER BY name"
        ).fetchall()
        return [r[0] for r in rows]

    def __iter__(self) -> "Points":
        """Iterate over points: ``for point in points: ...``."""
        self._iter_names = self.list()
        self._iter_index = 0
        return self

    def __next__(self) -> Point:
        """Return the next Point during iteration."""
        if self._iter_index >= len(self._iter_names):
            raise StopIteration
        name = self._iter_names[self._iter_index]
        self._iter_index += 1
        return self._find(name)

    def __len__(self) -> int:
        """Return the number of saved points."""
        return len(self.list())

    def __getitem__(self, name: str) -> Point:
        """Get a point by subscript: ``points["pick"]``. Raises KeyError if not found."""
        return self._find(name)

    def __contains__(self, name: str) -> bool:
        """Check if a point exists: ``"pick" in points``."""
        row = self._conn.execute(
            "SELECT 1 FROM points WHERE name = ?", (name,)
        ).fetchone()
        return row is not None

    def get(self, name: str) -> Point | None:
        """Safely get a point, returning None if not found."""
        try:
            return self[name]
        except KeyError:
            return None

    @property
    def path(self) -> Path:
        """The resolved file path for this database."""
        return self._path

    def export_json(self, path: str | Path) -> None:
        """Export all points to a human-readable JSON file.

        Args:
            path: Output file path (will be overwritten).
        """
        out: dict[str, dict[str, list[float]]] = {}
        for name in self.list():
            point = self._find(name)
            out[name] = {"pose": point.pose}
        Path(path).write_text(json.dumps(out, indent=2) + "\n")

    def import_json(self, path: str | Path) -> None:
        """Import points from a JSON file.

        Reads JSON exported by ``export_json()`` and saves each point
        to the database. Overwrites existing points with the same name.

        Args:
            path: Input JSON file path.

        Raises:
            PointError: If the file format is invalid.
        """
        raw = Path(path).read_text()
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise PointError("Invalid JSON format: expected a dict keyed by point name.")
        for name, point_data in data.items():
            pose = point_data.get("pose")
            if pose is None:
                raise PointError(
                    f"Invalid point '{name}': missing 'pose'."
                )
            self.save(Point(name=name, pose=pose))
