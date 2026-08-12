# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.1] 2026-08-12

### Added
- `urkit init` command to scaffold a default `config.yaml` with all options documented. Supports `--output` for custom path and `--force` to overwrite existing files

### Docs
- Added OS-specific PC network setup instructions (Linux, macOS, Windows) with GUI steps
- Added recommended workflow: `urkit init` → edit config → `urkit teach` → Python code

## [0.4.0] 2026-07-31

### Breaking
- `move_to(linear=True, ik_reference=...)` now raises `MotionError`. `moveL` doesn't accept a custom IK seed (`qnear`). Set `linear=False` to use `ik_reference`, or omit it for linear moves
- `move_relative()` removed `linear` and `ik_reference` parameters. Always uses linear Cartesian move (`moveL`). For joint-space relative moves, resolve the target pose manually and call `move_to`
- `move_sequence()` signature changed from `targets: list[...]` to `*targets` variadic. Both `move_sequence("a", "b")` and `move_sequence(["a", "b"])` are accepted
- `move_sequence()` removed `asynchronous` parameter. Path-based moves execute synchronously
- `_resolve_ik_reference()` raises `PointError` when named point not found (was: log warning + fall back to current joints)

### Added
- Freedrive axis selection menu (`3` key in teach pendant). Toggle individual axes (X, Y, Z, Roll, Pitch, Yaw) on/off with arrow keys, space to toggle, enter to apply
- `enable_freedrive()` accepts custom axis list: `robot.enable_freedrive([1, 1, 1, 1, 0, 0])` for X+Y+Z+Roll+Pitch
- `get_current_point(offset=..., offset_z=...)`. Get current TCP pose with optional offset, same signature as `get_point()`
- `payload` property on `URRobot`. Read current payload mass in kg
- `default_vel` and `default_acc` properties with setters. Change velocity/acceleration at runtime with validation and warnings
- `move_sequence()` always builds a blended path (`moveL(path)` or `moveJ(path)`). No more individual move calls. Checks IK reachability before sending
- 0.2s settle delay when cycling freedrive modes. Prevents trajectory discontinuity protective stops

### Changed
- `set_tcp_offset()` → `tcp_offset` property (getter + setter)
- `set_speed_slider()` / `get_speed_slider()` → `speed_slider` property (getter + setter)
- `set_speed()` / `set_acc()` → `default_vel` / `default_acc` properties (getter + setter)
- `get_pose()` → `get_point()` rename
- `current_point()` → `get_current_point()`. Returns pose list `[x,y,z,rx,ry,rz]` instead of dict `{"pose": [...], "joints": [...]}`
- `acceleration` parameter → `acc` in `move_until_contact()` and `speedL()` for consistency
- Freedrive XYZ mode: `[1,1,1,0,0,1]` → `[1,1,1,0,0,0]`. Position only, no Rz rotation (use ROTATION mode or custom axes)
- Freedrive center: tool frame (`getActualTCPPose()`) → base frame (`[0,0,0,0,0,0]`). Axes are always relative to base, not tool orientation
- Teach pendant freedrive: `F` toggles ALL ↔ XYZ (simpler cycle). Axis menu via `3` key
- Gripper preset key normalization accepts both `_` and `-` (e.g., `ROBOTIQ_2F-140` and `ROBOTIQ-2F-140` resolve the same)
- README rewritten with "What it is / When to use / How it works" structure and clearer IK reference guidance

### Removed
- `get_tcp_pose()`. Use `get_current_point()` instead
- `is_remote_mode()`. Removed Dashboard dependency for remote mode check
- `get_polyscope_version()`. Removed Dashboard dependency for version check
- `Telemetry.get_payload()`. Use `robot.payload` property instead

### Fixed
- Stale integration tests updated for new API (`get_current_point()`, property setters, `PointError`)
- Move sequence tests updated for path-based execution (single `moveL(path)`/`moveJ(path)` call instead of individual calls)

## [0.3.26] 2026-07-29

