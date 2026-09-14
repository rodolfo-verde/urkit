# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `URRobot.set_held_payload(mass, center_of_gravity=None)`: add the mass of a picked-up object to the payload before moving it (the controller's gravity compensation uses the payload, so the arm sags and drifts without it). `mass=0` resets to the base payload captured at connect, never to a literal zero. The object CoG defaults to the TCP position (gripped at center) and the combined CoG is the mass-weighted average of base and object. New reads: `robot.base_payload` (gripper + tooling) and `robot.held_payload` (0 = none); `robot.payload` is the total. The teach pendant payload row shows the held mass (e.g. `1.427kg +0.050 held`), and the 9 key sets it from the pendant (`Held payload in kg (0 = reset to base)`). A manual `set_payload()` while nothing is held redefines the base payload; while a payload is held it raises (the mass would be ambiguous). Constructor `mass=` / `center_of_gravity=` / `tcp_offset=` overrides now work the same as in `from_config` (they previously leaked into the gripper backend kwargs and raised).
- `EpickGripper` backend: Robotiq EPick vacuum gripper (e-Series only) over the same RS485 Robotiq protocol as the 2F series, using the legacy Robotiq ASCII commands (requires the Robotiq Gripper Control URCap, same as the 2F presets). Semantics are inverted from the 2F: `close()` grips (pump on) and blocks until the gripper confirms a secured object, raising `GripperError` if nothing is under the suction cup when the grip timeout expires (a failed grip leaves the vacuum on; call `open()` to release); `open()` releases (pump off + blow-off) and waits until the vacuum is lost. Grip parameters: `max_vacuum` = max vacuum level 20-100% (default 60, the Robotiq URCap default; 100 runs the pump continuously and cannot confirm a grip), `min_vacuum` = min vacuum 10% up to the max (default 40), `grip_timeout` = grip timeout in 100 ms units (default 30 = 3 s); the ranges are enforced at construction and on every setter, and a parameter of one backend passed to another raises `GripperError` instead of being ignored. `set_position_percent(p)` is repurposed as a one-shot vacuum grip (0 = release, 1-100 = grip at that level with the normal secured-object wait). Detection runs the EPick in advanced mode (rMOD=1) and confirms the secured-to-min object flag, which the EPick only sets while the vacuum is actually held: automatic mode (rMOD=0) false-positives on a short "seemingly constant" vacuum with no object on the cup, so urkit does not use it
- Six EPick cup presets, one per bracket system + cup size: `ROBOTIQ_EPICK_SINGLE_S/L`, `ROBOTIQ_EPICK_DUAL_S/L`, `ROBOTIQ_EPICK_QUAD_S/L` (S = Ø40, L = Ø55; config/CLI names like `epick-quad-l`). Mass, CoG, and TCP come from the manual's Table 6-4 (body + bracket stack) and the official Festo datasheets for the cups Robotiq ships (VASB-40-1/4-PUR-B: 30 g / 32 mm, VASB-55-1/4-PUR-B: 39 g / 39 mm); all-small presets reproduce Table 6-4 exactly, and each TCP z is the bottom of the cups. Configurations without cups cannot grip and have no preset (pass mass overrides during setup). The teach pendant adapts to the EPick: the gripper row shows `max=` [7] and `min=` [6], [7] sets the max vacuum and [6] the min vacuum (grip timeout is set via `grip_timeout` in the config, not from the pendant)

### Changed
- `URRobot` no longer swallows gripper construction errors: a bad gripper parameter (out of range, or belonging to a different backend) now raises `GripperError` at connect time instead of logging a warning and continuing without a gripper

### Fixed
- Test suite: `test_speed_out_of_range_raises` was defined twice in `TestRobotiqGripper`; the second definition shadowed the first, so the constructor speed-range test never ran. Renamed to `test_init_speed_out_of_range_raises`

## [0.5.1] 2026-08-26

