"""The tub façade: frames in, state changes and frames-to-send out. Sans-IO."""

from __future__ import annotations

import logging
import math
from collections.abc import Callable
from functools import partial

from ..definitions.model import (
    ButtonEntity,
    DirectCommand,
    DirectControl,
    FieldValue,
    NumberEntity,
    StepperControl,
    SwitchEntity,
    TubDefinition,
)
from ..protocol.frame import Frame
from ..transport.base import TransmitForbidden
from .bus import BOARD_MID, BusClient, DirectBusClient
from .control import SetpointController, ToggleController
from .state import TubState

log = logging.getLogger(__name__)


class CommandBlocked(TransmitForbidden):
    """Transmit is on, but the tub's state does not allow this command (``requires``)."""


Listener = Callable[[dict[str, FieldValue]], None]


class Tub:
    def __init__(self, definition: TubDefinition, transmit: bool = False, state: TubState | None = None) -> None:
        self.definition = definition
        self.transmit = transmit
        self.state = state or TubState()
        self.bus: BusClient | DirectBusClient
        if definition.bus.mode == "direct":
            hello = definition.bus.hello
            self.bus = DirectBusClient(
                definition.bus,
                definition.command_type,
                transmit,
                definition.status_type,
                hello=self._direct_frame(definition.direct_commands[hello]) if hello else None,
            )
        else:
            self.bus = BusClient(definition.bus, definition.command_type, transmit)
        self._listeners: list[Listener] = []
        self.setpoints: dict[str, SetpointController] = {}
        for e in definition.entities:
            if isinstance(e, NumberEntity) and isinstance(e.control, StepperControl):
                self.setpoints[e.key] = SetpointController(
                    self._press_code,
                    definition.buttons[e.control.up],
                    definition.buttons[e.control.down],
                    step=e.step,
                    minimum=e.min,
                    maximum=e.max,
                    confirm_frames=e.control.confirm_frames,
                    max_attempts=e.control.max_attempts,
                    press_queued=lambda: bool(self.bus.queue),
                )
        self.switches: dict[str, ToggleController] = {}
        for e in definition.entities:
            if isinstance(e, SwitchEntity):
                self.switches[e.key] = ToggleController(
                    partial(self._press_switch, e),
                    name=e.key,
                    confirm_frames=e.confirm_frames,
                    max_presses=e.max_presses,
                    press_queued=lambda: bool(self.bus.queue),
                )
        self.bad_status_frames = 0
        hyp = [k for k, f in definition.fields.items() if f.status == "hypothesis"]
        if hyp:
            log.info("definition %s: fields still hypotheses: %s", definition.id, ", ".join(hyp))

    def subscribe(self, listener: Listener) -> None:
        self._listeners.append(listener)

    # -- receive ---------------------------------------------------------------

    def on_frame(self, frame: Frame) -> list[Frame]:
        out = self.bus.handle(frame)
        if frame.type == self.definition.status_type and frame.mid == BOARD_MID:
            decoded = self.definition.decode_payload(frame.payload)
            if len(decoded) < self.definition.status_length:
                self.bad_status_frames += 1
                return out
            values = self.definition.decode_status(decoded)
            changed = self.state.update(values)
            for key, ctl in self.setpoints.items():
                ent = self.definition.entity(key)
                assert isinstance(ent, NumberEntity) and isinstance(ent.control, StepperControl)
                sp = values.get(ent.field)
                mode = values.get(ent.control.set_mode_field) if ent.control.set_mode_field else None
                ctl.on_status(
                    float(sp) if isinstance(sp, (int, float)) and not isinstance(sp, bool) else None,
                    mode if isinstance(mode, bool) else None,
                )
            # Switches read the merged state: a field may come from an extra frame (lights).
            current = self.state.values
            for key, toggle in self.switches.items():
                sw = self.definition.entity(key)
                assert isinstance(sw, SwitchEntity)
                on = current.get(sw.field)
                off = current.get(sw.off_field) if sw.off_field else None
                toggle.on_status(
                    on if isinstance(on, bool) else None,
                    current.get(sw.progress_field) if sw.progress_field else None,
                    off if isinstance(off, bool) else None,
                )
            if changed:
                for listener in self._listeners:
                    listener(changed)
        elif frame.mid == BOARD_MID and (extra := self.definition.extra_frame_for(frame.type)) is not None:
            name, spec = extra
            if len(frame.payload) < spec.length:
                self.bad_status_frames += 1
                return out
            changed = self.state.merge(self.definition.decode_frame(name, frame.payload))
            if changed:
                for listener in self._listeners:
                    listener(changed)
        return out

    def on_connect(self) -> None:
        """Call after each transport connect (a direct bus drops stale commands)."""
        self.bus.on_connect()

    # -- commands --------------------------------------------------------------

    def press(self, entity_key: str) -> None:
        ent = self.definition.entity(entity_key)
        if not isinstance(ent, ButtonEntity):
            raise KeyError(f"{entity_key} is not a button")
        self._press_named(ent.press)

    def set_switch(self, entity_key: str, on: bool) -> None:
        """Press the switch's button until its field reads ``on`` (no press if it already does)."""
        if not self.transmit:
            raise TransmitForbidden("transmit disabled; switch change ignored")
        self.switches[entity_key].set_target(on)

    def set_number(self, entity_key: str, value: float) -> float:
        if not self.transmit:
            raise TransmitForbidden("transmit disabled; setpoint change ignored")
        if entity_key in self.setpoints:
            return self.setpoints[entity_key].set_target(value)
        ent = self.definition.entity(entity_key)
        if not isinstance(ent, NumberEntity) or not isinstance(ent.control, DirectControl):
            raise KeyError(f"{entity_key} is not a number")
        if not math.isfinite(value):  # min()/max() would turn NaN into a real setpoint
            raise ValueError(f"{entity_key}: {value!r} is not a number")
        if not ent.min <= value <= ent.max:  # one message is one frame here: refuse, never clamp
            raise ValueError(f"{entity_key}: {value!r} is outside {ent.min:g}..{ent.max:g}")
        # One frame, no retry: the tub's next status frame shows whether it took effect.
        target = round(value / ent.step) * ent.step
        self._send_direct(self.definition.direct_commands[ent.control.command], round(target))
        log.info("%s: queued %s", entity_key, round(target))
        return target

    def _press_named(self, name: str) -> None:
        if name in self.definition.buttons:
            self._press_code(self.definition.buttons[name])
        else:
            self._send_direct(self.definition.direct_commands[name], None)

    def _press_switch(self, ent: SwitchEntity) -> None:
        try:
            self._press_named(ent.press)
        except TransmitForbidden as exc:  # a `requires` guard: stop, do not raise into the receive path
            log.warning("%s: %s", ent.key, exc)
            self.switches[ent.key].cancel()

    def _press_code(self, code: int) -> None:
        self.bus.enqueue_press(code)

    def _direct_frame(self, command: DirectCommand, value: int | None = None) -> Frame:
        addr = self.definition.bus.client_address
        assert addr is not None  # the loader requires it with bus.mode direct
        return Frame(addr, self.definition.bus.client_mid, command.type, command.build(value))

    def _send_direct(self, command: DirectCommand, value: int | None) -> None:
        if not self.transmit or not isinstance(self.bus, DirectBusClient):
            raise TransmitForbidden("transmit disabled; command not queued")
        for fkey, want in command.requires:
            got = self.state.values.get(fkey)
            if got is not want:  # None: no status frame decoded yet
                seen = "not seen yet" if got is None else f"is {got}"
                raise CommandBlocked(f"{command.key} needs {fkey} = {want}, {fkey} {seen}; command not queued")
        self.bus.enqueue(self._direct_frame(command, value))
