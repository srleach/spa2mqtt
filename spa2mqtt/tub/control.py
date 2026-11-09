"""Closed-loop setpoint control by button presses (docs/design.md §6).

The topside behaves like this (docs/protocol.md §5 d2, §7; capture D7):

* The first Temp up/down press only enters *set mode* (status byte d2 bit 5). The setpoint
  does not change.
* Each further press while in set mode changes the setpoint by one step (0.5 °C).
* Set mode ends about 5 s after the last press.

When the definition names the set-mode field, the controller uses it. A press that turns set
mode on is recognised as the "wake" press, and the next press is sent on the next status frame.
Without the field, the controller falls back to waiting ``confirm_frames`` and retrying.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from ..definitions.model import FieldValue

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
        press_queued: Callable[[], bool] | None = None,
    ) -> None:
        self._press = press
        # True while our last press is still waiting for a bus slot. The confirmation
        # countdown must not run before the press has actually been sent.
        self._press_queued = press_queued or (lambda: False)
        self.up_code = up_code
        self.down_code = down_code
        self.step = step
        self.minimum = minimum
        self.maximum = maximum
        self.confirm_frames = confirm_frames
        self.max_attempts = max_attempts
        self.target: float | None = None
        self.attempts = 0
        self.wake_presses = 0
        self._pending = False
        self._wait = 0
        self._at_press: float | None = None
        self._mode_at_press: bool | None = None

    def set_target(self, value: float) -> float:
        clamped = min(self.maximum, max(self.minimum, value))
        target = round(clamped / self.step) * self.step
        self.target = target
        self.attempts = 0
        self.wake_presses = 0
        self._pending = False
        log.info("setpoint target %.1f", target)
        return target

    def on_status(self, setpoint: float | None, set_mode: bool | None = None) -> None:
        """Call on every status frame. ``set_mode`` is None when the tub has no such field."""
        if self.target is None or setpoint is None:
            return
        if abs(setpoint - self.target) < self.step / 2:
            log.info(
                "setpoint reached %.1f after %d presses (%d to enter set mode)",
                setpoint,
                self.attempts,
                self.wake_presses,
            )
            self.target = None
            self._pending = False
            return
        if self._pending:
            if self._press_queued():
                return  # not sent yet (e.g. still claiming a channel): nothing to judge
            moved = setpoint != self._at_press
            entered = set_mode is True and self._mode_at_press is False
            if moved:
                self._pending = False
            elif entered:
                self.wake_presses += 1  # the press only opened the set screen; step now
                self._pending = False
            else:
                self._wait -= 1
                if self._wait > 0:
                    return
                self._pending = False  # no effect seen: retry
        if self.attempts >= self.max_attempts:
            log.warning("setpoint %.1f not reached after %d presses; giving up", self.target, self.attempts)
            self.target = None
            return
        self._press(self.up_code if setpoint < self.target else self.down_code)
        self.attempts += 1
        self._pending = True
        self._wait = self.confirm_frames
        self._at_press = setpoint
        self._mode_at_press = set_mode


class ToggleController:
    """Drive an on/off state with a toggle button (docs/design.md §6).

    A pump button only toggles, or cycles off → low → high → off, so "on" and "off" are
    reached by pressing and reading the state back. A press is sent only while the state
    differs from the target. After a press the controller waits ``confirm_frames`` status
    frames for the state to follow: a second press sent too early would toggle a two-state
    pump straight back. A change in the ``progress`` value (a pump speed) shows that the
    press did land, so the next press need not wait.
    """

    def __init__(
        self,
        press: Callable[[], None],
        *,
        name: str = "switch",
        confirm_frames: int = 10,
        max_presses: int = 3,
        press_queued: Callable[[], bool] | None = None,
    ) -> None:
        self._press = press
        self._press_queued = press_queued or (lambda: False)
        self.name = name
        self.confirm_frames = confirm_frames
        self.max_presses = max_presses
        self.target: bool | None = None
        self.presses = 0
        self._pending = False
        self._wait = 0
        self._progress_at_press: FieldValue = None

    def set_target(self, on: bool) -> None:
        self.target = on
        self.presses = 0
        self._pending = False
        log.info("%s target %s", self.name, "on" if on else "off")

    def cancel(self) -> None:
        self.target = None
        self._pending = False

    def on_status(self, state: bool | None, progress: FieldValue = None, off_state: bool | None = None) -> None:
        """Call on every status frame with the switch's field and its progress value.
        ``off_state`` is the switch's off field when it has one: "off" is reached when it reads
        false, not when ``state`` does."""
        if off_state is not None and self.target is False:
            state = off_state
        if self.target is None or state is None:
            return
        if state is self.target:
            if self.presses:
                log.info("%s is %s after %d presses", self.name, "on" if state else "off", self.presses)
            self.cancel()
            return
        if self._pending:
            if self._press_queued():
                return  # not sent yet: nothing to judge
            if progress == self._progress_at_press:
                self._wait -= 1
                if self._wait > 0:
                    return
            self._pending = False  # the press stepped the state, or had no visible effect
        if self.presses >= self.max_presses:
            log.warning(
                "%s did not turn %s after %d presses; giving up",
                self.name,
                "on" if self.target else "off",
                self.presses,
            )
            self.cancel()
            return
        self._press()
        self.presses += 1
        self._pending = True
        self._wait = self.confirm_frames
        self._progress_at_press = progress
