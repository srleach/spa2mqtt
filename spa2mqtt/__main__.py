"""Command line: ``python -m spa2mqtt {run,monitor,replay,validate,definitions}``."""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import logging
import sys
import time
from collections.abc import Callable
from pathlib import Path

from .config import TransportConfig, load_config
from .definitions import DefinitionError, available_definitions, load_definition
from .definitions.model import FieldValue


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="spa2mqtt")
    sub = parser.add_subparsers(dest="cmd")
    p_run = sub.add_parser("run", help="bridge the tub to MQTT (default)")
    p_run.add_argument("-c", "--config", default="config.yml")
    p_rep = sub.add_parser("replay", help="decode a capture and print state changes (no MQTT, no TX)")
    p_rep.add_argument("capture", type=Path)
    p_rep.add_argument("-d", "--definition", default="jacuzzi_j235")
    p_mon = sub.add_parser("monitor", help="read-only live decode to the terminal (no MQTT, never transmits)")
    p_mon.add_argument("host", nargs="?", help="RS485-to-TCP bridge address, e.g. the EW11A")
    p_mon.add_argument("-p", "--port", type=int, default=8899)
    p_mon.add_argument("-d", "--definition", default="jacuzzi_j235")
    p_mon.add_argument("-i", "--interval", type=float, default=10.0, help="seconds between status reports")
    p_mon.add_argument("--record", metavar="FILE", help="append a raw capture (tools/capture.py format)")
    p_mon.add_argument("--json", action="store_true", help="JSON lines instead of text")
    p_mon.add_argument("--quiet-changes", action="store_true", help="only periodic reports")
    p_mon.add_argument("--describe", action="store_true", help="show each field's note in reports")
    p_mon.add_argument("--serial", metavar="DEVICE", help="read a USB RS485 adapter instead of TCP")
    p_mon.add_argument("--replay", metavar="CAPTURE", type=Path, help="decode a capture file instead of the bus")
    p_mon.add_argument("--speed", type=float, default=0.0, help="replay speed (0 = as fast as possible)")
    p_val = sub.add_parser("validate", help="validate tub definition files")
    p_val.add_argument("definitions", nargs="*")
    sub.add_parser("definitions", help="list available tub definitions")
    args = parser.parse_args(argv)

    if args.cmd in (None, "run"):
        cfg = load_config(getattr(args, "config", "config.yml"))
        logging.basicConfig(level=cfg.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
        from .app import run

        asyncio.run(run(cfg))
        return 0

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if args.cmd == "replay":
        from .app import run
        from .tub import Tub

        cfg = dataclasses.replace(
            load_config(None, env={}),
            definition=args.definition,
            transmit=False,
            transport=TransportConfig(type="replay", path=str(args.capture), speed=0),
        )

        def attach(tub: Tub) -> None:
            def show(changed: dict[str, FieldValue]) -> None:
                frames = tub.state.status_frames
                print(f"[{frames:6d}] " + " ".join(f"{k}={v}" for k, v in sorted(changed.items())))

            tub.subscribe(show)

        asyncio.run(run(cfg, mqtt_enabled=False, on_tub=attach))
        return 0
    if args.cmd == "monitor":
        return _monitor(args)
    if args.cmd == "validate":
        targets = args.definitions or sorted(set(available_definitions().values()))
        ok = True
        for t in targets:
            try:
                d = load_definition(t)
                print(f"OK   {t}: {d.id} ({len(d.fields)} fields, {len(d.entities)} entities)")
            except DefinitionError as exc:
                ok = False
                print(f"FAIL {t}: {exc}")
        return 0 if ok else 1
    if args.cmd == "definitions":
        for name, path in sorted(available_definitions().items()):
            print(f"{name:32s} {path}")
        return 0
    return 2


def _monitor(args: argparse.Namespace) -> int:
    from .monitor import Monitor, open_record
    from .transport import ReplayTransport, TcpTransport, Transport
    from .transport.serial import SerialTransport

    definition = load_definition(args.definition)
    transport: Transport
    clock: Callable[[], float] = time.time
    if args.replay:
        replay = ReplayTransport(args.replay, speed=args.speed, status_type=definition.status_type)
        transport = replay
        clock = lambda: replay.current_time  # noqa: E731 - report on the capture's own timeline
    elif args.serial:
        transport = SerialTransport(args.serial, definition.bus.baud)
    elif args.host:
        transport = TcpTransport(args.host, args.port)
    else:
        print("monitor: give a bridge HOST, --serial DEVICE or --replay CAPTURE", file=sys.stderr)
        return 2
    record = open_record(args.record)
    mon = Monitor(
        definition,
        sys.stdout,
        interval=args.interval,
        show_changes=not args.quiet_changes,
        as_json=args.json,
        describe=args.describe,
        record=record,
        clock=clock,
    )
    if not args.json:
        src = args.replay or args.serial or f"{args.host}:{args.port}"
        print(
            f"spa2mqtt monitor: {definition.name} from {src}. Read-only: transmit is disabled and "
            f"nothing is published. Ctrl-C to stop."
        )
    try:
        asyncio.run(mon.run(transport, reconnect=not args.replay))
    except KeyboardInterrupt:
        pass
    finally:
        mon.report()
        if record is not None:
            record.close()
            print(f"raw capture appended to {args.record}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
