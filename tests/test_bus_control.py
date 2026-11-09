"""Bus arbitration and setpoint control against the mock board. No real bus involved."""

from __future__ import annotations

import pytest

from spa2mqtt.definitions import TubDefinition
from spa2mqtt.transport import TransmitForbidden
from spa2mqtt.tub import BusState, Tub

from .mockboard import TOPSIDE, MockBoard


def run(tub: Tub, board: MockBoard, cycles: int) -> None:
    for _ in range(cycles):
        pending = board.cycle()
        while pending:
            frame = pending.pop(0)
            for out in tub.on_frame(frame):
                pending[0:0] = board.receive(out)


def test_transmit_disabled_refuses_everything(j235: TubDefinition) -> None:
    tub = Tub(j235, transmit=False)
    with pytest.raises(TransmitForbidden):
        tub.press("pump_1_button")
    with pytest.raises(TransmitForbidden):
        tub.set_number("temperature_set_control", 39.0)
    board = MockBoard()
    run(tub, board, 50)
    assert board.assigned == [] and board.presses == []
    assert tub.bus.state is BusState.LISTEN


def test_no_claim_without_a_command(j235: TubDefinition) -> None:
    tub = Tub(j235, transmit=True)
    board = MockBoard()
    run(tub, board, 50)
    assert board.assigned == []  # lazy: enabling transmit alone sends nothing
    assert tub.bus.state is BusState.LISTEN


def test_channel_request_then_press(j235: TubDefinition) -> None:
    tub = Tub(j235, transmit=True)
    board = MockBoard()
    run(tub, board, 10)
    tub.press("pump_1_button")
    run(tub, board, 10)
    assert board.assigned == [0x11]
    assert board.acked == [0x11]
    assert board.presses == [(0x11, 0x04)]
    assert tub.state.values["pump_1_speed"] == "low"


def test_dormant_channel_is_reused(j235: TubDefinition) -> None:
    tub = Tub(j235, transmit=True)
    board = MockBoard(polled=[TOPSIDE, 0x12])  # 0x12 polled but never answers
    run(tub, board, 10)
    tub.press("pump_2_button")
    run(tub, board, 5)
    assert board.assigned == []
    assert board.presses == [(0x12, 0x05)]


def test_setpoint_loop_handles_set_mode_and_converges(j235: TubDefinition) -> None:
    tub = Tub(j235, transmit=True)
    board = MockBoard()
    run(tub, board, 10)
    assert tub.set_number("temperature_set_control", 40.0) == 40.0
    run(tub, board, 80)
    assert tub.state.values["setpoint"] == 40.0
    codes = [c for _, c in board.presses]
    assert codes == [0x01] * 4  # 1 press to enter set mode + 3 steps of 0.5 °C
    assert tub.setpoints["temperature_set_control"].target is None


def test_setpoint_loop_retries_lost_presses_and_clamps(j235: TubDefinition) -> None:
    tub = Tub(j235, transmit=True)
    board = MockBoard(ignore_presses=2)
    run(tub, board, 10)
    assert tub.set_number("temperature_set_control", 12.0) == 20.0  # clamped to entity min
    run(tub, board, 600)
    assert tub.state.values["setpoint"] == 20.0


def test_setpoint_loop_gives_up(j235: TubDefinition) -> None:
    tub = Tub(j235, transmit=True)
    board = MockBoard(ignore_presses=10_000)
    run(tub, board, 10)
    tub.set_number("temperature_set_control", 39.0)
    run(tub, board, 1000)
    ctl = tub.setpoints["temperature_set_control"]
    assert ctl.target is None
    assert ctl.attempts == 60  # max_attempts from the definition


def test_conflict_on_our_channel_releases_it(j235: TubDefinition) -> None:
    from spa2mqtt.protocol import Frame, cc_encode

    tub = Tub(j235, transmit=True)
    board = MockBoard()
    run(tub, board, 10)
    tub.press("pump_1_button")
    run(tub, board, 5)
    assert tub.bus.channel == 0x11
    tub.on_frame(Frame(0x11, 0xBF, 0x06))
    tub.on_frame(Frame(0x11, 0xBF, 0xCC, cc_encode(0, key=1)))  # someone else answered our CTS
    assert tub.bus.channel is None
    assert tub.bus.state is BusState.LISTEN


