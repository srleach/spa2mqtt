# spa2mqtt v2: design

Status: **plan**, written before implementation (phase 2). Deviations found during
implementation are recorded in §11 and in the pull request.

## 1. Goals and non-goals

**Goals**

1. Keep the deployed architecture: RS485 ↔ tub, MQTT ↔ Home Assistant, as a Docker
   container talking to an RS485-to-TCP bridge (EW11A).
2. Separate the code into layers with one direction of dependency:
   transport → protocol codec → tub model → HA/MQTT.
3. **Config-driven tubs.** A new tub model is a data file (YAML, validated by a JSON
   Schema). No Python or C++ is needed unless it uses a framing or cipher family that does
   not exist yet.
4. A native **ESPHome external component** that consumes the *same* definition files, so the
   ESP32 exposes the same controls and sensors over the ESPHome API.
5. Keep the HA identities the current stack uses (`unique_id`s, device, entity IDs).
6. Tests that replay the captured dumps, plus lint, type checks and CI.

**Non-goals (this PR)**

* Lights, filter-cycle programming, menu automation, climate entity. The definition schema
  can express them later; there is no J235 evidence for them yet (protocol.md §9).
* Unencrypted (0x16) Jacuzzi boards on a direct RS485 tap, and on ESPHome. Since §11 row
  12 the bridge supports one such tub, the J345, through its ProLink module only
  (`protocol: jacuzzi_plain`, [protocol-plain.md](protocol-plain.md)). The legacy
  `jacuzzi_j335_unencrypted_*` debug definitions were not ported (debug-only, unverified,
  wrong message type): the J345 definition was written from the captures.

## 2. Safety model (transmit)

The single most important design rule: **nothing transmits unless explicitly enabled.**

* Both implementations have a `transmit` setting, **default `false`**. With it off, the
  transport is never written to; the code path that would write raises (Python) or returns
  early and logs (C++).
* All bus writes go through one choke point, marked `# TRANSMITS` / `// TRANSMITS`:
  * Python: `BusWriter.send()` in `spa2mqtt/tub/bus.py`.
  * C++: `SpaBus::transmit_frame_()` in `spa_bus.cpp`.
  * A test asserts that no other module calls `Transport.write`.
* No transmission at start-up. The legacy bridge claims a channel (0x01/0x03) automatically;
  the new code only claims a channel lazily, when the first command is queued **and**
  `transmit` is on.
* With `transmit: false`, command entities (buttons, setpoint number) are still announced, so
  HA identities stay intact, but they report as **unavailable** and commands are dropped with
  a warning.
* Development and CI use only replayed captures and an in-process mock board.

## 3. Architecture

```
                ┌───────────────── spa2mqtt (Python, Docker) ──────────────────┐
 RS485 ── EW11A ─► transport ─► protocol ─► tub ─────────► ha ──► MQTT ──► HA
          (TCP)    tcp/serial/   framing,    decoder,      discovery,
                   replay        crc, cipher state, bus,   bridge
                                             setpoint
                       ▲                        ▲
                       └──── definitions/*.yaml (JSON Schema) ────┐
                                                                  │ read at compile time
                ┌──────────── ESPHome external component ─────────┴──────────┐
 RS485 ── UART ─► SpaBus (C++): FrameDecoder → fold → field table → entities ─► ESPHome API ─► HA
                  generated from the definition by esphome/components/spa_bus/__init__.py
                └──────────────────────────────────────────────────────────────┘
```

### 3.1 Python module layout

