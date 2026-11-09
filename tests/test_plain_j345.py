"""Jacuzzi J345 (plain protocol through a ProLink module): the owner's five captures replayed
through the real pipeline, and the direct transmit path held to the bytes pyjacuzzi sent.

Nobody on the project has this tub. These tests pin the definition to its evidence: every
cited line exists, every decode matches the capture, and nothing can be transmitted that the
pyjacuzzi session (S) does not contain, apart from the setpoints listed in
``test_nothing_else_can_be_emitted``.
"""

from __future__ import annotations

import copy
import io
import re
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
import yaml

from spa2mqtt.__main__ import main
from spa2mqtt.app import discovery_config, pump
from spa2mqtt.captures import read_capture
from spa2mqtt.config import load_config
from spa2mqtt.definitions import DefinitionError, TubDefinition
from spa2mqtt.definitions.loader import parse_definition
from spa2mqtt.definitions.model import ButtonEntity, DirectControl, NumberEntity, SwitchEntity
from spa2mqtt.ha.bridge import MqttBridge, MqttSettings
from spa2mqtt.ha.discovery import build_discovery
from spa2mqtt.monitor import Monitor
from spa2mqtt.protocol import Frame
from spa2mqtt.transport import ReplayTransport, TransmitForbidden
from spa2mqtt.tub import BusState, BusWriter, CommandBlocked, DirectBusClient, Tub

from .conftest import PLAIN_CAPTURES, PlainLine, plain_lines
from .mockprolink import MockProlink
from .test_ha import FakeClient

LINES: dict[str, list[PlainLine]] = {key: plain_lines(path) for key, path in PLAIN_CAPTURES.items()}
SENT = {no: raw for no, direction, _, raw, _ in LINES["S"] if direction == "TX"}
STATUS = next(f for _, d, f, _, _ in LINES["S"] if d == "RX" and f.type == 0x16)  # S L5
LIGHTS = next(f for _, d, f, _, _ in LINES["S"] if d == "RX" and f.type == 0x23)  # S L6
HELLO = SENT[3]


def states(definition: TubDefinition, key: str) -> tuple[Tub, dict[int, dict[str, Any]]]:
    """Replay the received frames of one capture; the decoded state after each line."""
    tub = Tub(definition, transmit=False)
    after: dict[int, dict[str, Any]] = {}
    for no, direction, frame, _, _ in LINES[key]:
        if direction == "RX":
            assert tub.on_frame(frame) == []  # receive-only: never anything to send
            after[no] = dict(tub.state.values)
    return tub, after


def has(values: dict[str, Any], **expected: Any) -> None:
    assert {k: values.get(k) for k in expected} == expected


def drain(tub: Tub, frames: int = 12) -> list[bytes]:
    """Feed status frames; the wire bytes of everything the tub wants to send."""
    return [out.encode() for _ in range(frames) for out in tub.on_frame(STATUS)]


def write_log(path: Path, key: str) -> Path:
    """One capture's received frames in the .log format the replay transport reads."""
    path.write_text(
        "".join(f"{ts:.3f} RX {raw.hex()}\n" for _, d, _, raw, ts in LINES[key] if d == "RX"), encoding="ascii"
    )
    return path


# --- 1. the captures themselves ----------------------------------------------------------


def test_census() -> None:
    def count(key: str) -> Counter[tuple[str, int, int, int]]:
        return Counter((d, f.addr, f.mid, f.type) for _, d, f, _, _ in LINES[key])

    assert count("S") == {
        ("RX", 0xFF, 0xAF, 0x16): 13,
        ("RX", 0xFF, 0xAF, 0x23): 19,
        ("RX", 0x0A, 0xBF, 0x1B): 1,
        ("TX", 0x0A, 0xBF, 0x19): 1,
        ("TX", 0x0A, 0xBF, 0x20): 3,
        ("TX", 0x0A, 0xBF, 0x17): 4,
        ("TX", 0x0A, 0xBF, 0x21): 18,
    }
    assert count("D") == {("RX", 0xFF, 0xAF, 0x16): 125, ("RX", 0xFF, 0xAF, 0x23): 38}
    assert sum(count("X1").values()) == 100 and sum(count("X2").values()) == 100
    assert count("X3") == {("RX", 0xFF, 0xAF, 0x16): 1316, ("RX", 0xFF, 0xAF, 0x23): 395}
    # no clear-to-send, poll or channel traffic anywhere in the receive-only captures
    assert {t for key in ("D", "X1", "X2", "X3") for _, _, _, t in count(key)} == {0x16, 0x23}
    for lines in LINES.values():
        for _, _, frame, raw, _ in lines:
            assert frame.encode() == raw


