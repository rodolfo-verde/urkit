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
pip install urkit
```

Requires Python 3.8+ and a Universal Robots e-Series (UR3e to UR30).

### Robot Setup (one-time)

1. **Network**: `☰` → `System` → `Network`: set the robot's IP and subnet.
2. **Remote Control**: `☰` → `System` → `Remote Control`: Enable. Press the remote/local button on the pendant.
3. **Security**: `☰` → `Security` → `Services`: enable RTDE and disable EtherNet/IP, PROFINET, or MODBUS if they're claiming RTDE registers. Save and restart.

That's it. No `.urp` files to run, no extra programs needed.

### Robotiq Grippers (optional)

Install the **Robotiq Gripper Control** URCap: download from [robotiq.com/support](https://robotiq.com/support), copy the `.urcap` to a USB drive, mount on the robot, and install via `☰` → `Settings` → `System` → `URCaps`.

### Hello World

```python
from urkit import URRobot, ROBOTIQ_HAND_E

robot = URRobot(ip="172.31.1.200", points="points.db", gripper=ROBOTIQ_HAND_E)
robot.gripper.activate()

robot.move_to("home")
robot.move_to("pick", offset=[0, 0, 0.05, 0, 0, 0])
robot.gripper.close()
robot.move_to("place")
robot.gripper.open()
```

The typical workflow:

1. **Teach points** — use the CLI to position the robot and save named waypoints.
2. **Write code** — create a robot, move to points by name, apply offsets, run sequences.
3. **Iterate** — add more points, tweak your code, repeat.

---

## Interactive CLI

URKit provides two CLI tools: **teach** for interactive robot control, and **points** for browsing saved waypoints.

### Teach Mode

The interactive teach pendant for moving the robot, saving points, and checking telemetry:

```bash
urkit teach 172.31.1.200              # with robot IP
urkit teach                           # reads IP from config.yaml
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
| `-v`, `--verbose` | Show verbose output (debug connection issues) |

### Points Explorer

Browse saved waypoints with real-time search filtering — no robot connection needed:

```bash
urkit points                          # uses default points.db
urkit points test_points.db           # use specific database
```

**Features:**
- **Type to search** — real-time substring filtering
- **Fuzzy matching** — type `pk` to find `pick_1` (>60% match)
- **Smart sorting** — exact prefix matches first, then substring, then fuzzy
- **Spatial sorting** — points ordered by proximity to "home" point (XYZ distance)
- **Theme-aware** — automatically adapts colors for light/dark terminals
- **Arrow keys** — scroll · **ESC** — quit

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

---

## API Reference

### Connecting

```python
from urkit import URRobot, ROBOTIQ_HAND_E

robot = URRobot(ip="172.31.1.200", points="points.db", gripper=ROBOTIQ_HAND_E)
```

With custom motion defaults:

```python
robot = URRobot(
    ip="172.31.1.200",
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
robot.gripper.set_force(50)           # grip force: 0-100
robot.gripper.set_speed(80)           # movement speed: 0-100
```

Override preset values for custom fingers:

```python
robot = URRobot(ip="172.31.1.200", points="points.db", gripper=ROBOTIQ_HAND_E, max_mm=120)
```

#### Digital I/O Grippers

For suction cups, solenoids, or custom actuators:

```python
from urkit import URRobot, DigitalGripperConfig

robot = URRobot(
    ip="172.31.1.200",
    points="points.db",
    gripper=DigitalGripperConfig(pin=3),
)

robot.gripper.open()    # turn pin off (release)
robot.gripper.close()   # turn pin on (grab)
```

### Points & Motion

The points database is optional — create a robot without one and attach later:

```python
robot = URRobot(ip="172.31.1.200")
robot.points_db = "points.db"
```

#### Moving to Points

```python
robot.move_to("pick")                      # linear move (default)
robot.move_to("pick", linear=False)        # joint move
robot.move_to("pick", vel=1.0, acc=0.5)    # override speed
```

#### Raw Poses

```python
robot.move_to([0.5, 0, 0.3, 0, 0, 0])     # [x, y, z, rx, ry, rz]
```

#### Offsets

```python
robot.move_to("pick", offset=[0, 0, 0.05, 0, 0, 0])  # 5cm above pick
```

#### Coordinate Frame

```python
from urkit import MoveFrame

robot.move_frame = MoveFrame.TOOL   # default is BASE
robot.move_to("pick", offset=[0, 0, 0.05])  # 5cm along tool Z
```

- **BASE** (default): offset relative to robot base
- **TOOL**: offset relative to TCP orientation

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
robot.move_relative([0, 0, 0.05], frame=MoveFrame.TOOL)
```

#### Sequences with Blending

```python
robot.move_sequence(["a", "b", "c"])
robot.move_sequence(["a", "b", "c"], blend_radius=0.02)
```

#### Contact Detection

```python
robot.move_until_contact([0, 0, -0.02, 0, 0, 0])  # Ctrl+C to stop
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
robot.speed_stop()                    # emergency stop
robot.set_speed_slider(0.5)           # 50% hardware velocity cap
```

The speed slider is a hardware-level multiplier — same as the physical slider on the pendant. It's global, persistent, and affects all motion commands.

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
scaling = robot.get_speed_scaling()   # 0.0-1.0
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
| `robot_ip` | Robot IP address | `192.168.1.100` |
| `points_path` | Path to SQLite points database | `points.db` |
| `gripper` | Gripper preset name | `hand-e`, `2f-85`, `2f-140`, `digital` |
| `default_vel` | Default linear velocity (m/s) | `0.5` |
| `default_acc` | Default linear acceleration (m/s²) | `0.3` |

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

1. **CLI flags** — `urkit teach 172.31.1.200 --gripper none`
2. **Config file** — values from `config.yaml`
3. **Built-in defaults** — `points.db`, no gripper, 0.5 m/s velocity

### Saving Config

The CLI **never** modifies your config file automatically. Press **Y** inside the teach pendant to save. This way you only save settings you've actually tested.

```bash
urkit teach 172.31.1.200 --gripper hand-e  # test, then press Y
urkit teach                                 # next time: reads from config
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
robot = URRobot.from_config({"robot_ip": "172.31.1.200", "gripper": "2f-85"})
```

---

## Advanced

### Raw RTDE Access

URKit doesn't try to wrap everything. Access the raw `ur_rtde` interfaces for advanced features:

```python
robot.rtde_control.moveUntilContact([0, 0, -0.02, 0, 0, 0])
robot.rtde_control.forceMode(...)
robot.rtde_control.servoJ(...)
robot.rtde_receive.getActualCurrent()
```

Full `ur_rtde` documentation: <https://sdurobotics.gitlab.io/ur_rtde/>

### Connection Lifecycle

```python
robot.connection_lost       # bool: check if RTDE dropped
robot.reconnect_rtde()      # reconnect after a drop
robot.disconnect()          # clean shutdown
```

### Error Handling

```python
from urkit import URKitError, RobotNotInRemoteModeError, RtdeRegisterConflictError

try:
    robot = URRobot(ip="172.31.1.200", points="points.db")
except RobotNotInRemoteModeError:
    print("Enable remote control on the teach pendant!")
except RtdeRegisterConflictError:
    print("Disable EtherNet/IP, PROFINET, or MODBUS!")
except URKitError as e:
    print(f"Error: {e}")
```