### Fixed
- Joint limits: J3 corrected to ±360° (was ±180°). All UR e-Series joints are ±360° per official datasheets
- README: removed references to non-existent methods (`is_at_pose`, `is_at_joints`, `move_by`)
- README: fixed `set_position_percent` polarity (0=open, 100=closed) and TCP orient description
- README: restructured for better flow. Configuration before CLI, More API section for specialized topics
- README: removed duplicates (`disconnect()`, `stop()`, `from_config()`)

### Changed
- `load_config` and `resolve_config` are now private (`_load_config`, `_resolve_config`). Use `URRobot.from_config()` instead

## [0.3.25] 2026-07-29

### Fixed
- Version mismatch between `pyproject.toml` and `__init__.py` in v0.3.24 release

## [0.3.24] 2026-07-29

### Fixed
- `move_until_contact` checks force/torque only on moving axes (where speed > 0) instead of all 6 eliminates false contact triggers from noise on idle axes

## [0.3.23] 2026-07-29

### Added
- `move_until_contact(timeout, max_distance)` optional guards to abort if contact is not detected within a time limit (seconds) or travel distance (meters), whichever fires first
- `move_until_contact` returns `bool` `True` if contact detected, `False` if timeout or max_distance exceeded (real errors still raise `MotionError`)

## [0.3.22] 2026-07-28

### Fixed
- `orient_tcp(pose, direction)` replaced heading-preservation heuristic with minimal relative rotation (computes smallest rotation from current Z-axis to target direction). Eliminates unexpectedly large swings (e.g., 104.5° → 90° for yaw=30° to +X)

## [0.3.21] 2026-07-28

### Added
- `orient_tcp(pose, direction)` generalized TCP orientation function that points tool Z along any base-axis direction while preserving heading
- TCP orient submenu in teach pendant (T key) select from 6 directions: −Z (down), +Z (up), −Y, +Y, −X, +X
- TCP offset displayed at boot (replaces IK ref boot print), IK ref displayed on teach pendant screen

### Changed
- `orient_tcp_down()` now delegates to `orient_tcp(pose, [0, 0, -1])` same behavior, shared implementation

## [0.3.20] 2026-07-27

### Added
- Global `ik_reference` setting on `URRobot` set once, applies to all motion commands (`move_to`, `move_relative`, `move_sequence`) to prevent elbow/wrist flipping (IK ambiguity)
- `ik_reference` in config.yaml and `from_config()` persistent setup without code changes
- `ik_reference` in CLI teach pendant reads from config.yaml, shows at boot
- Per-call `ik_reference` parameter on `move_to()`, `move_relative()`, `move_sequence()` override global default per move
- README documentation with recommendation to always use `ik_reference` for stable motion

## [0.3.19] 2026-07-27

### Changed
- `is_moving()` now uses pose-based arrival detection instead of velocity thresholds compares current TCP pose to move target (2mm / 2° tolerance) instead of checking joint/TCP velocities, fixing false "still moving" on heavier robots (UR15e, UR20, UR30) with residual vibration
- Teach CLI goto loop now has a 60s timeout to prevent hanging when robot is already at target

## [0.3.18] 2026-07-27

### Fixed
- Teach CLI (`urkit teach`) now applies `gripper_config` overrides (`tcp_offset`, `mass`, `center_of_gravity`) from config.yaml to preset grippers previously it used raw preset defaults, causing position mismatches between CLI-saved points and `from_config()` execution

## [0.3.17] 2026-07-27

### Added
- YAML config `gripper` key now accepts a dict for custom gripper/payload definitions define arbitrary mass, center of gravity, and TCP offset without code
- `gripper_config` overrides now support physical properties (`mass`, `center_of_gravity`, `tcp_offset`) to override built-in preset values

## [0.3.16] 2026-07-20

### Added
- `set_speed(vel)` and `set_acc(acc)` to change default velocity and acceleration at runtime all subsequent moves pick up new values
- `default_vel` and `default_acc` read-only properties on `URRobot`
- Soft warnings when values exceed typical limits (> 2 m/s velocity, > 6 m/s² acceleration)