def test_fixtures_are_redacted() -> None:
    for path in PLAIN_CAPTURES.values():
        data = path.read_bytes()
        assert b"\r" not in data
        assert set(re.findall(rb"\d+\.\d+\.\d+\.\d+", data)) <= {b"192.0.2.1"}, path.name


# --- 2-4. replay --------------------------------------------------------------------------


def test_replay_s(j345: TubDefinition) -> None:
    tub, at = states(j345, "S")
    assert at[4] == {}  # the 0x1B reply decodes to nothing
    has(at[5], hour=19, minute=34, day_of_week=3, day_of_month=21, month=5, year=2025)
    has(at[5], water_temperature=100, setpoint=80, pump_1=False, pump_2=False, circulation_pump=False)
    has(at[5], heater=False, flow_switch=False, secondary_temperature=102, clearray_days=364, state_raw=8)
    has(at[5], celsius_mode=False, set_mode=False, error_code=0)
    has(at[9], setpoint=90, state_raw=8)
    has(at[11], setpoint=100, circulation_pump=True, state_raw=2, flow_switch=False, heater=False)
    has(at[12], flow_switch=True)
    has(at[14], setpoint=101, set_mode=False, heater=False)
    has(at[18], pump_2=True, pump_1=False)
    has(at[21], pump_2=False)
    has(at[23], pump_1=True, pump_2=False)
    has(at[25], pump_1=False)
    assert (at[19]["minute"], at[53]["minute"]) == (35, 36)
    has(at[27], light_mode="white", light_brightness=60, light_red=85, light_green=85, light_blue=85)
    has(at[30], light_mode="blue", light_red=0, light_green=0, light_blue=255)
    has(at[33], light_mode="green")
    has(at[36], light_mode="orange", light_red=170, light_green=85, light_blue=0)
    has(at[39], light_mode="red")
    has(at[42], light_mode="violet")
    has(at[45], light_mode="aqua")
    has(at[51], light_mode="yellow")
    has(at[55], light_mode="amber", light_red=146, light_green=109, light_blue=0)
    has(at[58], light_mode="off", light_brightness=0)
    has(at[79], light_mode="off", light_brightness=0)
    assert [at[n]["light_brightness"] for n in (64, 67, 70, 73, 76)] == [20, 40, 60, 80, 100]
    assert all(at[n]["light_mode"] == "blue" for n in (64, 67, 70, 73, 76))  # brightness keeps the colour
    assert all(v["water_temperature"] == 100 for no, v in at.items() if no >= 5)
    assert tub.state.status_frames == 13 and tub.bad_status_frames == 0


def test_replay_d(j345: TubDefinition) -> None:
    tub, at = states(j345, "D")
    has(at[5], light_mode="off")
    has(at[6], hour=6, minute=35, setpoint=101, water_temperature=100, circulation_pump=True, flow_switch=True)
    has(at[76], pump_1=True)
    has(at[103], pump_1=False)
    has(at[110], pump_2=True)
    has(at[130], pump_2=False)
    has(at[135], set_mode=False, display_state=0)
    has(at[136], set_mode=True, display_state=1, setpoint=101, heater=False)
    has(at[143], setpoint=102, heater=True)
    has(at[163], set_mode=True, display_state=1)
    has(at[164], set_mode=False, display_state=0, setpoint=102)
    assert tub.state.status_frames == 125  # the 38 lights frames merge without counting


def test_replay_x(j345: TubDefinition) -> None:
    _, x1 = states(j345, "X1")
    has(x1[1], water_temperature=101, circulation_pump=False, flow_switch=False, clearray_days=7, reminder=True)
    has(x1[1], day_of_week=2, day_of_month=20, display_aux=255, secondary_temperature=97)
    _, x2 = states(j345, "X2")
    has(x2[2], hour=17, minute=16, clearray_days=365, reminder=False)
    has(x2[19], light_mode="blend")
    assert (x2[32]["light_brightness"], x2[45]["light_brightness"]) == (66, 33)
    _, x3 = states(j345, "X3")
    has(x3[6], setpoint=103, water_temperature=102, heater=True, clearray_days=0, reminder=True)
    has(x3[6], day_of_week=2, day_of_month=27, display_aux=3)
    has(x3[1118], pump_1=True, pump_2=False)
    has(x3[1153], pump_1=True, pump_2=True)
    has(x3[1241], setpoint=104, set_mode=True)
    has(x3[1299], setpoint=101, heater=False)
    has(x3[1354], light_mode="blend")
    has(x3[1376], light_mode="blend paused")
    has(x3[1542], clearray_days=365, reminder=False)
    has(x3[1403], hour=19, minute=59)
    has(x3[1663], hour=20, minute=0)
    # every setpoint any capture shows is inside the range the number entity offers
    seen = {v["setpoint"] for at in (x1, x2, x3) for v in at.values() if "setpoint" in v}
    assert seen == {101, 103, 104, 102}


