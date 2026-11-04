"""MQTT side: publishes discovery, availability and state; routes HA commands to the tub.

paho-mqtt runs its network loop in its own thread. Incoming commands are handed to the
asyncio loop with ``call_soon_threadsafe``; publishing from the asyncio thread is safe.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

from ..definitions.model import ButtonEntity, FieldValue, NumberEntity, StateEntity, TubDefinition
from ..transport.base import TransmitForbidden
from ..tub.tub import Tub
from .discovery import DiscoveryConfig, EntityTopics, build_discovery, format_state

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class MqttSettings:
    host: str = "localhost"
    port: int = 1883
    username: str | None = None
    password: str | None = None
    client_id: str = "spa2mqtt"


@dataclass
class Publisher:
    """Change-driven publishing with a heartbeat (legacy ``sensor_update_intervals``)."""

    publish: Callable[[str, str, bool], None]
    heartbeat: float = 60.0
    overrides: dict[str, float] = field(default_factory=dict)
    clock: Callable[[], float] = time.monotonic
    _last: dict[str, tuple[str, float]] = field(default_factory=dict)

    def offer(self, key: str, topic: str, payload: str | None, force: bool = False) -> bool:
        if payload is None:
            return False
        now = self.clock()
        prev = self._last.get(key)
        interval = self.overrides.get(key, self.heartbeat)
        if force or prev is None or prev[0] != payload or now - prev[1] >= interval:
            self.publish(topic, payload, False)
            self._last[key] = (payload, now)
            return True
        return False


class MqttBridge:
    def __init__(
        self,
        tub: Tub,
        definition: TubDefinition,
        discovery: DiscoveryConfig,
        settings: MqttSettings,
        heartbeat: float = 60.0,
        heartbeat_overrides: dict[str, float] | None = None,
        client: Any | None = None,
    ) -> None:
        self.tub = tub
        self.definition = definition
        self.discovery = discovery
        self.settings = settings
        self.entities: list[EntityTopics] = build_discovery(definition, discovery)
        self._by_command = {e.command_topic: e for e in self.entities if e.command_topic}
        self._loop: asyncio.AbstractEventLoop | None = None
        self.client = client or self._make_client()
        self.publisher = Publisher(self._publish, heartbeat, heartbeat_overrides or {})
        tub.subscribe(self._on_changes)

    # -- lifecycle -------------------------------------------------------------

    def _make_client(self) -> mqtt.Client:
        client = mqtt.Client(CallbackAPIVersion.VERSION2, client_id=self.settings.client_id)
        if self.settings.username:
            client.username_pw_set(self.settings.username, self.settings.password)
        client.will_set(self.discovery.availability_topic, "offline", retain=True)
        client.on_connect = self._on_connect
        client.on_message = self._on_message
        return client

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self.client.connect_async(self.settings.host, self.settings.port)
        self.client.loop_start()

    def stop(self) -> None:
        self._publish(self.discovery.availability_topic, "offline", True)
        self.client.loop_stop()
        self.client.disconnect()

    def _on_connect(self, client: Any, userdata: Any, flags: Any, reason_code: Any, properties: Any = None) -> None:
        log.info("MQTT connected (%s)", reason_code)
        self.publish_discovery()
        client.subscribe([(t, 1) for t in self._by_command] + [(f"{self.discovery.discovery_prefix}/status", 1)])

    def publish_discovery(self) -> None:
        for e in self.entities:
            self._publish(e.config_topic, json.dumps(e.payload, sort_keys=True), True)
        self._publish(self.discovery.availability_topic, "online", True)
        self._publish(self.discovery.control_availability_topic, "online" if self.tub.transmit else "offline", True)
        self.republish_all()

    def republish_all(self) -> None:
        for e in self.entities:
            self._publish_entity_state(e, force=True)

    # -- state -----------------------------------------------------------------

    def _on_changes(self, changed: dict[str, FieldValue]) -> None:
        for e in self.entities:
            if isinstance(e.entity, (StateEntity, NumberEntity)) and e.entity.field in changed:
                self._publish_entity_state(e)

    def heartbeat(self) -> None:
        for e in self.entities:
            self._publish_entity_state(e)

    def _publish_entity_state(self, e: EntityTopics, force: bool = False) -> None:
        if e.state_topic is None or not isinstance(e.entity, (StateEntity, NumberEntity)):
            return
        value = self.tub.state.values.get(e.entity.field)
        self.publisher.offer(e.entity.key, e.state_topic, format_state(value), force=force)

    def _publish(self, topic: str, payload: str, retain: bool) -> None:
        self.client.publish(topic, payload, qos=1 if retain else 0, retain=retain)

    # -- commands --------------------------------------------------------------

    def _on_message(self, client: Any, userdata: Any, message: Any) -> None:
        topic = message.topic
        payload = message.payload.decode("utf-8", "replace").strip()
        if topic == f"{self.discovery.discovery_prefix}/status":
            if payload == "online" and self._loop is not None:
                self._loop.call_soon_threadsafe(self.publish_discovery)
            return
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self.handle_command, topic, payload)

    def handle_command(self, topic: str, payload: str) -> None:
        e = self._by_command.get(topic)
        if e is None:
            return
        try:
            if isinstance(e.entity, ButtonEntity):
                self.tub.press(e.entity.key)
            elif isinstance(e.entity, NumberEntity):
                target = self.tub.set_number(e.entity.key, float(payload))
                log.info("%s target set to %s", e.entity.key, target)
        except TransmitForbidden as exc:
            log.warning("ignored %s: %s (set spa.transmit: true to enable commands)", e.entity.key, exc)
        except ValueError:
            log.warning("ignored %s: bad payload %r", e.entity.key, payload)