```
spa2mqtt/
  __main__.py            CLI: run | replay | decode | validate
  app.py                 composition root (builds the layers from config)
  config.py              runtime config (YAML + env vars, legacy keys accepted)
  transport/
    base.py              Transport protocol: async read_chunk(); write() (guarded)
    tcp.py               TCP client with reconnect/backoff (EW11A)
    serial.py            optional direct serial (pyserial-asyncio extra)
    replay.py            replays '<epoch> RX <hex>' capture logs; refuses write()
  protocol/
    crc.py               CRC-8 0x07/0x02/0x02
    framing.py           streaming FrameDecoder, encode_frame()
    frame.py             Frame dataclass (addr, mid, type, payload)
    cipher.py            fold(), cc_encode()/cc_decode()
  definitions/
    model.py             typed dataclasses (TubDefinition, FieldDef, EntityDef, …)
    loader.py            resolve name/alias/path → validate (jsonschema + semantics) → model
  tub/
    decoder.py           status payload → {field: value} using FieldDef transforms
    state.py             TubState: last values, change detection, timestamps
    bus.py               BusClient state machine (LISTEN/CLAIM/REQUESTED/READY), BusWriter,
                         DirectBusClient (fixed address, no claim: plain boards via ProLink)
    control.py           CommandQueue, SetpointController (press loop with retries)
  ha/
    discovery.py         pure functions: definition + install config → discovery payloads
    bridge.py            paho-mqtt client: publish config/state/availability, route commands
definitions/
  tub-definition.schema.json
  jacuzzi_j235.yaml
  jacuzzi_j345.yaml      plain protocol, bridge only
esphome/
  components/spa_bus/    __init__.py, sensor.py, binary_sensor.py, button.py, number.py,
                         text_sensor.py, spa_bus.{h,cpp}, spa_protocol.{h,cpp} (framework-free)
  example-jacuzzibridge-esp.yaml
tools/
  capture.py             receive-only raw capture (never writes)
  research/              analysis scripts behind docs/protocol.md
tests/
  fixtures/captures/     raw/*.log, decoded/*.csv (ground truth)
  test_*.py              unit + replay tests
  cpp/                   host-compiled tests of spa_protocol.cpp against the same fixtures
```

Dependencies: `PyYAML`, `paho-mqtt>=2`, `jsonschema`. Optional: `pyserial-asyncio`.
`ha-mqtt-discoverable` is dropped. It hid the topic scheme, forced pydantic, and the bridge
needs exact control of topics to keep HA identities (§8).

### 3.2 Data flow (Python)

1. The transport yields byte chunks.
2. `FrameDecoder` resynchronises on `7E`, frames by `LEN`, checks the CRC and yields `Frame`s.
3. `BusClient` sees every frame (CTS/CC bookkeeping). Status frames whose `type` matches the
   definition go to the decoder, which applies `fold` and the field transforms.
4. `TubState.update()` returns the fields that changed.
5. `ha.bridge` publishes changed values immediately. Unchanged values are re-published every
   `heartbeat` seconds (default 60, per-entity overrides), as the legacy `sensor_update_intervals` did.
6. HA commands go through `ha.bridge` → `tub.control` (button press / setpoint target) →
   `CommandQueue` → `BusClient` sends on the next CTS for our channel (if transmit is enabled).

## 4. Tub-definition schema

One YAML file per tub model in `definitions/`, validated by
`definitions/tub-definition.schema.json` (JSON Schema draft 2020-12) plus semantic checks in
the loader (referenced fields/buttons exist, byte offsets within the payload length, unique
keys). Sketch:

```yaml
schema_version: 1
id: jacuzzi_j235
aliases: [jacuzzi_j235_encrypted]       # legacy config name keeps working
name: Jacuzzi J235
manufacturer: Jacuzzi
model: J235
protocol: balboa_encrypted              # codec family implemented in code
temperature_unit: C

bus:                                    # only used when transmit is enabled
  baud: 115200
  client_mid: 0xBF
  channel_request_magic: [0xF1, 0x73]
  dormant_channel_threshold: 5

status:
  type: 0xC4
  decode: fold                          # fold | unkey | decrypt (J235 today) | plain (jacuzzi_plain)
  length: 16                            # decoded payload bytes

commands:
  type: 0xCC
  encode: cc_xor                        # [K, K ^ 0xE0 ^ code]
  buttons: {temp_up: 0x01, temp_down: 0x02, pump_1: 0x04, pump_2: 0x05}

fields:                                 # decoded-payload field map
  water_temperature: {byte: 5, xor: 0x02, scale: 0.5, status: confirmed, evidence: "protocol.md §5 d5"}
  setpoint:          {byte: 8, scale: 0.5, status: inferred}
  heater:            {byte: 10, bit: 6, status: inferred}
  hour:              {byte: 0, xor: 0x06, status: confirmed}

entities:
  - key: current_temperature            # stable key = HA unique_id suffix (legacy: whole id)
    component: sensor                   # sensor | binary_sensor | button | number | text_sensor | switch
    field: water_temperature
    name: Current Water Temperature
    device_class: temperature
    unit_of_measurement: "°C"
    state_class: measurement
    icon: mdi:coolant-temperature
  - key: pump_1_button
    component: button
    press: pump_1
  - key: temperature_set_control
    component: number
    field: setpoint
    control: {type: stepper, up: temp_up, down: temp_down}
    min: 20
    max: 40
    step: 0.5
    mode: slider
```

