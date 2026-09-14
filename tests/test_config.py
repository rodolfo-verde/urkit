"""Tests for config key validation (unknown top-level keys must raise).

A config file is urkit-only: unknown keys (usually typos) must fail
loudly instead of being silently ignored. The known set is the union
of everything urkit reads, including CLI-only keys like expert_mode.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from urkit.config import (
    VALID_CONFIG_KEYS,
    _load_config,
    validate_config_keys,
)
from urkit.robot import URRobot


class TestValidateConfigKeys:
    def test_all_valid_keys_pass(self) -> None:
        validate_config_keys({k: None for k in VALID_CONFIG_KEYS})

    def test_empty_config_passes(self) -> None:
        validate_config_keys({})

    def test_unknown_key_raises_with_offender(self) -> None:
        with pytest.raises(ValueError, match="robot_ipe"):
            validate_config_keys({"robot_ipe": "192.168.1.50"})

    def test_multiple_unknowns_sorted_and_listed(self) -> None:
        with pytest.raises(ValueError) as excinfo:
            validate_config_keys({"zzz": 1, "aaa": 2, "robot_ip": "x"})
        msg = str(excinfo.value)
        assert "aaa" in msg and "zzz" in msg
        assert msg.index("aaa") < msg.index("zzz")
        assert "robot_ip" not in msg.split("Valid keys")[0].split("config key(s): ")[1]

    def test_error_lists_valid_keys(self) -> None:
        with pytest.raises(ValueError) as excinfo:
            validate_config_keys({"bogus": 1})
        for key in sorted(VALID_CONFIG_KEYS):
            assert key in str(excinfo.value)

    def test_cli_only_key_is_valid_for_library(self) -> None:
        # expert_mode is read only by the CLI; from_config must accept it
        # so a valid urkit teach config is a valid library config.
        validate_config_keys({"robot_ip": "192.168.1.50", "expert_mode": True})


class TestLoadConfigValidation:
    def test_unknown_key_in_file_raises(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.yaml"
        cfg.write_text("robot_ip: 192.168.1.50\nrobot_ipe: 192.168.1.50\n")
        with pytest.raises(ValueError, match="robot_ipe"):
            _load_config(str(cfg))

    def test_valid_file_loads(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.yaml"
        cfg.write_text("robot_ip: 192.168.1.50\nexpert_mode: true\n")
        data = _load_config(str(cfg))
        assert data["robot_ip"] == "192.168.1.50"
        assert data["expert_mode"] is True

    def test_missing_file_still_returns_empty(self, tmp_path: Path) -> None:
        assert _load_config(str(tmp_path / "nope.yaml")) == {}

    def test_malformed_yaml_raises_with_file_and_reason(
        self, tmp_path: Path
    ) -> None:
        cfg = tmp_path / "config.yaml"
        cfg.write_text("robot_ip: [192.168.1.50\n  bad indent: here\n")
        with pytest.raises(ValueError, match="Malformed YAML") as excinfo:
            _load_config(str(cfg))
        assert str(cfg) in str(excinfo.value)

    def test_non_mapping_document_raises(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.yaml"
        cfg.write_text("- just\n- a\n- list\n")
        with pytest.raises(ValueError, match="must be a YAML mapping"):
            _load_config(str(cfg))

    def test_empty_file_is_no_config(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.yaml"
        cfg.write_text("")
        assert _load_config(str(cfg)) == {}


class TestFromConfigValidation:
    def test_dict_unknown_key_raises_before_connect(self) -> None:
        with pytest.raises(ValueError, match="bogus_key"):
            URRobot.from_config({"robot_ip": "127.0.0.1", "bogus_key": 1})

    def test_file_unknown_key_raises(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.yaml"
        cfg.write_text("robot_ip: 127.0.0.1\npoints_paths: points.db\n")
        with pytest.raises(ValueError, match="points_paths"):
            URRobot.from_config(str(cfg))
