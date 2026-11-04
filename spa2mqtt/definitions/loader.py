"""Load, validate and type a tub definition.

Validation has two layers: the JSON Schema (structure, ranges) and semantic checks that a
schema cannot express (references between fields/buttons/entities, offsets inside the
payload, unique keys).
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

import jsonschema
import yaml

from .model import (
    BusConfig,
    ButtonEntity,
    EntityDef,
    FieldDef,
    NumberEntity,
    StateEntity,
    StepperControl,
    TubDefinition,
)

REPO_DEFINITIONS = Path(__file__).resolve().parents[2] / "definitions"
PACKAGED_DEFINITIONS = Path(__file__).resolve().parent / "data"
SCHEMA_NAME = "tub-definition.schema.json"


class DefinitionError(ValueError):
    pass


def definitions_dir() -> Path:
    for candidate in (PACKAGED_DEFINITIONS, REPO_DEFINITIONS):
        if (candidate / SCHEMA_NAME).is_file():
            return candidate
    raise DefinitionError(f"no definitions directory found (looked in {PACKAGED_DEFINITIONS}, {REPO_DEFINITIONS})")


@cache
def _schema() -> dict[str, Any]:
    data: dict[str, Any] = json.loads((definitions_dir() / SCHEMA_NAME).read_text(encoding="utf-8"))
    return data


def available_definitions() -> dict[str, Path]:
    """Map of id and alias → file, for every definition in the definitions directory."""
    out: dict[str, Path] = {}
    for path in sorted(definitions_dir().glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for name in [raw.get("id"), *raw.get("aliases", [])]:
            if isinstance(name, str):
                out[name] = path
    return out


def load_definition(name_or_path: str | Path) -> TubDefinition:
    path = Path(name_or_path)
    if not path.suffix:
        known = available_definitions()
        if str(name_or_path) not in known:
            raise DefinitionError(f"unknown tub definition {name_or_path!r}; available: {sorted(known)}")
        path = known[str(name_or_path)]
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return parse_definition(raw, source=str(path))


def parse_definition(raw: Any, source: str = "<memory>") -> TubDefinition:
    try:
        jsonschema.validate(raw, _schema())
    except jsonschema.ValidationError as exc:
        where = "/".join(str(p) for p in exc.absolute_path) or "<root>"
        raise DefinitionError(f"{source}: schema violation at {where}: {exc.message}") from exc

    status = raw["status"]
    length = int(status["length"])
    fields: dict[str, FieldDef] = {}
    for key, f in raw["fields"].items():
        fd = FieldDef(
            key=key,
            byte=f["byte"],
            status=f["status"],
            length=f.get("length", 1),
            xor=f.get("xor", 0),
            bit=f.get("bit"),
            shift=f.get("shift", 0),
            mask=f.get("mask"),
            scale=f.get("scale"),
            offset=float(f.get("offset", 0.0)),
            invalid=frozenset(f.get("invalid", [])),
            map={int(k): v for k, v in f["map"].items()} if "map" in f else None,
            evidence=f.get("evidence", ""),
            description=f.get("description", ""),
        )
        if fd.byte + fd.length > length:
            raise DefinitionError(
                f"{source}: field {key!r} reads bytes {fd.byte}..{fd.byte + fd.length - 1} "
                f"beyond status length {length}"
            )
        if fd.bit is not None and fd.bit >= 8 * fd.length:
            raise DefinitionError(f"{source}: field {key!r} bit {fd.bit} outside a {fd.length}-byte value")
        fields[key] = fd

    commands = raw.get("commands")
    buttons: dict[str, int] = dict(commands["buttons"]) if commands else {}

    entities: list[EntityDef] = []
    seen: set[str] = set()
    for e in raw["entities"]:
        key = e["key"]
        if key in seen:
            raise DefinitionError(f"{source}: duplicate entity key {key!r}")
        seen.add(key)
        common: dict[str, Any] = {
            "key": key,
            "component": e["component"],
            "name": e["name"],
            "icon": e.get("icon"),
            "entity_category": e.get("entity_category"),
            "enabled_by_default": e.get("enabled_by_default", True),
            "description": e.get("description", ""),
        }
        comp = e["component"]

        def need_field(fkey: str, entity_key: str = key) -> None:
            if fkey not in fields:
                raise DefinitionError(f"{source}: entity {entity_key!r} references unknown field {fkey!r}")

        def need_button(bkey: str, entity_key: str = key) -> None:
            if bkey not in buttons:
                raise DefinitionError(f"{source}: entity {entity_key!r} references unknown button {bkey!r}")

        if comp in ("sensor", "binary_sensor", "text_sensor"):
            need_field(e["field"])
            kind = fields[e["field"]].kind
            if comp == "binary_sensor" and kind != "bool":
                raise DefinitionError(f"{source}: binary_sensor {key!r} needs a bit field")
            if comp == "sensor" and kind != "number":
                raise DefinitionError(f"{source}: sensor {key!r} needs a numeric field")
            entities.append(
                StateEntity(
                    **common,
                    field=e["field"],
                    device_class=e.get("device_class"),
                    unit_of_measurement=e.get("unit_of_measurement"),
                    state_class=e.get("state_class"),
                    accuracy_decimals=e.get("accuracy_decimals"),
                )
            )
        elif comp == "button":
            need_button(e["press"])
            entities.append(ButtonEntity(**common, press=e["press"]))
        elif comp == "number":
            need_field(e["field"])
            ctl = e["control"]
            need_button(ctl["up"])
            need_button(ctl["down"])
            if not e["min"] < e["max"]:
                raise DefinitionError(f"{source}: number {key!r} needs min < max")
            entities.append(
                NumberEntity(
                    **common,
                    field=e["field"],
                    control=StepperControl(
                        up=ctl["up"],
                        down=ctl["down"],
                        confirm_frames=ctl.get("confirm_frames", 3),
                        max_attempts=ctl.get("max_attempts", 40),
                    ),
                    min=float(e["min"]),
                    max=float(e["max"]),
                    step=float(e["step"]),
                    mode=e.get("mode"),
                    device_class=e.get("device_class"),
                    unit_of_measurement=e.get("unit_of_measurement"),
                )
            )
        else:  # pragma: no cover - schema prevents this
            raise DefinitionError(f"{source}: unsupported component {comp!r}")

    if any(isinstance(e, (ButtonEntity, NumberEntity)) for e in entities) and not commands:
        raise DefinitionError(f"{source}: control entities need a 'commands' section")

    bus_raw = raw.get("bus", {})
    magic = bus_raw.get("channel_request_magic", [0xF1, 0x73])
    bus = BusConfig(
        baud=bus_raw.get("baud", 115200),
        client_mid=bus_raw.get("client_mid", 0xBF),
        channel_request_magic=(magic[0], magic[1]),
        dormant_channel_threshold=bus_raw.get("dormant_channel_threshold", 5),
    )
    return TubDefinition(
        id=raw["id"],
        name=raw["name"],
        manufacturer=raw["manufacturer"],
        model=raw["model"],
        protocol=raw["protocol"],
        temperature_unit=raw["temperature_unit"],
        status_type=status["type"],
        status_length=length,
        command_type=commands["type"] if commands else None,
        buttons=buttons,
        fields=fields,
        entities=tuple(entities),
        bus=bus,
        aliases=tuple(raw.get("aliases", [])),
        description=raw.get("description", ""),
        source_path=source,
    )
