#!/usr/bin/env python3
"""
Demo 2: Complete pick-and-place cycle

Full cycle:
  1. Pick object from pick location
  2. Place it at place location
  3. Return home
  4. Pick it back up from place location
  5. Bring it back to original pick location

Shows the proper approach pattern with Z offsets to avoid collisions.
"""

from urkit import URRobot

robot = URRobot.from_config("config.yaml")
robot.gripper.activate()

print("Moving to home...")
robot.move_to("home")

# --- PICK ---
print("\n--- PICK ---")
print("Approaching pick (5cm above)...")
robot.move_to("pick", offset_z=0.05)

print("At pick position...")
robot.move_to("pick")

print("Closing gripper...")
robot.gripper.close()

print("Retracting...")
robot.move_to("pick", offset_z=0.05)

# --- PLACE ---
print("\n--- PLACE ---")
print("Approaching place (5cm above)...")
robot.move_to("place", offset_z=0.05)

print("At place position...")
robot.move_to("place")

print("Opening gripper...")
robot.gripper.open()

print("Retracting...")
robot.move_to("place", offset_z=0.05)

# --- RETURN HOME ---
print("\nMoving to home...")
robot.move_to("home")

# --- PICK BACK UP ---
print("\n--- PICK BACK UP ---")
print("Approaching place (5cm above)...")
robot.move_to("place", offset_z=0.05)

print("At pick position...")
robot.move_to("place")

print("Closing gripper...")
robot.gripper.close()

print("Retracting...")
robot.move_to("place", offset_z=0.05)

# --- BRING BACK ---
print("\n--- BRING BACK ---")
print("Approaching pick (5cm above)...")
robot.move_to("pick", offset_z=0.05)

print("At place position...")
robot.move_to("pick")

print("Opening gripper...")
robot.gripper.open()

print("Retracting...")
robot.move_to("pick", offset_z=0.05)

# --- DONE ---
print("\nMoving to home...")
robot.move_to("home")

print("\nDone! Full cycle complete.")
