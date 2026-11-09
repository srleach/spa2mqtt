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
    ButtonMeta,
    DirectCommand,
    DirectControl,
    EntityDef,
    ExtraFrame,
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


def _keystream(status: dict[str, Any], length: int, source: str) -> bytes | None:
    """S[i] = xor ^ ((start - i + adjust[i]) mod 64); S[0] = 0 (the key position)."""
    if status["decode"] != "decrypt":
        return None
    ks = status.get("keystream")
    if ks is None:
        raise DefinitionError(f"{source}: status.decode 'decrypt' needs status.keystream")
    adjust = {int(k): int(v) for k, v in ks.get("adjust", {}).items()}
    out = bytearray(length)
    for i in range(1, length):
        out[i] = ks["xor"] ^ ((ks["start"] - i + adjust.get(i, 0)) % 64)
    return bytes(out)


def _check_family(raw: dict[str, Any], source: str) -> None:
    """Which protocol family may use which decode, encode, bus mode and sections."""
    plain = raw["protocol"] == "jacuzzi_plain"
    commands = raw.get("commands")
    bus = raw.get("bus", {})
    if plain != (raw["status"]["decode"] == "plain"):
        raise DefinitionError(f"{source}: status.decode 'plain' and protocol 'jacuzzi_plain' go together")
    if commands and plain != (commands["encode"] == "plain"):
        raise DefinitionError(f"{source}: commands.encode 'plain' and protocol 'jacuzzi_plain' go together")
    direct = bus.get("mode", "claim") == "direct"
    if commands and direct != (commands["encode"] == "plain"):
        raise DefinitionError(f"{source}: commands.encode 'plain' and bus.mode 'direct' go together")
    if direct and "client_address" not in bus:
        raise DefinitionError(f"{source}: bus.mode 'direct' needs bus.client_address")
    if not plain:
        if direct:
            raise DefinitionError(f"{source}: bus.mode 'direct' is only allowed with protocol 'jacuzzi_plain'")
        if commands and "direct" in commands:
            raise DefinitionError(f"{source}: commands.direct is only allowed with protocol 'jacuzzi_plain'")
        if "extra_frames" in raw:
            raise DefinitionError(f"{source}: extra_frames is only allowed with protocol 'jacuzzi_plain'")


def _direct_commands(
    commands: dict[str, Any] | None, buttons: dict[str, int], fields: dict[str, FieldDef], source: str
) -> dict[str, DirectCommand]:
    out: dict[str, DirectCommand] = {}
    for key, c in (commands or {}).get("direct", {}).items():
        if key in buttons:
            raise DefinitionError(f"{source}: command {key!r} is both a button and a direct command")
        payload = tuple(None if b == "value" else int(b) for b in c["payload"])
        slots = payload.count(None)
        if slots > 1:
            raise DefinitionError(f"{source}: direct command {key!r} has more than one value slot")
        if slots and ("min" not in c or "max" not in c):
            raise DefinitionError(f"{source}: direct command {key!r} has a value slot and needs min and max")
        if not slots and ("min" in c or "max" in c):
            raise DefinitionError(f"{source}: direct command {key!r} has min/max but no value slot")
        if slots and not c["min"] <= c["max"]:
            raise DefinitionError(f"{source}: direct command {key!r} needs min <= max")
        for fkey in c.get("requires", {}):
            if fkey not in fields:
                raise DefinitionError(f"{source}: direct command {key!r} requires unknown field {fkey!r}")
            if fields[fkey].kind != "bool" or fields[fkey].frame != "status":
                raise DefinitionError(f"{source}: direct command {key!r} requires {fkey!r}: not a status bit field")
        out[key] = DirectCommand(
            key=key,
            type=c["type"],
            payload=payload,
            status=c["status"],
            minimum=c.get("min"),
            maximum=c.get("max"),
            evidence=c.get("evidence", ""),
            description=c.get("description", ""),
            requires=tuple(sorted(c.get("requires", {}).items())),
        )
    return out


def _direct_number(e: dict[str, Any], fd: FieldDef, commands: dict[str, DirectCommand], source: str) -> DirectControl:
    """A number set by one direct command: the raw byte sent must be the value shown."""
    key = e["key"]
    name = e["control"]["command"]
    cmd = commands.get(name)
    if cmd is None:
        raise DefinitionError(f"{source}: number {key!r} references unknown direct command {name!r}")
    if not cmd.takes_value:
        raise DefinitionError(f"{source}: number {key!r} needs a direct command with a value slot")
    simple = fd.kind == "number" and fd.length == 1 and fd.scale is None and fd.offset == 0
    if not simple or fd.xor or fd.shift or fd.mask is not None:
        raise DefinitionError(f"{source}: number {key!r} with direct control needs a plain one-byte field")
    if not all(float(e[k]).is_integer() for k in ("min", "max", "step")):
        raise DefinitionError(f"{source}: number {key!r} with direct control needs integer min, max and step")
    assert cmd.minimum is not None and cmd.maximum is not None
    if e["min"] < cmd.minimum or e["max"] > cmd.maximum:
        raise DefinitionError(
            f"{source}: number {key!r} range {e['min']}..{e['max']} is outside direct command "
            f"{name!r} ({cmd.minimum}..{cmd.maximum})"
        )
    return DirectControl(command=name)