# --- 5-6. nothing is sent unless asked ----------------------------------------------------


def test_receive_only_refuses_everything(j345: TubDefinition) -> None:
    tub = Tub(j345, transmit=False)
    assert isinstance(tub.bus, DirectBusClient) and tub.bus.state is BusState.LISTEN
    for e in j345.entities:
        if isinstance(e, ButtonEntity):
            with pytest.raises(TransmitForbidden):
                tub.press(e.key)
        elif isinstance(e, NumberEntity):
            with pytest.raises(TransmitForbidden):
                tub.set_number(e.key, 90)
    with pytest.raises(TransmitForbidden):
        tub.bus.enqueue(Frame(0x0A, 0xBF, 0x17, b"\x04"))
    tub.on_connect()
    assert drain(tub, 50) == [] and not tub.bus.queue


def test_transmit_enabled_sends_nothing_without_a_command(j345: TubDefinition) -> None:
    tub = Tub(j345, transmit=True)
    tub.on_connect()
    for _, _, frame, _, _ in LINES["D"]:
        assert tub.on_frame(frame) == []  # lazy: no hello at start-up


# --- 7-8. transmit reproduces the captured bytes -------------------------------------------

Action = tuple[str, str] | tuple[str, str, int] | None
ACTIONS: dict[int, Action] = {
    3: None,  # the connection check goes out by itself, before the first command
    8: ("set", "temperature_set_control", 90),
    10: ("set", "temperature_set_control", 100),
    13: ("set", "temperature_set_control", 101),
    17: ("press", "pump_2_button"),
    20: ("press", "pump_2_button"),
    22: ("press", "pump_1_button"),
    24: ("press", "pump_1_button"),
    26: ("press", "light_white_button"),
    29: ("press", "light_blue_button"),
    32: ("press", "light_green_button"),
    35: ("press", "light_orange_button"),
    38: ("press", "light_red_button"),
    41: ("press", "light_violet_button"),
    44: ("press", "light_aqua_button"),
    47: ("press", "light_white_button"),
    50: ("press", "light_yellow_button"),
    54: ("press", "light_amber_button"),
    57: ("set", "light_brightness", 0),
    60: ("press", "light_blue_button"),
    63: ("set", "light_brightness", 20),
    66: ("set", "light_brightness", 40),
    69: ("set", "light_brightness", 60),
    72: ("set", "light_brightness", 80),
    75: ("set", "light_brightness", 100),
    78: ("set", "light_brightness", 0),
}


def act(tub: Tub, action: Action) -> None:
    if action is None:
        return
    if action[0] == "press":
        tub.press(action[1])
    else:
        assert len(action) == 3
        tub.set_number(action[1], action[2])


def test_action_table_covers_every_sent_line() -> None:
    assert set(ACTIONS) == set(SENT) and len(SENT) == 26


@pytest.mark.parametrize("line", sorted(ACTIONS))
def test_emitted_frames_equal_the_captured_bytes(j345: TubDefinition, line: int) -> None:
    tub = Tub(j345, transmit=True)
    tub.on_connect()
    assert tub.on_frame(STATUS) == []  # the setpoint command needs one decoded status frame
    act(tub, ACTIONS[line] or ("press", "pump_1_button"))
    sent = drain(tub)
    assert sent[0] == HELLO == bytes.fromhex("7e070abf190100957e")  # S L3, first on a connection
    if ACTIONS[line] is not None:
        assert sent[1:] == [SENT[line]], f"S L{line}: {SENT[line].hex()}"


