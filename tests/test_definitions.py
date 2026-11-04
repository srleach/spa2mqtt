"""Definition schema and semantic validation."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from spa2mqtt.definitions import DefinitionError, available_definitions, load_definition
from spa2mqtt.definitions.loader import parse_definition

# What Home Assistant has registered today (MQTT platform, read 2026-11-04). This set is the
# minimum the definition must keep exposing, with these exact unique_ids and names.
HA_ENTITIES = {
    "current_temperature": ("sensor", "Current Water Temperature"),
    "setpoint_temperature": ("sensor", "Target Water Temperature"),
    "circulation_pump_status": ("binary_sensor", "Circulation Pump Status"),
    "secondary_pump_status": ("binary_sensor", "Secondary Pump Status"),
    "main_pump_status": ("binary_sensor", "Main Pump Status"),
    "manual_circulation_call": ("binary_sensor", "Manual Circulation Call"),
    "heater_active": ("binary_sensor", "Heater Active"),
    "temperature_increment": ("button", "Temperature Increment"),
    "temperature_decrement": ("button", "Temperature Decrement"),
    "pump_1_button": ("button", "Pump 1 Button"),
    "pump_2_button": ("button", "Pump 2 Button"),
    "temperature_set_control": ("number", "Temperature Set Control"),
}


def test_every_definition_validates() -> None:
    paths = set(available_definitions().values())
    assert paths
    for p in paths:
        load_definition(p)


def test_legacy_alias_resolves() -> None:
    assert load_definition("jacuzzi_j235_encrypted").id == "jacuzzi_j235"


def test_j235_keeps_every_ha_identity() -> None:
    d = load_definition("jacuzzi_j235")
    got = {e.key: (e.component, e.name) for e in d.entities}
    for key, expected in HA_ENTITIES.items():
        assert got.get(key) == expected, key


def _raw() -> dict[str, Any]:
    d = load_definition("jacuzzi_j235")
    data: dict[str, Any] = yaml.safe_load(Path(d.source_path).read_text(encoding="utf-8"))
    return data


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda r: r["entities"][0].update(field="nope"), "unknown field"),
        (lambda r: r["entities"].append(dict(r["entities"][0])), "duplicate entity key"),
        (lambda r: r["fields"]["hour"].update(byte=20), "beyond status length"),
        (lambda r: r["fields"].update(bad={"byte": 0, "bit": 1, "scale": 2, "status": "inferred"}), "schema"),
        (lambda r: r["entities"][7].update(press="nope"), "unknown button"),
        (lambda r: r.update(protocol="something_else"), "schema"),
        (lambda r: r["entities"][2].update(field="water_temperature"), "needs a bit field"),
    ],
)
def test_broken_definitions_are_rejected(mutate: Any, message: str) -> None:
    raw = copy.deepcopy(_raw())
    mutate(raw)
    with pytest.raises(DefinitionError, match=message):
        parse_definition(raw)


def test_unknown_definition_name() -> None:
    with pytest.raises(DefinitionError, match="unknown tub definition"):
        load_definition("no_such_tub")


def test_field_transforms(j235: Any) -> None:
    f = j235.fields
    assert f["water_temperature"].decode(bytes([0] * 5 + [0x4F] + [0] * 10)) == 38.5
    assert f["hour"].decode(bytes([0x13] + [0] * 15)) == 21
    assert f["pump_1_speed"].decode(bytes([0, 0, 0x13] + [0] * 13)) == "high"
    assert f["year"].decode(bytes([0] * 9 + [26] + [0] * 6)) == 2026
    assert f["heater"].decode(bytes([0] * 10 + [0x40] + [0] * 5)) is True
    assert f["hour"].decode(b"") is None