### Changed
- Windows CLI support is now official: the "not fully tested" startup warning is removed from `urkit teach` and `urkit points`, and the README platform section lists Linux and Windows as fully supported (macOS runs the same POSIX code path as Linux)
- Teach pendant: TCP position now displays in millimeters (e.g. `X= -127.0`) to match the step size and gripper units. The "moving to point" screen follows the same convention
- Teach pendant: screen frame widened from 72 to 92 columns and the key reference is now a column grid: every yellow key in MOVE/ORIENT/STEP/GRIPPER/POINTS/OTHER lines up in the same column, and no row carries more than three units (POINTS splits its five keys across two lines). The "moving to point" screen uses the same frame width
- Teach pendant: footer grid drops M, N, and 0 (inline hints on the Frame, Go To, and Speed status rows cover them, same pattern as the gripper [6]/[7] hints) and swaps 3 for F: the freedrive status row always hints both keys inline, so the footer carries the primary freedrive key instead of the axis picker. The freedrive row hint now reads `[F: cycle, 3: axes]` when OFF and `[3: axes, F: cycle]` when ON: F cycles OFF → ALL → XYZ → OFF (so it says "cycle", not "off")
- Teach pendant: step key descriptions drop their units (`1: Linear`, `2: Angular`), since the 1/2 input prompts already show them, and the grid column widths tighten to fit the longest remaining unit
- Teach pendant: gripper row spells out force and speed instead of the cryptic `F=`/`S=` shorthand (e.g. `force=100 [7]  speed=100 [6]`)
- README: the Joint Display sample screen updated to the current layout (mm position, aligned columns)

### Fixed
- Teach pendant: status messages now stay on screen for 15 seconds (message TTL) instead of being cleared after the first redraw. The 0.5s freedrive periodic refresh was erasing a fresh message before it could be read, and without freedrive messages lingered until the next keypress
- Teach pendant: urkit log warnings now reach the screen after the first command. The `messages = []` rebind orphaned the screen log handler's reference to the original list, so later warnings were appended to a list that was never read again; the message list is now pruned in place
- Teach pendant: ESC (or an empty Enter) in the step size, gripper position/speed/force, and speed slider prompts now shows "Cancelled" instead of "Invalid ... value". A cancelled input returns None from `_read_input()`, which was passed to `float()` and its `TypeError` misreported as invalid input
- Type annotations from the 0.5.0 changes that mypy flagged: `_resolve_ik_reference()` now accepts the GLOBAL sentinel type and raises a descriptive `MotionError` if the sentinel is ever resolved directly, and `_next_freedrive_step()` is typed `tuple[bool, FreedriveMode | list[int] | None]` instead of `tuple[bool, object]`, with the caller raising if the cycle returns no mode
- Teach pendant header centering: `str.center()` was applied after the ANSI color wrap, so escape bytes counted as width and the title lines sat off-center. Plain text is centered first, then colored
- Teach pendant status alignment: X/Y/Z, R/P/Y, and J1-J6 values use fixed-width fields so the three rows share the same columns

## [0.5.0] 2026-08-25