def emittable(definition: TubDefinition) -> set[bytes]:
    """Every frame the definition can make the tub model send, found by driving the model."""
    out: set[bytes] = set()
    actions: list[Action] = []
    for e in definition.entities:
        if isinstance(e, ButtonEntity):
            actions.append(("press", e.key))
        elif isinstance(e, NumberEntity):
            assert isinstance(e.control, DirectControl)
            actions += [("set", e.key, v) for v in range(int(e.min), int(e.max) + 1, int(e.step))]
            for v in (int(e.min) - 30, int(e.min) - 1, int(e.max) + 1, int(e.max) + 30):
                refused = Tub(definition, transmit=True)
                refused.on_frame(STATUS)
                with pytest.raises(ValueError, match="is outside"):  # refused, never clamped
                    refused.set_number(e.key, v)
                assert not refused.bus.queue
    for action in actions:
        tub = Tub(definition, transmit=True)
        tub.on_frame(STATUS)
        act(tub, action)
        out.update(drain(tub))
    for e in definition.entities:
        if isinstance(e, SwitchEntity):  # both targets: one of them differs from the state in STATUS
            for on in (True, False):
                tub = Tub(definition, transmit=True)
                tub.on_frame(STATUS)
                tub.set_switch(e.key, on)
                out.update(drain(tub, 60))
    return out


def test_nothing_else_can_be_emitted(j345: TubDefinition) -> None:
    can = emittable(j345)
    captured = set(SENT.values())
    assert captured <= can
    never_sent = {Frame(0x0A, 0xBF, 0x20, bytes([t])).encode() for t in range(80, 105) if t not in (90, 100, 101)}
    assert can - captured == never_sent  # the one extrapolation: the same 0x20 frame, other °F
    assert len(can) == 43


def test_only_documented_commands_exist(j345: TubDefinition) -> None:
    assert j345.buttons == {"pump_1": 0x04, "pump_2": 0x05}
    assert {c.type for c in j345.direct_commands.values()} == {0x19, 0x20, 0x21}
    assert j345.command_type == 0x17 and j345.command_encode == "plain"


# --- 9. closed loop against the mock --------------------------------------------------------


def run(tub: Tub, board: MockProlink, cycles: int = 4) -> None:
    for _ in range(cycles):
        pending = board.cycle()
        while pending:
            frame = pending.pop(0)
            for out in tub.on_frame(frame):
                pending[0:0] = board.receive(out)


def test_closed_loop(j345: TubDefinition) -> None:
    tub, board = Tub(j345, transmit=True), MockProlink()
    assert isinstance(tub.bus, DirectBusClient)
    tub.on_connect()
    run(tub, board)
    assert board.received == [] and tub.state.values["setpoint"] == 80

    assert tub.set_number("temperature_set_control", 90) == 90
    run(tub, board)
    assert [f.type for f in board.received] == [0x19, 0x20] and tub.bus.replies_seen == 1
    assert tub.state.values["setpoint"] == 90
    for outside in (120, 104.5, 79.9, 50):
        with pytest.raises(ValueError, match=r"is outside 80\.\.104"):
            tub.set_number("temperature_set_control", outside)
    assert tub.set_number("temperature_set_control", 104) == 104
    run(tub, board)
    assert tub.state.values["setpoint"] == 104
    assert tub.set_number("temperature_set_control", 80) == 80
    assert tub.set_number("temperature_set_control", 100.4) == 100
    run(tub, board, 6)
    assert tub.state.values["setpoint"] == 100

    for button, field in (("pump_1_button", "pump_1"), ("pump_2_button", "pump_2")):
        tub.press(button)
        run(tub, board)
        assert tub.state.values[field] is True
        tub.press(button)
        run(tub, board)
        assert tub.state.values[field] is False

    tub.press("light_blue_button")
    run(tub, board)
    has(tub.state.values, light_mode="blue", light_brightness=60, light_blue=255)
    assert tub.set_number("light_brightness", 47) == 40
    run(tub, board)
    has(tub.state.values, light_mode="blue", light_brightness=40)
    tub.set_number("light_brightness", 0)
    run(tub, board)
    has(tub.state.values, light_mode="off", light_brightness=0)
    assert [f.type for f in board.received].count(0x19) == 1  # one connection check per connection


def test_direct_command_bounds(j345: TubDefinition) -> None:
    cmd = j345.direct_commands["set_temperature"]
    assert cmd.build(104) == b"\x68" and cmd.build(80) == b"\x50"
    for bad in (105, 79, None, 90.5, True):
        with pytest.raises(ValueError, match="set_temperature"):
            cmd.build(bad)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="takes no value"):
        j345.direct_commands["light_red"].build(1)
    assert j345.direct_commands["connection_check"].build() == b"\x01\x00"


