# URKit

[![PyPI](https://img.shields.io/pypi/v/urkit.svg)](https://pypi.org/project/urkit/)

**URKit** makes it easy to get a Universal Robots e-Series robot moving from Python.

## What it is

A thin layer over [`ur_rtde`](https://sdurobotics.gitlab.io/ur_rtde/) that handles the common stuff: connecting, teaching named points, moving between them, gripper control, telemetry. Raw RTDE interfaces are exposed for anything deeper.

No .urp files, no Dashboard API, no extra programs to run on the robot. Just connect over the network and go. Handles power-on, brake release, and RTDE setup in the constructor so you don't have to.

Comes with an interactive teach pendant CLI for positioning the robot and saving waypoints, plus a Python API for scripting motion, gripper control, I/O, and telemetry.

## When to use this

Projects where the robot is part of something bigger. Computer vision, machine learning, sensor fusion, data logging. If your project lives in Python, keep the robot control in Python too.

Built for labs and research setups where you need to get the robot moving fast and integrate it with other software. Not designed as a drop-in replacement for Polyscope in production cells, but perfectly capable for anything that runs from a PC.

## How it works

Use the CLI to position the robot and save named waypoints. Then reference them by name in your code: move to points, apply deltas, run sequences. Points are stored in a local SQLite database, no robot-side setup needed.

The typical workflow: teach points with the pendant, write a few lines of Python to string them together, run it. Add vision, add sensors, add logic. The robot is just one component in your pipeline.

---

## Table of Contents

- [Quick Start](#quick-start)
- [Configuration](#configuration)
  - [Create a Config File](#create-a-config-file)
  - [Location](#location)
  - [Keys](#keys)
  - [Gripper Config](#gripper-config)
  - [Saving Config](#saving-config)
  - [Programmatic](#programmatic)
- [Interactive CLI](#interactive-cli)
  - [Init](#init)
  - [Teach Mode](#teach-mode)
  - [Points Explorer](#points-explorer)
  - [Key Map](#key-map)
- [API Reference](#api-reference)
  - [Connecting](#connecting)
  - [Grippers](#grippers)
  - [Points & Motion](#points--motion)
  - [Telemetry](#telemetry)
- [More API](#more-api)
  - [Digital I/O](#digital-io)
  - [Geometry](#geometry)
  - [Robot Lifecycle](#robot-lifecycle)
- [Advanced](#advanced)
  - [Raw RTDE Access](#raw-rtde-access)
  - [Connection Lifecycle](#connection-lifecycle)
  - [Error Handling](#error-handling)
- [Changelog](#changelog)

---

## Quick Start

```bash
pip install -U urkit
```

The `-U` (upgrade) flag ensures you always get the latest version. This project is in early development and changes frequently.

Requires Python 3.8+ and a Universal Robots e-Series (UR3e to UR30).

### Platform Support

- **Linux, Windows**: fully supported. The interactive CLIs (`urkit teach`, `urkit points`) are tested on both platforms
- **macOS**: runs the same POSIX terminal code path as Linux (termios/select); there is no macOS-specific code

### Robot Setup (one-time)

1. **Network**: Connect your PC to the robot via Ethernet cable (direct) or a switch.

   First, configure the robot: `☰` → `System` → `System` → `Network`. Set a static IP, e.g., `192.168.1.50` / Subnet `255.255.255.0`.

   Then set a matching static IP on your PC. The exact IP can be anything, as long as the first three octets match the robot's network and the last octet is different:

   **Linux**:
   - Open `Settings` → `Network` → click the gear icon next to `Wired`
   - Go to `IPv4` tab → change `Automatic (DHCP)` to `Manual`
   - Enter Address: `192.168.1.1`, Netmask: `255.255.255.0`
   - Click `Apply`, then toggle the connection off and on

   **macOS**:
   - Open `System Settings` → `Network` → click `Ethernet` (or your adapter)
   - Click `Details...` next to the adapter name → `TCP/IP`
   - Set `Configure IPv4` to `Manually`
   - Enter IP: `192.168.1.1`, Subnet Mask: `255.255.255.0`
   - Click `OK`

   **Windows**:
   - Open `Settings` → `Network & internet` → `Ethernet`
   - Click the adapter name (e.g., `Ethernet`) at the top
   - Under `IP settings`, click `Edit` → select `Manual`
   - Toggle `IPv4` On, enter IP: `192.168.1.1`, Subnet mask: `255.255.255.0`
   - Click `Save`

   Verify connectivity: `ping 192.168.1.50`.
2. **Remote Control**: `☰` → `System` → `Remote Control`: Enable. Press the remote/local button on the pendant.
3. **Security**: `☰` → `Security` → `Services`: enable RTDE and disable EtherNet/IP, PROFINET, or MODBUS if they're claiming RTDE registers. Save and restart.

That's it. No `.urp` files to run, no extra programs needed.

### Example

If you have a Robotiq gripper, install the **Robotiq Gripper Control** URCap first: download from [robotiq.com/support](https://robotiq.com/support), copy the `.urcap` to a USB drive, and install via `☰` → `Settings` → `System` → `URCaps`.

```python
from urkit import URRobot, ROBOTIQ_HAND_E  # or ROBOTIQ_2F_85, ROBOTIQ_2F_140, ROBOTIQ_EPICK_SINGLE_S, or gripper=None

robot = URRobot(ip="192.168.1.50", points="points.db", gripper=ROBOTIQ_HAND_E)
robot.gripper.activate()

robot.move_to("home")
robot.move_to("pick", dz=0.05)  # 5cm above
robot.gripper.close()
robot.move_to("place")
robot.gripper.open()
```

The typical workflow:

1. **Scaffold config.** Run `urkit init` to create a default `config.yaml`.
2. **Edit it.** Set your robot IP, gripper type, and other settings.
3. **Teach points.** Run `urkit teach` (auto-loads config) to position the robot and save waypoints.
4. **Write code.** Load the config and move to points by name:

```python
from urkit import URRobot

robot = URRobot.from_config("config.yaml")
robot.move_to("home")
robot.move_to("pick", dz=0.05)
```

5. **Iterate.** Add more points, tweak your code, repeat.

---

## Configuration

URKit uses a YAML config file (`config.yaml`) to persist settings between sessions.

### Create a Config File

Generate a default config with all options documented:

```bash
urkit init                          # writes config.yaml in CWD
urkit init --output station_a.yaml  # custom path
urkit init --force                  # overwrite if exists
```

Edit the generated file with your robot IP and gripper settings.

### Location

The CLI auto-loads `config.yaml` from the current working directory. Pass `--config` for a custom path.

### Keys

| Key | Description | Example |
|-----|-------------|---------|
| `robot_ip` | Robot IP address | `192.168.1.50` |
| `points_path` | Path to SQLite points database | `points.db` |
| `gripper` | Gripper preset name | `hand-e`, `2f-85`, `2f-140`, `epick-single-s`, `digital` |
| `ik_reference` | IK reference posture (prevents elbow flipping) | `home` |
| `default_vel` | Default linear velocity (m/s) | `0.5` |
| `default_acc` | Default linear acceleration (m/s²) | `0.3` |
| `expert_mode` | Disable safety speed clamping | `false` |

### Gripper Config

Built-in preset with overrides:

```yaml
gripper: hand-e
gripper_config:
  force: 50
  speed: 80
```

Digital I/O gripper:

```yaml
gripper: digital
gripper_config:
  pin: 3
  close_on_high: true
```

Custom gripper (arbitrary payload + TCP offset, no backend):

```yaml
gripper:
  mass: 0.5
  center_of_gravity: [0.0, 0.0, 0.0]
  tcp_offset: [0.0, 0.0, 0.175, 0.0, 0.0, 0.0]
  backend: none
```

Override physical properties on a built-in preset:

```yaml
gripper: 2f-85
gripper_config:
  mass: 1.2
  center_of_gravity: [0.0, 0.0, 0.07]
  tcp_offset: [0.0, 0.0, 0.200, 0.0, 0.0, 0.0]
```

### CLI Override Precedence

1. **CLI flags.** `urkit teach 192.168.1.50 --gripper none`
2. **Config file.** Values from `config.yaml`
3. **Built-in defaults.** `points.db`, no gripper, 0.5 m/s velocity

### Saving Config

The CLI **never** modifies your config file automatically. Press **Y** inside the teach pendant to save. This way you only save settings you've actually tested.

```bash
urkit teach 192.168.1.50 --gripper hand-e  # test, then press Y
urkit teach                               # next time: reads from config
```

Multiple workcells:

```bash
urkit teach --config station_a.yaml   # press Y to save
urkit teach --config station_b.yaml   # separate config
```

### Programmatic

```python
from urkit import URRobot

robot = URRobot.from_config("config.yaml")
robot = URRobot.from_config("config.yaml", ip="10.0.0.50")  # override IP
robot = URRobot.from_config({"robot_ip": "192.168.1.50", "gripper": "2f-85"})  # dict, no file
```

---

## Interactive CLI

URKit provides three CLI tools: **init** to scaffold a config file, **teach** for interactive robot control, and **points** for browsing saved waypoints.

### Init

Generate a default config file with all options documented:

```bash
urkit init                          # writes config.yaml in CWD
urkit init --output station_a.yaml  # custom path
urkit init --force                  # overwrite if exists
```

### Teach Mode

The interactive teach pendant for moving the robot, saving points, and checking telemetry:

```bash
urkit teach 192.168.1.50             # with robot IP
urkit teach                          # reads IP from config.yaml
```

**Flags:**

| Flag | Description |
|------|-------------|
| `ip` | Robot IP address (positional, overrides config) |
| `--gripper` | Gripper preset: `2f-85`, `2f-140`, `hand-e`, `epick-single-s`, `digital`, `none` |
| `--gripper-pin` | Digital gripper output pin (default: 0) |
| `--gripper-force` | 2F grip force 0-100 (EPick: use `max_vacuum` in `gripper_config`) |
| `--gripper-speed` | 2F movement speed 0-100 (EPick: use `grip_timeout` in `gripper_config`) |
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
        <tr><td><code>6</code></td><td>Set speed / grip timeout</td></tr>
        <tr><td><code>7</code></td><td>Set force / max vacuum</td></tr>
      </table>
    </td>
    <td align="center" style="width:33%">
      <table>
        <tr><th>Key</th><th>Action</th></tr>
        <tr><td><code>B</code></td><td><strong>Save</strong> current position</td></tr>
        <tr><td><code>G</code></td><td>Go to saved point (<code>Space</code> to cancel mid-move, <code>ESC</code> to exit)</td></tr>
        <tr><td><code>H</code></td><td>Delete saved point</td></tr>
        <tr><td><code>P</code></td><td>Open points explorer</td></tr>
        <tr><td><code>R</code></td><td>Rename saved point</td></tr>
      </table>
    </td>
    <td align="center" style="width:34%">
      <table>
        <tr><th>Key</th><th>Action</th></tr>
        <tr><td><code>F</code></td><td>Freedrive toggle (ALL ↔ XYZ)</td></tr>
        <tr><td><code>3</code></td><td>Freedrive axis menu (toggle individual axes)</td></tr>
        <tr><td><code>M</code></td><td>Toggle frame (BASE / TOOL)</td></tr>
        <tr><td><code>N</code></td><td>Go To mode (Cartesian / Joint)</td></tr>
        <tr><td><code>T</code></td><td>Open TCP orient submenu (6 directions)</td></tr>
        <tr><td><code>Y</code></td><td>Save config to file</td></tr>
        <tr><td><code>ESC</code></td><td>Exit</td></tr>
      </table>
    </td>
  </tr>
</table>

### Joint Display

The teach pendant shows live joint angles alongside TCP position and orientation:

```
 Position (mm) X= +432.0  Y= +111.0  Z= +227.0
 Orientation   R= +131.3  P= -121.0  Y=  +8.0
 Joints        J1=+150.0  J2= +20.0  J3=+160.0
               J4= +50.0  J5= -80.0  J6=+157.0
```

Joint angles color-code proximity to mechanical limits:

- **Yellow**: within 10% of joint range (warning)
- **Red**: within 5% of joint range (danger)

UR e-Series joint limits:

| Joint | Range |
|-------|-------|
| J1 (shoulder pan) | ±360° |
| J2 (shoulder lift) | ±360° |
| J3 (elbow) | ±360° |
| J4 (wrist 1) | ±360° |
| J5 (wrist 2) | ±360° |
| J6 (wrist 3) | ±360° |



### Safety

By default, **Go To** and **TCP orient** movements use a slow velocity (0.125 m/s) so its safer for anyone standing near the robot. The user's speed slider still applies as a global multiplier on top of this.

Delta movements (W/S/A/D/Q/E) use step-size-based velocities that scale with the speed slider set by the user.

To disable the slow default and use full speed, pass `--expert` or set `expert_mode: true` in your config:

```bash
urkit teach 192.168.1.50 --expert
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

robot = URRobot(ip="192.168.1.50", points="points.db", gripper=ROBOTIQ_HAND_E)
```

With custom motion defaults:

```python
robot = URRobot(
    ip="192.168.1.50",
    points="points.db",
    gripper=ROBOTIQ_HAND_E,
    default_vel=0.5,    # m/s
    default_acc=0.3,    # m/s²
)
```

See [Configuration](#configuration) for `from_config()` usage.

The constructor takes a few seconds on first call: it validates the connection, checks remote mode, powers on the robot, releases brakes, and connects RTDE. Subsequent calls are faster if the robot is already running.

### Grippers

Built-in presets:

| Preset | Description |
|--------|-------------|
| `ROBOTIQ_HAND_E` | Robotiq Hand-E (2F-85-E) |
| `ROBOTIQ_2F_85` | Robotiq 2F-85 |
| `ROBOTIQ_2F_140` | Robotiq 2F-140 |
| `ROBOTIQ_EPICK_SINGLE_S/L` | EPick + 1 cup (S = Ø40, L = Ø55) |
| `ROBOTIQ_EPICK_DUAL_S/L` | EPick + 2-cup bracket (S = Ø40, L = Ø55) |
| `ROBOTIQ_EPICK_QUAD_S/L` | EPick + 4-cup bracket (S = Ø40, L = Ø55) |

```python
robot.gripper.activate()              # required before open/close (Robotiq only)
robot.gripper.deactivate()            # deactivate (Robotiq only)
robot.gripper.is_activated()          # check activation state

robot.gripper.open()                  # fully open (blocking by default)
robot.gripper.close()                 # fully closed, stops on contact
robot.gripper.open(wait=False)        # non-blocking return (waits for position)
robot.gripper.set_position_mm(20)     # 20mm open (Robotiq only, 0 = fully closed)
robot.gripper.set_position_percent(50) # 50% open (2F; repurposed on the EPick, see below)
robot.gripper.set_force(50)           # grip force: 0-100 (Robotiq only)
robot.gripper.set_speed(80)           # movement speed: 0-100 (Robotiq only)

robot.gripper.get_position_mm()       # last commanded position in mm
robot.gripper.max_travel_mm()         # max finger travel (e.g. 85.0 for 2F-85)
```

Override preset values for custom fingers:

```python
robot = URRobot(ip="192.168.1.50", points="points.db", gripper=ROBOTIQ_HAND_E, max_mm=120)
```

Override physical properties (e.g., custom fingers or added hardware change the weight):

```python
robot = URRobot(
    ip="192.168.1.50",
    points="points.db",
    gripper=ROBOTIQ_HAND_E,
    mass=1.2,                          # override preset mass
    center_of_gravity=[0.0, 0.0, 0.07], # override CoG
    tcp_offset=[0.0, 0.0, 0.180, 0, 0, 0],  # override TCP offset
)
```

#### Digital I/O Grippers

Robotiq grippers use a serial protocol over the robot's RS485 port. If you have a suction cup, solenoid, or any actuator controlled by a single digital output pin, use `DigitalGripperConfig` instead. It just turns that pin on (close) and off (open).

```python
from urkit import URRobot, DigitalGripperConfig

robot = URRobot(
    ip="192.168.1.50",
    points="points.db",
    gripper=DigitalGripperConfig(pin=3),  # pin 3 goes high = close
)

robot.gripper.open()    # turn pin 3 off
robot.gripper.close()   # turn pin 3 on
```

`set_force()` and `set_speed()` are not available for digital grippers.

#### EPick Vacuum Gripper

The EPick presets drive a Robotiq EPick vacuum gripper (e-Series only) over the same RS485 Robotiq protocol as the 2F series, using the legacy Robotiq ASCII commands. They require the **Robotiq Gripper Control** URCap installed (same setup as the 2F presets).

The semantics are inverted compared to the 2F grippers:

```python
robot.gripper.activate()          # required before open/close
robot.gripper.close()             # grip: pump on, wait until an object is secured
robot.gripper.open()              # release: pump off + blow-off, wait until the object is gone
```

`close()` does not return until the gripper has confirmed a secured object (see Detection below), and raises `GripperError` if no object is detected within the grip timeout. A failed grip leaves the vacuum on, so call `open()` to release before moving again. `open()` waits until the vacuum is lost (the object has dropped).

Grip parameters (set at connect time, or changed between grips):

```python
robot.gripper.set_max_vacuum(60)    # max vacuum level, 20-100% (default 60, the Robotiq URCap default)
robot.gripper.set_min_vacuum(40)    # min vacuum level, 10% up to the max vacuum (default 40)
robot.gripper.set_grip_timeout(30)  # grip timeout in 100 ms units, 0-100 (default 30 = 3 s)
```

The ranges are enforced at construction and on every setter (max 20-100, min 10 up to the current max, timeout 0-100), and a parameter of one backend passed to another raises `GripperError` instead of being ignored (`force`/`speed` on the EPick, `max_vacuum`/`grip_timeout` on the 2F). The same names work in `config.yaml`:

```yaml
gripper: epick-single-s
gripper_config:
  max_vacuum: 70
  grip_timeout: 40
```

With `set_max_vacuum(100)` the pump runs continuously and the gripper cannot confirm a grip; keep the max vacuum below 100% (60 works for typical cups and trays). The same physics applies at lower levels: if the max vacuum is higher than a leaky seal can reach, the pump keeps hunting and never enters the stable hold phase where the secured flag appears, so the grip times out (verified: a marginal-seal object gripped at 60/40 but timed out at 80/50 and 80/30). For leaky seals keep `max_vacuum` low and `min_vacuum` at or below what the seal sustains, not the other way around.

`set_position_mm()`, `get_position_mm()`, and `max_travel_mm()` are not available: the EPick has no finger travel. `set_position_percent(p)` is repurposed as a manual vacuum override: `p=0` releases, `1-100` grips at that vacuum level (bypassing the secured-object wait).

**Payload and TCP.** The bare generator body is 0.706 kg, CoG `[0, 0, 0.0515]`, TCP `[0, 0, 0.113, 0, 0, 0]` (Robotiq EPick manual, Table 6-4); cups and brackets change all three. The kits ship cups in two sizes (Ø 40 mm and Ø 55 mm), so there is one preset per bracket system + cup size (configurations without cups cannot grip and have no preset):

| Preset | Config / CLI name | Setup |
|--------|-------------------|-------|
| `ROBOTIQ_EPICK_SINGLE_S` | `epick-single-s` | 1 small (Ø40) cup on the generator port |
| `ROBOTIQ_EPICK_SINGLE_L` | `epick-single-l` | 1 large (Ø55) cup on the generator port |
| `ROBOTIQ_EPICK_DUAL_S` | `epick-dual-s` | 2-cup bracket, small cups |
| `ROBOTIQ_EPICK_DUAL_L` | `epick-dual-l` | 2-cup bracket, large cups |
| `ROBOTIQ_EPICK_QUAD_S` | `epick-quad-s` | 4-cup bracket, small cups |
| `ROBOTIQ_EPICK_QUAD_L` | `epick-quad-l` | 4-cup bracket, large cups |

```python
from urkit import URRobot, ROBOTIQ_EPICK_SINGLE_S

robot = URRobot(ip="192.168.1.50", gripper=ROBOTIQ_EPICK_SINGLE_S)
```

The TCP z of each preset is the bottom of the cups, the limiting point for approach moves. The presets use the manual's Table 6-4 for the body and bracket stack, and the official Festo datasheets for the cups Robotiq ships (VASB-40-1/4-PUR-B: 30 g / 32 mm, VASB-55-1/4-PUR-B: 39 g / 39 mm); all-small combinations reproduce Table 6-4 exactly:

| Preset | Mass (kg) | CoG z (m) | TCP z (m) |
|--------|-----------|-----------|-----------|
| body only (reference) | 0.706 | 0.0515 | 0.113 |
| `ROBOTIQ_EPICK_SINGLE_S` | 0.736 | 0.0547 | 0.145 |
| `ROBOTIQ_EPICK_SINGLE_L` | 0.745 | 0.0557 | 0.152 |
| `ROBOTIQ_EPICK_DUAL_S` | 1.116 | 0.0819 | 0.196 |
| `ROBOTIQ_EPICK_DUAL_L` | 1.134 | 0.0837 | 0.203 |
| `ROBOTIQ_EPICK_QUAD_S` | 1.341 | 0.0920 | 0.196 |
| `ROBOTIQ_EPICK_QUAD_L` | 1.377 | 0.0947 | 0.203 |

Bracket mass is derived (±15 g) and the Ø55 height is CAD-derived (±2 mm); if your setup is critical, measure the actual stack and pass `mass` / `center_of_gravity` / `tcp_offset` overrides, which still work:

```python
robot = URRobot(
    ip="192.168.1.50",
    gripper=ROBOTIQ_EPICK_SINGLE_S,
    mass=0.74,
    tcp_offset=[0.0, 0.0, 0.147, 0.0, 0.0, 0.0],
)
```

**Detection.** The EPick runs in advanced mode (rMOD=1): the pump reaches the max vacuum level, stops, and the vacuum decays back to the min level. An object is only "secured" while the vacuum is actually held there, so `close()` returns as soon as that secured state is observed on the gripper's object flag. With nothing under the suction cup the vacuum collapses and the secured state never occurs, so `close()` times out and raises `GripperError` after the grip timeout (set via `grip_timeout`). In automatic mode (rMOD=0) the EPick reports a short "seemingly constant" vacuum as an object, which false-positives with no object on the cup, so urkit does not use it.

### Points & Motion

The points database is optional. Create a robot without one and attach later:

```python
robot = URRobot(ip="192.168.1.50")
robot.points_db = "points.db"
```

#### Moving to Points

```python
robot.move_to("pick")                      # linear move (default)
robot.move_to("pick", linear=False)        # joint move
robot.move_to("pick", vel=1.0, acc=0.5)    # override speed
robot.move_to("pick", asynchronous=True)   # non-blocking, returns immediately
robot.move_to([0.5, 0, 0.3, 0, 0, 0])      # raw pose (no points DB needed)
```

- **Linear (moveL):** TCP moves in a straight line. Predictable path, slower near complex orientations.
- **Joint (moveJ):** Each joint moves simultaneously. Faster, but the TCP follows an arc.
- **Asynchronous:** When `asynchronous=True`, the move runs in the UR controller's background thread and the method returns immediately.

#### Non-Blocking Moves

Start a move and do other things while it runs:

```python
robot.move_to("pick", asynchronous=True)

# Poll until done
while robot.is_moving():
    time.sleep(0.01)

# Or cancel mid-move (see [Speed Control](#speed-control) for `stop()`)
robot.move_to("pick", asynchronous=True)
while robot.is_moving():
    if should_cancel:
        robot.stop()
        break
    time.sleep(0.01)
```

**Teach pendant Go To** uses this pattern internally. Space cancels the move and returns to the menu.

#### Pose Format

A pose is `[x, y, z, rx, ry, rz]`: position in meters and orientation as a **rotation vector** (axis-angle in radians). This is not RPY (roll/pitch/yaw). The teach pendant displays RPY in degrees, which is a different representation. Values you see on the pendant won't match `get_current_point()` directly.

#### Deltas

Deltas can use individual parameters or a full 6-element list:

```python
robot.move_to("pick", dz=0.05)  # 5cm above
robot.move_to("pick", dx=0.01, dz=-0.02)  # combined
robot.move_to("pick", delta=[0, 0, 0.05, 0, 0.1, 0])  # full with rotation
```

#### Resolve a Pose

Get a pose without moving. Useful for logging, comparisons, or custom motion:

```python
point = robot.get_point("pick")
point = robot.get_point("pick", delta=[0, 0, 0.05, 0, 0, 0])  # with delta
robot.move_to(pose)  # move to the resolved pose later
```

#### Coordinate Frame

```python
from urkit import MoveFrame

robot.move_frame = MoveFrame.TOOL   # default is BASE
robot.move_relative(dz=0.05)  # 5cm along tool Z
```

- **BASE** (default): delta relative to robot base
- **TOOL**: delta relative to TCP orientation

#### IK Reference

**Problem:** When the robot has multiple valid joint configurations to reach the same TCP pose (e.g., elbow up vs. elbow down), it can unexpectedly flip its posture between moves. This is called an **IK ambiguity** and it causes "weird" movements where the robot takes a strange path or flips its wrist.

**Solution:** Set an **IK reference posture**, a saved point that defines your preferred arm configuration. The robot then stays close to that posture for all moves.

```python
# 1. Put the robot in your preferred posture (e.g., "home")
# 2. Save it: robot.save_point("home")
# 3. Set as IK reference:
robot.ik_reference = "home"

# Now all moves stay close to that posture, no elbow flipping
robot.move_to("pick")
robot.move_to("place")
robot.move_relative(dz=-0.05)
```

**In config.yaml** (recommended for permanent setup):

```yaml
robot_ip: 192.168.1.50
ik_reference: home    # prevents weird elbow/wrist flips
```

**How it works:** The robot's inverse kinematics solver uses the reference posture as a bias (`qnear`). The TCP still reaches the exact same pose, but the arm configuration (elbow up/down, wrist orientation) stays consistent with your reference. Under the hood, poses are resolved to joint angles and sent as `moveJ` instead of `moveL`.

**Per-move override:**

```python
robot.ik_reference = "home"                    # global default
robot.move_to("weird_pose", ik_reference=None) # one move without it
robot.move_to("back", ik_reference="current") # use current joints
```

**When to use it:**

- **Use it** for sequences of positional moves between waypoints: pick/place paths, assembly sequences, anything where the robot travels between distant points. It prevents elbow/wrist flipping.
- **Don't use it** for rotation-heavy movements (orientation adjustments, fine-tuning angles). The `qnear` seed can push joints into unexpected configs for pure rotations, and you lose the controller's native Cartesian trajectory planner (lookahead, smoothing). Set `ik_reference=None` for these moves.

Default is `None` (controller handles IK natively). Set it globally when most of your moves are positional, and override per-move when you need rotations.

#### Point Management

Points are stored as absolute TCP poses in the robot base frame. When you move to a point, the controller moves whatever TCP is currently active to that base-frame pose, so the tool tip lands at the same physical location. Change the TCP offset (or swap grippers) and your saved points stay valid.

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
robot.move_relative(dy=0.01)  # 1cm along Y
robot.move_relative(dz=0.05, frame=MoveFrame.TOOL)  # 5cm along tool Z
robot.move_relative([0, 0.01, 0, 0, 0, 0])  # full 6-element delta
```

Individual delta parameters (`dx`, `dy`, `dz`, `drx`, `dry`, `drz`) are mutually exclusive with the `delta` list. Use one or the other.

#### Sequences

```python
# Both styles work:
robot.move_sequence("a", "b", "c")          # variadic
robot.move_sequence(["a", "b", "c"])        # list
```

`move_sequence` builds a path from all targets and executes it in a single call with blending. Requires at least 2 targets. Two modes:

**With `ik_reference`** (positional paths): All poses resolve to joints using chained inverse kinematics. The first pose resolves relative to the reference, the second relative to the first's resolved joints, and so on. Executed as a single `moveJ(path)` call. Keeps the arm configuration consistent (no elbow flipping):

```python
robot.ik_reference = "home"
robot.move_sequence(["a", "b", "c"], blend_radius=0.02)  # 2cm blend
```

**Without `ik_reference`** (Cartesian path): Builds a blended `moveL(path)`. The controller handles IK natively, better for rotation-heavy sequences where `ik_reference` causes unexpected joint behavior:

```python
robot.move_sequence(["a", "b", "c"], blend_radius=0.02)  # blended Cartesian path
```

Before sending any move, it checks that each pose has a valid IK solution. Unreachable poses raise `MotionError`. If a named point doesn't exist, it raises `PointError` instead of silently falling back.

#### Contact Detection

```python
# Move straight down until contact (zeros FT sensor automatically)
robot.move_until_contact(vz=-0.02)

# Custom threshold (default: 5.0 N/Nm)
robot.move_until_contact(vz=-0.02, threshold=10.0)

# Skip zeroing if you need absolute force values
robot.move_until_contact(vz=-0.02, zero_first=False)

# Full speed vector
robot.move_until_contact([0, 0, -0.02, 0, 0, 0])

# Abort after 10s or 200mm of travel, whichever comes first
robot.move_until_contact(vz=-0.02, timeout=10.0, max_distance=0.2)

# Returns True if contact detected, False if timeout/max_distance hit
for _ in range(3):
    if robot.move_until_contact(vz=-0.02, timeout=10.0, max_distance=0.2):
        break  # contact detected
    # No contact, back off and retry
    robot.move_relative(dz=0.01)

# Manual zero (e.g. before custom force-based logic)
robot.zero_ft_sensor()
```

#### Velocity Control

```python
robot.move_velocity([0, 0, -0.02, 0, 0, 0], duration=1.0)
```

#### Freedrive Mode

```python
from urkit import FreedriveMode

robot.enable_freedrive()              # all 6 axes free
robot.enable_freedrive(FreedriveMode.XYZ)      # linear axes only (X, Y, Z)
robot.enable_freedrive(FreedriveMode.ROTATION) # rotation only (Roll, Pitch, Yaw)
robot.enable_freedrive([1, 1, 1, 1, 0, 0])    # custom: X+Y+Z+Roll+Pitch
robot.disable_freedrive()             # disable before sending motion commands
robot.is_freedrive_active             # check state
```

**Teach pendant:** Press `F` to toggle freedrive (ALL ↔ XYZ). Press `3` to open the axis selection menu arrow keys navigate, space toggles each axis on/off, enter applies.

#### Speed Control

```python
robot.stop()                          # stop current move immediately (stopL + stopJ)
robot.speed_stop()                    # stop velocity-controlled motion (not E-stop)
robot.speed_slider = 0.5           # 50% velocity cap
robot.speed_slider              # read current slider (0.0-1.0)
```

The speed slider controls the pendant's speed multiplier. It's global, persistent, and affects all motion commands.

#### Changing Default Speed & Acceleration

Override the constructor defaults at runtime. All subsequent moves pick up the new values:

```python
robot.default_vel = 0.1   # slow for precision work
robot.move_to("insert")
robot.default_vel = 0.5   # back to normal

robot.default_acc = 0.05    # gentle acceleration

robot.default_vel      # read current velocity (m/s)
robot.default_acc      # read current acceleration (m/s²)
```

#### Inverse Kinematics

```python
joints = robot.inverse_kinematics([0.5, 0, 0.3, 0, 0, 0])
```

### Telemetry

```python
pose = robot.get_current_point()           # [x, y, z, rx, ry, rz]
pose = robot.get_current_point(dz=0.05)  # with delta
joints = robot.get_joint_positions()       # [j0..j5]
force = robot.get_tcp_force()              # [fx, fy, fz, mx, my, mz]
mode = robot.get_robot_mode()              # "REMOTE_CONTROL", "SERVOING", etc.
payload = robot.payload                    # kg
robot.is_protective_stopped()              # bool
robot.is_emergency_stopped()               # bool
```

#### Arrival Detection

`is_moving()` tracks the target pose or joints stored by `move_to()` and compares against the current position. Returns `False` when within tolerance:

```python
robot.move_to("pick", asynchronous=True)

# Wait until arrived (default tolerances: 2mm position, ~2° orientation)
while robot.is_moving():
    time.sleep(0.01)

# Tighter tolerances
while robot.is_moving(position_tolerance=0.001, orientation_tolerance=0.017):
    time.sleep(0.01)

# Joint moves, tighter joint tolerance
while robot.is_moving(joint_tolerance=0.001):
    time.sleep(0.01)
```

For joint-space moves (when `ik_reference` is active or `linear=False`), `is_moving()` compares joint angles. For Cartesian moves, it compares TCP pose. When no target is set (e.g., after a relative move without `move_to`), it returns `False`.

---

## More API

Less common but useful when you need them.

### Digital I/O

Pins 0–7 are standard, 8–15 configurable, 16–17 tool.

```python
# Outputs
robot.set_digital_output(0, True)
robot.set_digital_outputs({0: True, 1: False, 8: True})
robot.set_digital_outputs(False)      # clear all pins 0–15
robot.get_digital_output(0)           # read back output state

# Inputs
robot.get_digital_input(0)
robot.wait_for_input(0, True, timeout=10.0)  # block until pin 0 goes high

# Analog
robot.get_analog_input(0)             # read analog input (pin 0–1)
robot.get_analog_output(0)            # read analog output (pin 0–1)

# Tool I/O
robot.get_tool_input(0)               # tool digital input (pin 0–1)
robot.get_tool_output(0)              # tool digital output (pin 0–1)
```

### Geometry

Conversion utilities for rotation vectors, quaternions, and RPY angles (rxyz convention, same as UR teach pendant):

```python
from urkit import (
    orient_tcp,
    orient_tcp_down,
    quat_to_rotvec,
    quat_to_rpy,
    rpy_to_quat,
    rotvec_to_quat,
)

# Orient TCP along an arbitrary direction (minimal rotation)
new_pose = orient_tcp(current_pose, [0, 0, -1])  # point down
new_pose = orient_tcp(current_pose, [1, 0, 0])   # point forward

# Orient TCP straight down (convenience wrapper)
new_pose = orient_tcp_down(current_pose)

# Rotation conversions
q = rotvec_to_quat([0, 0, 1.57])   # rotvec → quaternion (x, y, z, w)
rv = quat_to_rotvec(q)              # quaternion → rotvec
rpy = quat_to_rpy(q)                # quaternion → RPY (radians)
q = rpy_to_quat(0, 0, 1.57)        # RPY → quaternion
```

### Robot Lifecycle

Manual power and brake control via the Dashboard:

```python
robot.power_on()          # power on (skips if already on)
robot.release_brakes()    # release brakes (enable control)
robot.recover()           # clear protective stop
robot.power_off()         # power off
```

The constructor handles all of this automatically. Use these methods when you need fine-grained control (e.g., recovering from a safety stop without recreating the robot).

TCP and payload can be set manually (gripper presets do this automatically):

```python
robot.tcp_offset = [0, 0, 0.15, 0, 0, 0]
robot.set_payload(1.5, [0, 0, 0.05])  # mass (kg), center of gravity [x, y, z]
```

Clean shutdown:

```python
robot.disconnect()  # close RTDE, Dashboard, points DB, gripper
```

`disconnect()` is called automatically on garbage collection. Call it explicitly to release resources immediately.

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
```

An RTDE drop is fatal for the session: urkit raises and the CLI exits.
Restart `urkit` (or create a new `URRobot`) to reconnect. urkit
deliberately does not auto-reconnect mid-session: a silent reconnect
hides what happened to the link and lets the native layer resynchronize
state behind your back.

**What happens when the link drops mid-session** (verified by
force-dropping the network with Windows firewall rules):

- **Before a motion call**: every motion command checks the link first
  and raises `URKitConnectionError` immediately. This matters because a
  call into the native layer on a dead link would not return an error:
  the vendored `ur_rtde` library enters its own internal reconnect
  loop and blocks indefinitely (measured: 45 s+ and still hanging
  under a firewall block).
- **While a motion is running**: the CLI's connection monitor detects
  the drop within ~0.1 s and exits cleanly (interrupt watcher on
  Windows, SIGALRM on Unix). In library code, an in-flight call can
  block inside the native reconnect loop; kill the process and restart.
- **After a hard drop**: the robot can keep the RTDE registers locked
  until the dead connection times out. If a fresh connect fails with
  `RtdeRegisterConflictError`, power cycle the controller (dashboard
  `power off` / `power on` works remotely; or Settings -> System ->
  Shutdown on the pendant), then reconnect.

### Error Handling

```python
from urkit import URKitError, MotionError, PointError

try:
    robot = URRobot(ip="192.168.1.50", points="points.db")
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

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for the full version history.
