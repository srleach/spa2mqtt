"""The read-only monitor (spa2mqtt monitor)."""

from __future__ import annotations

import ast
import io
import json
from pathlib import Path

import pytest

from spa2mqtt.__main__ import main
from spa2mqtt.captures import read_capture
from spa2mqtt.definitions import TubDefinition
from spa2mqtt.monitor import Monitor, ReadOnlyTransport
from spa2mqtt.transport import ReplayTransport, TransmitForbidden

from .conftest import RAW_D7

ROOT = Path(__file__).resolve().parents[1]


async def _run(j235: TubDefinition, **kw: object) -> tuple[Monitor, str]:
    replay = ReplayTransport(RAW_D7)
    out = io.StringIO()
    mon = Monitor(j235, out, clock=lambda: replay.current_time, **kw)  # type: ignore[arg-type]
    await mon.run(replay, reconnect=False)
    return mon, out.getvalue()


async def test_monitor_replays_d7(j235: TubDefinition) -> None:
    mon, text = await _run(j235, interval=60.0)
    # one report at the first status frame, then one per >= 60 s; reports fire on chunk
    # boundaries, so they drift late and the 541 s capture yields 8 or 9 periodic ones
    assert text.count("read-only, nothing is transmitted") in (9, 10)
    assert text.count("panel press on channel 0x10: pump_1 (0x04)") == 6
    assert text.count("panel press on channel 0x10: pump_2 (0x05)") == 2
    assert "change: Heater Active=on" in text
    assert "Secondary Value Raw=" not in text.split("===")[0]  # diagnostic noise stays out of change lines
    assert "crc errors 0" in text
    assert mon.tub.bus.channel is None and mon.tub.transmit is False


async def test_monitor_records_exactly_what_it_read(j235: TubDefinition, tmp_path: Path) -> None:
    rec = tmp_path / "rec.log"
    with rec.open("w", encoding="ascii") as fh:
        await _run(j235, interval=1e9, record=fh)
    got = b"".join(r.data for r in read_capture(rec) if r.kind == "RX")
    want = b"".join(r.data for r in read_capture(RAW_D7) if r.kind == "RX")
    assert got == want


async def test_monitor_json_lines(j235: TubDefinition) -> None:
    _, text = await _run(j235, interval=120.0, as_json=True)
    events = [json.loads(line) for line in text.splitlines()]
    kinds = {e["event"] for e in events}
    assert kinds == {"status", "change", "press"}
    first = next(e for e in events if e["event"] == "status")
    assert first["values"]["water_temperature"] == 38.5 and first["transmit"] is False


async def test_read_only_transport_refuses_writes() -> None:
    guarded = ReadOnlyTransport(ReplayTransport(RAW_D7))
    with pytest.raises(TransmitForbidden):
        await guarded.write(b"\x7e")


def test_monitor_cli_replay(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["monitor", "--replay", str(RAW_D7), "--interval", "1000", "--quiet-changes"]) == 0
    out = capsys.readouterr().out
    assert "Read-only: transmit is disabled and nothing is published" in out
    assert "change:" not in out


def test_monitor_cli_needs_a_source(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["monitor"]) == 2


def test_monitor_module_cannot_send() -> None:
    src = (ROOT / "spa2mqtt" / "monitor.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names}
    assert "BusWriter" not in imported
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "write":
            target = ast.unparse(node.func.value)
            assert "transport" not in target and "_inner" not in target, target