## [0.3.15] 2026-07-15

### Fixed
- Teach pendant config now saves to CWD instead of always resolving to the project root `config.yaml` follows the user, not the package

## [0.3.14] 2026-07-15

### Fixed
- `enable_freedrive` uses current TCP pose as center for constrained modes (XYZ, ROTATION) instead of `[0,0,0,0,0,0]` prevents IK failure when robot is far from base origin
- `enable_freedrive` captures ur_rtde stderr to surface robot errors in CLI instead of generic "returned false"
- `move_sequence` replaced `Path`/`movePath` API with individual `moveL`/`moveJ` calls `blend_radius` now ignored
- `move_until_contact` accepts individual `speed_x/y/z/rx/ry/rz` keyword params alongside `speed_vector`

### Changed
- Moved inline imports to top of file (`RtdeRegisterConflictError`, `resolve_config`) only optional/circular imports remain inline with justification

## [0.3.13] 2026-07-14

### Fixed
- `Points` SQLite connection now allows cross-thread access (`check_same_thread=False`) enables calling `move_to()` from background threads without `ProgrammingError`

## [0.3.12] 2026-07-10

### Added
- `URRobot.save_point(name, pose)` optional `pose` parameter to save an arbitrary TCP pose without moving the robot. Omit `pose` to save the current position (existing behavior).

## [0.3.11] 2026-07-10

### Fixed
- Always stop running program via Dashboard before RTDE connect (was: only after boot) handles crashed sessions leaving ExternalControl running
- RTDE connection retries (2×5s) with clear error message pointing to controller reboot when registers are locked
- CLI no longer shows misleading "Remote Control not enabled" hint when the real issue is locked RTDE registers

## [0.3.10] 2026-07-10

### Fixed
- RTDE connection retries once after boot (5s delay) Secondary Interface may not be ready immediately after power-on + brake release

## [0.3.9] 2026-07-10

### Fixed
- `power_on()` now waits for robot to reach `IDLE` mode (was "not POWER_OFF") the robot could still be in `POWER_ON` or `BOOTING` where the dashboard rejects "brake release" with a mounting error
- `release_brakes(force=False)` new `force` parameter to skip the mode check after power_on, since `IDLE` is ambiguous (brakes engaged vs released). Retry logic added for "mounting is not correct" responses
- Poll timeouts reduced from 30s to 15s for faster failure detection

## [0.3.8] 2026-07-07

### Added
- `move_to(offset_x, offset_y, offset_z, offset_rx, offset_ry, offset_rz)` individual offset parameters as a cleaner alternative to the 6-element list
- `get_pose(offset_x, offset_y, offset_z, offset_rx, offset_ry, offset_rz)` individual offset parameters, same pattern as move_to
- `move_relative(delta_x, delta_y, delta_z, delta_rx, delta_ry, delta_rz)` individual delta parameters, same pattern as move_to

### Fixed
- `move_frame` docstring example used invalid 3-element offset list

## [0.3.7] 2026-07-07

### Added
- `zero_ft_sensor()` zero the robot's force/torque sensor (wraps `rtde_control.zeroFtSensor()`)
- `move_until_contact(zero_first=True)` new parameter to zero FT sensor before contact detection (default True)

### Changed
- `activate_gripper()` renamed to `_activate_gripper()` (private) use `robot.gripper.activate()` directly as the public API

## [0.3.6] 2026-07-07

### Changed
- Gripper activation timeout increased from 5s to 10s

## [0.3.5] 2026-07-07

### Changed
- `set_position(mm)` renamed to `set_position_mm(mm)` name now makes the unit explicit
- `set_position_percent(percent)` added 0 = fully open, 100 = fully closed, delegates to preamble's `rq_move_norm` / `rq_move_and_wait_norm`
- Payload tracking: `get_payload()` now returns the locally-tracked value instead of reading from RTDE `payload` output field (which returns garbage on some PolyScope versions)
- Payload: `set_payload()` now uses `setTargetPayload()` with fallback to `setPayload()` for older PolyScope (< 5.11.0), logs warning on fallback, tracks mass locally
- CLI: `--gripper` now accepts case-insensitive input and both `-` / `_` (e.g. `2F_140`, `HAND-E`, `none` all work)
- Added `get_polyscope_version()` returns PolyScope version string via Dashboard (e.g. '5.25.0'), or None if unavailable