def parse_definition(raw: Any, source: str = "<memory>") -> TubDefinition:
    try:
        jsonschema.validate(raw, _schema())
    except jsonschema.ValidationError as exc:
        where = "/".join(str(p) for p in exc.absolute_path) or "<root>"
        raise DefinitionError(f"{source}: schema violation at {where}: {exc.message}") from exc
    _check_family(raw, source)

    status = raw["status"]
    length = int(status["length"])
    extra_frames = {k: ExtraFrame(type=x["type"], length=x["length"]) for k, x in raw.get("extra_frames", {}).items()}
    if "status" in extra_frames:
        raise DefinitionError(f"{source}: 'status' is reserved and cannot name an extra frame")
    if len({status["type"], *(x.type for x in extra_frames.values())}) != len(extra_frames) + 1:
        raise DefinitionError(f"{source}: extra_frames must each have their own frame type")
    if "fold_template" in status and len(status["fold_template"]) // 2 != length:
        raise DefinitionError(f"{source}: status.fold_template must be {length} bytes")
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
            frame=f.get("frame", "status"),
        )
        if fd.frame != "status" and fd.frame not in extra_frames:
            raise DefinitionError(f"{source}: field {key!r} references unknown frame {fd.frame!r}")
        frame_length = length if fd.frame == "status" else extra_frames[fd.frame].length
        if fd.byte + fd.length > frame_length:
            raise DefinitionError(
                f"{source}: field {key!r} reads bytes {fd.byte}..{fd.byte + fd.length - 1} "
                f"beyond {fd.frame} length {frame_length}"
            )
        if fd.bit is not None and fd.bit >= 8 * fd.length:
            raise DefinitionError(f"{source}: field {key!r} bit {fd.bit} outside a {fd.length}-byte value")
        fields[key] = fd

    commands = raw.get("commands")
    buttons: dict[str, int] = {}
    button_meta: dict[str, ButtonMeta] = {}
    for key, b in (commands["buttons"] if commands else {}).items():
        if isinstance(b, dict):
            buttons[key] = b["code"]
            button_meta[key] = ButtonMeta(b["status"], b.get("evidence", ""), b.get("description", ""))
        else:
            buttons[key] = b
    direct = _direct_commands(commands, buttons, fields, source)
    unit = "°" + raw["temperature_unit"]

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

        if e.get("device_class") == "temperature" and e.get("unit_of_measurement", unit) != unit:
            raise DefinitionError(
                f"{source}: entity {key!r} unit {e['unit_of_measurement']!r} does not match temperature_unit ({unit})"
            )

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
            if e["press"] not in direct:
                need_button(e["press"])
            elif direct[e["press"]].takes_value:
                raise DefinitionError(f"{source}: button {key!r} cannot press {e['press']!r}: it needs a value")
            entities.append(ButtonEntity(**common, press=e["press"]))
        elif comp == "number":
            need_field(e["field"])
            ctl = e["control"]
            if not e["min"] < e["max"]:
                raise DefinitionError(f"{source}: number {key!r} needs min < max")
            control: StepperControl | DirectControl
            if ctl["type"] == "direct":
                control = _direct_number(e, fields[e["field"]], direct, source)
            else:
                need_button(ctl["up"])
                need_button(ctl["down"])
                mode_field = ctl.get("set_mode_field")
                if mode_field is not None:
                    need_field(mode_field)
                    if fields[mode_field].kind != "bool":
                        raise DefinitionError(f"{source}: number {key!r} set_mode_field must be a bit field")
                control = StepperControl(
                    up=ctl["up"],
                    down=ctl["down"],
                    confirm_frames=ctl.get("confirm_frames", 3),
                    max_attempts=ctl.get("max_attempts", 40),
                    set_mode_field=mode_field,
                )
            entities.append(
                NumberEntity(
                    **common,
                    field=e["field"],
                    control=control,
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
        mode=bus_raw.get("mode", "claim"),
        client_address=bus_raw.get("client_address"),
        hello=bus_raw.get("hello"),
        send_gap_frames=bus_raw.get("send_gap_frames", 4),
    )
    if bus.hello is not None and (bus.hello not in direct or direct[bus.hello].takes_value):
        raise DefinitionError(f"{source}: bus.hello {bus.hello!r} must name a direct command with no value slot")
    if bus.hello is not None and direct[bus.hello].requires:
        raise DefinitionError(f"{source}: bus.hello {bus.hello!r} cannot have requires")
    ha = raw.get("ha", {})
    return TubDefinition(
        id=raw["id"],
        name=raw["name"],
        manufacturer=raw["manufacturer"],
        model=raw["model"],
        protocol=raw["protocol"],
        temperature_unit=raw["temperature_unit"],
        status_type=status["type"],
        status_length=length,
        status_decode=status["decode"],
        fold_template=bytes.fromhex(status["fold_template"]) if "fold_template" in status else None,
        status_stream=_keystream(status, length, source),
        command_type=commands["type"] if commands else None,
        buttons=buttons,
        fields=fields,
        entities=tuple(entities),
        bus=bus,
        aliases=tuple(raw.get("aliases", [])),
        description=raw.get("description", ""),
        source_path=source,
        command_encode=commands["encode"] if commands else None,
        direct_commands=direct,
        button_meta=button_meta,
        extra_frames=extra_frames,
        device_name=ha.get("device_name", raw["name"]),
        device_identifier=ha.get("device_identifier", raw["id"]),
    )
