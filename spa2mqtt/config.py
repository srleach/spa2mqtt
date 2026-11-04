"""Runtime configuration: config.yml plus environment variables.

Legacy keys from the v1 config are accepted (with a warning) so an existing config.yml keeps
working. See config.yml.example and docs/design.md §5.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TransportConfig:
    type: str = "tcp"  # tcp | serial | replay
    host: str = "192.168.1.100"
    port: int = 8899
    device: str = "/dev/ttyUSB0"
    baud: int = 115200
    path: str = ""
    speed: float = 1.0


@dataclass(frozen=True, slots=True)
class AppConfig:
    definition: str = "jacuzzi_j235"
    transport: TransportConfig = field(default_factory=TransportConfig)
    transmit: bool = False
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_username: str | None = None
    mqtt_password: str | None = None
    discovery_prefix: str = "homeassistant"
    base_topic: str = "spa2mqtt"
    device_name: str = "Jacuzzi J235"
    device_identifier: str = "185569045"
    unique_id_prefix: str = ""
    legacy_topics: bool = True
    heartbeat: float = 60.0
    heartbeat_overrides: dict[str, float] = field(default_factory=dict)
    log_level: str = "INFO"


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def load_config(path: str | Path | None = "config.yml", env: dict[str, str] | None = None) -> AppConfig:
    env = dict(os.environ) if env is None else env
    raw: dict[str, Any] = {}
    if path is not None and Path(path).is_file():
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    elif path is not None:
        log.info("no %s; using defaults and environment variables", path)

    spa: dict[str, Any] = raw.get("spa", {}) or {}
    mqtt: dict[str, Any] = raw.get("mqtt", {}) or {}
    ha: dict[str, Any] = raw.get("ha", {}) or {}

    definition = spa.get("definition")
    if definition is None and "config" in spa:
        log.warning("config key spa.config is deprecated; use spa.definition")
        definition = spa["config"]
    definition = env.get("SPA_DEFINITION") or env.get("VARIANT_DEFINITION") or definition or "jacuzzi_j235"

    t: dict[str, Any] = dict(spa.get("transport", {}) or {})
    legacy_conn = spa.get("connection")
    if legacy_conn:
        log.warning("config key spa.connection is deprecated; use spa.transport")
        t.setdefault("host", legacy_conn.get("spa_address"))
        t.setdefault("port", legacy_conn.get("spa_port"))
    if env.get("SPA_IP"):
        t["host"] = env["SPA_IP"]
    if env.get("SPA_PORT"):
        t["port"] = env["SPA_PORT"]
    d = TransportConfig()
    transport = TransportConfig(
        type=str(t.get("type", "tcp")),
        host=str(t.get("host") or d.host),
        port=int(t.get("port") or d.port),
        device=str(t.get("device", d.device)),
        baud=int(t.get("baud", d.baud)),
        path=str(t.get("path", "")),
        speed=float(t.get("speed", 1.0)),
    )

    transmit = _truthy(env["SPA_TRANSMIT"]) if "SPA_TRANSMIT" in env else _truthy(spa.get("transmit", False))

    legacy_intervals = raw.get("sensor_update_intervals") or {}
    return AppConfig(
        definition=str(definition),
        transport=transport,
        transmit=transmit,
        mqtt_host=str(env.get("MQTT_BROKER") or mqtt.get("broker") or mqtt.get("host") or "localhost"),
        mqtt_port=int(env.get("MQTT_PORT") or mqtt.get("port") or 1883),
        mqtt_username=env.get("MQTT_USERNAME") or mqtt.get("username"),
        mqtt_password=env.get("MQTT_PASSWORD") or mqtt.get("password"),
        discovery_prefix=str(ha.get("discovery_prefix", "homeassistant")),
        base_topic=str(ha.get("base_topic", "spa2mqtt")),
        device_name=str(ha.get("device_name", "Jacuzzi J235")),
        device_identifier=str(ha.get("device_identifier", "185569045")),
        unique_id_prefix=str(ha.get("unique_id_prefix", "")),
        legacy_topics=_truthy(ha.get("legacy_topics", True)),
        heartbeat=float(ha.get("heartbeat", legacy_intervals.get("default", 60))),
        heartbeat_overrides={
            k: float(v) for k, v in (ha.get("heartbeat_overrides") or legacy_intervals.get("overrides") or {}).items()
        },
        log_level=str(env.get("LOG_LEVEL") or raw.get("log_level", "INFO")),
    )
