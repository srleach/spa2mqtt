"""Command line: ``python -m spa2mqtt {run,replay,validate,definitions}``."""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import logging
import sys
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


if __name__ == "__main__":
    sys.exit(main())
