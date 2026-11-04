"""The tub façade: frames in, state changes and frames-to-send out. Sans-IO."""

from __future__ import annotations

import logging
from collections.abc import Callable

from ..definitions.model import ButtonEntity, FieldValue, NumberEntity, TubDefinition
from ..protocol.cipher import fold
from ..protocol.frame import Frame
from ..transport.base import TransmitForbidden
from .bus import BusClient
from .control import SetpointController
from .state import TubState

log = logging.getLogger(__name__)

BOARD_MID = 0xAF
Listener = Callable[[dict[str, FieldValue]], None]


class Tub:
    def __init__(self, definition: TubDefinition, transmit: bool = False, state: TubState | None = None) -> None:
        self.definition = definition
        self.transmit = transmit
        self.state = state or TubState()
        self.bus = BusClient(definition.bus, definition.command_type, transmit)
        self._listeners: list[Listener] = []
        self.setpoints: dict[str, SetpointController] = {}
        for e in definition.entities:
            if isinstance(e, NumberEntity):
                self.setpoints[e.key] = SetpointController(
                    self._press_code,
                    definition.buttons[e.control.up],
                    definition.buttons[e.control.down],
                    step=e.step,
                    minimum=e.min,
                    maximum=e.max,
                    confirm_frames=e.control.confirm_frames,
                    max_attempts=e.control.max_attempts,
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
            decoded = fold(frame.payload)
            if len(decoded) < self.definition.status_length:
                self.bad_status_frames += 1
                return out
            values = self.definition.decode_status(decoded)
            changed = self.state.update(values)
            for key, ctl in self.setpoints.items():
                ent = self.definition.entity(key)
                assert isinstance(ent, NumberEntity)
                sp = values.get(ent.field)
                ctl.on_status(float(sp) if isinstance(sp, (int, float)) and not isinstance(sp, bool) else None)
            if changed:
                for listener in self._listeners:
                    listener(changed)
        return out

    # -- commands --------------------------------------------------------------

    def press(self, entity_key: str) -> None:
        ent = self.definition.entity(entity_key)
        if not isinstance(ent, ButtonEntity):
            raise KeyError(f"{entity_key} is not a button")
        self._press_code(self.definition.buttons[ent.press])

    def set_number(self, entity_key: str, value: float) -> float:
        if not self.transmit:
            raise TransmitForbidden("transmit disabled; setpoint change ignored")
        return self.setpoints[entity_key].set_target(value)

    def _press_code(self, code: int) -> None:
        self.bus.enqueue_press(code)