def test_setpoint_is_refused_unless_the_tub_reports_fahrenheit(
    j345: TubDefinition, caplog: pytest.LogCaptureFixture
) -> None:
    """The 0x20 byte is whole degrees F only while the topside is in Fahrenheit (PJ L394-397)."""
    assert j345.direct_commands["set_temperature"].requires == (("celsius_mode", False),)
    assert j345.fields["celsius_mode"].byte == 13 and j345.fields["celsius_mode"].bit == 0
    payload = bytearray(STATUS.payload)
    payload[13] |= 0x01
    celsius = Frame(STATUS.addr, STATUS.mid, STATUS.type, bytes(payload))

    tub = Tub(j345, transmit=True)
    tub.on_connect()
    with pytest.raises(CommandBlocked, match="celsius_mode not seen yet"):  # no status frame yet
        tub.set_number("temperature_set_control", 90)
    tub.on_frame(celsius)
    assert tub.state.values["celsius_mode"] is True
    with pytest.raises(CommandBlocked, match="celsius_mode is True"):
        tub.set_number("temperature_set_control", 80)
    cfg = discovery_config(load_config(None, env={}), j345)
    bridge = MqttBridge(tub, j345, cfg, MqttSettings(), client=FakeClient())
    with caplog.at_level("WARNING"):
        bridge.handle_command("spa2mqtt/jacuzzi_j345/temperature_set_control/set", "80")
    assert "celsius_mode is True" in caplog.text and "spa.transmit" not in caplog.text
    assert not tub.bus.queue and [out for _ in range(12) for out in tub.on_frame(celsius)] == []

    tub.press("pump_1_button")  # the other commands carry no unit and are not blocked
    tub.set_number("light_brightness", 0)
    assert [f.type for f in tub.bus.queue] == [0x17, 0x21]
    tub.bus.queue.clear()
    tub.on_frame(STATUS)  # back in Fahrenheit
    assert tub.set_number("temperature_set_control", 90) == 90
    assert [f.encode() for f in tub.bus.queue] == [SENT[8]]


# --- 10. spacing, queue limit, reconnect ------------------------------------------------------


def test_spacing_queue_limit_and_reconnect(j345: TubDefinition, caplog: pytest.LogCaptureFixture) -> None:
    tub = Tub(j345, transmit=True)
    assert isinstance(tub.bus, DirectBusClient) and j345.bus.send_gap_frames == 4
    tub.press("pump_1_button")
    tub.press("pump_2_button")
    sent_at: dict[int, bytes] = {}
    for i in range(1, 13):
        assert tub.on_frame(LIGHTS) == []  # lights frames neither trigger a send nor count
        for out in tub.on_frame(STATUS):
            sent_at[i] = out.encode()
    assert sent_at == {1: HELLO, 5: SENT[22], 9: SENT[17]}

    for _ in range(9):
        tub.press("pump_1_button")
    assert len(tub.bus.queue) == 8 and "command queue full" in caplog.text  # the ninth is dropped

    tub.on_connect()
    assert not tub.bus.queue and "dropping 8 queued command" in caplog.text
    assert drain(tub) == []
    tub.press("pump_2_button")
    assert drain(tub) == [HELLO, SENT[17]]  # the hello is sent again on the new connection


def test_no_hello_when_the_definition_drops_it(j345: TubDefinition) -> None:
    raw = raw_j345()
    del raw["bus"]["hello"]
    tub = Tub(parse_definition(raw), transmit=True)
    tub.press("pump_1_button")
    assert drain(tub) == [SENT[22]]


# --- 11. the app pipeline -----------------------------------------------------------------------


class FakeTransport:
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = chunks
        self.written: list[bytes] = []

    async def connect(self) -> None: ...

    async def read(self) -> bytes:
        return self.chunks.pop(0) if self.chunks else b""

    async def write(self, data: bytes) -> None:
        self.written.append(data)

    async def close(self) -> None: ...


async def test_pipeline_receive_only(j345: TubDefinition, tmp_path: Path) -> None:
    transport = ReplayTransport(write_log(tmp_path / "s.log", "S"), definition=j345)
    tub = Tub(j345, transmit=False)
    writer = BusWriter(transport, enabled=False)
    await transport.connect()
    tub.on_connect()
    await pump(transport, tub, writer)
    assert tub.state.status_frames == 13 and tub.state.values["setpoint"] == 101
    assert writer.frames_sent == 0 and transport.writes_attempted == 0


async def test_pipeline_writes_the_captured_bytes(j345: TubDefinition) -> None:
    transport = FakeTransport([STATUS.encode()] * 12)
    tub = Tub(j345, transmit=True)
    writer = BusWriter(transport, enabled=True)
    tub.on_connect()
    tub.on_frame(STATUS)
    tub.press("pump_1_button")
    tub.set_number("temperature_set_control", 90)
    await pump(transport, tub, writer)
    assert transport.written == [HELLO, SENT[22], SENT[8]]