## [0.3.4] 2026-07-03

### Added
- Reachability pre-check for Cartesian moves in `move_to()`
- Catches unreachable poses before robot moves, raises `MotionError`

## [0.3.3] 2026-07-03

### Added
- Safe mode step caps: L=10mm / A=1° (expert mode keeps L=50mm / A=5°)

## [0.3.2] 2026-07-03

### Added
- `6`/`7` keys for gripper speed/force (prompt-based, Robotiq only)
- Force/speed display on Gripper line (`F=100 S=100`)
- Force/speed applied before each gripper operation (rq_set_force/rq_set_speed)

### Fixed
- Missing `points_path` argument in `_submenu_explore_points` (P key crash)
- Redundant inline import of `load_config` in teach pendant
- Redundant Enter key handler in points explorer (auto-refreshes every 2s)

## [0.3.1] 2026-07-03

### Added
- Async motion support: `move_to()`, `movel()`, `movej()` accept `asynchronous=True`
- `is_moving()` method polls joint/TCP velocity to detect motion
- `stop()` method sends `stopL(5.0, True)` + `stopJ(5.0, True)` for reliable stops
- Go To submenu: Space key cancels moves, dedicated moving screen with progress bar
- Progress bar uses TCP position distance (monotonic never goes down)
- Joint angle display in main screen (J1-J3 and J4-J6 lines)
- Joint limit proximity warnings (yellow at 10%, red at 5%)
- Payload/TCP color coding (green when configured, dim when not)
- Mypy strict mode configuration in `pyproject.toml`
- CHANGELOG.md with version history
- AGENTS.md with project maintenance rules

### Changed
- ESC exits CLI, Space cancels current move (was ESC for both)
- Exit paths call `robot.stop()` before `speed_stop()`
- Removed `interruptible_move_to()` no longer needed with async API
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

## [0.3.0] 2026-06-19

### Added
- Safe/expert mode display in header
- speed_stop on ESC and Ctrl+C exit
- Safety features for teach mode

## [0.2.1] 2026-06-18

### Added
- `get_pose()` method for retrieving saved point poses

### Fixed
- README documentation refinements

## [0.2.0] 2026-06-18

### Changed
- Restructured README and fixed `rtde_frequency` documentation

## [0.1.1] 2026-06-16

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
- Fix deactivate() docstring no freedrive restriction required
- Fix freedrive cycle: always start from ALL instead of remembering last mode
- Add Rz rotation to XYZ freedrive mode
- Skip gripper is_connected() ping during freedrive
- Remove auto-open on activate and is_connected() ping from CLI
- Remove is_connected() from Gripper interface
- Document XYZ+Rz freedrive mode in CLI and README
- Show XYZ+Rz in freedrive status line instead of enum name

### Removed
- DO round-trip hardware read and suppress redundant freedrive messages
- rtde_frequency parameter hardcode 500Hz
- Incorrect URCap mention from error message
- Fix error message for RTDE script upload failure
- Fix ur_rtde segfault at 125Hz and add ExternalControl URCap error

### Fixed
- Align OTHER continuation line with spacing instead of repeating label
- Fix footer: Exit: ESC, split OTHER into two lines
- Revert footer to compact layout, keep P: Explorer
- Clean up footer keymap: split OTHER, add P: Explorer, Exit: ESC

## [0.1.0] 2026-06-12

### Added
- Initial release
- Connection validation and lifecycle
- Motion commands (moveJ, moveL, move_by, move_velocity, move_until_contact)
- Points database (SQLite-backed)
- Gripper abstraction (Robotiq, Digital)
- Geometry helpers (quaternion, rotvec, RPY)
- Teach pendant CLI with live telemetry
- Test suite (132 tests)
