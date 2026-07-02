# URKit

[![PyPI](https://img.shields.io/pypi/v/urkit.svg)](https://pypi.org/project/urkit/)

**URKit** is a Python toolkit for [Universal Robots](https://www.universal-robots.com/) e-Series robots that makes the common stuff simple and gets out of the way for everything else.

Built on [`ur_rtde`](https://sdurobotics.gitlab.io/ur_rtde/), it packages the operations you reach for most: connecting, moving to named points, gripper control, telemetry, and I/O, while exposing the raw RTDE interfaces for anything deeper.

---

## Table of Contents

- [Quick Start](#quick-start)
- [Interactive CLI](#interactive-cli)
  - [Teach Mode](#teach-mode)
  - [Points Explorer](#points-explorer)
  - [Key Map](#key-map)
- [API Reference](#api-reference)
  - [Connecting](#connecting)
  - [Grippers](#grippers)
  - [Points & Motion](#points--motion)
  - [Telemetry](#telemetry)
  - [Digital I/O](#digital-io)
- [Configuration](#configuration)
- [Advanced](#advanced)
  - [Raw RTDE Access](#raw-rtde-access)
  - [Connection Lifecycle](#connection-lifecycle)
  - [Error Handling](#error-handling)

---

## Quick Start

```bash
pip install -U urkit
```

The `-U` (upgrade) flag ensures you always get the latest version — this project is in early development and changes frequently.

Requires Python 3.8+ and a Universal Robots e-Series (UR3e to UR30).

### Robot Setup (one-time)

1. **Network**: `☰` → `System` → `System` → `Network`. Set a static IP on the robot and a matching one on your PC. Both addresses must share the same first three octets (the network), with a different last octet (the host). For example:
   - **Robot**: `172.31.1.42` / Subnet `255.255.255.0`
   - **PC**: `172.31.1.1` / Netmask `255.255.255.0`
   - Verify with `ping 172.31.1.42`. Connect via direct Ethernet cable or a switch.
2. **Remote Control**: `☰` → `System` → `Remote Control`: Enable. Press the remote/local button on the pendant.
3. **Security**: `☰` → `Security` → `Services`: enable RTDE and disable EtherNet/IP, PROFINET, or MODBUS if they're claiming RTDE registers. Save and restart.

That's it. No `.urp` files to run, no extra programs needed.

### Example

If you have a Robotiq gripper, install the **Robotiq Gripper Control** URCap first: download from [robotiq.com/support](https://robotiq.com/support), copy the `.urcap` to a USB drive, and install via `☰` → `Settings` → `System` → `URCaps`.

```python
from urkit import URRobot, ROBOTIQ_HAND_E  # or ROBOTIQ_2F_85, ROBOTIQ_2F_140, or gripper=None

robot = URRobot(ip="172.31.1.42", points="points.db", gripper=ROBOTIQ_HAND_E)
robot.gripper.activate()

robot.move_to("home")
robot.move_to("pick", offset=[0, 0, 0.05, 0, 0, 0])
robot.gripper.close()
robot.move_to("place")
robot.gripper.open()
```

The typical workflow:

1. **Teach points.** Use the CLI to position the robot and save named waypoints.
2. **Write code.** Create a robot, move to points by name, apply offsets, run sequences.
3. **Iterate.** Add more points, tweak your code, repeat.

---

## Interactive CLI

URKit provides two CLI tools: **teach** for interactive robot control, and **points** for browsing saved waypoints.

### Teach Mode

The interactive teach pendant for moving the robot, saving points, and checking telemetry:

```bash
urkit teach 172.31.1.42              # with robot IP
urkit teach                          # reads IP from config.yaml
```

**Flags:**

| Flag | Description |
|------|-------------|
| `ip` | Robot IP address (positional, overrides config) |
| `--gripper` | Gripper preset: `2f-85`, `2f-140`, `hand-e`, `digital`, `none` |
| `--gripper-pin` | Digital gripper output pin (default: 0) |
| `--gripper-force` | Robotiq force 0-100 |
| `--gripper-speed` | Robotiq speed 0-100 |
| `--gripper-close-on-high` | Digital polarity: `true` or `false` |
| `--points` | Path to `points.db` file (overrides config) |
| `--config` | Path to config file (default: `config.yaml` in project root or CWD) |
| `-e`, `--expert` | Disable safety speed clamping (full speed for goto/tcp-down) |
| `-v`, `--verbose` | Show verbose output (debug connection issues) |

### Points Explorer

Browse saved waypoints with real-time search filtering. No robot connection needed:

```bash
urkit points                          # uses default points.db
urkit points test_points.db           # use specific database
```

### Key Map

All movement and orientation keys support **hold-to-repeat**.

<table>
  <tr>
    <th align="center">Movement</th>
    <th align="center">Orientation</th>
    <th align="center">Step Size</th>
  </tr>
  <tr>
    <td align="center" style="width:33%">
      <table>
        <tr><th>Key</th><th>Action</th></tr>
        <tr><td><code>W</code> / <code>S</code></td><td>+X / -X</td></tr>
        <tr><td><code>A</code> / <code>D</code></td><td>+Y / -Y</td></tr>
        <tr><td><code>Q</code> / <code>E</code></td><td>+Z / -Z</td></tr>
      </table>
    </td>
    <td align="center" style="width:33%">
      <table>
        <tr><th>Key</th><th>Action</th></tr>
        <tr><td><code>U</code> / <code>O</code></td><td>Roll - / +</td></tr>
        <tr><td><code>I</code> / <code>K</code></td><td>Pitch - / +</td></tr>
        <tr><td><code>J</code> / <code>L</code></td><td>Yaw - / +</td></tr>
      </table>
    </td>
    <td align="center" style="width:34%">
      <table>
        <tr><th>Key</th><th>Action</th></tr>
        <tr><td><code>1</code></td><td>Set linear step (mm)</td></tr>
        <tr><td><code>2</code></td><td>Set angular step (deg)</td></tr>
        <tr><td><code>.</code></td><td>Reset defaults (5 mm / 2°)</td></tr>
      </table>
    </td>
  </tr>
</table>

<table>
  <tr>
    <th align="center">Gripper</th>
    <th align="center">Points</th>
    <th align="center">Controls</th>
  </tr>
  <tr>
    <td align="center" style="width:33%">
      <table>
        <tr><th>Key</th><th>Action</th></tr>
        <tr><td><code>X</code></td><td>Open</td></tr>
        <tr><td><code>C</code></td><td>Close</td></tr>
        <tr><td><code>V</code></td><td>Set position (mm)</td></tr>
      </table>
    </td>
    <td align="center" style="width:33%">
      <table>
        <tr><th>Key</th><th>Action</th></tr>
        <tr><td><code>B</code></td><td><strong>Save</strong> current position</td></tr>
        <tr><td><code>G</code></td><td>Go to saved point</td></tr>
        <tr><td><code>H</code></td><td>Delete saved point</td></tr>
        <tr><td><code>P</code></td><td>Open points explorer</td></tr>
        <tr><td><code>R</code></td><td>Rename saved point</td></tr>
      </table>
    </td>
    <td align="center" style="width:34%">
      <table>
        <tr><th>Key</th><th>Action</th></tr>
        <tr><td><code>F</code></td><td>Freedrive (OFF → ALL → XYZ+Rz)</td></tr>
        <tr><td><code>M</code></td><td>Toggle frame (BASE / TOOL)</td></tr>
        <tr><td><code>N</code></td><td>Go To mode (Cartesian / Joint)</td></tr>
        <tr><td><code>T</code></td><td>Orient TCP down (180°)</td></tr>
        <tr><td><code>Y</code></td><td>Save config to file</td></tr>
        <tr><td><code>ESC</code></td><td>Exit</td></tr>
      </table>
    </td>
  </tr>
</table>

### Joint Display

The teach pendant shows live joint angles alongside TCP position and orientation:

```
 Position      X=+0.432  Y=+0.111  Z=+0.227
 Orientation   R=+131.3  P=-121.0  Y= +8.0
 Joints        J1=+150.0  J2=+020.0  J3=+160.0
               J4=+050.0  J5=-080.0  J6=+157.0
```

Joint angles color-code proximity to mechanical limits:

- **Yellow**: within 10% of joint range (warning)
- **Red**: within 5% of joint range (danger)

UR e-Series joint limits:

| Joint | Range | Notes |
|-------|-------|-------|
| J1 (shoulder pan) | ±360° | Full rotation |
| J2 (shoulder lift) | ±360° | Full rotation |
| J3 (elbow) | ±180° | Physically restricted — shoulder lift gets in the way |
| J4 (wrist 1) | ±360° | Full rotation |
| J5 (wrist 2) | ±360° | Full rotation |
| J6 (wrist 3) | ±360° | Tool flange unlimited rotation |

Thresholds scale with each joint's range, so warning zones feel proportional across all joints.

### Safety

By default, **Go To** and **TCP Down** movements use a slow velocity (0.125 m/s) so its safer for anyone standing near the robot. The user's speed slider still applies as a global multiplier on top of this.

Delta movements (W/S/A/D/Q/E) use step-size-based velocities that scale with the speed slider set by the user.

To disable the slow default and use full speed, pass `--expert` or set `expert_mode: true` in your config:

```bash
urkit teach 172.31.1.42 --expert
```

```yaml
# config.yaml
expert_mode: true
```

---

## API Reference

### Connecting

```python
from urkit import URRobot, ROBOTIQ_HAND_E

robot = URRobot(ip="172.31.1.42", points="points.db", gripper=ROBOTIQ_HAND_E)
```

With custom motion defaults:

```python
robot = URRobot(
    ip="172.31.1.42",
    points="points.db",
    gripper=ROBOTIQ_HAND_E,
    default_vel=0.5,    # m/s
    default_acc=0.3,    # m/s²
)
```

From a config file:

```python
robot = URRobot.from_config("config.yaml")
robot = URRobot.from_config("config.yaml", ip="10.0.0.50")  # override IP
```

### Grippers

Three built-in presets:

| Preset | Description |
|--------|-------------|
| `ROBOTIQ_HAND_E` | Robotiq 2F-140-E (Hand-E series) |
| `ROBOTIQ_2F_85` | Robotiq 2F-85 |
| `ROBOTIQ_2F_140` | Robotiq 2F-140 |

```python
robot.gripper.activate()              # required before open/close (Robotiq only)
robot.gripper.is_activated()          # check activation state

robot.gripper.open()                  # fully open (blocking by default)
robot.gripper.close()                 # fully closed, stops on contact
robot.gripper.open(wait=False)        # non-blocking return
robot.gripper.set_position(20)        # 20mm open (Robotiq only, 0 = closed)
robot.gripper.set_force(50)           # grip force: 0-100 (Robotiq only)
robot.gripper.set_speed(80)           # movement speed: 0-100 (Robotiq only)
```

Override preset values for custom fingers:

```python
robot = URRobot(ip="172.31.1.42", points="points.db", gripper=ROBOTIQ_HAND_E, max_mm=120)
```

#### Digital I/O Grippers

Robotiq grippers use a serial protocol over the robot's RS485 port. If you have a suction cup, solenoid, or any actuator controlled by a single digital output pin, use `DigitalGripperConfig` instead. It just turns that pin on (close) and off (open).

```python
from urkit import URRobot, DigitalGripperConfig

robot = URRobot(
    ip="172.31.1.42",
    points="points.db",
    gripper=DigitalGripperConfig(pin=3),  # pin 3 goes high = close
)

robot.gripper.open()    # turn pin 3 off
robot.gripper.close()   # turn pin 3 on
```

`set_force()` and `set_speed()` are not available for digital grippers.

### Points & Motion

The points database is optional. Create a robot without one and attach later:

```python
robot = URRobot(ip="172.31.1.42")
robot.points_db = "points.db"
```

#### Moving to Points

```python
robot.move_to("pick")                      # linear move (default)
robot.move_to("pick", linear=False)        # joint move
robot.move_to("pick", vel=1.0, acc=0.5)    # override speed
```

- **Linear (moveL):** TCP moves in a straight line. Predictable path, slower near complex orientations.
- **Joint (moveJ):** Each joint moves simultaneously. Faster, but the TCP follows an arc.

#### Pose Format

A pose is `[x, y, z, rx, ry, rz]`: position in meters and orientation as a **rotation vector** (axis-angle in radians). This is not RPY (roll/pitch/yaw). The teach pendant displays RPY in degrees, which is a different representation. Values you see on the pendant won't match `get_tcp_pose()` directly.

#### Offsets

Offsets are 6-element lists `[dx, dy, dz, drx, dry, drz]`:

```python
robot.move_to("pick", offset=[0, 0, 0.05, 0, 0, 0])  # 5cm above pick
```

#### Resolve a Pose

Get a pose without moving. Useful for logging, comparisons, or custom motion:

```python
pose = robot.get_pose("pick")
pose = robot.get_pose("pick", offset=[0, 0, 0.05, 0, 0, 0])  # with offset
robot.move_to(pose)  # move to the resolved pose later
```

#### Coordinate Frame

```python
from urkit import MoveFrame

robot.move_frame = MoveFrame.TOOL   # default is BASE
robot.move_relative([0, 0, 0.05, 0, 0, 0])  # 5cm along tool Z
```

- **BASE** (default): delta relative to robot base
- **TOOL**: delta relative to TCP orientation

#### Points are tool-agnostic

Points are stored in the active TCP frame, so they work with any tool. If you swap grippers and set the correct TCP offset, your saved points remain valid.

#### Point Management

```python
robot.save_point("here")
robot.point_names()           # ["home", "pick", "place"]
robot.rename_point("old", "new")
robot.delete_point("old")
robot.export_points("backup.json")
robot.import_points("backup.json")
```

#### Relative Moves

```python
robot.move_relative([0, 0.01, 0, 0, 0, 0])  # 1cm along Y
robot.move_relative([0, 0, 0.05, 0, 0, 0], frame=MoveFrame.TOOL)  # 5cm along tool Z
```

#### Sequences with Blending

```python
robot.move_sequence(["a", "b", "c"])
robot.move_sequence(["a", "b", "c"], blend_radius=0.02)
```

#### Contact Detection

```python
robot.move_until_contact([0, 0, -0.02, 0, 0, 0])
```

#### Velocity Control

```python
robot.move_velocity([0, 0, -0.02, 0, 0, 0], duration=1.0)
```

#### Freedrive Mode

```python
from urkit import FreedriveMode

robot.enable_freedrive()              # all 6 axes free
robot.enable_freedrive(FreedriveMode.XYZ)      # linear axes + Rz rotation
robot.enable_freedrive(FreedriveMode.ROTATION) # rotation only
robot.disable_freedrive()             # disable before sending motion commands
robot.is_freedrive_active             # check state
```

#### Speed Control

```python
robot.speed_stop()                    # stop velocity-controlled motion (not E-stop)
robot.set_speed_slider(0.5)           # 50% velocity cap
robot.get_speed_slider()              # read current slider (0.0-1.0)
```

The speed slider controls the pendant's speed multiplier. It's global, persistent, and affects all motion commands.

#### Inverse Kinematics

```python
joints = robot.inverse_kinematics([0.5, 0, 0.3, 0, 0, 0])
```

### Telemetry

```python
pose = robot.get_tcp_pose()           # [x, y, z, rx, ry, rz]
joints = robot.get_joint_positions()  # [j0..j5]
force = robot.get_tcp_force()         # [fx, fy, fz, mx, my, mz]
mode = robot.get_robot_mode()         # "REMOTE_CONTROL", "SERVOING", etc.
payload = robot.get_payload()         # kg
robot.is_protective_stopped()         # bool
robot.is_emergency_stopped()          # bool
robot.current_point()                 # {"pose": [...], "joints": [...]}
```

### Digital I/O

```python
robot.set_digital_output(0, True)
robot.set_digital_outputs({0: True, 1: False, 8: True})
robot.set_digital_outputs(False)      # clear all

robot.get_digital_input(0)
robot.get_analog_input(0)
robot.get_tool_input(0)

robot.wait_for_input(0, True, timeout=10.0)  # block until pin 0 goes high
```

---

## Configuration

URKit uses a YAML config file (`config.yaml`) to persist settings between sessions.

### Location

URKit searches for `config.yaml` in this order:
1. Explicit path via `--config` flag or `load_config("path")`
2. Project root (where `src/urkit` lives)
3. Current working directory

### Keys

| Key | Description | Example |
|-----|-------------|---------|
| `robot_ip` | Robot IP address | `172.31.1.42` |
| `points_path` | Path to SQLite points database | `points.db` |
| `gripper` | Gripper preset name | `hand-e`, `2f-85`, `2f-140`, `digital` |
| `default_vel` | Default linear velocity (m/s) | `0.5` |
| `default_acc` | Default linear acceleration (m/s²) | `0.3` |
| `expert_mode` | Disable safety speed clamping | `false` |

### Gripper Config

```yaml
gripper: digital
gripper_config:
  pin: 3
  close_on_high: true
```

```yaml
gripper: hand-e
gripper_config:
  force: 50
  speed: 80
```

### CLI Override Precedence

1. **CLI flags.** `urkit teach 172.31.1.42 --gripper none`
2. **Config file.** Values from `config.yaml`
3. **Built-in defaults.** `points.db`, no gripper, 0.5 m/s velocity

### Saving Config

The CLI **never** modifies your config file automatically. Press **Y** inside the teach pendant to save. This way you only save settings you've actually tested.

```bash
urkit teach 172.31.1.42 --gripper hand-e  # test, then press Y
urkit teach                               # next time: reads from config
```

Multiple workcells:

```bash
urkit teach --config station_a.yaml   # press Y to save
urkit teach --config station_b.yaml   # separate config
```

### Programmatic

```python
from urkit import load_config, resolve_config

config = load_config()                          # auto-resolve
config = load_config("/path/to/my.yaml")        # explicit path
path = resolve_config()                         # returns Path or None
robot = URRobot.from_config({"robot_ip": "172.31.1.42", "gripper": "2f-85"})
```

---

## Advanced

### Raw RTDE Access

URKit doesn't try to wrap everything. Access the raw `ur_rtde` interfaces for advanced features:

```python
robot.rtde_control.forceMode(...)
robot.rtde_control.servoJ(...)
robot.rtde_receive.getActualCurrent()
```

Full `ur_rtde` documentation: <https://sdurobotics.gitlab.io/ur_rtde/>

### Connection Monitoring

```python
robot.connection_lost       # bool: check if RTDE dropped
robot.reconnect_rtde()      # reconnect after a drop
```

`disconnect()` is called automatically when the robot object is garbage collected.

### Error Handling

```python
from urkit import URKitError, MotionError, PointError

try:
    robot = URRobot(ip="172.31.1.42", points="points.db")
except RobotNotInRemoteModeError:
    print("Enable remote control on the teach pendant!")
except RtdeRegisterConflictError:
    print("Disable EtherNet/IP, PROFINET, or MODBUS!")
except URKitError as e:
    print(f"Error: {e}")
```

Common runtime errors:

| Exception | When |
|-----------|------|
| `MotionError` | Unreachable pose, bad TCP offset, freedrive failure |
| `PointError` | Point not found, no points database configured |
| `GripperError` | Gripper activation or communication failure |
| `URKitIOError` | Invalid pin number, I/O read/write failure |
| `TelemetryError` | Cannot read pose, joints, force, etc. |

When the robot enters protective stop or the RTDE connection drops, motion commands raise `URKitConnectionError` and the program should exit. The CLI handles this automatically.

### Connection Notes

The `URRobot` constructor takes a few seconds on first call: it validates the connection, checks remote mode, powers on the robot, releases brakes, and connects RTDE. Subsequent calls are faster if the robot is already running.