# --- 12. Home Assistant ----------------------------------------------------------------------------


def test_ha_identity_and_commands(j345: TubDefinition) -> None:
    cfg = discovery_config(load_config(None, env={}), j345)
    assert (cfg.device_name, cfg.device_identifier) == ("Jacuzzi J345", "jacuzzi_j345")
    ents = {e.entity.key: e for e in build_discovery(j345, cfg)}
    temp = ents["current_temperature"].payload
    assert temp["device"] == {
        "identifiers": ["jacuzzi_j345"],
        "name": "Jacuzzi J345",
        "manufacturer": "Jacuzzi",
        "model": "J345",
        "sw_version": temp["device"]["sw_version"],
    }
    assert temp["unit_of_measurement"] == "°F"
    assert temp["state_topic"] == "spa2mqtt/jacuzzi_j345/current_temperature/state"
    num = ents["temperature_set_control"].payload
    assert (num["min"], num["max"], num["step"], num["unit_of_measurement"]) == (80.0, 104.0, 1.0, "°F")
    light = ents["light_brightness"].payload
    assert (light["min"], light["max"], light["step"]) == (0.0, 100.0, 20.0)
    assert len({e.config_topic for e in ents.values()}) == len(j345.entities)

    tub, client = Tub(j345, transmit=True), FakeClient()
    bridge = MqttBridge(tub, j345, cfg, MqttSettings(), client=client)
    tub.on_frame(STATUS)
    tub.on_frame(LIGHTS)
    state = {t: p for t, p, _ in client.published}
    assert state["spa2mqtt/jacuzzi_j345/current_temperature/state"] == "100"
    assert state["spa2mqtt/jacuzzi_j345/temperature_set_control/state"] == "80"
    assert state["spa2mqtt/jacuzzi_j345/light_mode/state"] == "off"
    assert state["spa2mqtt/jacuzzi_j345/light_brightness/state"] == "0"
    bridge.handle_command("spa2mqtt/jacuzzi_j345/temperature_set_control/set", "90")
    assert [f.encode() for f in tub.bus.queue] == [SENT[8]]
    bridge.handle_command("spa2mqtt/jacuzzi_j345/light_red_button/press", "PRESS")
    assert [f.encode() for f in tub.bus.queue] == [SENT[8], SENT[38]]

    for junk in ("nan", "inf", "-inf", "warm", "", "1e9", "105", "79", "-5"):  # never becomes a frame
        bridge.handle_command("spa2mqtt/jacuzzi_j345/temperature_set_control/set", junk)
    assert len(tub.bus.queue) == 2

    quiet = Tub(j345, transmit=False)
    MqttBridge(quiet, j345, cfg, MqttSettings(), client=FakeClient()).handle_command(
        "spa2mqtt/jacuzzi_j345/temperature_set_control/set", "90"
    )
    assert not quiet.bus.queue


def test_config_yml_still_overrides_the_identity(j345: TubDefinition, tmp_path: Path) -> None:
    p = tmp_path / "config.yml"
    p.write_text("ha:\n  device_name: Garden Tub\n  device_identifier: tub-1\n", encoding="utf-8")
    cfg = discovery_config(load_config(p, env={}), j345)
    assert (cfg.device_name, cfg.device_identifier) == ("Garden Tub", "tub-1")


# --- 13. monitor ------------------------------------------------------------------------------------


async def test_monitor_replays_d(j345: TubDefinition, tmp_path: Path) -> None:
    replay = ReplayTransport(write_log(tmp_path / "d.log", "D"), definition=j345)
    out = io.StringIO()
    mon = Monitor(j345, out, interval=1e9, clock=lambda: replay.current_time)
    await mon.run(replay, reconnect=False)  # raises if the tub model ever yields a frame
    mon.report()
    text = out.getvalue()
    assert "=== Jacuzzi J345" in text and "folded" not in text
    assert "  plain   06 23 75 05 19 02 00 64 fa 66" in text
    assert "change: Pump 1=on" in text and "change: Target Water Temperature=102" in text
    assert "crc errors 0" in text and "status frames 125" in text
    assert "status (plain)" in text and "presses seen none" in text
    assert mon.tub.transmit is False and not mon.tub.bus.queue