**Field transform** (identical in Python and C++, golden-tested across both):

```
raw = big-endian integer of decoded[byte : byte + length]      (length default 1)
raw = raw ^ xor                                                 (default 0)
if bit is set:    value = (raw >> bit) & 1           → bool
else:             raw   = (raw >> shift) & mask      (defaults 0, all ones)
                  if raw in invalid: value = None
                  elif map:  value = map[raw]  (unknown raw → None, warn once)
                  else:      value = raw * scale + offset       (defaults 1, 0)
```

Every field carries `status: confirmed | inferred | hypothesis`, mirroring protocol.md. The
bridge logs hypothesis-backed entities at start-up. An entity may set
`enabled_by_default: false` (used for new diagnostics, not for the legacy set).

**What needs code vs data.** A new tub that speaks `balboa_encrypted` with a different field
map, button set, or entity list needs only a YAML file. A new framing or cipher family needs
a codec in `protocol/` and `spa_protocol.cpp`. The `protocol` key selects it, and an unknown
value fails validation.

## 5. Runtime configuration (bridge)

`config.yml` (or env vars). Install-specific settings live here, not in the definition:

```yaml
spa:
  definition: jacuzzi_j235          # legacy key `config:` accepted
  transport: {type: tcp, host: 192.168.1.100, port: 8899}   # legacy spa.connection.* accepted
  transmit: false                   # MUST be set true to send any command
mqtt: {broker: …, port: 1883, username: …, password: …}
ha:
  discovery_prefix: homeassistant
  device_name: Jacuzzi J235
  device_identifier: "185569045"    # legacy device id, keeps the HA device
  unique_id_prefix: ""              # "" = legacy bare unique_ids (default)
  legacy_topics: true               # publish discovery to the ha-mqtt-discoverable topics
  heartbeat: 60
  heartbeat_overrides: {secondary_pump_status: 90, circulation_pump_status: 90}
```

Decision: `unique_id_prefix` defaults to `""` because the only deployed install relies on
bare unique_ids. New installs with more than one MQTT integration should set a prefix; this
is documented in the README.

## 6. Bus state machine and setpoint control

Implemented as in protocol.md §4, with these choices:

* **LISTEN** always; it records `known_channels` (CTS targets) and `active_channels` (CC sources).
* A channel is claimed only when the command queue is non-empty and transmit is on.
* Dormant-channel reuse is tried first, then a 0x01 request on the next 0x00.
* A CC seen from another device on our channel drops back to LISTEN (conflict).
* **SetpointController:** target clamped to entity min/max and rounded to `step`. On each
  status frame:
  1. If `|setpoint − target| < step/2`, done.
  2. Otherwise, at most one press is in flight. Press up or down, then wait for
     `confirm_frames` (default 3) status frames.
  3. If the setpoint did not move, retry. Give up after `max_attempts` (default 40, enough
     for 20 °C of travel), logged.
  4. A topside change during the loop is respected: a new HA target replaces the old one, and
     no automatic re-assertion happens after completion.
  This replaces the legacy approach of queueing *N* presses at once and assuming each one
  lands.
* Buttons enqueue a single press. There is no de-duplication; HA buttons are momentary.
* **ToggleController** (`switch` entities): the target is on or off. On each status frame:
  1. If the field equals the target, done. No press is sent when it already does.
  2. Otherwise, at most one press is in flight. Press, then wait `confirm_frames` (default
     10) status frames for the field to follow. A change in `progress_field` (a pump speed)
     ends the wait at once: the press landed, and the cycle needs another.
  3. Give up after `max_presses` (default 3), logged. The J235 board keeps pump 1 on while
     it heats or filters, so "off" can be impossible.

**Direct bus mode** (`bus.mode: direct`, protocol-plain.md §6–§7). A ProLink module's TCP
stream has no CTS, so `DirectBusClient` replaces the claim logic for `jacuzzi_plain`
definitions:

* Frames are sent from the fixed `bus.client_address`. There is no channel state.
* The queue holds whole frames (button presses and direct commands), at most 8.
* One frame is released per `send_gap_frames` status frames. Only status frames count, so
  the spacing follows the tub's own cadence.
* `bus.hello`, when set, is sent once per connection, immediately before the first queued
  frame. Nothing is sent at start-up.
* `Tub.on_connect()` (called by the app after each transport connect) clears the queue and
  re-arms the hello, so a command queued before an outage is not sent after it.
