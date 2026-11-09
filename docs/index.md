# spa2mqtt

spa2mqtt connects the RS485 bus of a Balboa-family "encrypted" hot-tub controller to
Home Assistant. RS485 is the two-wire serial bus that the tub's control board uses to talk
to its topside panel. The Jacuzzi J235 is the first supported tub. Related Jacuzzi and
Sundance boards use the same protocol family. The MQTT bridge also reads one unencrypted
Jacuzzi, the J345, through its ProLink module.

You can run it in two ways. Both use the same tub definitions, so both give the same
entities in Home Assistant.

| | MQTT bridge | ESPHome component |
|---|---|---|
| Runs on | Any Docker host (Python) | An ESP32 with an RS485 transceiver |
| Connects to the tub through | An RS485-to-TCP adapter such as the EW11A, or a USB RS485 adapter | The ESP32's own UART |
| Talks to Home Assistant through | An MQTT broker, with MQTT discovery | The ESPHome native API |
| Install guide | [Docker Compose](install/docker-compose.md) or [Portainer](install/portainer.md) | [ESPHome](esphome/index.md) |

<div class="s2m-diagram" markdown="0">
--8<-- "assets/architecture.svg"
</div>

!!! danger "Mains voltage"
    A spa contains mains voltage and can deliver a large fault current. Isolate the spa at
    its breaker before you open any panel. Wiring anything into it is at your own risk.
    Read [Safety](safety.md) before you start.

## Receive-only by default

spa2mqtt never transmits to the tub unless you enable transmit. With transmit off, it only
listens, so a wrong setting or a wrong tub definition cannot change the tub. Buttons and the
temperature setpoint still appear in Home Assistant, but they show as unavailable. See
[Safety](safety.md) for what changes when you enable transmit.

## Where to start

1. Read [Getting started](getting-started.md). It helps you choose between the MQTT bridge
   and ESPHome, and it shows a read-only first run.
2. Install with [Docker Compose](install/docker-compose.md), [Portainer](install/portainer.md)
   or [ESPHome](esphome/index.md).
3. Look up settings in [Configuration](configuration.md).

## Supported tubs

| Model | Board | Definition | Status |
|---|---|---|---|
| Jacuzzi J235 (2018) | Encrypted (C4/CC frames) | `jacuzzi_j235` | Sensors confirmed against labelled captures. The transmit path is tested against a simulated board, not yet against the tub. |
| Jacuzzi J345 (J-300 series) | Plain (0x16 frames) via the ProLink module | `jacuzzi_j345` | MQTT bridge only. Decoded from the owner's captures; transmit reproduces captured pyjacuzzi frames; not yet run against the tub by this project. See the [J345 guide](tubs/jacuzzi-j345.md). |

To add your tub, see [Monitor and capture](monitor-and-capture.md) and
[Tub definitions](tub-definitions.md).

## Credits

spa2mqtt builds on community reverse engineering:
[HyperActiveJ](https://github.com/HyperActiveJ/sundance780-jacuzzi-balboa-rs485-tcp),
[dhmsjs/pyjacuzzi](https://github.com/dhmsjs/pyjacuzzi),
[garbled1/pybalboa](https://github.com/garbled1/pybalboa),
[ccutrer/balboa_worldwide_app](https://github.com/ccutrer/balboa_worldwide_app),
[jackbrown1993/Jacuzzi-RS485](https://github.com/jackbrown1993/Jacuzzi-RS485) and
[Iraithium/sundance-rs485-controller](https://github.com/Iraithium/sundance-rs485-controller).
