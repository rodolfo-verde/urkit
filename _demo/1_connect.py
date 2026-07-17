#!/usr/bin/env python3
"""Demo 1: Connect and move to home — 2 lines of code."""

from urkit import URRobot

robot = URRobot.from_config("config.yaml")
robot.move_to("home", linear=False)
print("At home!")
