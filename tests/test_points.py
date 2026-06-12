"""Tests for the Points SQLite-backed waypoint database."""

from __future__ import annotations

import os
import tempfile

import pytest

from urkit.exceptions import PointError
from urkit.points import Point, Points


@pytest.fixture
def points():
    """Create a Points instance in an in-memory SQLite database."""
    s = Points(":memory:")
    return s


def _p(name, pose=None):
    """Helper to create a Point for save() calls."""
    if pose is None:
        pose = [1, 2, 3, 4, 5, 6]
    return Point(name=name, pose=pose)


# ------------------------------------------------------------------
# Save / load (subscript access)
# ------------------------------------------------------------------


def test_save_and_subscript(points):
    pose = [0.5, 0.0, 0.3, 0.0, 0.0, 0.0]
    points.save(_p("pick", pose))

    loaded = points["pick"]
    assert loaded.pose == pose


def test_save_overwrites(points):
    points.save(_p("p", [1, 2, 3, 4, 5, 6]))
    points.save(_p("p", [7, 8, 9, 10, 11, 12]))

    loaded = points["p"]
    assert loaded.pose == [7, 8, 9, 10, 11, 12]


def test_subscript_missing_key(points):
    with pytest.raises(KeyError):
        _ = points["nonexistent"]


# ------------------------------------------------------------------
# Delete
# ------------------------------------------------------------------


def test_delete(points):
    points.save(_p("x"))
    points.delete("x")

    with pytest.raises(KeyError):
        _ = points["x"]


def test_delete_missing_key(points):
    with pytest.raises(KeyError):
        points.delete("nonexistent")


# ------------------------------------------------------------------
# Rename
# ------------------------------------------------------------------


def test_rename(points):
    points.save(_p("old"))
    points.rename("old", "new")

    assert "old" not in points.list()
    assert "new" in points.list()
    loaded = points["new"]
    assert loaded.pose == [1, 2, 3, 4, 5, 6]


def test_rename_missing_old(points):
    with pytest.raises(KeyError):
        points.rename("nonexistent", "new")


def test_rename_to_existing(points):
    points.save(_p("a"))
    points.save(_p("b", [7, 8, 9, 10, 11, 12]))

    with pytest.raises(PointError, match="already exists"):
        points.rename("a", "b")


# ------------------------------------------------------------------
# List, contains, get
# ------------------------------------------------------------------


def test_list_sorted(points):
    points.save(_p("charlie"))
    points.save(_p("alpha"))
    points.save(_p("bravo"))

    assert points.list() == ["alpha", "bravo", "charlie"]


def test_list_empty(points):
    assert points.list() == []


def test_contains(points):
    points.save(_p("pick", [0.5, 0, 0.3, 0, 0, 0]))
    assert "pick" in points
    assert "missing" not in points


def test_get_existing(points):
    points.save(_p("pick", [0.5, 0, 0.3, 0, 0, 0]))
    point = points.get("pick")
    assert isinstance(point, Point)
    assert point.name == "pick"


def test_get_missing(points):
    result = points.get("nonexistent")
    assert result is None


# ------------------------------------------------------------------
# Iteration
# ------------------------------------------------------------------


def test_iteration(points):
    points.save(_p("charlie"))
    points.save(_p("alpha"))
    points.save(_p("bravo"))

    names = [p.name for p in points]
    assert names == ["alpha", "bravo", "charlie"]


def test_iteration_empty(points):
    assert list(points) == []


def test_len(points):
    assert len(points) == 0
    points.save(_p("a"))
    assert len(points) == 1
    points.save(_p("b"))
    assert len(points) == 2


def test_list_equals_len(points):
    points.save(_p("a"))
    points.save(_p("b"))
    points.save(_p("c"))
    assert len(points) == len(points.list())


# ------------------------------------------------------------------
# Validation
# ------------------------------------------------------------------


def test_pose_length_validation(points):
    with pytest.raises(PointError, match="6 values"):
        points.save(Point(name="bad", pose=[1, 2, 3]))


# ------------------------------------------------------------------
# File persistence
# ------------------------------------------------------------------