* A `number` with `control.type: direct` is one frame with the value rounded to `step`. A
  value outside `min`..`max` is refused, not clamped. There is no `SetpointController` and
  no retry: pyjacuzzi sent each command once, and all took.
* A `switch` is one frame, sent only when the field differs from the target. The loader
  requires `max_presses: 1`.
* A direct command may carry `requires` (status bit fields and the value each must have).
  `Tub` refuses the command (`CommandBlocked`) when the last status frame disagrees or none
  has been decoded. The J345 uses it to block the setpoint in Celsius mode.
* Both clients hand frames to the same `BusWriter`, which stays the only writer.

## 7. ESPHome component (`spa_bus`)

**Native, no Docker sidecar.** Everything the bridge does fits on an ESP32: UART at 115200,
40-byte frames, a CRC table, a 16-byte field decode, a small state machine. IR proves the same
workload on an ESP32 for Sundance boards. There is nothing that needs a sidecar.

```yaml
external_components:
  - source: github://srleach/spa2mqtt@main
    components: [spa_bus]
uart:
  id: spa_uart
  tx_pin: GPIO17
  rx_pin: GPIO18
  baud_rate: 115200
spa_bus:
  id: spa
  uart_id: spa_uart
  definition: jacuzzi_j235        # name/alias from definitions/, or a path to a YAML file
  transmit: false                 # default; buttons/number unavailable when false
  # flow_control_pin: GPIOxx      # RS485 DE/RE if the transceiver needs it
sensor:
  - platform: spa_bus
    entity: current_temperature   # key from the definition
    name: Current Water Temperature
```

**Sharing the definitions.** `external_components` clones the whole repository, so the
component's Python code (`__init__.py`) reads `definitions/<name>.yaml` from the clone at
**compile time**. It validates the file with the same schema (the `jsonschema` package if
available, otherwise structural checks; the full validation runs in CI) and generates C++
calls that load the field table, button codes and entity bindings into `SpaBus`:

```cpp
spa->add_field(5, 1, 0x02, 0, 0xFF, -1, 0.5f, 0.0f);   // water_temperature
spa->add_button("pump_1", 0x04);
```

Platforms reference definition entities by `entity:` key. Final validation checks that the
key exists and that its `component` matches the platform. Default `name`, `device_class`,
`unit`, `icon`, `state_class` and `entity_category` come from the definition, so a minimal
YAML only needs `entity:`. To avoid hand-writing a dozen entries, a generated
**package** `esphome/packages/<definition>.yaml` lists every entity of a definition.
`tools/gen_esphome_package.py` regenerates it, and CI fails if it is stale.

**C++ structure.**

* `spa_protocol.{h,cpp}`: framework-free (no ESPHome headers). CRC, `FrameDecoder`, fold, CC
  encode, field decode. Compiled on the host in CI and run against the same fixtures as the
  Python tests (golden JSON produced by the Python decoder).
* `spa_bus.{h,cpp}`: the ESPHome `Component` + `UARTDevice`. Reads the UART in `loop()`, owns
  the bus state machine, the command queue, the setpoint controller, and the entity bindings.
* Entities: `SpaSensor`, `SpaBinarySensor`, `SpaButton`, `SpaNumber`, plus a diagnostic
  `text_sensor` (bus state: listening / claiming / ready / tx disabled).
* Entities publish on change plus a heartbeat (default 60 s). Command entities are marked
  unavailable when `transmit: false`.

## 8. HA identity preservation and migration

**MQTT bridge (drop-in replacement).**

* Same device: identifiers `185569045`, name `Jacuzzi J235`. Manufacturer/model are corrected
  to `Jacuzzi`/`J235`; HA updates those in place.
* Same `unique_id`s: bare entity keys (`current_temperature`, `heater_active`, …).
* Same discovery **config topics** as ha-mqtt-discoverable:
  `homeassistant/<component>/Jacuzzi-J235/<clean(name)>/config` with
  `clean = re.sub(r"[^A-Za-z0-9_-]", "-", s)`. The new retained config replaces the old
  one in place, so there is no duplicate-unique_id conflict and no orphaned retained message.
* State and command topics move from `hmd/<component>/Jacuzzi-J235/<Name>/…` to
  `spa2mqtt/<device>/<key>/{state,set}` plus a shared availability topic. The config payload
  announces them, so HA follows automatically. Old `hmd/…` state topics are not retained by
  the legacy code (except availability), so nothing is left over.
