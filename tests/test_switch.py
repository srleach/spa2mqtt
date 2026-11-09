"""Pump switches: a toggle button pressed until the state reads right. No real bus involved."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from spa2mqtt.definitions import DefinitionError, TubDefinition
from spa2mqtt.definitions.loader import parse_definition
from spa2mqtt.definitions.model import SwitchEntity
from spa2mqtt.ha import DiscoveryConfig, build_discovery
from spa2mqtt.ha.bridge import MqttBridge, MqttSettings
from spa2mqtt.transport import TransmitForbidden
from spa2mqtt.tub import Tub
from spa2mqtt.tub.control import ToggleController

from .mockboard import MockBoard
from .mockprolink import MockProlink
from .test_bus_control import run
from .test_ha import FakeClient
from .test_plain_j345 import run as run_prolink

ROOT = Path(__file__).resolve().parents[1]
PUMP_1, PUMP_2, LIGHT = 0x04, 0x05, 0x12


def codes(board: MockBoard) -> list[int]:
    return [code for _, code in board.presses]


# -- J235: claiming bus, pump 1 cycles off -> low -> high -> off ------------------------


def test_switch_refused_when_transmit_disabled(j235: TubDefinition) -> None:
    tub = Tub(j235, transmit=False)
    with pytest.raises(TransmitForbidden):
        tub.set_switch("pump_1_switch", True)
    board = MockBoard()
    run(tub, board, 30)
    assert board.presses == [] and board.assigned == []


def test_two_state_pump_takes_one_press_each_way(j235: TubDefinition) -> None:
    tub = Tub(j235, transmit=True)
    board = MockBoard()
    run(tub, board, 5)
    tub.set_switch("pump_2_switch", True)
    run(tub, board, 40)
    assert codes(board) == [PUMP_2] and board.pump2
    assert tub.switches["pump_2_switch"].target is None
    tub.set_switch("pump_2_switch", False)
    run(tub, board, 40)
    assert codes(board) == [PUMP_2, PUMP_2] and not board.pump2


def test_no_press_when_the_state_already_matches(j235: TubDefinition) -> None:
    tub = Tub(j235, transmit=True)
    board = MockBoard(pump2=True)
    run(tub, board, 5)
    tub.set_switch("pump_2_switch", True)
    tub.set_switch("pump_1_switch", False)
    run(tub, board, 40)
    assert board.presses == [] and board.assigned == []  # not even a channel claim


@pytest.mark.parametrize(
    ("key", "start", "presses", "end"),
    [
        ("pump_1_switch", 0, 2, 2),  # Pump 1 is the jets: off -> low -> high
        ("pump_1_switch", 1, 1, 2),
        ("pump_1_low_switch", 0, 1, 1),
        ("pump_1_low_switch", 2, 2, 1),  # high -> off -> low
    ],
)
def test_pump_1_on_steps_to_its_speed(j235: TubDefinition, key: str, start: int, presses: int, end: int) -> None:
    tub = Tub(j235, transmit=True)
    board = MockBoard(pump1=start)
    run(tub, board, 5)
    tub.set_switch(key, True)
    run(tub, board, 40)
    assert codes(board) == [PUMP_1] * presses and board.pump1 == end


def test_pump_1_off_from_high_is_one_press(j235: TubDefinition) -> None:
    tub = Tub(j235, transmit=True)
    board = MockBoard(pump1=2)
    run(tub, board, 5)
    tub.set_switch("pump_1_switch", False)
    run(tub, board, 40)
    assert codes(board) == [PUMP_1] and board.pump1 == 0


def test_pump_1_jets_ignore_the_low_speed(j235: TubDefinition) -> None:
    """The board runs pump 1 low to heat or filter: the jets switch reads off and is not pressed."""
    tub = Tub(j235, transmit=True)
    board = MockBoard(pump1=1)
    run(tub, board, 5)
    assert tub.state.values["pump_1_high"] is False and tub.state.values["pump_1_low"] is True
    tub.set_switch("pump_1_switch", False)
    run(tub, board, 40)
    assert board.presses == [] and board.pump1 == 1


@pytest.mark.parametrize(("start", "presses"), [(1, 2), (2, 1)])
def test_pump_1_low_off_steps_through_the_cycle(j235: TubDefinition, start: int, presses: int) -> None:
    """Off is pump 1 fully off (off_field), so from low it passes through high."""
    tub = Tub(j235, transmit=True)
    board = MockBoard(pump1=start)
    run(tub, board, 5)
    tub.set_switch("pump_1_low_switch", False)
    run(tub, board, 40)
    assert codes(board) == [PUMP_1] * presses and board.pump1 == 0


def test_speed_change_lets_the_second_press_follow_at_once(j235: TubDefinition) -> None:
    """low -> high leaves pump 1 running; the speed shows that the press landed."""
    tub = Tub(j235, transmit=True)
    board = MockBoard(pump1=1)
    run(tub, board, 5)
    tub.set_switch("pump_1_low_switch", False)
    run(tub, board, 9)  # fewer cycles than one confirm window (claim + two presses)
    assert codes(board) == [PUMP_1, PUMP_1] and board.pump1 == 0


def test_lost_press_is_retried_only_after_the_confirm_window(j235: TubDefinition) -> None:
    tub = Tub(j235, transmit=True)
    board = MockBoard(ignore_presses=1)
    run(tub, board, 5)
    tub.set_switch("pump_2_switch", True)
    run(tub, board, 8)
    assert codes(board) == [PUMP_2] and not board.pump2  # waiting, not pressing again
    run(tub, board, 40)
    assert codes(board) == [PUMP_2, PUMP_2] and board.pump2


def test_switch_gives_up_after_max_presses(j235: TubDefinition, caplog: pytest.LogCaptureFixture) -> None:
    """Pump 1 held on by the board (heating): presses do nothing, and the switch stops."""
    tub = Tub(j235, transmit=True)
    board = MockBoard(pump1=1, ignore_presses=99)
    run(tub, board, 5)
    tub.set_switch("pump_1_low_switch", False)
    run(tub, board, 200)
    assert codes(board) == [PUMP_1] * 3
    assert tub.switches["pump_1_low_switch"].target is None
    assert "did not turn off after 3 presses" in caplog.text


# -- J235 light: CA frame, button steps the colour within a few seconds, else toggles -------


def test_light_state_comes_from_the_lights_frame(j235: TubDefinition) -> None:
    tub = Tub(j235, transmit=False)
    run(tub, MockBoard(light_mode=0x02), 5)
    assert (tub.state.values["light_on"], tub.state.values["light_mode"]) == (True, "blue")
    run(tub, MockBoard(), 5)
    assert (tub.state.values["light_on"], tub.state.values["light_mode"]) == (False, "off")


def test_light_on_and_off_after_a_pause_take_one_press_each(j235: TubDefinition) -> None:
    tub = Tub(j235, transmit=True)
    board = MockBoard()
    run(tub, board, 5)
    tub.set_switch("light_switch", True)
    run(tub, board, 40)
    assert codes(board) == [LIGHT] and tub.state.values["light_mode"] == "blend"
    tub.set_switch("light_switch", False)
    run(tub, board, 40)
    assert codes(board) == [LIGHT, LIGHT] and board.light_mode == 0


def test_light_off_soon_after_on_waits_out_the_step_window(j235: TubDefinition) -> None:
    """A press inside the window only steps the colour; the retry comes after it, and turns off."""
    tub = Tub(j235, transmit=True)
    board = MockBoard()
    run(tub, board, 5)
    tub.set_switch("light_switch", True)
    run(tub, board, 6)
    assert board.light_mode == 0x80
    tub.set_switch("light_switch", False)
    run(tub, board, 60)
    assert codes(board) == [LIGHT, LIGHT, LIGHT] and board.light_mode == 0
    assert tub.switches["light_switch"].target is None


def test_new_target_replaces_the_old_one(j235: TubDefinition) -> None:
    tub = Tub(j235, transmit=True)
    board = MockBoard()
    run(tub, board, 5)
    tub.set_switch("pump_2_switch", True)
    tub.set_switch("pump_2_switch", False)  # changed their mind before anything was sent
    run(tub, board, 40)
    assert board.presses == []


def test_toggle_controller_waits_for_a_queued_press() -> None:
    sent: list[int] = []
    queued = True
    ctl = ToggleController(lambda: sent.append(1), confirm_frames=2, max_presses=3, press_queued=lambda: queued)
    ctl.set_target(True)
    for _ in range(20):
        ctl.on_status(False)
    assert sent == [1]  # still waiting for a bus slot: the confirm window has not started
    queued = False
    ctl.on_status(False)
    ctl.on_status(False)
    assert sent == [1, 1]
    ctl.on_status(None)  # an unreadable state never presses
    ctl.on_status(True)
    assert ctl.target is None


# -- J345: direct bus, one frame and no retry -------------------------------------------


def test_j345_switch_sends_one_captured_frame(j345: TubDefinition) -> None:
    tub = Tub(j345, transmit=True)
    board = MockProlink()
    run_prolink(tub, board)
    tub.set_switch("pump_1_switch", True)
    run_prolink(tub, board, 8)
    sent = [f.encode().hex() for f in board.received]
    assert sent == ["7e070abf190100957e", "7e060abf17049c7e"]  # hello, then S L22 (pump 1)
    assert board.pump1 and tub.state.values["pump_1"] is True
    tub.set_switch("pump_1_switch", True)  # already on: nothing more
    tub.set_switch("pump_2_switch", False)  # already off
    run_prolink(tub, board, 8)
    assert len(board.received) == 2


def test_j345_switch_never_retries(j345: TubDefinition) -> None:
    sw = j345.entity("pump_2_switch")
    assert isinstance(sw, SwitchEntity) and sw.max_presses == 1

    class Deaf(MockProlink):
        def receive(self, frame: Any) -> list[Any]:
            self.received.append(frame)
            return []

    tub = Tub(j345, transmit=True)
    board = Deaf()
    run_prolink(tub, board)
    tub.set_switch("pump_2_switch", True)
    run_prolink(tub, board, 40)
    assert [f.type for f in board.received] == [0x19, 0x17]
    assert tub.switches["pump_2_switch"].target is None


# -- Home Assistant ---------------------------------------------------------------------


def test_switch_discovery_and_commands(j235: TubDefinition, caplog: pytest.LogCaptureFixture) -> None:
    by_key = {e.entity.key: e for e in build_discovery(j235, DiscoveryConfig())}
    sw = by_key["pump_1_switch"]
    assert sw.config_topic == "homeassistant/switch/Jacuzzi-J235/Pump-1/config"
    assert sw.payload["state_topic"] == sw.state_topic == "spa2mqtt/jacuzzi_j235/pump_1_switch/state"
    assert sw.payload["command_topic"] == "spa2mqtt/jacuzzi_j235/pump_1_switch/set"
    assert (sw.payload["payload_on"], sw.payload["payload_off"]) == ("ON", "OFF")
    assert {"topic": "spa2mqtt/jacuzzi_j235/control/availability"} in sw.payload["availability"]

    tub = Tub(j235, transmit=True)
    client = FakeClient()
    bridge = MqttBridge(tub, j235, DiscoveryConfig(), MqttSettings(), client=client)
    board = MockBoard()
    run(tub, board, 3)
    assert ("spa2mqtt/jacuzzi_j235/pump_1_switch/state", "OFF", False) in client.published
    bridge.handle_command("spa2mqtt/jacuzzi_j235/pump_1_switch/set", "ON")
    run(tub, board, 20)
    assert ("spa2mqtt/jacuzzi_j235/pump_1_switch/state", "ON", False) in client.published
    bridge.handle_command("spa2mqtt/jacuzzi_j235/pump_1_switch/set", "toggle")
    assert "bad payload 'toggle'" in caplog.text
    run(tub, board, 20)
    assert codes(board) == [PUMP_1, PUMP_1]  # off -> low -> high


def test_switch_commands_ignored_when_transmit_disabled(j235: TubDefinition, caplog: pytest.LogCaptureFixture) -> None:
    tub = Tub(j235, transmit=False)
    bridge = MqttBridge(tub, j235, DiscoveryConfig(), MqttSettings(), client=FakeClient())
    bridge.handle_command("spa2mqtt/jacuzzi_j235/pump_2_switch/set", "ON")
    assert tub.switches["pump_2_switch"].target is None
    assert "transmit" in caplog.text


# -- definition rules -------------------------------------------------------------------


def raw(name: str) -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load((ROOT / "definitions" / f"{name}.yaml").read_text(encoding="utf-8"))
    return copy.deepcopy(data)


def switch(data: dict[str, Any], key: str) -> dict[str, Any]:
    found: dict[str, Any] = next(e for e in data["entities"] if e["key"] == key)
    return found


@pytest.mark.parametrize(
    ("name", "mutate", "message"),
    [
        ("jacuzzi_j235", lambda s: s.update(field="setpoint"), "needs a bit field"),
        ("jacuzzi_j235", lambda s: s.update(field="nope"), "unknown field 'nope'"),
        ("jacuzzi_j235", lambda s: s.update(press="nope"), "unknown button 'nope'"),
        ("jacuzzi_j235", lambda s: s.update(progress_field="nope"), "unknown field 'nope'"),
        ("jacuzzi_j235", lambda s: s.update(off_field="nope"), "unknown field 'nope'"),
        ("jacuzzi_j235", lambda s: s.update(off_field="pump_1_speed"), "off_field must be a bit field"),
        ("jacuzzi_j235", lambda s: s.update(max_presses=0), "schema violation"),
        ("jacuzzi_j235", lambda s: s.update(retries=2), "schema violation"),
        ("jacuzzi_j345", lambda s: s.update(max_presses=2), "max_presses must be 1 with bus.mode direct"),
        ("jacuzzi_j345", lambda s: s.update(press="set_temperature"), "it needs a value"),
    ],
)
def test_broken_switches_are_rejected(name: str, mutate: Any, message: str) -> None:
    data = raw(name)
    mutate(switch(data, "pump_1_switch"))
    with pytest.raises(DefinitionError, match=message):
        parse_definition(data, "test")
