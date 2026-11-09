"""HA discovery identity, bridge behaviour and config compatibility."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

from spa2mqtt.config import load_config
from spa2mqtt.definitions import TubDefinition
from spa2mqtt.ha.bridge import MqttBridge, MqttSettings, Publisher
from spa2mqtt.ha.discovery import DiscoveryConfig, build_discovery, format_state, legacy_clean
from spa2mqtt.tub import Tub

from .conftest import RAW_D1, frames_of
from .test_definitions import HA_ENTITIES


def test_legacy_clean_matches_ha_mqtt_discoverable() -> None:
    assert legacy_clean("Jacuzzi J235") == "Jacuzzi-J235"
    assert legacy_clean("Pump 1 Button") == "Pump-1-Button"


def test_discovery_preserves_legacy_identity(j235: TubDefinition) -> None:
    ents = {e.entity.key: e for e in build_discovery(j235, DiscoveryConfig())}
    for key, (component, name) in HA_ENTITIES.items():
        e = ents[key]
        assert e.payload["unique_id"] == key
        assert e.config_topic == f"homeassistant/{component}/Jacuzzi-J235/{legacy_clean(name)}/config"
        assert e.payload["device"]["identifiers"] == ["185569045"]
        assert e.payload["device"]["name"] == "Jacuzzi J235"
        assert e.payload["name"] == name


def test_discovery_payload_snapshot(j235: TubDefinition) -> None:
    ents = {e.entity.key: e for e in build_discovery(j235, DiscoveryConfig())}
    assert ents["current_temperature"].payload == {
        "name": "Current Water Temperature",
        "unique_id": "current_temperature",
        "device": {"identifiers": ["185569045"], "name": "Jacuzzi J235", "manufacturer": "Jacuzzi", "model": "J235"},
        "availability": [{"topic": "spa2mqtt/jacuzzi_j235/availability"}],
        "availability_mode": "all",
        "icon": "mdi:coolant-temperature",
        "state_topic": "spa2mqtt/jacuzzi_j235/current_temperature/state",
        "device_class": "temperature",
        "unit_of_measurement": "°C",
        "state_class": "measurement",
        "suggested_display_precision": 1,
    }
    num = ents["temperature_set_control"].payload
    assert num["command_topic"] == "spa2mqtt/jacuzzi_j235/temperature_set_control/set"
    assert (num["min"], num["max"], num["step"], num["mode"]) == (20.0, 40.0, 0.5, "slider")
    assert {"topic": "spa2mqtt/jacuzzi_j235/control/availability"} in num["availability"]
    assert {"topic": "spa2mqtt/jacuzzi_j235/control/availability"} in ents["pump_1_button"].payload["availability"]
    assert "control" not in json.dumps(ents["heater_active"].payload)


def test_prefix_and_new_topics(j235: TubDefinition) -> None:
    cfg = DiscoveryConfig(unique_id_prefix="spa_", legacy_topics=False)
    e = next(x for x in build_discovery(j235, cfg) if x.entity.key == "heater_active")
    assert e.payload["unique_id"] == "spa_heater_active"
    assert e.config_topic == "homeassistant/binary_sensor/jacuzzi_j235/heater_active/config"


def test_format_state() -> None:
    assert format_state(True) == "ON"
    assert format_state(38.0) == "38.0"
    assert format_state(38.5) == "38.5"
    assert format_state("low") == "low"
    assert format_state(None) is None


class FakeClient:
    def __init__(self) -> None:
        self.published: list[tuple[str, str, bool]] = []

    def publish(self, topic: str, payload: str, qos: int = 0, retain: bool = False) -> None:
        self.published.append((topic, payload, retain))


def make_bridge(j235: TubDefinition, transmit: bool) -> tuple[Tub, MqttBridge, FakeClient]:
    tub = Tub(j235, transmit=transmit)
    client = FakeClient()
    bridge = MqttBridge(tub, j235, DiscoveryConfig(), MqttSettings(), client=client)
    return tub, bridge, client


def test_bridge_publishes_config_availability_and_state(j235: TubDefinition) -> None:
    tub, bridge, client = make_bridge(j235, transmit=False)
    bridge.publish_discovery()
    retained = {t: p for t, p, r in client.published if r}
    assert retained["spa2mqtt/jacuzzi_j235/availability"] == "online"
    assert retained["spa2mqtt/jacuzzi_j235/control/availability"] == "offline"
    assert len([t for t, p in retained.items() if t.endswith("/config") and p]) == len(j235.entities)
    client.published.clear()
    for f in frames_of(RAW_D1):
        tub.on_frame(f)
    state = {t: p for t, p, _ in client.published}
    assert state["spa2mqtt/jacuzzi_j235/current_temperature/state"] == "38.0"
    assert state["spa2mqtt/jacuzzi_j235/heater_active/state"] == "OFF"
    assert state["spa2mqtt/jacuzzi_j235/temperature_set_control/state"] == "38.0"


def test_bridge_commands_ignored_when_transmit_disabled(j235: TubDefinition, caplog: Any) -> None:
    tub, bridge, _ = make_bridge(j235, transmit=False)
    bridge.handle_command("spa2mqtt/jacuzzi_j235/pump_1_button/press", "PRESS")
    bridge.handle_command("spa2mqtt/jacuzzi_j235/temperature_set_control/set", "39")
    assert not tub.bus.queue
    assert "transmit" in caplog.text


def test_bridge_commands_queue_when_enabled(j235: TubDefinition) -> None:
    tub, bridge, client = make_bridge(j235, transmit=True)
    bridge.publish_discovery()
    assert ("spa2mqtt/jacuzzi_j235/control/availability", "online", True) in client.published
    bridge.handle_command("spa2mqtt/jacuzzi_j235/pump_1_button/press", "PRESS")
    assert list(tub.bus.queue) == [0x04]
    bridge.handle_command("spa2mqtt/jacuzzi_j235/temperature_set_control/set", "39.2")
    assert tub.setpoints["temperature_set_control"].target == 39.0
    bridge.handle_command("spa2mqtt/jacuzzi_j235/temperature_set_control/set", "warm")  # ignored


def test_publisher_heartbeat() -> None:
    now = [0.0]
    sent: list[str] = []
    pub = Publisher(lambda t, p, r: sent.append(p), heartbeat=60, overrides={"x": 90}, clock=lambda: now[0])
    assert pub.offer("x", "t", "1")
    assert not pub.offer("x", "t", "1")
    now[0] = 61
    assert not pub.offer("x", "t", "1")  # override 90 s
    assert pub.offer("x", "t", "2")  # change publishes immediately
    now[0] = 200
    assert pub.offer("x", "t", "2")
    assert sent == ["1", "2", "2"]


def test_legacy_config_file_still_works(tmp_path: Path) -> None:
    p = tmp_path / "config.yml"
    p.write_text(
        "spa:\n  connection:\n    spa_address: 192.168.1.100\n    spa_port: 8899\n  config: jacuzzi_j235_encrypted\n"
        "mqtt:\n  broker: 192.168.1.7\n  port: 1883\n  username: u\n  password: p\n",
        encoding="utf-8",
    )
    cfg = load_config(p, env={})
    assert cfg.definition == "jacuzzi_j235_encrypted"
    assert (cfg.transport.host, cfg.transport.port) == ("192.168.1.100", 8899)
    assert (cfg.mqtt_host, cfg.mqtt_username, cfg.mqtt_password) == ("192.168.1.7", "u", "p")
    assert cfg.transmit is False
    assert cfg.unique_id_prefix == "" and cfg.legacy_topics is True


def test_env_overrides() -> None:
    cfg = load_config(
        None,
        env={
            "SPA_IP": "10.0.0.5",
            "SPA_PORT": "1234",
            "SPA_TRANSMIT": "true",
            "VARIANT_DEFINITION": "jacuzzi_j235",
            "MQTT_BROKER": "mq",
        },
    )
    assert (cfg.transport.host, cfg.transport.port, cfg.transmit, cfg.mqtt_host) == ("10.0.0.5", 1234, True, "mq")


def test_default_identity_comes_from_the_definition(j235: TubDefinition) -> None:
    from spa2mqtt.app import discovery_config

    loaded = load_config(None, env={})
    assert loaded.device_name is None and loaded.device_identifier is None
    cfg = discovery_config(loaded, j235)
    # the J235 keeps the device the v1 bridge created: same values as DiscoveryConfig()'s defaults
    assert (cfg.device_name, cfg.device_identifier) == ("Jacuzzi J235", "185569045")
    assert (cfg.device_name, cfg.device_identifier) == (
        DiscoveryConfig().device_name,
        DiscoveryConfig().device_identifier,
    )
    assert [e.config_topic for e in build_discovery(j235, cfg)] == [
        e.config_topic for e in build_discovery(j235, DiscoveryConfig())
    ]


def test_text_values_are_discovered_as_sensors(j235: TubDefinition) -> None:
    """Home Assistant has no `text_sensor` MQTT component: a config published there is ignored."""
    from spa2mqtt.definitions import load_definition

    for definition, key, legacy in (
        (j235, "pump_1_speed", "homeassistant/sensor/Jacuzzi-J235/Pump-1-Speed/config"),
        (load_definition("jacuzzi_j345"), "light_mode", "homeassistant/sensor/Jacuzzi-J345/Light-Mode/config"),
    ):
        cfg = DiscoveryConfig(device_name=definition.device_name, device_identifier=definition.device_identifier)
        for legacy_topics in (True, False):
            entities = build_discovery(definition, dataclasses.replace(cfg, legacy_topics=legacy_topics))
            topics = {e.entity.key: e.config_topic for e in entities}
            assert topics[key].startswith("homeassistant/sensor/")
            assert not any("/text_sensor/" in t for t in topics.values())
            if legacy_topics:
                assert topics[key] == legacy
            assert len(set(topics.values())) == len(topics)  # no two entities share a config topic
        payload = next(e.payload for e in entities if e.entity.key == key)
        assert "unit_of_measurement" not in payload and "state_class" not in payload  # a text value


def test_bridge_clears_the_config_it_used_to_publish_as_text_sensor(j235: TubDefinition) -> None:
    _, bridge, client = make_bridge(j235, transmit=False)
    bridge.publish_discovery()
    assert ("homeassistant/text_sensor/Jacuzzi-J235/Pump-1-Speed/config", "", True) in client.published
    cleared = [t for t, p, _ in client.published if p == ""]
    assert cleared == [
        "homeassistant/text_sensor/Jacuzzi-J235/Pump-1-Speed/config",
        "homeassistant/text_sensor/Jacuzzi-J235/Light-Mode/config",  # never published; clearing is harmless
    ]
