"""Closed-loop setpoint control by button presses (docs/design.md §6)."""

from __future__ import annotations

import logging
from collections.abc import Callable

log = logging.getLogger(__name__)


class SetpointController:
    def __init__(
        self,
        press: Callable[[int], None],
        up_code: int,
        down_code: int,
        *,
        step: float,
        minimum: float,
        maximum: float,
        confirm_frames: int = 3,
        max_attempts: int = 40,
    ) -> None:
        self._press = press
        self.up_code = up_code
        self.down_code = down_code
        self.step = step
        self.minimum = minimum
        self.maximum = maximum
        self.confirm_frames = confirm_frames
        self.max_attempts = max_attempts
        self.target: float | None = None
        self.attempts = 0
        self._pending = False
        self._wait = 0
        self._at_press: float | None = None

    def set_target(self, value: float) -> float:
        clamped = min(self.maximum, max(self.minimum, value))
        target = round(clamped / self.step) * self.step
        self.target = target
        self.attempts = 0
        self._pending = False
        log.info("setpoint target %.1f", target)
        return target

    def on_status(self, setpoint: float | None) -> None:
        if self.target is None or setpoint is None:
            return
        if abs(setpoint - self.target) < self.step / 2:
            log.info("setpoint reached %.1f after %d presses", setpoint, self.attempts)
            self.target = None
            self._pending = False
            return
        if self._pending:
            if setpoint != self._at_press:
                self._pending = False  # the press landed; decide the next one now
            else:
                self._wait -= 1
                if self._wait > 0:
                    return
                self._pending = False  # no movement: retry (first press may only wake the panel)
        if self.attempts >= self.max_attempts:
            log.warning("setpoint %.1f not reached after %d presses; giving up", self.target, self.attempts)
            self.target = None
            return
        self._press(self.up_code if setpoint < self.target else self.down_code)
        self.attempts += 1
        self._pending = True
        self._wait = self.confirm_frames
        self._at_press = setpoint