def _without_set_mode_field(j235: TubDefinition) -> TubDefinition:
    import dataclasses

    from spa2mqtt.definitions import NumberEntity

    ents = tuple(
        dataclasses.replace(e, control=dataclasses.replace(e.control, set_mode_field=None))
        if isinstance(e, NumberEntity)
        else e
        for e in j235.entities
    )
    return dataclasses.replace(j235, entities=ents)


def _frames_to_target(definition: TubDefinition, target: float) -> tuple[int, list[int], int]:
    tub = Tub(definition, transmit=True)
    board = MockBoard()
    run(tub, board, 10)
    tub.set_number("temperature_set_control", target)
    cycles = 0
    while tub.setpoints["temperature_set_control"].target is not None and cycles < 400:
        run(tub, board, 1)
        cycles += 1
    return cycles, [c for _, c in board.presses], tub.setpoints["temperature_set_control"].wake_presses


def test_set_mode_aware_controller_uses_exactly_one_wake_press(j235: TubDefinition) -> None:
    _, codes, wakes = _frames_to_target(j235, 40.0)
    assert codes == [0x01] * 4  # 1 wake + 3 steps from 38.5 to 40.0
    assert wakes == 1


def test_set_mode_awareness_is_faster_than_retry_fallback(j235: TubDefinition) -> None:
    aware, codes_aware, _ = _frames_to_target(j235, 40.0)
    blind, codes_blind, wakes_blind = _frames_to_target(_without_set_mode_field(j235), 40.0)
    assert codes_aware == codes_blind == [0x01] * 4  # both converge with the same presses
    assert wakes_blind == 0  # without the field it cannot tell a wake press from a lost one
    assert aware < blind


def test_already_in_set_mode_needs_no_wake_press(j235: TubDefinition) -> None:
    tub = Tub(j235, transmit=True)
    board = MockBoard()
    run(tub, board, 10)
    board.apply(0x01)  # someone at the topside just pressed Temp up: set mode is open
    run(tub, board, 1)
    assert tub.state.values["set_mode"] is True
    tub.set_number("temperature_set_control", 39.0)
    run(tub, board, 20)
    assert [c for _, c in board.presses] == [0x01]
    assert tub.state.values["setpoint"] == 39.0


def test_set_mode_field_must_be_a_bit_field() -> None:
    import copy

    import pytest

    from spa2mqtt.definitions import DefinitionError
    from spa2mqtt.definitions.loader import parse_definition

    from .test_definitions import _raw

    raw = copy.deepcopy(_raw())
    for e in raw["entities"]:
        if e["component"] == "number":
            e["control"]["set_mode_field"] = "water_temperature"
    with pytest.raises(DefinitionError, match="bit field"):
        parse_definition(raw)


def test_slow_channel_grant_does_not_duplicate_presses(j235: TubDefinition) -> None:
    for definition in (j235, _without_set_mode_field(j235)):
        tub = Tub(definition, transmit=True)
        board = MockBoard(new_client_poll_after=60)  # ~18 s before the board offers a channel
        run(tub, board, 10)
        tub.set_number("temperature_set_control", 39.5)
        run(tub, board, 150)
        assert [c for _, c in board.presses] == [0x01] * 3  # 1 wake + 2 steps, no extras
        assert tub.state.values["setpoint"] == 39.5


def test_j235_keeps_the_claiming_bus_client(j235: TubDefinition) -> None:
    from spa2mqtt.tub import BusClient

    tub = Tub(j235, transmit=True)
    assert type(tub.bus) is BusClient
    tub.on_connect()  # a reconnect changes nothing for a claiming client
    assert tub.bus.state is BusState.LISTEN and not tub.bus.queue
