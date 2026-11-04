# spa2mqtt

Bridges the RS485 bus of Balboa-family "encrypted" hot-tub controllers (Jacuzzi J235 and
relatives, Sundance-style boards) to Home Assistant. Two ways to run it, one shared set of
tub definitions:

* **MQTT bridge** (Python, Docker): talks to an RS485-to-TCP adapter (e.g. EW11A) or a USB
  RS485 adapter and publishes Home Assistant MQTT discovery.
* **ESPHome component** `spa_bus`: runs on an ESP32 with an RS485 transceiver and exposes the
  same entities natively over the ESPHome API, with no extra box and no cloud.

> **Warning.** A spa contains mains voltage and a large potential fault current. Wiring
> anything into it is at your own risk.

## Safety: receive-only by default

Both implementations **never transmit unless you set `transmit: true`**, and even then only
when a command is issued (nothing is sent at start-up). While transmit is off, buttons and the
setpoint control are announced but shown as unavailable (MQTT) or log a warning (ESPHome).
Every write to the bus goes through one function marked `TRANSMITS`, and a test enforces it.

## Documentation

* [`docs/protocol.md`](docs/protocol.md): the wire protocol, with evidence and a status
  (confirmed / inferred / hypothesis) on every claim.
* [`docs/research-notes.md`](docs/research-notes.md): sources, conflicts, open questions.
* [`docs/design.md`](docs/design.md): architecture, definition schema, ESPHome approach, migration.
* [`docs/history.md`](docs/history.md): how the project got here.

## MQTT bridge

```bash
cp config.yml.example config.yml   # set the adapter address and MQTT broker
docker compose up -d --build
```

Or without Docker: `pip install .` then `spa2mqtt run -c config.yml`.

Other commands:

```bash
spa2mqtt definitions                       # list tub definitions
spa2mqtt validate                          # validate all definitions
spa2mqtt replay tests/fixtures/captures/raw/2026-11-04T220754Z_j235_labelled.log
```

### Read-only check against the tub

`spa2mqtt monitor` decodes the live bus and prints it to the terminal. It does not connect to
MQTT, and it cannot transmit: the tub model runs receive-only, the module has no bus writer, and
the transport is wrapped so that any write raises. Stop the v1 container first. It transmits at
start-up, and the EW11A may accept only one TCP client.

```bash
git clone git@github.com:srleach/spa2mqtt.git && cd spa2mqtt
git checkout claude/relaxed-turing-ic1k9p
python3 -m venv .venv && . .venv/bin/activate && pip install -e .
spa2mqtt monitor 192.168.25.73 --interval 10 --record monitor-session.log
```

You get a full report straight away, then one every `--interval` seconds. Each report has the
latest raw status frame, the folded payload, every field with its evidence status, frame rates
and checksum errors. In between, the monitor prints each change and each topside button press
as it happens. Useful flags: `--describe` (field notes), `--quiet-changes`, `--json` (JSON
lines), `--serial /dev/tty…` (USB RS485 adapter), `--replay FILE` (decode a capture instead).
`--record` appends a raw capture in the `tools/capture.py` format, so a monitor session can be
added to the test fixtures afterwards.

### Migrating from v1

The v1 implementation is kept on branch `legacy/pre-rewrite`.

* Your existing `config.yml` keeps working: `spa.config`, `spa.connection.*` and the env vars
  `SPA_IP`, `SPA_PORT`, `VARIANT_DEFINITION`, `MQTT_*` are still read.
* HA identities are unchanged: same device (`185569045`), same `unique_id`s, discovery
  published to the same topics, so retained configs are replaced in place. Entity IDs stay
  the same.
* **Behaviour change:** buttons and *Temperature Set Control* are unavailable until you add
  `transmit: true` under `spa:` (or `SPA_TRANSMIT=true`).
* State topics move from `hmd/…` to `spa2mqtt/jacuzzi_j235/…`; HA follows automatically.
* New entities: *Pump 1 Speed*, *Light Button*, and disabled-by-default diagnostics.
* *Main Pump Status* now documents what it has always measured: pump 1 on **high**. *Circulation
  Pump Status* is pump 1 running at any speed (the J235 circulates on pump 1 low).

### Capturing data

`tools/capture.py` records raw bus traffic **without ever writing to it**, with typed labels
for what you do at the topside. Captures in that format replay through the whole pipeline
and are welcome as issues or PRs (`tests/fixtures/captures/raw/`).

```bash
python3 tools/capture.py 192.168.1.100 8899
```

## ESPHome

See [`esphome/example-jacuzzibridge-esp.yaml`](esphome/example-jacuzzibridge-esp.yaml) for a
complete device (Waveshare ESP32-S3-ETH-8DI-8RO, RS485 on GPIO17/18). The essentials:

```yaml
external_components:
  - source: github://srleach/spa2mqtt@main
    components: [spa_bus]

packages:
  spa_entities: github://srleach/spa2mqtt/esphome/packages/jacuzzi_j235.yaml@main

uart:
  id: spa_uart
  tx_pin: GPIO17
  rx_pin: GPIO18
  baud_rate: 115200

spa_bus:
  uart_id: spa_uart
  definition: jacuzzi_j235      # or a path to your own definition YAML
  transmit: false
```

The component reads the tub definition at compile time, so adding a tub needs no C++.
Entities can also be declared individually, e.g.
`sensor: [{platform: spa_bus, entity: current_temperature, name: Water}]`.

Moving from the MQTT bridge to ESPHome: stop the bridge, delete the MQTT device in Home
Assistant, then adopt the ESP. With `friendly_name: Jacuzzi J235` the entity IDs come out the
same.

## Adding a tub

1. Capture traffic with `tools/capture.py` while pressing topside buttons, and label them.
2. Copy `definitions/jacuzzi_j235.yaml`, adjust the field map, buttons and entities. The schema
   (`definitions/tub-definition.schema.json`) documents every key; `spa2mqtt validate` checks it.
3. Drop your capture into `tests/fixtures/captures/raw/` and add expectations to
   `tests/test_replay.py`.
4. Run `python3 tools/gen_esphome_package.py` to generate the ESPHome package.

Boards that use a different framing or cipher (e.g. unencrypted Jacuzzi 0x16) need a new codec
in `spa2mqtt/protocol/` and `esphome/components/spa_bus/spa_protocol.cpp`.

## Supported tubs

| Model | Board | Definition | Status |
|---|---|---|---|
| Jacuzzi J235 (2018) | encrypted (C4/CC) | `jacuzzi_j235` | Sensors confirmed against labelled captures; transmit path implemented and tested against a simulated board, not yet against the tub |

## Development

```bash
pip install -e ".[dev]"
ruff check . && ruff format --check . && mypy && pytest
```

The tests replay real captures. `tests/test_cpp_core.py` compiles the ESPHome component's
C++ core on the host and checks it decodes every captured frame exactly as the Python bridge does.

## Credits

Built on community reverse engineering:
[HyperActiveJ](https://github.com/HyperActiveJ/sundance780-jacuzzi-balboa-rs485-tcp) (Sundance 780),
[dhmsjs/pyjacuzzi](https://github.com/dhmsjs/pyjacuzzi) (Jacuzzi/Prolink),
[garbled1/pybalboa](https://github.com/garbled1/pybalboa),
[ccutrer/balboa_worldwide_app](https://github.com/ccutrer/balboa_worldwide_app),
[jackbrown1993/Jacuzzi-RS485](https://github.com/jackbrown1993/Jacuzzi-RS485), and
[Iraithium/sundance-rs485-controller](https://github.com/Iraithium/sundance-rs485-controller)
(prior art for ESPHome).