### Changed
- A named `ik_reference` with no points DB configured now raises `PointError` immediately instead of warning and falling back to current joint positions: a configured posture reference cannot silently become a no-op
- `URRobot.move_relative()` keyword parameters `delta_x`, `delta_y`, `delta_z`, `delta_rx`, `delta_ry`, `delta_rz` renamed to `dx`, `dy`, `dz`, `drx`, `dry`, `drz`. This matches the element names the `delta` list already uses in the docs (`[dx, dy, dz, drx, dry, drz]`) and the abbreviated `vel`/`acc` style. Breaking: old names now raise `TypeError`
- `move_to()`, `get_point()`, and `get_current_point()`: the `offset` list parameter renamed to `delta`, and `offset_x`/`offset_y`/`offset_z`/`offset_rx`/`offset_ry`/`offset_rz` renamed to `dx`/`dy`/`dz`/`drx`/`dry`/`drz`. Every shift in the motion API now uses one pattern: `delta=[x, y, z, rx, ry, rz]` or `dx`..`drz` plus `frame=`. `Point.with_offset()` renamed to `Point.with_delta()`. The `tcp_offset` property is unchanged (it is the persisted TCP calibration, not a motion delta). Breaking
- `move_until_contact()` and `move_velocity()`: `speed_vector` renamed to `velocity`, and `speed_x`/`speed_y`/`speed_z`/`speed_rx`/`speed_ry`/`speed_rz` renamed to `vx`/`vy`/`vz`/`vrx`/`vry`/`vrz`. The v prefix is the standard velocity notation, pairing with d for deltas. Docstring element names fixed in the same pass (`vRoll`/`vPitch`/`dYaw` were wrong). Breaking
- `ik_reference` in `move_to()` and `move_sequence()`: the `"__global__"` magic string is replaced by a public `urkit.GLOBAL` sentinel object, compared by identity. Default behavior is unchanged (use the robot's global setting), `None` still disables for one move, and passing the old string now raises a `MotionError` with a migration hint. Also removes the footgun of a point literally named `__global__` being hijacked as the sentinel. The global setting itself (constructor, `config.yaml`, `robot.ik_reference` property) now rejects both the old string and GLOBAL at assignment time, so a bad value cannot sit in the robot and only fail later as a point-lookup error. Breaking

### Fixed
- Root cause of `stopScript failed: WinError 1` and motion hangs: when the RTDE link drops mid-session, the vendored ur_rtde C++ layer enters an internal reconnect loop, so a motion call blocks inside it (measured 45+ s with the link blocked) and a later call surfaces WinError 1 from the half-rebuilt socket. urkit now fails fast: `_check_connection()` checks the live `isConnected()` state at every motion entry point (it previously only checked a flag nothing set) and raises immediately, and `URRobot.reconnect_rtde()` is removed because a Python-level reconnect races the C++ layer's own loop, which is exactly what created the WinError 1 window. An RTDE drop is now fatal for the session; the README documents the verified behavior and recovery, including a controller power cycle after a hard drop
- Arrow keys (and Home/End/F keys) no longer fire movement or point keys in the CLIs, on both platforms. The input loops consumed raw burst bytes, so a CSI sequence's ESC byte parsed as a cancel and its final byte as a key (an up arrow fired the 'a' move handler, a down arrow the 'b' save-point handler). `read_chars()`/`read_key()` parse and drop complete escape sequences, keep real ESC presses (with a short grace wait for sequences split across reads), and are used by the main loops, prompts, and submenus
- Windows: exit-time `Exception in thread interrupt-watcher` cascade. `stop_interrupt_watcher()` now joins the watcher so the CLI never restores the console while it is still inside msvcrt, and the watcher loop snapshots its globals and never raises, even during interpreter shutdown
- `URRobot.disconnect()` is idempotent: the second call (from `__del__` during interpreter shutdown) is a no-op, so exit cannot double-stop the robot or double-close sockets the C++ layer has already torn down. The teach CLI also stops the RTDE control script (clean stop) before the dashboard program stop on exit
- Windows: redirected consoles (cp1252) no longer crash with `UnicodeEncodeError` on the `●`/`✓` status symbols; output degrades to `?`
- Freedrive F key: the cycle was stuck between ALL and XYZ and could never reach OFF. It now cycles OFF -> ALL (or the last custom axes) -> XYZ -> OFF
- Misleading key hints: `N` now says Cart/Joint instead of GoTo, the gripper speed/force hints sit next to the live values, and the freedrive hints reflect the actual cycle

### Added
- ur_rtde C++ stderr is captured by default to `urkit_rtde_stderr.log` in the working directory (append) instead of /dev/null, and the captured text is re-emitted as a WARNING, so move failures surface on the pendant screen and in application logs. `URKIT_RTDE_STDERR` still overrides the path
- `URKIT_LOG_FILE=<path>` tees the full urkit debug log to a file for post-mortem
- Freedrive axis picker (key 3) works in both states: with freedrive off it opens fully locked and Enter enables exactly the selected axes; with it on, Enter re-applies live. L/U lock/unlock all
- Status messages are colored by severity: red for failures, yellow for warnings and cancellations, green for completed actions
- The gripper UI (status extras and key hints) hides when no gripper is configured or active
- Movement errors include the RTDE control connection state, so a dropped link is identifiable from the message itself

## [0.4.6] 2026-08-18

### Fixed
- Windows: exit-time crash (`stopScript failed: WinError 1` plus `Exception in thread interrupt-watcher` tracebacks). Pressing Ctrl+C made both the main loop and the interrupt watcher run cleanup, so two threads called robot.stop() at once. The main loop now tells the watcher to stand down before it starts its own cleanup, and the watcher exits quietly if the console is closing
- Silent move failures: ur_rtde reports a rejected move (control script stopped, robot in a stop state, command timeout) by printing to raw stderr and returning False, while urkit redirected stderr to /dev/null and ignored the return value. The move was treated as a success and the robot just stopped with no message. moveL/moveJ now raise a MotionError when the controller rejects the command, so the pendant shows the error

### Added
- `URKIT_RTDE_STDERR=<path>` environment variable: capture ur_rtde's otherwise-suppressed stderr output in a file (append mode). This is the only place ur_rtde reports why a move was rejected, so it is the diagnostic for move failures and RTDE disconnects
- Interrupt watcher diagnostic: when it fires, the main thread's blocked location (file:line:function) is printed to stderr, e.g. a socket read inside ur_rtde
- Version shown in the CLI headers (teach pendant and points explorer)

## [0.4.5] 2026-08-18

### Fixed
- Windows: `urkit teach` freeze when a fault or RTDE disconnect (e.g. "Reconnecting" after holding a movement key) happened while the main thread was blocked in a robot call. On Windows, Ctrl+C is a raw console byte and no SIGALRM exists, so while blocked, neither the input loops nor the watchdog could react and Ctrl+C was unresponsive. A small Windows-only watcher thread now polls for a Ctrl+C byte (only while no other CLI code is reading input, pushing any other byte back so nothing is lost) and for the monitor's fault flag, then runs the same cleanup as the SIGINT handler and exits. Linux and macOS behavior is unchanged

## [0.4.4] 2026-08-18

### Fixed
- Windows: `urkit teach` startup failure (`SetConsoleMode failed`). The main loop requested raw console mode with echo still enabled, which some consoles refuse. Raw mode now always disables echo on both platforms; the CLIs render typed input themselves
- Windows: console mode errors now include the Win32 error code, the operation that failed, and the requested mode, instead of a bare failure message

## [0.4.3] 2026-08-18

### Fixed
- Windows: arrow keys (and Home/End/PgUp/PgDn/Insert/Delete) in the teach and points CLIs. The msvcrt scan-code lookup compared bytes against int dict keys, so every extended key was silently dropped
- Windows: 64-bit HANDLE truncation. ctypes prototypes for GetStdHandle/GetConsoleMode/SetConsoleMode are now declared so handle values are not truncated to 32 bits
- Teach pendant: input prompts and submenus no longer double-echo typed characters. The pre-shim code ran the main loop in cbreak (echo on) but prompts and menus with echo off; the shim now preserves both states
- Points explorer: mixed input bursts (e.g. a letter and backspace typed together) are processed in order, and Ctrl+C quits on Windows (it arrives as a raw byte there)

## [0.4.2] 2026-08-17

### Docs
- Clarified in README and docstrings that saved points are absolute TCP poses in the robot base frame, and why they stay valid after TCP changes
- README: added platform support section. Windows CLI support is not fully tested and not officially supported; a warning is printed at CLI startup on Windows

### Added
- Windows support for the interactive CLIs (`urkit teach`, `urkit points`). New `urkit/cli/terminal.py` shim provides raw terminal mode and non-blocking key input on both platforms: termios/tty/select on Unix, msvcrt + kernel32 console modes on Windows
- On Windows the terminal shim translates extended keycodes (arrows, Home/End, PgUp/PgDn, Insert, Delete) into the same ANSI escape sequences a Unix terminal emits, so key handling is identical across platforms
- On Windows, ANSI virtual terminal processing is enabled on stdout so colors and cursor codes render on older conhost versions

### Changed
- `ConnectionMonitor` skips the SIGALRM interrupt on Windows (no self-signals). Faults are still detected via the `fault_detected` flag, which the CLI input loops poll every 50ms. On Windows a fault during a long blocking RTDE call surfaces when the call returns instead of being interrupted immediately

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
