# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [3.2] — 2026-07-03

### Added
- `6`/`7` keys for gripper speed/force (prompt-based, Robotiq only)
- Force/speed display on Gripper line (`F=100 S=100`)
- Force/speed applied before each gripper operation (rq_set_force/rq_set_speed)

### Fixed
- Missing `points_path` argument in `_submenu_explore_points` (P key crash)
- Redundant inline import of `load_config` in teach pendant
- Redundant Enter key handler in points explorer (auto-refreshes every 2s)

## [3.1] — 2026-07-03

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

## [0.3.0] — 2026-06-19

### Added
- Safe/expert mode display in header
- speed_stop on ESC and Ctrl+C exit
- Safety features for teach mode

## [0.2.1] — 2026-06-18

### Added
- `get_pose()` method for retrieving saved point poses

### Fixed
- README documentation refinements

## [0.2.0] — 2026-06-18

### Changed
- Restructured README and fixed `rtde_frequency` documentation

## [0.1.1] — 2026-06-16

### Added
- `--gripper none` flag to disable gripper
- `--config` flag for config file path
- Save config on demand (Y key in CLI)
- PyPI badge in README
- Repository URL in `pyproject.toml`

### Changed
- Read `__version__` from `importlib.metadata` instead of hardcoding

### Fixed
- Freedrive cycle: always start from ALL instead of remembering last mode
- Inverted gripper percentage to match Robotiq GUI convention
- Show gripper status on Gripper line regardless of freedrive state
- Fix deactivate() docstring — no freedrive restriction required
- Fix freedrive cycle: always start from ALL instead of remembering last mode
- Add Rz rotation to XYZ freedrive mode
- Skip gripper is_connected() ping during freedrive
- Remove auto-open on activate and is_connected() ping from CLI
- Remove is_connected() from Gripper interface
- Document XYZ+Rz freedrive mode in CLI and README
- Show XYZ+Rz in freedrive status line instead of enum name

### Removed
- DO round-trip hardware read and suppress redundant freedrive messages
- rtde_frequency parameter — hardcode 500Hz
- Incorrect URCap mention from error message
- Fix error message for RTDE script upload failure
- Fix ur_rtde segfault at 125Hz and add ExternalControl URCap error

### Fixed
- Align OTHER continuation line with spacing instead of repeating label
- Fix footer: Exit: ESC, split OTHER into two lines
- Revert footer to compact layout, keep P: Explorer
- Clean up footer keymap: split OTHER, add P: Explorer, Exit: ESC

## [0.1.0] — 2026-06-12

### Added
- Initial release
- Connection validation and lifecycle
- Motion commands (moveJ, moveL, move_by, move_velocity, move_until_contact)
- Points database (SQLite-backed)
- Gripper abstraction (Robotiq, Digital)
- Geometry helpers (quaternion, rotvec, RPY)
- Teach pendant CLI with live telemetry
- Test suite (132 tests)