* Entity IDs are unchanged, because HA keys the registry by `unique_id`. **Behavioural change:**
  buttons and the setpoint number are unavailable until `spa.transmit: true` is set.

**ESPHome (optional, later).** The ESPHome device is a new HA device. If its
`friendly_name` is `Jacuzzi J235`, ESPHome generates the **same entity IDs**
(`sensor.jacuzzi_j235_current_water_temperature`, …). The switch-over is therefore:

1. Stop the bridge.
2. Delete the MQTT device in HA, so the entity IDs are released.
3. Flash and adopt the ESP.

Long-term statistics follow the entity ID. The example YAML uses `friendly_name: Jacuzzi J235`
for this reason.

**Rollback.** The legacy code is preserved on branch `legacy/pre-rewrite` (`b0a5323`).
The legacy `config.yml` keys keep working, so rolling back is a container image change.

## 9. Test strategy

| Layer | Tests | Fixtures |
|---|---|---|
| CRC / framing | known-good frames, corrupted CRC, split chunks, junk between frames, 0x7E inside payload, oversize LEN | D1 raw frames; synthetic |
| Cipher | fold on D1 equals expected; fold ⇔ key-stream identity; CC encode/decode on the SC example frame | D1, SC/HJ frames |
| Field decode | every decoded CSV row decodes; clock fields match filename wall-clock; timeline assertions (heater on rows 1–51, circulation rows 1–277, idle afterwards) | D2–D6 |
| Replay end-to-end | raw D1 through the full pipeline → expected HA states; CSVs re-encoded to frames with random keys (marked synthetic) → identical decode | D1–D6 |
| Definitions | every `definitions/*.yaml` validates; J235 entity keys ⊇ HA entity set; semantic checks fail on broken examples | – |
| HA discovery | snapshot of every config payload (topic, unique_id, device, command/state topics) | – |
| Bus / control | mock board: no write ever with transmit off; dormant-channel claim; request/ack; setpoint loop converges, retries, gives up; conflict handling | in-process mock |
| C++ core | host build of `spa_protocol.cpp`; decode every fixture frame and compare with Python's golden JSON | same fixtures |
| ESPHome | `esphome config` on the example; `esphome compile` in CI (slow job) | example YAML |

Tooling: `ruff` (lint and format), `mypy --strict` on `spa2mqtt/`, `pytest`, GitHub Actions
jobs `python`, `cpp`, `esphome`.

## 10. Decisions log

| # | Decision | Why |
|---|---|---|
| 1 | ~~Canonical decode is the pairwise fold (Model B)~~, superseded by §11 row 11 (per-byte decryption). | Key-independent; correct calendar day on J235; equals the legacy definition offsets, so identities and history are unaffected (protocol.md §3.2). |
| 2 | Drop `ha-mqtt-discoverable`; use paho directly. | Needed exact topic control for identity preservation; fewer dependencies (pydantic). |
| 3 | `transmit` defaults to false in both implementations. | User constraint and bus safety; the legacy code transmitted at start-up. |
| 4 | Lazy channel claim. | Never touch the bus unless a command needs it. |
| 5 | Keep hypothesis-backed legacy entities (main/secondary pump, manual circulation). | They are the minimum set HA uses today. They are flagged `status: hypothesis` and documented. |
| 6 | Definitions are YAML with a JSON Schema in the repo root `definitions/`. | Human-editable; one source for Python and ESPHome codegen. |
| 7 | ESPHome entities are declared by `entity:` key plus a generated package, rather than auto-created by the hub. | Idiomatic ESPHome (users can rename, filter, hide); explicit IDs; still zero duplication via the package. |
| 8 | Legacy unencrypted J335 definitions are not ported. | Debug-only, unverified, used the wrong message type for plain boards. The J345 definition (§11 row 12) was written from captures instead. |
| 9 | Temperature unit is configuration, not decoded. | No unit flag is known on encrypted boards (protocol.md §8). |
| 10 | Wire format for captures is `<epoch> RX <hex>` / `MARK`. | Same file from the capture tool, the replay transport, and the tests. |
| 11 | A tub nobody on the project can test may transmit only frames a capture shows working. Every button and direct command carries a status and evidence, and a test enumerates what the definition can emit. | The J345 is driven on the strength of its owner's pyjacuzzi capture. A decode error shows a wrong value; a wrong frame acts on someone else's tub. |
| 12 | The Home Assistant device name and identifier default from the tub definition (`ha:`, else `name` and `id`). The J235 pins `185569045` in its YAML. | Environment-only installs (Portainer on Home Assistant OS) cannot set `ha:` keys, and a second tub must not appear as "Jacuzzi J235". |
| 13 | A `text_sensor` is published to Home Assistant as a `sensor`. The bridge clears the retained config it used to publish under `text_sensor`. | Home Assistant's MQTT discovery has no `text_sensor` component, so Pump 1 Speed and Light Mode never appeared. `text_sensor` stays in definitions because it is the ESPHome platform name. |
| 14 | Pump switches are new entities next to the pump buttons, and they are bridge-only. | The buttons keep their keys and names, so no Home Assistant entity changes. The ESPHome component would need a new platform and a second controller in the C++ core; the package generator leaves switches out until then. |
| 15 | `spa2mqtt capture` compares keyed frames after removing the key, and writes the capture file format. | The J235 re-keys every status, lights and panel frame, so a byte comparison would suppress nothing. A dump that replays needs no second parser. |

