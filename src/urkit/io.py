"""Digital I/O operations for Universal Robots e-Series.

Reads and writes digital I/O signals via the RTDE IO and
receive interfaces. All pins are addressed by their hardware
number (0–17) — no separate "standard" vs "configurable" methods.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Union

import time
from urkit.exceptions import URKitIOError as IOError

if TYPE_CHECKING:
    from rtde_io import RTDEIOInterface
    from rtde_receive import RTDEReceiveInterface

logger = logging.getLogger(__name__)


class IO:
    """Digital I/O operations via RTDE.

    Wraps the RTDE interfaces with typed, documented accessors for
    digital I/O signals. All methods raise IOError on failure.

    Pins are addressed by their hardware number:
    - 0–7: standard digital I/O
    - 8–15: configurable digital I/O
    - 16–17: tool digital I/O

    Args:
        rtde_io: RTDEIOInterface instance (for setting outputs).
        rtde_receive: RTDEReceiveInterface instance (for reading inputs/outputs).

    Example:
        >>> io = IO(rtde_io, rtde_r)
        >>> io.set_digital_output(0, True)
        >>> io.set_digital_outputs({0: True, 1: False, 8: True})
        >>> value = io.get_digital_output(0)
    """

    def __init__(
        self,
        rtde_io: "RTDEIOInterface",
        rtde_receive: "RTDEReceiveInterface",
    ) -> None:
        self._rtde_io = rtde_io
        self._rtde_r = rtde_receive

    # ── Digital Outputs ────────────────────────────────────────────

    def set_digital_output(self, pin: int, value: bool) -> None:
        """Set a digital output pin.

        Args:
            pin: Digital output pin index (0–15 on e-Series).
                Pins 0–7 are standard, 8–15 are configurable.
            value: True to set high, False to set low.

        Raises:
            IOError: If the pin is invalid or the operation fails.
        """
        if not isinstance(value, bool):
            raise IOError(
                f"Digital output value must be bool, got {type(value).__name__}."
            )
        if not 0 <= pin <= 15:
            raise IOError(
                f"Digital output pin must be 0–15, got {pin}. "
                "Pins 0–7 are standard, 8–15 are configurable."
            )
        try:
            if pin < 8:
                self._rtde_io.setStandardDigitalOut(pin, value)
            else:
                self._rtde_io.setConfigurableDigitalOut(pin - 8, value)
        except Exception as e:
            raise IOError(
                f"Failed to set digital output {pin} to {value}: {e}"
            )

    def set_digital_outputs(
        self, values: Union[bool, dict[int, bool]]
    ) -> None:
        """Set multiple digital outputs at once.

        Pass a dict of ``{pin: value}`` pairs, or a single bool
        to set all pins 0–15 to the same value.

        Args:
            values: Dict mapping pin numbers to bool values,
                or a single bool to apply to all pins.

        Raises:
            IOError: If any pin is invalid or the operation fails.

        Example:
            >>> # Set specific pins
            >>> io.set_digital_outputs({0: True, 1: False, 8: True})
            >>> # Clear all outputs
            >>> io.set_digital_outputs(False)
        """
        if isinstance(values, bool):
            pins = {p: values for p in range(16)}
        else:
            pins = dict(values)

        for pin, value in pins.items():
            self.set_digital_output(pin, value)

    def get_digital_output(self, pin: int) -> bool:
        """Get the current state of a digital output.

        Args:
            pin: Digital output pin index (0–17 on e-Series).
                Pins 0–7 are standard, 8–15 configurable, 16–17 tool.

        Returns:
            True if the output is high, False if low.

        Raises:
            IOError: If the pin is invalid or the read fails.
        """
        if not 0 <= pin <= 17:
            raise IOError(
                f"Digital output pin must be 0–17, got {pin}."
            )
        try:
            return bool(self._rtde_r.getDigitalOutState(pin))
        except Exception as e:
            raise IOError(
                f"Failed to read digital output {pin}: {e}"
            )

    # ── Digital Inputs ─────────────────────────────────────────────

    def get_digital_input(self, pin: int) -> bool:
        """Get the current state of a digital input.

        Args:
            pin: Digital input pin index (0–17 on e-Series).
                Pins 0–7 are standard, 8–15 configurable, 16–17 tool.

        Returns:
            True if high, False if low.

        Raises:
            IOError: If the pin is invalid or the read fails.
        """
        if not 0 <= pin <= 17:
            raise IOError(
                f"Digital input pin must be 0–17, got {pin}."
            )
        try:
            return bool(self._rtde_r.getDigitalInState(pin))
        except Exception as e:
            raise IOError(
                f"Failed to read digital input {pin}: {e}"
            )

    def get_tool_input(self, pin: int) -> bool:
        """Get the current state of a tool digital input.

        Tool inputs correspond to pins 16–17 on the robot's I/O board
        (the tool connector). Use pin 0 or 1 to access them.

        Args:
            pin: Tool input pin index (0–1).

        Returns:
            True if high, False if low.

        Raises:
            IOError: If the pin is invalid or the read fails.
        """
        if not 0 <= pin <= 1:
            raise IOError(f"Tool input pin must be 0–1, got {pin}.")
        try:
            return bool(self._rtde_r.getDigitalInState(16 + pin))
        except Exception as e:
            raise IOError(
                f"Failed to read tool digital input {pin}: {e}"
            )

    def get_tool_output(self, pin: int) -> bool:
        """Get the current state of a tool digital output.

        Tool outputs correspond to pins 16–17 on the robot's I/O board.
        Tool outputs are configured in the robot's I/O mapping and cannot
        be set directly via RTDE — they are controlled by the robot
        controller based on the configured mode (auto/manual). This method
        reads the actual output state.

        Args:
            pin: Tool output pin index (0–1).

        Returns:
            True if high, False if low.

        Raises:
            IOError: If the pin is invalid or the read fails.
        """
        if not 0 <= pin <= 1:
            raise IOError(f"Tool output pin must be 0–1, got {pin}.")
        try:
            return bool(self._rtde_r.getDigitalOutState(16 + pin))
        except Exception as e:
            raise IOError(
                f"Failed to read tool digital output {pin}: {e}"
            )

    # ── Analog ─────────────────────────────────────────────────────

    def get_analog_input(self, pin: int) -> float:
        """Get the current value of a standard analog input.

        Reads from the robot's analog input channel (0–10V or 4–20mA
        depending on the robot's configuration).

        Args:
            pin: Analog input pin index (0–1).

        Returns:
            Analog value in volts or amperes.

        Raises:
            IOError: If the pin is invalid or the read fails.
        """
        if pin == 0:
            read_fn = self._rtde_r.getStandardAnalogInput0
        elif pin == 1:
            read_fn = self._rtde_r.getStandardAnalogInput1
        else:
            raise IOError(f"Analog input pin must be 0–1, got {pin}.")
        try:
            return float(read_fn())
        except Exception as e:
            raise IOError(
                f"Failed to read analog input {pin}: {e}"
            )

    def get_analog_output(self, pin: int) -> float:
        """Get the current value of a standard analog output.

        Args:
            pin: Analog output pin index (0–1).

        Returns:
            Analog value in volts or amperes.

        Raises:
            IOError: If the pin is invalid or the read fails.
        """
        if pin == 0:
            read_fn = self._rtde_r.getStandardAnalogOutput0
        elif pin == 1:
            read_fn = self._rtde_r.getStandardAnalogOutput1
        else:
            raise IOError(f"Analog output pin must be 0–1, got {pin}.")
        try:
            return float(read_fn())
        except Exception as e:
            raise IOError(
                f"Failed to read analog output {pin}: {e}"
            )

    # ── Wait ───────────────────────────────────────────────────────

    def wait_for_input(
        self,
        pin: int,
        value: bool = True,
        *,
        timeout: float = 10.0,
    ) -> bool:
        """Block until a digital input reaches the desired value.

        Polls the specified digital input at ~50 Hz until it matches
        *value* or *timeout* seconds have elapsed.

        Args:
            pin: Digital input pin index (0–17).
            value: Desired value (True for high, False for low).
            timeout: Maximum wait time in seconds (default 10.0).

        Returns:
            True if the input reached the desired value, False if timed out.

        Raises:
            IOError: If the pin is invalid or the read fails.

        Example:
            >>> # Wait for a limit switch on pin 0
            >>> if not io.wait_for_input(0, True, timeout=5.0):
            ...     raise TimeoutError("Limit switch not triggered")
        """
        if not 0 <= pin <= 17:
            raise IOError(f"Digital input pin must be 0–17, got {pin}.")

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                if bool(self._rtde_r.getDigitalInState(pin)) == value:
                    return True
            except Exception as e:
                raise IOError(f"Failed to read input pin {pin}: {e}")
            time.sleep(0.02)  # ~50 Hz polling
        return False
