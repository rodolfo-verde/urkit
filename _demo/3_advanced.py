#!/usr/bin/env python3
"""
Demo 3: Full cycle with approach points and sequences

Same pick-and-place as demo 2 but using:
  - get_pose() — resolve named points with offsets
  - move_sequence() — chain moves into one call
  - get_tcp_pose() — live telemetry
"""

from urkit import URRobot

robot = URRobot.from_config("config.yaml")

print("Moving to home...")
robot.move_to("home")

print("Activating gripper...")
robot.gripper.activate()
robot.gripper.open()

# --- Resolve approach points with offsets ---
pick_above = robot.get_pose("pick", offset_z=0.05)
place_above = robot.get_pose("place", offset_z=0.05)

# --- PICK ---
print("\n--- PICK ---")
robot.move_sequence(["home", pick_above, "pick"])

print("Closing gripper...")
robot.gripper.close()

# --- PLACE ---
print("\n--- PLACE ---")
robot.move_sequence([pick_above, place_above, "place"])

tcp = robot.get_tcp_pose()
print(f"TCP at place: [{tcp[0]:.3f}, {tcp[1]:.3f}, {tcp[2]:.3f}]")

print("Opening gripper...")
robot.gripper.open()

# --- RETURN HOME ---
print("\nMoving to home...")
robot.move_sequence([place_above, "home"])

# --- PICK BACK UP ---
print("\n--- PICK BACK UP ---")
robot.move_sequence(["home", place_above, "place"])

print("Closing gripper...")
robot.gripper.close()

# --- BRING BACK ---
print("\n--- BRING BACK ---")
robot.move_sequence([place_above, pick_above, "pick"])

print("Opening gripper...")
robot.gripper.open()

# --- DONE ---
print("\nMoving to home...")
robot.move_sequence([pick_above, "home"])

print("\nDone! Full cycle complete.")