## 11. Deviations from this plan

| # | Deviation | Why |
|---|---|---|
| 1 | Mid-implementation, the owner's labelled raw capture (D7) arrived. The J235 definition gained `pump_1_speed` (text sensor), `light_button`, `set_mode`, and two disabled-by-default diagnostics. Internal field names were renamed to their confirmed meaning (`pump_1_running`, `pump_1_high`). Entity keys and names were unchanged. | Evidence over folklore (protocol.md §5). HA identities untouched. |
| 2 | Channel acquisition: the 0x00/0x01 request is the primary path; dormant-channel reuse is kept as a fallback. | D7 shows the topside answers every CTS on the only polled channel, so there is never a dormant channel on this install. |
| 3 | SetpointController waits for movement instead of counting presses. | D7: the first press only enters set mode. The planned loop already tolerated this; tests now model it explicitly (mock board). |
| 4 | ESPHome command entities cannot be marked unavailable individually. With `transmit: false` they log a warning and do nothing, and the optional `bus_state` text sensor reads `receive-only`. | ESPHome entities have no per-entity availability. The MQTT bridge does mark them unavailable. |
| 5 | The ESPHome `definition.py` loader uses `jsonschema` only when installed (ESPHome does not ship it) and otherwise does structural checks. CI validates every definition with the full schema. | Avoid forcing an extra dependency into users' ESPHome environments. |
| 6 | `SpaCore` (definition tables + decoder + bus + setpoint loop) lives in the framework-free header, and `SpaBus` is a thin ESPHome wrapper. | Lets the host test drive the exact production state machine, not a copy. |
| 7 | Docker image build is verified in CI only. | No Docker daemon in the development sandbox. |
| 9 | Set-mode awareness: `control.set_mode_field` names the bit that shows the topside's set screen. The controller treats a press that opens set mode as the wake press and steps on the next frame. It also no longer counts down while its press is still queued for a bus slot. | protocol.md §7a. The queued-press guard fixes a real overshoot found by the new tests (a slow channel grant caused duplicate presses). Ported to the C++ core. |
| 11 | Status decoding moved from the pairwise fold to per-byte decryption (`status.decode: decrypt` with a `keystream`). Fields read plaintext with no per-field XOR. Legacy fold-only logs are rebuilt through `status.fold_template`. | Raw captures showed the fold loses data when both bytes of a pair change (protocol.md §3.3). The fix also makes the field map portable to Sundance boards. It supersedes decision 1. |
| 10 | `spa2mqtt monitor`: a standalone, read-only live decoder for the terminal (text or JSON lines, optional raw recording). | The owner's first contact with the real tub runs without MQTT and without any transmit path. |
| 8 | ~~Unencrypted Jacuzzi captures from unmerged PR 12 were recovered into `tests/fixtures/captures/unencrypted/` but are not decoded.~~ Superseded by row 12. | They evidenced the `plain` codec non-goal; no J235 relevance. |
| 12 | The plain protocol is supported for one tub, the Jacuzzi J345 behind a ProLink module: `protocol: jacuzzi_plain`, `status.decode: plain`, a second decoded frame (`extra_frames`, lights 0x23), `commands.direct`, and `bus.mode: direct`. Bridge only: the ESPHome loader rejects the protocol and the package generator skips it. No C++ changed. | A contributor's tub, with five captures that include a pyjacuzzi session of working commands. The ProLink stream has no CTS, so the claim logic cannot send to it. |
