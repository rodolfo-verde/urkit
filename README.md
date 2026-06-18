# URKit

[![PyPI](https://img.shields.io/pypi/v/urkit.svg)](https://pypi.org/project/urkit/)

**URKit** is a Python toolkit for [Universal Robots](https://www.universal-robots.com/) e-Series robots that makes the common stuff simple and gets out of the way for everything else.

Built on [`ur_rtde`](https://sdurobotics.gitlab.io/ur_rtde/), it packages the operations you reach for most: connecting, moving to named points, gripper control, telemetry, and I/O, while exposing the raw RTDE interfaces for anything deeper. It doesn't try to replace `ur_rtde`; it sits on top of it so you can use both in tandem.

## Installation

```bash
pip install urkit
```

Requires Python 3.8+ and a Universal Robots e-Series (UR3e to UR30).

### Robotiq Grippers (optional)

If you're using a Robotiq gripper, install the **Robotiq Gripper Control** URCap:

1. Download from [robotiq.com/support](https://robotiq.com/support).
2. Copy the `.urcap` file to a USB drive and mount it on the robot.
3. `☰` → `Settings` → `System` → `URCaps` → Install from USB.
4. Activate and follow the on-screen instructions.

## Robot Setup (one-time)

1. **Network**: `☰` → `System` → `Network`: set the robot's IP and subnet. Make sure your PC is on the same network.
2. **Remote Control**: `☰` → `System` → `Remote Control`: Enable. Press the remote/local button on the pendant.
3. **Security**: `☰` → `Security` → `Services`: enable RTDE and disable EtherNet/IP, PROFINET, or MODBUS if they're claiming RTDE registers. Save and restart.

That's it. No `.urp` files to run, no extra programs needed.

---

## The Workflow

The typical workflow with URKit is simple:

1. **Teach points**: Use the interactive CLI to position the robot and save named waypoints.
2. **Write code**: Create a robot, move to points by name, apply offsets, run sequences.
3. **Iterate**: Add more points in the CLI, tweak your code, repeat.

```python
from urkit import URRobot, ROBOTIQ_HAND_E

# Connect: validates network, remote mode, powers on, sets gripper TCP/payload
robot = URRobot(ip="172.31.1.200", points="points.db", gripper=ROBOTIQ_HAND_E)

# Activate the gripper (required before open/close)
robot.gripper.activate()

# Move to a saved point
robot.move_to("home")

# Apply an offset — 5cm above the pick point
robot.move_to("pick", offset=[0, 0, 0.05, 0, 0, 0])
robot.gripper.close()
robot.move_to("place")
robot.gripper.open()
```

---

## Teaching Points (Interactive CLI)

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

```bash
urkit teach 172.31.1.200 --gripper hand-e --points /path/to/points.db
urkit teach --gripper digital --gripper-pin 3
urkit teach --gripper none            # no gripper (overrides config)
urkit teach --config /path/to/my.yaml # load custom config
urkit teach -v                        # verbose mode
```

### Points Explorer

Browse saved waypoints with real-time search filtering — no robot connection needed:

```bash
urkit points                          # uses default points.db
urkit points test_points.db           # use specific database
```

**Features:**
- **Type to search** — Real-time substring filtering
- **Fuzzy matching** — Type `pk` to find `pick_1` (>60% match)
- **Smart sorting** — Exact prefix matches first, then substring, then fuzzy
- **Spatial sorting** — Points ordered by proximity to "home" point (XYZ distance)
- **Theme-aware** — Automatically adapts colors for light/dark terminals
- **Arrow keys** — Scroll through results
- **ESC** — Quit

Try `urkit points`, type `pick` to filter, press ESC to exit.

### Key Map

All movement and orientation keys support **hold-to-repeat** — hold a key down for continuous motion.

<table>
  <tr>
    <th align="center">Movement</th>
    <th align="center">Orientation</th>
  </tr>
  <tr>
    <td align="center" style="width:50%">
      <table>
        <tr><th>Key</th><th>Action</th></tr>
        <tr><td><code>W</code> / <code>S</code></td><td>+X / -X</td></tr>
        <tr><td><code>A</code> / <code>D</code></td><td>+Y / -Y</td></tr>
        <tr><td><code>Q</code> / <code>E</code></td><td>+Z / -Z</td></tr>
      </table>
    </td>
    <td align="center" style="width:50%">
      <table>
        <tr><th>Key</th><th>Action</th></tr>
        <tr><td><code>U</code> / <code>O</code></td><td>Roll - / +</td></tr>
        <tr><td><code>I</code> / <code>K</code></td><td>Pitch - / +</td></tr>
        <tr><td><code>J</code> / <code>L</code></td><td>Yaw - / +</td></tr>
      </table>
    </td>
  </tr>
</table>

<table>
  <tr>
    <th align="center">Step Size</th>
    <th align="center">Gripper</th>
  </tr>
  <tr>
    <td align="center" style="width:50%">
      <table>
        <tr><th>Key</th><th>Action</th></tr>
        <tr><td><code>1</code></td><td>Set linear step (mm)</td></tr>
        <tr><td><code>2</code></td><td>Set angular step (deg)</td></tr>
        <tr><td><code>.</code></td><td>Reset defaults (5 mm / 2°)</td></tr>
      </table>
    </td>
    <td align="center" style="width:50%">
      <table>
        <tr><th>Key</th><th>Action</th></tr>
        <tr><td><code>X</code></td><td>Open</td></tr>
        <tr><td><code>C</code></td><td>Close</td></tr>
        <tr><td><code>V</code></td><td>Set position (mm)</td></tr>
      </table>
    </td>
  </tr>
</table>

<table>
  <tr>
    <th align="center">Points</th>
    <th align="center">Controls</th>
  </tr>
  <tr>
    <td align="center" style="width:50%">
      <table>
        <tr><th>Key</th><th>Action</th></tr>
        <tr><td><code>B</code></td><td><strong>Save</strong> current position</td></tr>
        <tr><td><code>G</code></td><td>Go to saved point</td></tr>
        <tr><td><code>H</code></td><td>Delete saved point</td></tr>
        <tr><td><code>P</code></td><td>Open points explorer</td></tr>
        <tr><td><code>R</code></td><td>Rename saved point</td></tr>
      </table>
    </td>
    <td align="center" style="width:50%">
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

Position the robot (keys or freedrive), press **B** to save, and the point is stored in your `points.db`. Load that same file in your code and you're ready to go.

---

## Connecting to the Robot

### Direct

```python
from urkit import URRobot, ROBOTIQ_HAND_E

robot = URRobot(ip="172.31.1.200", points="points.db", gripper=ROBOTIQ_HAND_E)
```

Set default motion speeds or RTDE frequency:

```python
robot = URRobot(
    ip="172.31.1.200",
    points="points.db",
    gripper=ROBOTIQ_HAND_E,
    default_vel=0.5,    # m/s
    default_acc=0.3,    # m/s²
    rtde_frequency=500, # Hz (default: 125)
)
```

### From Config

```python
robot = URRobot.from_config("config.yaml")
robot = URRobot.from_config("config.yaml", ip="10.0.0.50")  # override IP
```

See the [Configuration](#configuration) section for full details on config location, keys, and saving.

---

## Configuration

URKit uses a YAML config file (`config.yaml`) to persist settings between sessions. The CLI reads it automatically, and `URRobot.from_config()` loads it programmatically.

### Config File Location

URKit searches for `config.yaml` in this order:
1. Explicit path via `--config` flag or `load_config("path")`
2. Project root (where `src/urkit` lives)
3. Current working directory

If no config file exists, URKit uses built-in defaults and operates fine — the config is optional.

### Config Keys

| Key | Description | Example |
|-----|-------------|---------|
| `robot_ip` | Robot IP address | `192.168.1.100` |
| `points_path` | Path to SQLite points database | `points.db` |
| `gripper` | Gripper preset name | `hand-e`, `2f-85`, `2f-140`, `digital` |
| `default_vel` | Default linear velocity (m/s) | `0.5` |
| `default_acc` | Default linear acceleration (m/s²) | `0.3` |
| `rtde_frequency` | RTDE communication frequency (Hz) | `125` |
| `rtde_frequency` | RTDE communication frequency (Hz) | `125` |
| `rtde_frequency` | RTDE communication frequency (Hz) | `125` |
| `rtde_frequency` | RTDE communication frequency (Hz) | `125` |
| `rtde_frequency` | RTDE communication frequency (Hz) | `125` |

### Gripper Config Section

For digital grippers, specify pin and polarity:

```yaml
gripper: digital
gripper_config:
  pin: 3
  close_on_high: true
```

For Robotiq grippers, override preset values:

```yaml
gripper: hand-e
gripper_config:
  force: 50
  speed: 80
```

### CLI Override Precedence

Settings are resolved in this order (highest priority first):

1. **CLI flags** — `urkit teach 172.31.1.200 --gripper none`
2. **Config file** — values from `config.yaml`
3. **Built-in defaults** — `points.db` for points, no gripper, `0.5` m/s velocity

Use `--gripper none` to explicitly disable a gripper that's set in your config file.

### Saving Config

The CLI **never** modifies your config file automatically. Inside the teach pendant, press **Y** to save your current session's settings (IP, gripper, points path) to the config file. This way you only save settings you've actually tested and verified work.

```bash
# First connection — test everything, then press Y inside the pendant
urkit teach 172.31.1.200 --gripper hand-e

# After pressing Y, config.yaml is saved. Next time:
urkit teach                          # reads IP + gripper from config

# Custom config file
urkit teach --config station_a.yaml  # load from custom path
# press Y inside → saves back to station_a.yaml
```

This lets you maintain separate configs per workcell:

```bash
urkit teach --config station_a.yaml  # press Y to save
urkit teach --config station_b.yaml  # press Y to save
```

### Programmatic Config

```python
from urkit import load_config, resolve_config

# Load with auto-resolution
config = load_config()  # searches for config.yaml
config = load_config("/path/to/my.yaml")  # explicit path

# Check if config exists
path = resolve_config()  # returns Path or None

# Create robot from config dict
robot = URRobot.from_config({"robot_ip": "172.31.1.200", "gripper": "2f-85"})
```

---

## Gripper Presets

Three built-in presets: pick one and it handles mass, CoG, TCP offset, and backend:

| Preset | Description |
|--------|-------------|
| `ROBOTIQ_HAND_E` | Robotiq 2F-140-E (Hand-E series) |
| `ROBOTIQ_2F_85` | Robotiq 2F-85 |
| `ROBOTIQ_2F_140` | Robotiq 2F-140 |

Or look up presets programmatically:

```python
from urkit import PRESETS

preset = PRESETS["HAND-E"]  # GripperPreset object
```

Call `activate()` before using the gripper: it resets and calibrates. You decide when:

```python
robot.gripper.activate()  # required before open/close (Robotiq only)
robot.gripper.is_activated()  # check activation state (Robotiq only)

robot.gripper.open()              # fully open (blocking by default)
robot.gripper.close()             # fully closed, stops on contact
robot.gripper.open(wait=False)    # non-blocking return
robot.gripper.set_position(20)    # 20mm open (Robotiq only, 0 = closed)
robot.gripper.set_force(50)       # grip force: 0-100
robot.gripper.set_speed(80)       # movement speed: 0-100
robot.gripper.deactivate()        # deactivate (Robotiq only)
```

Override preset values for custom fingers:

```python
robot = URRobot(ip="172.31.1.200", points="points.db", gripper=ROBOTIQ_HAND_E, max_mm=120)
```

### Digital I/O Grippers

For suction cups, solenoids, or custom actuators:

```python
from urkit import URRobot, DigitalGripperConfig

# Digital grippers are on/off: no activate(), set_position(), or set_force()
robot = URRobot(
    ip="172.31.1.200",
    points="points.db",
    gripper=DigitalGripperConfig(pin=3),
)

robot.gripper.open()    # turn pin off (release)
robot.gripper.close()   # turn pin on (grab)
```

---

## Working with Points

Points are managed through the robot object. Save positions with the teach pendant CLI, then reference them by name in your code.

The points database is optional — you can create a robot without one and set it later:

```python
robot = URRobot(ip="172.31.1.200")  # no points database
robot.points_db = "points.db"       # attach later
robot.points_db = None              # or remove it
```

Without a points database, moving to raw poses (`move_to([x, y, z, ...])`) and telemetry still work. Calling `move_to("name")` or `save_point()` will raise `PointError`.

### Moving to Points

```python
# Linear move (default): straight line in Cartesian space
robot.move_to("pick")

# Joint move: faster, robot picks shortest path in joint space
robot.move_to("pick", linear=False)

# Override velocity (m/s) and acceleration (m/s²) for a single move
robot.move_to("pick", vel=1.0, acc=0.5)
```

### Moving to Raw Poses

Skip the database and move to a raw TCP pose:

```python
# [x, y, z, rx, ry, rz] in meters and radians
robot.move_to([0.5, 0, 0.3, 0, 0, 0])
robot.move_to([0.5, 0, 0.3, 0, 0, 0], linear=False)
```

### Offsets

Apply an offset to any point without creating a new saved point:

```python
# offset=[dx, dy, dz, droll, dpitch, dyaw]: meters and radians
robot.move_to("pick", offset=[0, 0, 0.05, 0, 0, 0])  # 5cm above pick
robot.move_to("pick", offset=[0.02, 0, 0.1, 0, 0, 0])  # 2cm forward, 10cm up
```

### Coordinate Frame (BASE / TOOL)

Offsets and relative moves use a coordinate frame to determine the direction of movement. The robot has a default frame (BASE by default) that can be changed at any time:

```python
from urkit import MoveFrame

# Set the default frame for all offsets and relative moves
robot.move_frame = MoveFrame.TOOL

# Offset is now relative to the tool's current orientation
robot.move_to("pick", offset=[0, 0, 0.05])  # 5cm along tool Z

# Override per-call
robot.move_to("pick", offset=[0, 0, 0.05], frame=MoveFrame.BASE)
```

- **BASE** (default): offset/delta is relative to the robot base. +X always moves along the base X axis.
- **TOOL**: offset/delta is relative to the TCP orientation. +X moves along the tool's local X axis.

### Point Management

```python
# Save the current position
robot.save_point("here")

# List all saved points
names = robot.point_names()  # ["home", "pick", "place"]

# Rename a point
robot.rename_point("old", "new")

# Delete a point
robot.delete_point("old")

# Export / import points as JSON
robot.export_points("backup.json")
robot.import_points("backup.json")

# Access the points database directly
robot.points_db  # Points object (read-only)
robot.points_db = "other.db"  # swap to a different database
```

### Relative Moves

Move relative to the current position:

```python
# [dx, dy, dz, droll, dpitch, dyaw] in meters and radians
robot.move_relative([0, 0.01, 0, 0, 0, 0])  # 1cm along Y (base frame)
robot.move_relative([0, 0, 0.05], frame=MoveFrame.TOOL)  # 5cm along tool Z
```

### Sequences with Blending

Move through multiple waypoints with corner blending:

```python
# Move through waypoints, stopping at each one
robot.move_sequence(["a", "b", "c"])

# blend_radius rounds corners (in meters): robot doesn't stop at intermediate points
robot.move_sequence(["a", "b", "c"], blend_radius=0.02)

# Joint-space sequence with blending
robot.move_sequence(["a", "b", "c"], linear=False, blend_radius=0.05)
```

---

## Advanced Motion

### Contact Detection

Move until force contact is detected (Ctrl+C to stop):

```python
# Move down at 20mm/s until force changes by 5N (default threshold)
robot.move_until_contact([0, 0, -0.02, 0, 0, 0])

# Higher threshold for heavier contact
robot.move_until_contact([0, 0, -0.02, 0, 0, 0], threshold=10.0)
```

### Velocity Control

Move at a constant velocity for a given duration:

```python
# Move at constant velocity for a given duration (speedL under the hood)
robot.move_velocity([0, 0, -0.02, 0, 0, 0], duration=1.0)  # down at 20mm/s for 1s
```

### Freedrive Mode

Enable manual robot manipulation:

```python
from urkit import FreedriveMode

# Freedrive lets you manually push the robot: motion commands won't work while active
robot.enable_freedrive()              # all 6 axes free
robot.enable_freedrive(FreedriveMode.XYZ)      # linear axes + Rz rotation
robot.enable_freedrive(FreedriveMode.ROTATION) # rotation only
robot.disable_freedrive()             # always disable before sending motion commands

# Check if freedrive is active
robot.is_freedrive_active
```

### Speed Control

```python
# Emergency stop: halt all motion immediately
robot.speed_stop()

# Set speed slider (0.0–1.0): hardware-level velocity multiplier
robot.set_speed_slider(0.5)  # all motions run at 50% of their programmed speed
```

The speed slider is a **hardware-level multiplier** applied by the UR controller itself — it's the same mechanism as the physical slider on the teach pendant.

- **Velocity is scaled:** `actual_velocity = vel * slider_factor`
- **Acceleration is NOT independently scaled** — the raw `acc` value is passed through, but the controller constrains ramp-up to the capped velocity ceiling
- **Global & persistent** — stays until you change it or the robot faults/resets
- Affects all motion commands: moveJ, moveL, trajectory, delta moves, velocity control

```python
# Example: 0.5 slider × 1.0 m/s movej = 0.5 m/s actual speed
robot.set_speed_slider(0.5)
robot.movej([-1.0, -1.5, 1.5, -1.0, 1.0, 0.0], vel=1.0, acc=0.5)
```

```python
# Inverse kinematics: pose → joint angles
joints = robot.inverse_kinematics([0.5, 0, 0.3, 0, 0, 0])
```

## Telemetry

```python
# Read real-time robot state
pose = robot.get_tcp_pose()           # [x, y, z, rx, ry, rz]: meters/radians
joints = robot.get_joint_positions()  # [j0..j5]: radians
force = robot.get_tcp_force()         # [fx, fy, fz, mx, my, mz]: Newtons/Nm
mode = robot.get_robot_mode()         # "REMOTE_CONTROL", "SERVOING", etc.
scaling = robot.get_speed_scaling()   # actual vs programmed speed (0.0-1.0)
payload = robot.get_payload()         # configured payload mass (kg)
robot.is_protective_stopped()         # bool: robot hit something or was pushed
robot.is_emergency_stopped()          # bool: e-stop pressed

# Get current pose + joints as a dict
pos = robot.current_point()
print(pos["pose"])    # [x, y, z, rx, ry, rz]
print(pos["joints"])  # [j0, j1, j2, j3, j4, j5]
```

---

## Digital I/O

```python
# Set a single output (pins 0-7 standard, 8-15 configurable)
robot.set_digital_output(0, True)

# Set multiple outputs at once, or clear all
robot.set_digital_outputs({0: True, 1: False, 8: True})
robot.set_digital_outputs(False)

# Read inputs (pins 0-17, including tool pins 16-17)
robot.get_digital_input(0)
robot.get_analog_input(0)
robot.get_tool_input(0)

# Read outputs
robot.get_digital_output(0)
robot.get_analog_output(0)
robot.get_tool_output(0)

# Block until a digital input changes (useful for limit switches, sensors)
if not robot.wait_for_input(0, True, timeout=10.0):
    raise TimeoutError("Limit switch not triggered")
```

---

## Advanced: Raw RTDE Access

URKit doesn't try to wrap everything. For advanced features like `forceMode`, `servoJ`, `getActualCurrent`, and more, access the raw `ur_rtde` interfaces:

```python
# rtde_control and rtde_receive give you the full ur_rtde API
robot.rtde_control.moveUntilContact([0, 0, -0.02, 0, 0, 0])
robot.rtde_control.forceMode(...)
robot.rtde_control.servoJ(...)

# Read robot current, temperature, or anything ur_rtde exposes
robot.rtde_receive.getActualCurrent()
```

Full `ur_rtde` documentation: <https://sdurobotics.gitlab.io/ur_rtde/>

---

## Connection Lifecycle

```python
# Check if RTDE connection dropped
robot.connection_lost

# Reconnect RTDE after a drop
robot.reconnect_rtde()

# Disconnect and clean up
robot.disconnect()
```

---

## Error Handling

```python
from urkit import URKitError, RobotNotInRemoteModeError, RtdeRegisterConflictError

try:
    robot = URRobot(ip="172.31.1.200", points="points.db")
except RobotNotInRemoteModeError:
    print("Enable remote control on the teach pendant!")
except RtdeRegisterConflictError:
    print("Disable EtherNet/IP, PROFINET, or MODBUS!")
except URKitError as e:
    # Catch-all for any urkit error (connection, motion, gripper, etc.)
    print(f"Error: {e}")
```
