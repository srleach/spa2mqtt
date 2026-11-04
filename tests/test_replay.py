"""Replay the captured dumps through the real pipeline (ground truth: docs/protocol.md §0)."""

from __future__ import annotations

import csv
import datetime as dt
import re
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from spa2mqtt.app import pump
from spa2mqtt.captures import read_capture
from spa2mqtt.definitions import TubDefinition
from spa2mqtt.protocol import Frame, FrameDecoder, fold
from spa2mqtt.transport import ReplayTransport, TransmitForbidden
from spa2mqtt.tub import BusWriter, Tub

from .conftest import DECODED, RAW_D1, RAW_D7, frames_of


def run_tub(definition: TubDefinition, frames: list[Frame]) -> tuple[Tub, list[dict[str, Any]]]:
    tub = Tub(definition, transmit=False)
    events: list[dict[str, Any]] = []
    tub.subscribe(lambda changed: events.append(dict(changed)))
    for f in frames:
        assert tub.on_frame(f) == []  # receive-only: never anything to send
    return tub, events


def sequence(events: list[dict[str, Any]], key: str) -> list[Any]:
    return [e[key] for e in events if key in e]


# --- D1: the only raw frames from 2025 -------------------------------------------------


def test_d1_state(j235: TubDefinition) -> None:
    tub, _ = run_tub(j235, frames_of(RAW_D1))
    v = tub.state.values
    assert (v["hour"], v["minute"], v["day_of_month"], v["month"], v["year"]) == (11, 38, 16, 5, 2025)
    assert v["water_temperature"] == 38.0
    assert v["setpoint"] == 38.0
    assert v["heater"] is False


# --- D7: owner's labelled raw capture, 2026-11-04 ----------------------------------------


def test_d7_census(d7_frames: list[Frame]) -> None:
    c = Counter((f.addr, f.mid, f.type) for f in d7_frames)
    assert c == {
        (0x10, 0xBF, 0x06): 24177,
        (0x10, 0xBF, 0xCC): 24177,
        (0xFE, 0xBF, 0x00): 542,
        (0xFF, 0xAF, 0xC4): 1804,
        (0xFF, 0xAF, 0xCA): 542,
    }


def test_d7_pumps_follow_topside_presses(j235: TubDefinition, d7_frames: list[Frame]) -> None:
    _, events = run_tub(j235, d7_frames)
    # owner marks: p1 press 1/2/3, accidental p1 x3, p2 x2, then heating starts pump 1 low
    assert sequence(events, "pump_1_speed") == ["off", "low", "high", "off", "low", "high", "off", "low"]
    assert sequence(events, "pump_2") == [False, True, False]
    assert sequence(events, "pump_1_running") == [False, True, False, True, False, True]


def test_d7_setpoint_and_heater(j235: TubDefinition, d7_frames: list[Frame]) -> None:
    tub, events = run_tub(j235, d7_frames)
    assert sequence(events, "setpoint") == [38.5, 39.0, 38.5, 39.0, 39.5, 40.0, 39.5, 39.0, 38.5]
    assert sequence(events, "heater") == [False, True]
    assert tub.state.values["water_temperature"] in (38.0, 38.5)
    v = tub.state.values
    assert (v["day_of_week"], v["day_of_month"], v["month"], v["year"]) == (3, 4, 11, 2026)  # Wed 4 Nov 2026


def test_d7_panel_button_codes(j235: TubDefinition, d7_frames: list[Frame]) -> None:
    tub, _ = run_tub(j235, d7_frames)
    codes = Counter(code for ch, code in tub.bus.observed_presses)
    assert set(codes) <= {0x01, 0x02, 0x04, 0x05, 0x12}
    assert tub.bus.polled_channels == {0x10}
    assert tub.bus.active_channels == {0x10}
    assert tub.bus.channel is None


def test_d7_set_mode_precedes_setpoint_change(j235: TubDefinition, d7_frames: list[Frame]) -> None:
    _, events = run_tub(j235, d7_frames)
    in_set_mode = False
    for e in events:
        in_set_mode = e.get("set_mode", in_set_mode)
        if "setpoint" in e and len(events) and e is not events[0]:
            assert in_set_mode, "setpoint changed outside set mode"


# --- D2-D6: decoded CSVs, re-encoded to synthetic frames ---------------------------------


def _epoch(path: Path) -> float | None:
    m = re.search(r"epoch(\d+)", path.name)
    return float(m.group(1)) if m else None


def _csv_frames(path: Path, definition: TubDefinition) -> list[Frame]:
    dec = FrameDecoder()
    frames: list[Frame] = []
    for rec in read_capture(path, definition=definition):
        frames += dec.feed(rec.data)
    return frames


@pytest.mark.parametrize("path", DECODED, ids=lambda p: p.name)
def test_decoded_csv_roundtrip_and_clock(j235: TubDefinition, path: Path) -> None:
    rows = [bytes(map(int, r)) for r in csv.reader(path.open()) if r]
    frames = _csv_frames(path, j235)
    assert [fold(f.payload) for f in frames] == rows  # rebuilt frames fold back to the logged values
    epoch = _epoch(path)
    if epoch is not None:
        first = j235.decode_status(j235.decode_payload(frames[0].payload))
        wall = dt.datetime.fromtimestamp(epoch, dt.UTC)
        tub_minutes = int(first["hour"]) * 60 + int(first["minute"])  # type: ignore[call-overload]
        wall_minutes = wall.hour * 60 + wall.minute
        assert 0 <= tub_minutes - wall_minutes <= 5  # tub on GMT, ~3 min fast in May 2025
        assert first["day_of_month"] == wall.day
        assert first["month"] == wall.month
        assert first["day_of_week"] == (wall.weekday() + 1) % 7  # 0 = Sunday
        assert first["year"] == wall.year