def test_file_based_persistence():
    """Points should persist across instances when using a file."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        s1 = Points(path)
        s1.save(_p("home", [0.5, 0, 0.3, 0, 0, 0]))
        s1._close()

        s2 = Points(path)
        loaded = s2["home"]
        assert loaded.pose == [0.5, 0, 0.3, 0, 0, 0]
        s2._close()
    finally:
        os.unlink(path)


def test_path_property(points):
    """Path property should return a resolved Path."""
    from pathlib import Path as P
    assert isinstance(points.path, P)


def test_save_float_normalization(points):
    """Integer values should be stored as floats."""
    points.save(_p("int_test"))
    loaded = points["int_test"]
    assert all(isinstance(v, float) for v in loaded.pose)


# ------------------------------------------------------------------
# Point tests
# ------------------------------------------------------------------


def test_namedpoint_dataclass():
    p = Point(name="pick", pose=[0.5, 0, 0.3, 0, 0, 0])
    assert p.name == "pick"
    assert p.pose == [0.5, 0, 0.3, 0, 0, 0]


def test_namedpoint_frozen():
    p = Point(name="pick", pose=[0.5, 0, 0.3, 0, 0, 0])
    with pytest.raises(Exception):
        p.name = "other"  # type: ignore


def test_namedpoint_with_offset():
    p = Point(name="pick", pose=[0.5, 0, 0.3, 0, 0, 0])
    p2 = p.with_offset([0.1, 0, 0, 0, 0, 0])
    assert p.pose[0] == 0.5  # original unchanged
    assert p2.pose[0] == 0.6


def test_namedpoint_with_offset_wrong_length():
    p = Point(name="pick", pose=[0.5, 0, 0.3, 0, 0, 0])
    with pytest.raises(PointError, match="6 values"):
        p.with_offset([1, 2, 3])


def test_namedpoint_with_name():
    p = Point(name="", pose=[0.5, 0, 0.3, 0, 0, 0])
    p2 = p.with_name("home")
    assert p2.name == "home"
    assert p2.pose == p.pose
    assert p.name == ""  # original unchanged


def test_namedpoint_with_name_chainable():
    p = Point(name="", pose=[0.5, 0, 0.3, 0, 0, 0])
    p2 = p.with_offset([0, 0, 0.1, 0, 0, 0]).with_name("above")
    assert p2.name == "above"
    assert p2.pose[2] == 0.4


def test_namedpoint_from_pose():
    p = Point.from_pose([0.5, 0, 0.3, 0, 0, 0])
    assert p.name == ""
    assert p.pose == [0.5, 0, 0.3, 0, 0, 0]


def test_namedpoint_from_pose_with_name():
    p = Point.from_pose([0.5, 0, 0.3, 0, 0, 0], name="ad hoc")
    assert p.name == "ad hoc"


def test_namedpoint_from_pose_wrong_length():
    with pytest.raises(PointError, match="6 values"):
        Point.from_pose([1, 2, 3])


# ------------------------------------------------------------------
# Subscript access tests
# ------------------------------------------------------------------


def test_subscript_access(points):
    points.save(_p("pick", [0.5, 0, 0.3, 0, 0, 0]))
    point = points["pick"]
    assert isinstance(point, Point)
    assert point.name == "pick"
    assert point.pose == [0.5, 0, 0.3, 0, 0, 0]


# ------------------------------------------------------------------
# JSON import/export
# ------------------------------------------------------------------


def test_export_json(points, tmp_path):
    points.save(_p("alpha", [0.5, 0, 0.3, 0, 0, 0]))
    points.save(_p("beta", [0.6, 0.1, 0.2, 0, 0, 0]))

    out = tmp_path / "points.json"
    points.export_json(out)

    import json

    data = json.loads(out.read_text())
    assert "alpha" in data
    assert "beta" in data
    assert data["alpha"]["pose"] == [0.5, 0, 0.3, 0, 0, 0]
    assert data["beta"]["pose"] == [0.6, 0.1, 0.2, 0, 0, 0]


def test_import_json(points, tmp_path):
    json_file = tmp_path / "points.json"
    json_file.write_text(
        '{"a": {"pose": [1, 2, 3, 4, 5, 6]}, '
        '"b": {"pose": [7, 8, 9, 10, 11, 12]}}'
    )
    points.import_json(json_file)

    assert points.list() == ["a", "b"]
    loaded_a = points["a"]
    assert loaded_a.pose == [1, 2, 3, 4, 5, 6]


def test_import_json_overwrites(points, tmp_path):
    points.save(_p("a", [1, 2, 3, 4, 5, 6]))
    json_file = tmp_path / "points.json"
    json_file.write_text(
        '{"a": {"pose": [7, 8, 9, 10, 11, 12]}}'
    )
    points.import_json(json_file)

    loaded = points["a"]
    assert loaded.pose == [7, 8, 9, 10, 11, 12]


def test_import_json_invalid_format(points, tmp_path):
    json_file = tmp_path / "bad.json"
    json_file.write_text('[1, 2, 3]')
    with pytest.raises(PointError, match="dict"):
        points.import_json(json_file)


def test_import_json_missing_field(points, tmp_path):
    json_file = tmp_path / "bad.json"
    json_file.write_text('{"p": {}}')
    with pytest.raises(PointError, match="missing"):
        points.import_json(json_file)


def test_save_with_namedpoint(points):
    p = Point(name="other", pose=[0.5, 0, 0.3, 0, 0, 0])
    points.save(p)
    loaded = points["other"]
    assert loaded.pose == [0.5, 0, 0.3, 0, 0, 0]


def test_save_empty_name_raises(points):
    with pytest.raises(PointError, match="must not be empty"):
        points.save(_p("", [1, 2, 3, 4, 5, 6]))
