#!/usr/bin/env python3
"""
Demo 6: Force-based contact detection

Shows the robot approaching a surface and stopping on contact.
move_until_contact zeros the FT sensor automatically.

Teach panel prep:
  - Point "home" taught — positioned above a flat surface (table, workpiece)
    with clear path downward to the surface.
"""

from urkit import URRobot

robot = URRobot.from_config("config.yaml")

print("Moving to home...")
robot.move_to("home")

start_pose = robot.get_tcp_pose()
print(f"Starting Z: {start_pose[2] * 100:.1f} cm")

print("\nMoving down until contact (5N threshold)...")
print("Watch the robot stop when it touches the surface.\n")

# Moves 2cm/s downward, stops when force exceeds 5N.
# Zeros the FT sensor automatically before starting.
robot.move_until_contact(speed_z=-0.02, threshold=5.0)

contact_pose = robot.get_tcp_pose()
delta_cm = abs((contact_pose[2] - start_pose[2]) * 100)
print(f"\nContact detected after moving {delta_cm:.1f} cm down")
print(f"Table surface is at Z = {contact_pose[2] * 100:.1f} cm")

print("\nRetreating 5cm...")
robot.move_relative(delta_z=0.05)

print("\nMoving to home...")
robot.move_to("home")

print("\nDone! The robot adapted to the surface position.")