def test_d2_heating_window(j235: TubDefinition) -> None:
    path = next(p for p in DECODED if "debug_messages_old" in p.name)
    rows = [j235.decode_status(j235.decode_payload(f.payload)) for f in _csv_frames(path, j235)]
    assert all(r["heater"] for r in rows[:46])  # 37.5 °C, below the 38.0 setpoint
    assert all(r["water_temperature"] < r["setpoint"] for r in rows[:46])  # type: ignore[operator]
    assert not any(r["heater"] for r in rows[51:])
    assert all(r["pump_1_speed"] == "low" and r["pump_1_running"] for r in rows[:277])
    assert all(r["pump_1_speed"] == "off" for r in rows[277:8752])


# --- per-byte decoding against frames from other tubs (protocol.md §3.3) -----------------

FOREIGN = [
    # Sundance 780 sample in HyperActiveJ's sundanceRS485.py (fc38ab5), °F
    (
        "7E26FFAFC4AEA7AAABA4A1C95DA5A1C2A19CBDCEBBE2B9BBADB4B5A7B7DFB1B29BD38D8E8F88F97E",
        (14, 17, 4, 14, 4, 2022, 96, 90),
    ),
    # dhmsjs/pyjacuzzi jacuzzi.py, labelled by its author "05/18/23 2:40PM, WS 103, WT 102", °F
    (
        "7e26ffafc4a2aba6a7a8ad0251abadc8ad90b122b6d3b5b7a0b8bc92bb14bdbedee681828384f07e",
        (14, 40, 4, 18, 5, 2023, 102, 103),
    ),
]


@pytest.mark.parametrize(("hexframe", "expected"), FOREIGN)
def test_per_byte_offsets_hold_on_other_tubs(j235: TubDefinition, hexframe: str, expected: tuple[int, ...]) -> None:
    (frame,) = FrameDecoder().feed(bytes.fromhex(hexframe))
    v = j235.decode_status(j235.decode_payload(frame.payload))
    got = (
        v["hour"],
        v["minute"],
        v["day_of_week"],
        v["day_of_month"],
        v["month"],
        v["year"],
        int(v["water_temperature"] * 2),
        int(v["setpoint"] * 2),
    )  # type: ignore[operator]
    assert got == expected


def test_per_byte_agrees_with_fold_on_every_raw_frame(j235: TubDefinition) -> None:
    """Fields read per byte give the old fold result wherever the fold was right."""
    from spa2mqtt.definitions.model import FieldDef

    fold_map = {  # the previous fold-based J235 definition (spa2mqtt 2.0.0)
        "hour": FieldDef("hour", 0, "confirmed", xor=6),
        "minute": FieldDef("minute", 11, "confirmed"),
        "water": FieldDef("water", 5, "confirmed", xor=2),
        "setpoint": FieldDef("setpoint", 8, "confirmed"),
        "heater": FieldDef("heater", 10, "confirmed", bit=6),
        "p1": FieldDef("p1", 1, "confirmed", bit=6),
        "p2": FieldDef("p2", 1, "confirmed", bit=2),
        "speed": FieldDef("speed", 2, "confirmed", shift=3, mask=3),
        "set": FieldDef("set", 2, "confirmed", bit=5),
        "dow": FieldDef("dow", 2, "confirmed", mask=7),
        "year": FieldDef("year", 9, "confirmed"),
    }
    for path in (RAW_D1, RAW_D7):
        for f in frames_of(path):
            if f.type != 0xC4:
                continue
            old = {k: d.decode(fold(f.payload)) for k, d in fold_map.items()}
            new = j235.decode_status(j235.decode_payload(f.payload))
            assert (new["hour"], new["minute"]) == (old["hour"], old["minute"])
            assert (new["water_temperature"], new["setpoint"]) == (int(old["water"]) / 2, int(old["setpoint"]) / 2)  # type: ignore[call-overload]
            assert (new["heater"], new["pump_1_running"], new["pump_2"], new["set_mode"]) == (
                old["heater"],
                old["p1"],
                old["p2"],
                old["set"],
            )
            assert new["pump_1_speed"] == ["off", "low", "high"][int(old["speed"])]  # type: ignore[call-overload]
            assert (new["day_of_week"], new["year"]) == (old["dow"], 2000 + int(old["year"]))  # type: ignore[call-overload]


# --- full async pipeline -----------------------------------------------------------------


async def test_pipeline_replay_never_writes(j235: TubDefinition) -> None:
    transport = ReplayTransport(RAW_D7)
    await transport.connect()
    tub = Tub(j235, transmit=False)
    writer = BusWriter(transport, enabled=False)
    await pump(transport, tub, writer)
    assert tub.state.status_frames == 1804
    assert writer.frames_sent == 0
    assert transport.writes_attempted == 0
    with pytest.raises(TransmitForbidden):
        await transport.write(b"\x7e")
