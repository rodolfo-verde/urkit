#!/usr/bin/env python3
"""
Demo 7: Real-time force/torque monitor (GUI)

Shows live force and torque readings on all 6 axes in a window.
Close the window or press Ctrl+C to stop.

Demonstrates full access to the robot's force/torque sensor.
"""

import tkinter as tk
import threading
import time

from urkit import URRobot


class ForceMonitor:
    """Simple GUI that displays live force/torque readings."""

    def __init__(self, robot: URRobot):
        self.robot = robot
        self.running = True

        # Zero the sensor
        robot.zero_ft_sensor()
        time.sleep(0.1)

        # Create window
        self.root = tk.Tk()
        self.root.title("Force/Torque Monitor")
        self.root.geometry("500x300")
        self.root.resizable(False, False)

        # Title
        title = tk.Label(
            self.root, text="FORCE / TORQUE", font=("Helvetica", 16, "bold")
        )
        title.pack(pady=(15, 5))

        # Force frame
        force_frame = tk.Frame(self.root)
        force_frame.pack(pady=5)

        tk.Label(force_frame, text="Force (N)", font=("Helvetica", 11, "bold")).grid(
            row=0, column=0, padx=15
        )
        tk.Label(force_frame, text="Torque (Nm)", font=("Helvetica", 11, "bold")).grid(
            row=0, column=2, padx=15
        )

        tk.Label(force_frame, text="Fx", font=("Helvetica", 9)).grid(
            row=1, column=0, padx=15, sticky="e"
        )
        tk.Label(force_frame, text="Fy", font=("Helvetica", 9)).grid(
            row=2, column=0, padx=15, sticky="e"
        )
        tk.Label(force_frame, text="Fz", font=("Helvetica", 9)).grid(
            row=3, column=0, padx=15, sticky="e"
        )

        tk.Label(force_frame, text="Tx", font=("Helvetica", 9)).grid(
            row=1, column=2, padx=15, sticky="e"
        )
        tk.Label(force_frame, text="Ty", font=("Helvetica", 9)).grid(
            row=2, column=2, padx=15, sticky="e"
        )
        tk.Label(force_frame, text="Tz", font=("Helvetica", 9)).grid(
            row=3, column=2, padx=15, sticky="e"
        )

        # Value labels (large font for projector)
        self.fx_label = tk.Label(
            force_frame, text="0.0", font=("Helvetica", 20), width=8, anchor="e"
        )
        self.fx_label.grid(row=1, column=1, padx=10)
        self.fy_label = tk.Label(
            force_frame, text="0.0", font=("Helvetica", 20), width=8, anchor="e"
        )
        self.fy_label.grid(row=2, column=1, padx=10)
        self.fz_label = tk.Label(
            force_frame, text="0.0", font=("Helvetica", 20), width=8, anchor="e"
        )
        self.fz_label.grid(row=3, column=1, padx=10)

        self.tx_label = tk.Label(
            force_frame, text="0.00", font=("Helvetica", 20), width=8, anchor="e"
        )
        self.tx_label.grid(row=1, column=3, padx=10)
        self.ty_label = tk.Label(
            force_frame, text="0.00", font=("Helvetica", 20), width=8, anchor="e"
        )
        self.ty_label.grid(row=2, column=3, padx=10)
        self.tz_label = tk.Label(
            force_frame, text="0.00", font=("Helvetica", 20), width=8, anchor="e"
        )
        self.tz_label.grid(row=3, column=3, padx=10)

        # Status
        self.status = tk.Label(
            self.root, text="Reading...", font=("Helvetica", 9), fg="gray"
        )
        self.status.pack(pady=10)

        # Close button
        close_btn = tk.Button(
            self.root, text="Close", command=self.close, font=("Helvetica", 11)
        )
        close_btn.pack(pady=5)

    def close(self):
        self.running = False
        self.root.quit()

    def update(self):
        """Update readings in background thread."""
        while self.running:
            try:
                wrench = self.robot.get_tcp_force()
                fx, fy, fz = wrench[0], wrench[1], wrench[2]
                tx, ty, tz = wrench[3], wrench[4], wrench[5]

                self.root.after(
                    0,
                    self._set_labels,
                    f"{fx:+.1f}",
                    f"{fy:+.1f}",
                    f"{fz:+.1f}",
                    f"{tx:+.2f}",
                    f"{ty:+.2f}",
                    f"{tz:+.2f}",
                )
            except Exception:
                break
            time.sleep(0.5)  # Update every 0.5s

    def _set_labels(self, fx, fy, fz, tx, ty, tz):
        self.fx_label.config(text=fx)
        self.fy_label.config(text=fy)
        self.fz_label.config(text=fz)
        self.tx_label.config(text=tx)
        self.ty_label.config(text=ty)
        self.tz_label.config(text=tz)

    def run(self):
        # Start background thread for readings
        thread = threading.Thread(target=self.update, daemon=True)
        thread.start()

        # Run GUI
        self.root.mainloop()


def main():
    robot = URRobot.from_config("config.yaml")

    print("Moving to home...")
    robot.move_to("home")

    print("Opening force monitor window...")
    monitor = ForceMonitor(robot)
    monitor.run()

    print("Done.")


if __name__ == "__main__":
    main()
