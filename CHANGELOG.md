# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] — 2026-07-03

### Added
- Async motion support: `move_to()`, `movel()`, `movej()` accept `asynchronous=True`
- `is_moving()` method — polls joint/TCP velocity to detect motion
- `stop()` method — sends `stopL(5.0, True)` + `stopJ(5.0, True)` for reliable stops
- Go To submenu: Space key cancels moves, dedicated moving screen with progress bar
- Progress bar uses TCP position distance (monotonic — never goes down)
- Joint angle display in main screen (J1-J3 and J4-J6 lines)
- Joint limit proximity warnings (yellow at 10%, red at 5%)
- Payload/TCP color coding (green when configured, dim when not)
- Mypy strict mode configuration in `pyproject.toml`
- CHANGELOG.md with version history
- AGENTS.md with project maintenance rules

### Changed
- ESC exits CLI, Space cancels current move (was ESC for both)
- Exit paths call `robot.stop()` before `speed_stop()`
- Removed `interruptible_move_to()` — no longer needed with async API
- Simplified header: `SAFE MODE` / `EXPERT MODE` (removed check marks)
- Fixed angular key mapping: `i/k` = ±Pitch, `j/l` = ±Yaw (was `i/j` and `k/l`)
- Fixed J4-J6 display bug: used `joints[i+3]` instead of `joints[i]`
- Converted joint limit thresholds from fixed degrees to percentages

### Fixed
- Freedrive exit race condition: `disable_freedrive()` before `speed_stop()`
- "No saved points" bug: load config and resolve `points_path` in `teach_command()`
- "Exiting teach pendant" printed twice: removed duplicate `_cleanup()` call
- `AttributeError: 'PosixPath' object has no attribute 'get'`: use `load_config()` instead of `resolve_config()`
- All pre-existing pyflakes warnings (0 warnings now)

## [0.2.0] — 2026-06-XX

### Added
- Initial release
- Connection validation and lifecycle
- Motion commands (moveJ, moveL, move_by, move_velocity, move_until_contact)
- Points database (SQLite-backed)
- Gripper abstraction (Robotiq, Digital)
- Geometry helpers (quaternion, rotvec, RPY)
- Teach pendant CLI with live telemetry
- Test suite (132 tests)

[Unreleased]
