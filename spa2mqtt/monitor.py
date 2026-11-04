"""Read-only standalone monitor: decode the live bus and print it to the terminal.

No MQTT, no Home Assistant, and no transmission. Three independent guards:

1. The tub model runs with ``transmit=False``, so the bus state machine never produces frames.
2. There is no ``BusWriter``: nothing in this module can send.
3. The transport is wrapped in :class:`ReadOnlyTransport`, whose ``write`` raises.

    spa2mqtt monitor 192.168.25.73                   # EW11A on port 8899
    spa2mqtt monitor 192.168.25.73 --interval 5 --record session.log
    spa2mqtt monitor --replay tests/fixtures/captures/raw/2026-11-04T220754Z_j235_labelled.log
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO

from .definitions import TubDefinition
from .definitions.model import FieldValue, StateEntity
from .protocol import Frame, FrameDecoder, cc_decode, fold
from .transport.base import TransmitForbidden, Transport
from .tub import Tub

log = logging.getLogger(__name__)

TYPE_NAMES = {
    0x00: "new-client poll",
    0x01: "channel request",
    0x02: "channel grant",
    0x03: "channel ack",
    0x06: "clear to send",
    0x07: "nothing to send",
    0xC4: "status",
    0xCA: "lights",
    0xCC: "panel/button",
}


class ReadOnlyTransport:
    """Pass-through for reads; refuses every write."""

    def __init__(self, inner: Transport) -> None:
        self._inner = inner

    async def connect(self) -> None:
        await self._inner.connect()

    async def read(self) -> bytes:
        return await self._inner.read()

    async def write(self, data: bytes) -> None:
        raise TransmitForbidden("monitor is read-only")

    async def close(self) -> None:
        await self._inner.close()


def _fmt(value: FieldValue) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, bool):
        return "on" if value else "off"
    if isinstance(value, float):
        return f"{value:.1f}"
    return str(value)


@dataclass
class Monitor:
    definition: TubDefinition
    out: TextIO
    interval: float = 10.0
    show_changes: bool = True
    as_json: bool = False
    describe: bool = False
    record: TextIO | None = None
    clock: Callable[[], float] = time.time
    tub: Tub = field(init=False)
    decoder: FrameDecoder = field(default_factory=FrameDecoder)
    counts: Counter[tuple[int, int]] = field(default_factory=Counter)
    window: Counter[int] = field(default_factory=Counter)
    presses: Counter[str] = field(default_factory=Counter)
    last_status: Frame | None = None
    started: float = 0.0
    _last_report: float = 0.0
    _last_code: dict[int, int] = field(default_factory=dict)
    _first_chunk: bool = True

    def __post_init__(self) -> None:
        self.tub = Tub(self.definition, transmit=False)
        self.tub.subscribe(self._on_changes)
        self._button_names = {code: name for name, code in self.definition.buttons.items()}
        self._labels = {e.field: e.name for e in self.definition.entities if isinstance(e, StateEntity)}
        # Fields that only feed disabled-by-default diagnostics change constantly; keep them out of
        # the live change lines (they still appear in every report).
        enabled = {e.field for e in self.definition.entities if isinstance(e, StateEntity) and e.enabled_by_default}
        diagnostic = {
            e.field for e in self.definition.entities if isinstance(e, StateEntity) and not e.enabled_by_default
        }
        self._quiet = (diagnostic - enabled) | {"minute"}
        self.started = self._last_report = self.clock()

    # -- input -------------------------------------------------------------------

    def feed(self, chunk: bytes) -> None:
        now = self.clock()
        if self._first_chunk:
            self._first_chunk = False
            self.started = self._last_report = now
        if self.record is not None:
            self.record.write(f"{now:.3f} RX {chunk.hex()}\n")
            self.record.flush()
        for frame in self.decoder.feed(chunk):
            self.counts[(frame.addr, frame.type)] += 1
            self.window[frame.type] += 1
            if self.tub.on_frame(frame):  # pragma: no cover - transmit=False never yields frames
                raise TransmitForbidden("tub model produced frames while read-only")
            if frame.type == self.definition.status_type and frame.mid == 0xAF:
                first = self.last_status is None
                self.last_status = frame
                if first:
                    self.report(now)  # show the full picture as soon as the tub is heard
            elif frame.type == self.definition.command_type:
                self._on_panel_frame(frame, now)
        if now - self._last_report >= self.interval:
            self.report(now)

    def _on_panel_frame(self, frame: Frame, now: float) -> None:
        code = cc_decode(frame.payload)
        prev = self._last_code.get(frame.addr, 0)
        self._last_code[frame.addr] = code or 0
        if code and code != prev:
            name = self._button_names.get(code, "unknown button")
            self.presses[name] += 1
            self._emit(
                {"event": "press", "channel": frame.addr, "code": code, "button": name},
                f"panel press on channel 0x{frame.addr:02X}: {name} (0x{code:02X})",
                now,
            )

    def _on_changes(self, changed: dict[str, FieldValue]) -> None:
        if not self.show_changes or self.tub.state.status_frames == 1:
            return
        now = self.clock()
        parts = [f"{self._labels.get(k, k)}={_fmt(v)}" for k, v in changed.items() if k not in self._quiet]
        if parts:
            self._emit({"event": "change", "fields": changed}, "change: " + ", ".join(parts), now)

    # -- output ------------------------------------------------------------------

    def _emit(self, obj: dict[str, object], text: str, now: float) -> None:
        if self.as_json:
            self.out.write(json.dumps({"t": round(now, 3), **obj}, default=str) + "\n")
        else:
            self.out.write(f"{time.strftime('%H:%M:%S', time.localtime(now))}  {text}\n")
        self.out.flush()

    def report(self, now: float | None = None) -> None:
        now = self.clock() if now is None else now
        span = now - self._last_report
        self._last_report = now
        rates = (
            {TYPE_NAMES.get(t, f"0x{t:02X}"): round(n / span, 1) for t, n in sorted(self.window.items())}
            if span >= 1.0
            else {}
        )
        self.window.clear()
        values = self.tub.state.values
        stats = self.decoder.stats
        bus = self.tub.bus
        if self.as_json:
            self.out.write(
                json.dumps(
                    {
                        "t": round(now, 3),
                        "event": "status",
                        "raw": self.last_status.encode().hex() if self.last_status else None,
                        "decoded": fold(self.last_status.payload).hex() if self.last_status else None,
                        "values": values,
                        "rates_per_s": rates,
                        "frames": stats.frames,
                        "crc_errors": stats.crc_errors,
                        "resyncs": stats.resyncs,
                        "polled_channels": sorted(bus.polled_channels),
                        "panel_channels": sorted(bus.active_channels),
                        "presses": dict(self.presses),
                        "transmit": False,
                    },
                    default=str,
                )
                + "\n"
            )
            self.out.flush()
            return
        w = self.out.write
        w(
            f"\n=== {self.definition.name} · {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now))} "
            f"· read-only, nothing is transmitted ===\n"
        )
        if self.last_status is None:
            w("  no status frames yet (is the bridge passing traffic? only one TCP client may be allowed)\n")
        else:
            w(f"  raw     {self.last_status.encode().hex(' ')}\n")
            w(f"  folded  {fold(self.last_status.payload).hex(' ')}\n")
            width = max(len(self._labels.get(k, k)) for k in self.definition.fields)
            for key, fdef in self.definition.fields.items():
                label = self._labels.get(key, key)
                mark = "" if fdef.status == "confirmed" else f"  ({fdef.status})"
                note = f"  {fdef.description}" if self.describe and fdef.description else ""
                w(f"  {label:<{width}}  {_fmt(values.get(key)):>8}{mark}{note}\n")
        w(
            f"  bus     frames {stats.frames} · crc errors {stats.crc_errors} · resyncs {stats.resyncs} · "
            f"status frames {self.tub.state.status_frames}\n"
        )
        w(f"  rates   {', '.join(f'{k} {v}/s' for k, v in rates.items()) or '-'}\n")
        w(
            f"  panels  polled {[f'0x{c:02X}' for c in sorted(bus.polled_channels)]} · "
            f"answering {[f'0x{c:02X}' for c in sorted(bus.active_channels)]} · "
            f"presses seen {dict(self.presses) or 'none'}\n"
        )
        self.out.flush()

    # -- loop --------------------------------------------------------------------

    async def run(self, transport: Transport, reconnect: bool = True) -> None:
        guarded = ReadOnlyTransport(transport)
        backoff = 1.0
        while True:
            try:
                await guarded.connect()
                backoff = 1.0
                while chunk := await guarded.read():
                    self.feed(chunk)
                if not reconnect:
                    return
                log.warning("bridge closed the connection")
            except (ConnectionError, OSError) as exc:
                if not reconnect:
                    raise
                log.warning("transport error: %s", exc)
            finally:
                await guarded.close()
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)


def open_record(path: str | None) -> TextIO | None:
    if not path:
        return None
    p = Path(path)
    fh = p.open("a", encoding="ascii")
    fh.write(f"# spa2mqtt monitor capture, started {time.strftime('%Y-%m-%dT%H:%M:%S%z')}\n")
    return fh