def test_monitor_record_to_stdout_round_trips(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    log = write_log(tmp_path / "d.log", "D")
    assert main(["monitor", "--replay", str(log), "-d", "jacuzzi_j345", "--record", "-", "--interval", "5"]) == 0
    out = capsys.readouterr().out
    assert "Jacuzzi J345" in out and "raw capture appended" not in out
    pasted = tmp_path / "portainer.log"  # what a user copies out of the container log view
    pasted.write_text(out, encoding="utf-8")
    got = b"".join(r.data for r in read_capture(pasted) if r.kind == "RX")
    assert got == b"".join(raw for _, _, _, raw, _ in LINES["D"])


# --- 14. every claim cites a line that exists ----------------------------------------------------------

CITATION = re.compile(r"\b(S|D|X1|X2|X3|PJ|JB)\b|\bL(\d+)\b")


def cited_lines(evidence: str) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    key: str | None = None
    for m in CITATION.finditer(evidence):
        if m.group(1):
            key = m.group(1)
        elif key in PLAIN_CAPTURES:
            out.append((key, int(m.group(2))))
        else:
            assert key is not None, f"line number without a source in {evidence!r}"
    return out


def test_every_field_and_command_has_status_and_checkable_evidence(j345: TubDefinition) -> None:
    claims: dict[str, tuple[str, str]] = {f"field {k}": (f.status, f.evidence) for k, f in j345.fields.items()}
    claims |= {f"command {k}": (c.status, c.evidence) for k, c in j345.direct_commands.items()}
    assert set(j345.button_meta) == set(j345.buttons)
    claims |= {f"button {k}": (b.status, b.evidence) for k, b in j345.button_meta.items()}
    frame_lines = {key: {no for no, *_ in lines} for key, lines in LINES.items()}
    checked = 0
    for name, (status, evidence) in claims.items():
        assert status in ("confirmed", "inferred", "hypothesis"), name
        assert evidence.strip(), f"{name} has no evidence"
        cites = cited_lines(evidence)
        if status == "confirmed":
            assert cites, f"{name} is 'confirmed' without a capture line"
        for key, no in cites:
            assert no in frame_lines[key], f"{name}: {key} L{no} holds no frame"
            checked += 1
    assert checked > 100
    # 'confirmed' commands are the ones S shows working; everything S never sent is not confirmed
    for key, cmd in j345.direct_commands.items():
        assert (cmd.status == "confirmed") == (key != "connection_check"), key


def test_sent_lines_cited_by_commands_are_tx_lines(j345: TubDefinition) -> None:
    for key, evidence in [(k, c.evidence) for k, c in j345.direct_commands.items()] + [
        (k, b.evidence) for k, b in j345.button_meta.items()
    ]:
        arrows = re.findall(r"L(\d+)->L(\d+)", evidence)
        assert arrows, key
        for tx, rx in arrows:
            assert int(tx) in SENT, f"{key}: S L{tx} is not a sent line"
            assert int(rx) not in SENT and int(rx) > int(tx)


# --- 15. loader: the semantic checks ---------------------------------------------------------------------


def raw_j345() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(
        (PLAIN_CAPTURES["S"].parents[4] / "definitions" / "jacuzzi_j345.yaml").read_text()
    )
    return data


def raw_j235() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(
        (PLAIN_CAPTURES["S"].parents[4] / "definitions" / "jacuzzi_j235.yaml").read_text()
    )
    return data


def ent(raw: dict[str, Any], key: str) -> dict[str, Any]:
    found: dict[str, Any] = next(e for e in raw["entities"] if e["key"] == key)
    return found


def direct(raw: dict[str, Any], key: str) -> dict[str, Any]:
    found: dict[str, Any] = raw["commands"]["direct"][key]
    return found


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        # 1. family
        (lambda r: r["status"].update(decode="fold"), "status.decode 'plain' and protocol 'jacuzzi_plain'"),
        (lambda r: r["commands"].update(encode="cc_xor"), "commands.encode 'plain' and protocol 'jacuzzi_plain'"),
        # 2. bus mode
        (lambda r: r["bus"].update(mode="claim"), "commands.encode 'plain' and bus.mode 'direct'"),
        (lambda r: r["bus"].pop("client_address"), "needs bus.client_address"),
        # 3. frames
        (lambda r: r["fields"]["light_mode"].update(frame="nope"), "unknown frame 'nope'"),
        (lambda r: r["fields"]["light_blue"].update(byte=28), "beyond lights length 28"),
        (lambda r: r["fields"]["hour"].update(byte=32), "beyond status length 32"),
        (lambda r: r["extra_frames"].update(status={"type": 0x24, "length": 4}), "'status' is reserved"),
        (lambda r: r["extra_frames"].update(more={"type": 0x16, "length": 4}), "own frame type"),
        # 4. direct command shape
        (lambda r: direct(r, "set_temperature").update(payload=["value", "value"]), "more than one value slot"),
        (lambda r: direct(r, "set_temperature").pop("min"), "needs min and max"),
        (lambda r: direct(r, "light_red").update(min=0, max=1), "no value slot"),
        (lambda r: direct(r, "set_temperature").update(min=105), "min <= max"),
        (lambda r: direct(r, "set_temperature").update(requires={"nope": False}), "requires unknown field"),
        (lambda r: direct(r, "set_temperature").update(requires={"setpoint": False}), "not a status bit field"),
        (lambda r: direct(r, "connection_check").update(requires={"celsius_mode": False}), "cannot have requires"),
        (lambda r: direct(r, "set_temperature").update(requires={"celsius_mode": 0}), "schema"),
        # 5. names
        (lambda r: r["commands"]["direct"].update(pump_1=dict(direct(r, "light_red"))), "both a button and a direct"),
        # 6. press
        (lambda r: ent(r, "pump_1_button").update(press="nope"), "references unknown button 'nope'"),
        (lambda r: ent(r, "pump_1_button").update(press="set_temperature"), "it needs a value"),
        # 7. direct number
        (lambda r: ent(r, "temperature_set_control")["control"].update(command="nope"), "unknown direct command"),
        (lambda r: ent(r, "temperature_set_control")["control"].update(command="light_red"), "with a value slot"),
        (lambda r: r["fields"]["setpoint"].update(scale=0.5), "plain one-byte field"),
        (lambda r: r["fields"]["setpoint"].update(mask=0x7F), "plain one-byte field"),
        (lambda r: ent(r, "temperature_set_control").update(field="clearray_days"), "plain one-byte field"),
        (lambda r: ent(r, "temperature_set_control").update(step=0.5), "integer min, max and step"),
        (lambda r: ent(r, "temperature_set_control").update(max=105), "outside direct command"),
        (lambda r: ent(r, "temperature_set_control").update(min=79), "outside direct command"),
        # 8. hello
        (lambda r: r["bus"].update(hello="set_temperature"), "bus.hello"),
        (lambda r: r["bus"].update(hello="pump_1"), "bus.hello"),
        # 9. units
        (lambda r: ent(r, "current_temperature").update(unit_of_measurement="°C"), "does not match temperature_unit"),
        (lambda r: r.update(temperature_unit="C"), "does not match temperature_unit"),
        # schema
        (lambda r: r["commands"]["buttons"]["pump_1"].pop("status"), "schema"),
        (lambda r: direct(r, "light_red").pop("status"), "schema"),
        (lambda r: direct(r, "set_temperature").update(max=300), "schema"),
        (lambda r: r["bus"].update(send_gap_frames=0), "schema"),
    ],
)
def test_broken_plain_definitions_are_rejected(mutate: Any, message: str) -> None:
    raw = copy.deepcopy(raw_j345())
    mutate(raw)
    with pytest.raises(DefinitionError, match=message):
        parse_definition(raw)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda r: r["status"].update(decode="plain"), "status.decode 'plain' and protocol 'jacuzzi_plain'"),
        (lambda r: r["commands"].update(encode="plain"), "commands.encode 'plain' and protocol 'jacuzzi_plain'"),
        (lambda r: r["bus"].update(mode="direct", client_address=0x0A), "go together"),
        (lambda r: r["commands"].update(direct={"x": {"type": 0x20, "payload": [1], "status": "hypothesis"}}), "only"),
        (lambda r: r.update(extra_frames={"lights": {"type": 0xCA, "length": 8}}), "extra_frames is only allowed"),
        (lambda r: r.update(protocol="jacuzzi_plain"), "go together"),
    ],
)
def test_encrypted_definitions_cannot_use_the_plain_features(mutate: Any, message: str) -> None:
    raw = copy.deepcopy(raw_j235())
    mutate(raw)
    with pytest.raises(DefinitionError, match=message):
        parse_definition(raw)


def test_identity_defaults(j345: TubDefinition, j235: TubDefinition) -> None:
    assert (j345.device_name, j345.device_identifier) == ("Jacuzzi J345", "jacuzzi_j345")
    assert (j235.device_name, j235.device_identifier) == ("Jacuzzi J235", "185569045")
    raw = raw_j345()
    raw["ha"] = {"device_name": "Tub", "device_identifier": "abc"}
    d = parse_definition(raw)
    assert (d.device_name, d.device_identifier) == ("Tub", "abc")
