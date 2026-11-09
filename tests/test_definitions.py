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
        (lambda r: r["fields"]["hour"].update(byte=40), "beyond status length"),
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


def _unkeyed(**bytes_at: int) -> bytes:
    out = bytearray(33)
    for k, v in bytes_at.items():
        out[int(k[1:])] = v
    return bytes(out)


def test_field_transforms(j235: Any) -> None:
    f = j235.fields
    # field transforms read decrypted plaintext
    assert f["water_temperature"].decode(_unkeyed(b10=77)) == 38.5
    assert f["hour"].decode(_unkeyed(b1=21)) == 21
    assert f["pump_1_speed"].decode(_unkeyed(b5=0x13)) == "high"
    assert f["year"].decode(_unkeyed(b19=26)) == 2026
    assert f["heater"].decode(_unkeyed(b21=0x40)) is True
    assert f["day_of_month"].decode(_unkeyed(b14=4 << 3)) == 4
    assert f["month"].decode(_unkeyed(b15=11)) == 11
    assert f["hour"].decode(b"") is None


def test_keystream(j235: Any) -> None:
    s = j235.status_stream
    assert j235.status_decode == "decrypt" and len(s) == 33 and s[0] == 0
    assert all(s[i] == 0x19 ^ ((31 - i) % 64) for i in range(1, 33) if i not in (5, 6, 14, 15, 22))
    assert all(s[i] == 0x19 ^ ((31 - i - 8) % 64) for i in (5, 6, 14, 15, 22))


def test_fold_template_matches_length(j235: Any) -> None:
    assert j235.fold_template is not None and len(j235.fold_template) == j235.status_length


def test_j345_legacy_alias_resolves() -> None:
    # the name the pre-rewrite definition had; the owner's existing stack still sets it
    assert load_definition("jacuzzi_j335_unencrypted_farenheit").id == "jacuzzi_j345"


def test_no_name_is_claimed_by_two_definitions() -> None:
    claimed: dict[str, Path] = {}
    for path in sorted(set(available_definitions().values())):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        for name in [raw["id"], *raw.get("aliases", [])]:
            assert name not in claimed, f"{name} is in {claimed.get(name)} and {path}"
            claimed[name] = path
    assert {"jacuzzi_j235", "jacuzzi_j345"} <= set(claimed)


def test_j235_uses_none_of_the_plain_features(j235: Any) -> None:
    assert j235.protocol == "balboa_encrypted" and j235.command_encode == "cc_xor"
    assert j235.bus.mode == "claim" and j235.bus.client_address is None and j235.bus.hello is None
    assert j235.direct_commands == {} and j235.button_meta == {}
    assert {k: (x.type, x.decode) for k, x in j235.extra_frames.items()} == {"lights": (0xCA, "fold")}
    status = [k for k, f in j235.fields.items() if f.frame == "status"]
    assert list(j235.decode_status(bytes(33))) == status
    assert {k for k, f in j235.fields.items() if f.frame == "lights"} == {"light_on", "light_mode"}
    assert j235.buttons == {"temp_up": 0x01, "temp_down": 0x02, "pump_1": 0x04, "pump_2": 0x05, "light": 0x12}
