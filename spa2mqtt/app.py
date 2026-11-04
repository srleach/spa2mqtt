"""Composition root: wires transport → protocol → tub → MQTT and runs the receive loop."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable

from . import __version__
from .config import AppConfig
from .definitions import TubDefinition, load_definition
from .protocol import FrameDecoder
from .transport import ReplayTransport, TcpTransport, TransmitForbidden, Transport
from .transport.serial import SerialTransport
from .tub import BusWriter, Tub

log = logging.getLogger(__name__)


def make_transport(cfg: AppConfig, definition: TubDefinition) -> Transport:
    t = cfg.transport
    if t.type == "tcp":
        return TcpTransport(t.host, t.port)
    if t.type == "serial":
        return SerialTransport(t.device, t.baud or definition.bus.baud)
    if t.type == "replay":
        return ReplayTransport(t.path, speed=t.speed, status_type=definition.status_type)
    raise ValueError(f"unknown transport type {t.type!r}")


async def pump(transport: Transport, tub: Tub, writer: BusWriter, decoder: FrameDecoder | None = None) -> None:
    """Read until end of stream. Frames the bus state machine wants to send go to the writer."""
    decoder = decoder or FrameDecoder()
    while True:
        chunk = await transport.read()
        if not chunk:
            return
        for frame in decoder.feed(chunk):
            for outgoing in tub.on_frame(frame):
                try:
                    await writer.send(outgoing)  # TRANSMITS (only when enabled)
                except TransmitForbidden as exc:  # pragma: no cover - BusClient never emits when disabled
                    log.error("%s", exc)


async def run(cfg: AppConfig, mqtt_enabled: bool = True, on_tub: Callable[[Tub], None] | None = None) -> None:
    definition = load_definition(cfg.definition)
    tub = Tub(definition, transmit=cfg.transmit)
    if cfg.transmit:
        log.warning("TRANSMIT ENABLED: commands from Home Assistant will be sent to the tub")
    else:
        log.info("transmit disabled (receive-only); command entities will be unavailable")
    if on_tub:
        on_tub(tub)

    bridge = None
    if mqtt_enabled:
        from .ha.bridge import MqttBridge, MqttSettings
        from .ha.discovery import DiscoveryConfig

        bridge = MqttBridge(
            tub,
            definition,
            DiscoveryConfig(
                discovery_prefix=cfg.discovery_prefix,
                base_topic=cfg.base_topic,
                device_name=cfg.device_name,
                device_identifier=cfg.device_identifier,
                unique_id_prefix=cfg.unique_id_prefix,
                legacy_topics=cfg.legacy_topics,
                sw_version=__version__,
            ),
            MqttSettings(cfg.mqtt_host, cfg.mqtt_port, cfg.mqtt_username, cfg.mqtt_password),
            heartbeat=cfg.heartbeat,
            heartbeat_overrides=cfg.heartbeat_overrides,
        )
        bridge.start(asyncio.get_running_loop())

    async def heartbeat() -> None:
        while bridge is not None:
            await asyncio.sleep(5)
            bridge.heartbeat()

    hb = asyncio.create_task(heartbeat())
    backoff = 1.0
    try:
        while True:
            transport = make_transport(cfg, definition)
            writer = BusWriter(transport, enabled=cfg.transmit)
            try:
                await transport.connect()
                backoff = 1.0
                await pump(transport, tub, writer)
                if cfg.transport.type == "replay":
                    return
                log.warning("bridge closed the connection")
            except (ConnectionError, OSError) as exc:
                log.warning("transport error: %s", exc)
            finally:
                await transport.close()
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60.0)
    finally:
        hb.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await hb
        if bridge is not None:
            bridge.stop()
