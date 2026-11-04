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
    assert (v["hour"], v["minute"], v["day_of_month"], v["month_low_bits"], v["year"]) == (11, 38, 16, 5, 2025)
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
    assert tub.state.values["day_of_week"] == 3  # Wednesday 4 Nov 2026
    assert tub.state.values["year"] == 2026


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


@pytest.mark.parametrize("path", DECODED, ids=lambda p: p.name)
def test_decoded_csv_roundtrip_and_clock(j235: TubDefinition, path: Path) -> None:
    rows = [bytes(map(int, r)) for r in csv.reader(path.open()) if r]
    dec = FrameDecoder()
    frames: list[Frame] = []
    for rec in read_capture(path):
        frames += dec.feed(rec.data)
    assert [fold(f.payload) for f in frames] == rows
    run_tub(j235, frames)
    epoch = _epoch(path)
    if epoch is not None:
        first = j235.decode_status(rows[0])
        wall = dt.datetime.fromtimestamp(epoch, dt.UTC)
        tub_minutes = int(first["hour"]) * 60 + int(first["minute"])  # type: ignore[call-overload]
        wall_minutes = wall.hour * 60 + wall.minute
        assert 0 <= tub_minutes - wall_minutes <= 5  # tub on GMT, ~3 min fast in May 2025
        assert first["day_of_month"] == wall.day
        assert first["month_low_bits"] == wall.month & 7
        assert first["day_of_week"] == (wall.weekday() + 1) % 7  # 0 = Sunday
        assert first["year"] == wall.year


def test_d2_heating_window(j235: TubDefinition) -> None:
    path = next(p for p in DECODED if "debug_messages_old" in p.name)
    rows = [j235.decode_status(bytes(map(int, r))) for r in csv.reader(path.open()) if r]
    assert all(r["heater"] for r in rows[:46])  # 37.5 °C, below the 38.0 setpoint
    assert all(r["water_temperature"] < r["setpoint"] for r in rows[:46])  # type: ignore[operator]
    assert not any(r["heater"] for r in rows[51:])
    assert all(r["pump_1_speed"] == "low" and r["pump_1_running"] for r in rows[:277])
    assert all(r["pump_1_speed"] == "off" for r in rows[277:8752])


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
