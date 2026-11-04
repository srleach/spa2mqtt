"""Load a spa2mqtt tub definition for code generation.

Pure Python (PyYAML only; uses jsonschema when it is installed) so it runs inside ESPHome's
environment and in the repo's tests. The repository's `definitions/` directory is found
relative to this file: external_components clones the whole repo, so
<clone>/esphome/components/spa_bus/definition.py -> <clone>/definitions/.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

DEFINITIONS_DIR = Path(__file__).resolve().parents[3] / "definitions"
SCHEMA = DEFINITIONS_DIR / "tub-definition.schema.json"
STATE_COMPONENTS = ("sensor", "binary_sensor", "text_sensor")


class DefinitionError(ValueError):
    pass


def _index() -> dict[str, Path]:
    out: dict[str, Path] = {}
    for path in sorted(DEFINITIONS_DIR.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for name in [raw.get("id"), *raw.get("aliases", [])]:
            if isinstance(name, str):
                out[name] = path
    return out


@lru_cache(maxsize=None)
def load(name_or_path: str) -> dict[str, Any]:
    path = Path(name_or_path)
    if path.suffix not in (".yaml", ".yml"):
        idx = _index()
        if name_or_path not in idx:
            raise DefinitionError(f"unknown tub definition {name_or_path!r}; available: {sorted(idx)}")
        path = idx[name_or_path]
    if not path.is_file():
        raise DefinitionError(f"definition file not found: {path}")
    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    try:
        import jsonschema  # optional inside ESPHome; always present in CI

        jsonschema.validate(raw, json.loads(SCHEMA.read_text(encoding="utf-8")))
    except ImportError:
        for key in ("id", "protocol", "status", "fields", "entities"):
            if key not in raw:
                raise DefinitionError(f"{path}: missing {key!r}") from None
    except Exception as exc:  # jsonschema.ValidationError
        raise DefinitionError(f"{path}: {exc}") from exc
    if raw["protocol"] != "balboa_encrypted":
        raise DefinitionError(f"{path}: protocol {raw['protocol']!r} not supported by spa_bus")
    raw["_path"] = str(path)
    return raw


def field_keys(defn: dict[str, Any]) -> list[str]:
    return list(defn["fields"])


def field_index(defn: dict[str, Any], key: str) -> int:
    return field_keys(defn).index(key)


def field_args(defn: dict[str, Any], key: str) -> dict[str, Any]:
    """Arguments for SpaBus::add_field, in the canonical transform's terms."""
    f = defn["fields"][key]
    return {
        "byte": f["byte"],
        "length": f.get("length", 1),
        "xor": f.get("xor", 0),
        "bit": f.get("bit", -1),
        "shift": f.get("shift", 0),
        "mask": f.get("mask", 0xFFFFFFFF),
        "has_scale": "scale" in f,
        "scale": float(f.get("scale", 1.0)),
        "offset": float(f.get("offset", 0.0)),
        "invalid": list(f.get("invalid", [])),
        "map": [(int(k), v) for k, v in f.get("map", {}).items()],
    }


def entity(defn: dict[str, Any], key: str) -> dict[str, Any]:
    for e in defn["entities"]:
        if e["key"] == key:
            return e
    raise DefinitionError(f"{defn['_path']}: no entity {key!r}; have {[e['key'] for e in defn['entities']]}")


def button_code(defn: dict[str, Any], button: str) -> int:
    return int(defn["commands"]["buttons"][button])


def cpp_setup_lines(defn: dict[str, Any], var: str = "spa") -> list[str]:
    """C++ statements that load the definition into a SpaBus/SpaCore. Used by the host test
    generator; the ESPHome codegen emits the same calls through cg.add()."""
    lines = [
        f"{var}->set_status_type({defn['status']['type']}, {defn['status']['length']});",
    ]
    if "commands" in defn:
        lines.append(f"{var}->set_command_type({defn['commands']['type']});")
    bus = defn.get("bus", {})
    magic = bus.get("channel_request_magic", [0xF1, 0x73])
    lines.append(f"{var}->set_bus_params({bus.get('client_mid', 0xBF)}, {magic[0]}, {magic[1]}, "
                 f"{bus.get('dormant_channel_threshold', 5)});")
    for key in field_keys(defn):
        lines.append(f"{var}->add_field({cpp_field_expr(field_args(defn, key))});")
    return lines


def cpp_field_expr(a: dict[str, Any]) -> str:
    inv = ", ".join(f"{v}u" for v in a["invalid"])
    mp = ", ".join(f"{{{k}u, {json.dumps(v)}}}" for k, v in a["map"])
    return (f"spa_proto::make_field({a['byte']}, {a['length']}, {a['xor']}u, {a['bit']}, {a['shift']}, "
            f"{a['mask']}u, {str(a['has_scale']).lower()}, {a['scale']}f, {a['offset']}f, {{{inv}}}, {{{mp}}})")
