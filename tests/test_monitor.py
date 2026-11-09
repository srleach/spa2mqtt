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
from spa2mqtt.monitor import FrameLog, Monitor, ReadOnlyTransport
from spa2mqtt.protocol import Frame
from spa2mqtt.transport import ReplayTransport, TransmitForbidden
from spa2mqtt.tub import Tub

from .conftest import RAW_D7, frames_of

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


# -- spa2mqtt capture ---------------------------------------------------------------------


async def _capture(j235: TubDefinition, **kw: object) -> tuple[FrameLog, str]:
    replay = ReplayTransport(RAW_D7)
    out = io.StringIO()
    frames = FrameLog(j235, out, clock=lambda: replay.current_time, **kw)  # type: ignore[arg-type]
    await frames.run(replay, reconnect=False)
    return frames, out.getvalue()


async def test_capture_leaves_out_repeats(j235: TubDefinition) -> None:
    frames, text = await _capture(j235)
    lines = text.splitlines()
    assert frames.decoder.stats.frames == 51242
    assert frames.shown == len(lines) == 434
    assert frames.shown + frames.suppressed == 51242
    # 45 clear-to-send polls a second collapse into the first one
    assert sum("clear to send" in line for line in lines) == 1
    # every status frame carries a new key: only a changed plaintext is a new line
    assert sum(line.endswith("status") or "status, after" in line for line in lines) == 67
    assert lines[0] == "1793830074.160 RX 7e0510bf065c7e  # 0x10 clear to send"
    assert any(line.endswith("repeats") for line in lines)


async def test_capture_all_prints_every_frame(j235: TubDefinition) -> None:
    frames, text = await _capture(j235, suppress=False)
    assert frames.shown == len(text.splitlines()) == 51242 and frames.suppressed == 0


async def test_capture_output_replays_to_the_same_states(j235: TubDefinition, tmp_path: Path) -> None:
    """The dump is a capture file: decoding it gives every state change of the full capture."""

    def changes(frames: list[Frame]) -> list[dict[str, object]]:
        tub = Tub(j235)
        seen: list[dict[str, object]] = []
        tub.subscribe(lambda changed: seen.append(dict(changed)))
        for f in frames:
            tub.on_frame(f)
        return seen

    _, text = await _capture(j235)
    dump = tmp_path / "dump.log"
    dump.write_text(text, encoding="ascii")
    assert changes(frames_of(dump)) == changes(frames_of(RAW_D7))


def test_capture_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["capture"]) == 2
    assert main(["capture", "--replay", str(RAW_D7)]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("# spa2mqtt capture: Jacuzzi J235 from ")
    assert "Repeated frames are left out" in out[0]
    assert out[-1] == "# 51242 frames: 434 shown, 50808 repeats left out, 0 crc errors, 0 resyncs"
    target = tmp_path / "dump.log"
    assert main(["capture", "--replay", str(RAW_D7), "-o", str(target)]) == 0
    assert capsys.readouterr().out.strip() == f"capture appended to {target}"
    assert len(target.read_text(encoding="ascii").splitlines()) == 436  # header, 434 frames, summary
    assert len(frames_of(target)) == 434


def test_capture_plain_board(j345: TubDefinition) -> None:
    """A plain board has no key: identical frames are repeats, a changed byte is a new line."""
    out = io.StringIO()
    frames = FrameLog(j345, out, clock=lambda: 1.0)
    status = bytes.fromhex("7e25ffaf161322750519080064fa5000000002000066011c016c8000800000000000000000b67e")
    changed = bytes.fromhex("7e25ffaf161322750519080064fa5a00000002000066011c016c8000800000000000000000107e")
    frames.feed(status * 3 + changed + status)
    lines = out.getvalue().splitlines()
    assert [line.split()[2] for line in lines] == [status.hex(), changed.hex(), status.hex()]
    assert lines[1].endswith("# 0xFF status (plain), after 2 repeats")
