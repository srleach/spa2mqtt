"""Pure functions that turn a tub definition into HA MQTT discovery messages.

Identity rules (docs/design.md §8):
* unique_id = ``unique_id_prefix + entity.key``. With the default empty prefix this is the
  bare key the legacy ha-mqtt-discoverable stack used.
* ``legacy_topics`` publishes config to ``<prefix>/<component>/<clean(device)>/<clean(name)>/config``,
  exactly where the legacy library did, so retained configs are replaced in place.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from ..definitions.model import ButtonEntity, EntityDef, NumberEntity, StateEntity, TubDefinition


def legacy_clean(raw: str) -> str:
    """ha_mqtt_discoverable.utils.clean_string."""
    return re.sub(r"[^A-Za-z0-9_-]", "-", raw)


def slug(raw: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", raw.lower()).strip("_")


@dataclass(frozen=True, slots=True)
class DiscoveryConfig:
    discovery_prefix: str = "homeassistant"
    base_topic: str = "spa2mqtt"
    device_name: str = "Jacuzzi J235"
    device_identifier: str = "185569045"
    unique_id_prefix: str = ""
    legacy_topics: bool = True
    sw_version: str = ""

    @property
    def node(self) -> str:
        return slug(self.device_name)

    @property
    def availability_topic(self) -> str:
        return f"{self.base_topic}/{self.node}/availability"

    @property
    def control_availability_topic(self) -> str:
        """'online' only while transmit is enabled; gates buttons and the setpoint number."""
        return f"{self.base_topic}/{self.node}/control/availability"


@dataclass(frozen=True, slots=True)
class EntityTopics:
    entity: EntityDef
    config_topic: str
    state_topic: str | None
    command_topic: str | None
    payload: dict[str, Any]


def _config_topic(cfg: DiscoveryConfig, e: EntityDef) -> str:
    if cfg.legacy_topics:
        return f"{cfg.discovery_prefix}/{e.component}/{legacy_clean(cfg.device_name)}/{legacy_clean(e.name)}/config"
    return f"{cfg.discovery_prefix}/{e.component}/{cfg.node}/{e.key}/config"


def device_payload(definition: TubDefinition, cfg: DiscoveryConfig) -> dict[str, Any]:
    dev: dict[str, Any] = {
        "identifiers": [cfg.device_identifier],
        "name": cfg.device_name,
        "manufacturer": definition.manufacturer,
        "model": definition.model,
    }
    if cfg.sw_version:
        dev["sw_version"] = f"spa2mqtt {cfg.sw_version}"
    return dev


def build_discovery(definition: TubDefinition, cfg: DiscoveryConfig) -> list[EntityTopics]:
    device = device_payload(definition, cfg)
    out: list[EntityTopics] = []
    for e in definition.entities:
        base = f"{cfg.base_topic}/{cfg.node}/{e.key}"
        payload: dict[str, Any] = {
            "name": e.name,
            "unique_id": f"{cfg.unique_id_prefix}{e.key}",
            "device": device,
            "availability": [{"topic": cfg.availability_topic}],
            "availability_mode": "all",
        }
        for attr in ("icon", "entity_category"):
            value = getattr(e, attr)
            if value:
                payload[attr] = value
        if not e.enabled_by_default:
            payload["enabled_by_default"] = False
        state_topic: str | None = None
        command_topic: str | None = None
        if isinstance(e, StateEntity):
            state_topic = f"{base}/state"
            payload["state_topic"] = state_topic
            for attr in ("device_class", "unit_of_measurement", "state_class"):
                value = getattr(e, attr)
                if value:
                    payload[attr] = value
            if e.accuracy_decimals is not None:
                payload["suggested_display_precision"] = e.accuracy_decimals
            if e.component == "binary_sensor":
                payload["payload_on"] = "ON"
                payload["payload_off"] = "OFF"
        elif isinstance(e, ButtonEntity):
            command_topic = f"{base}/press"
            payload["command_topic"] = command_topic
            payload["payload_press"] = "PRESS"
            payload["availability"].append({"topic": cfg.control_availability_topic})
        elif isinstance(e, NumberEntity):
            state_topic = f"{base}/state"
            command_topic = f"{base}/set"
            payload.update(
                {"state_topic": state_topic, "command_topic": command_topic, "min": e.min, "max": e.max, "step": e.step}
            )
            if e.mode:
                payload["mode"] = e.mode
            for attr in ("device_class", "unit_of_measurement"):
                value = getattr(e, attr)
                if value:
                    payload[attr] = value
            payload["availability"].append({"topic": cfg.control_availability_topic})
        out.append(EntityTopics(e, _config_topic(cfg, e), state_topic, command_topic, payload))
    return out


def format_state(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "ON" if value else "OFF"
    if isinstance(value, float):
        return f"{value:g}" if not value.is_integer() else f"{value:.1f}"
    return str(value)
