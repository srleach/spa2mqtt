# spa2mqtt

Bridges the RS485 bus of Balboa-family "encrypted" hot-tub controllers (Jacuzzi J235 and
relatives, Sundance-style boards) to Home Assistant. Two ways to run it, one shared set of
tub definitions:

* **MQTT bridge** (Python, Docker): talks to an RS485-to-TCP adapter (e.g. EW11A) or a USB
  RS485 adapter and publishes Home Assistant MQTT discovery.
* **ESPHome component** `spa_bus`: runs on an ESP32 with an RS485 transceiver and exposes the
  same entities natively over the ESPHome API, with no extra box and no cloud.

**Documentation: <https://seanrleach.co.uk/spa2mqtt/>**

> **Warning.** A spa contains mains voltage and a large potential fault current. Isolate it
> at the breaker before you open any panel. Wiring anything into it is at your own risk.
> Read the [safety page](https://seanrleach.co.uk/spa2mqtt/safety/) first.

## Safety: receive-only by default

Both implementations **never transmit unless you set `transmit: true`** (or
`SPA_TRANSMIT=true`), and even then only when a command is issued (nothing is sent at
start-up). While transmit is off, buttons and the setpoint control are announced but shown
as unavailable (MQTT) or log a warning (ESPHome). Every write to the bus goes through one
function marked `TRANSMITS`, and a test enforces it.

## Quick start: MQTT bridge (Docker Compose)

First check the bus with the read-only monitor. It never transmits and never connects to
MQTT. Stop anything else that connects to the adapter first.

```bash
docker run --rm -it ghcr.io/srleach/spa2mqtt:2 spa2mqtt monitor 192.168.1.100
```

Then run the bridge from the published image:

```bash
mkdir -p ~/spa2mqtt && cd ~/spa2mqtt
curl -fsSLO https://raw.githubusercontent.com/srleach/spa2mqtt/main/deploy/docker-compose.yml
curl -fsSL -o .env https://raw.githubusercontent.com/srleach/spa2mqtt/main/deploy/.env.example
# edit .env: SPA_IP, MQTT_BROKER, MQTT_USERNAME, MQTT_PASSWORD
docker compose up -d
```

Guides: [Docker Compose](https://seanrleach.co.uk/spa2mqtt/install/docker-compose/),
[Portainer](https://seanrleach.co.uk/spa2mqtt/install/portainer/) (including Home
Assistant OS), [configuration reference](https://seanrleach.co.uk/spa2mqtt/configuration/).

## Quick start: ESPHome

```yaml
external_components:
  - source: github://srleach/spa2mqtt@v2.0.0
    components: [spa_bus]

packages:
  spa_entities: github://srleach/spa2mqtt/esphome/packages/jacuzzi_j235.yaml@v2.0.0

uart:
  id: spa_uart
  tx_pin: GPIO17
  rx_pin: GPIO18
  baud_rate: 115200

spa_bus:
  uart_id: spa_uart
  definition: jacuzzi_j235
  transmit: false
```

A complete device is in [`esphome/example-jacuzzibridge-esp.yaml`](esphome/example-jacuzzibridge-esp.yaml)
(Waveshare ESP32-S3-ETH-8DI-8RO). See the [ESPHome guide](https://seanrleach.co.uk/spa2mqtt/esphome/).

## Versions

Every merge to `main` creates a semver release tag `vX.Y.Z` and a multi-arch image
`ghcr.io/srleach/spa2mqtt` tagged `X.Y.Z`, `X.Y`, `X`, `latest` and `sha-<short>`. Pin the major version
(`:2`) or a full version. See [Releases and versions](https://seanrleach.co.uk/spa2mqtt/releases/).

## Supported tubs

| Model | Board | Definition | Status |
|---|---|---|---|
| Jacuzzi J235 (2018) | encrypted (C4/CC) | `jacuzzi_j235` | Sensors confirmed against labelled captures; transmit path implemented and tested against a simulated board, not yet against the tub |

To add a tub, see [Tub definitions](https://seanrleach.co.uk/spa2mqtt/tub-definitions/) and
[Monitor and capture](https://seanrleach.co.uk/spa2mqtt/monitor-and-capture/). Captures are
welcome as issues or pull requests.

## Development

```bash
pip install -e ".[dev]"
ruff check . && ruff format --check . && mypy && pytest
docker compose up -d --build        # development image from this checkout; reads .env
pip install -r requirements-docs.txt && mkdocs serve   # documentation preview
```

The tests replay real captures. `tests/test_cpp_core.py` compiles the ESPHome component's
C++ core on the host and checks it decodes every captured frame exactly as the Python bridge does.

Background reading: [wire protocol](docs/protocol.md), [design](docs/design.md),
[research notes](docs/research-notes.md), [history](docs/history.md).

## Credits

Built on community reverse engineering:
[HyperActiveJ](https://github.com/HyperActiveJ/sundance780-jacuzzi-balboa-rs485-tcp) (Sundance 780),
[dhmsjs/pyjacuzzi](https://github.com/dhmsjs/pyjacuzzi) (Jacuzzi/Prolink),
[garbled1/pybalboa](https://github.com/garbled1/pybalboa),
[ccutrer/balboa_worldwide_app](https://github.com/ccutrer/balboa_worldwide_app),
[jackbrown1993/Jacuzzi-RS485](https://github.com/jackbrown1993/Jacuzzi-RS485), and
[Iraithium/sundance-rs485-controller](https://github.com/Iraithium/sundance-rs485-controller)
(prior art for ESPHome). See [NOTICE](NOTICE) for details.

## Licence and trademarks

MIT, see [LICENSE](LICENSE). Jacuzzi, Balboa, Sundance and other product names are
trademarks of their owners. This project is not affiliated with, endorsed by or supported
by any of them. Use it at your own risk: it can void a warranty, and a wrong command can
change how your tub heats.
