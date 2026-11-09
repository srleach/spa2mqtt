# Jacuzzi J235 (EW11A or ESP32)

This guide sets up spa2mqtt for a Jacuzzi J235: a J-200 series tub from 2018 with the
**encrypted** Balboa-family control board. spa2mqtt reads the board's RS485 bus through an
RS485-to-TCP adapter such as the Elfin EW11A, or through an ESP32 running the ESPHome
component. The definition ID is `jacuzzi_j235`. It is the default, so most settings on
this page are the defaults.

!!! note "Tested on the project's own tub"
    Every sensor was checked against labelled captures from the project's own J235.
    Transmit runs on that tub through the MQTT bridge and an EW11A (November 2026): the
    board granted the bridge channel `0x11`, and the buttons, *Temperature Set Control*
    and the switches act at the topside. Start receive-only on a new install, and watch
    the topside for the first commands.

## What is supported

Each row has the evidence status from the definition. *Confirmed* means a labelled
capture shows the change at the topside and the same change in the bytes. *Hypothesis*
means a pattern in the data, or a name from another project, that no capture confirms.
The [wire protocol](../protocol.md#5-c4-status-field-map-j235) has the bytes.

### Read

| Entity | Status | Notes |
|---|---|---|
| Current Water Temperature | Confirmed | °C, in 0.5 °C steps |
| Target Water Temperature | Confirmed | °C, in 0.5 °C steps |
| Pump 1 Speed | Confirmed | `off`, `low` or `high` |
| Main Pump Status | Confirmed | Pump 1 on high: the jets |
| Circulation Pump Status | Confirmed | Pump 1 running at any speed. The J235 has no separate circulation pump: it heats and filters on pump 1 low |
| Secondary Pump Status | Confirmed | Pump 2. Single speed |
| Heater Active | Confirmed | |
| Light Mode | Confirmed | `off`, a colour name, `blend` or `blend paused`. MQTT bridge only |
| Filter Change Days, Water Change Days, UV Lamp Days | Confirmed | The topside menu's FC, H2O and UV countdowns, in days. Diagnostics |
| Manual Circulation Call | Hypothesis | Never seen set on this tub |
| Set Mode Active, Display State, Secondary Value Raw | Mixed | Diagnostics, disabled by default |

### Control

All controls are unavailable until you [enable transmit](#enable-transmit).

| Entity | What it does |
|---|---|
| Temperature Increment, Temperature Decrement | One press of Temp up or Temp down. The first press only opens the set screen |
| Temperature Set Control | Presses Temp up or down until the setpoint matches. Range 20 to 40 °C, step 0.5 |
| Pump 1 Button, Pump 2 Button, Light Button | One press of that topside button. Pump 1 steps off, low, high, off |
| Pump 1 (switch) | The jets. Presses Pump 1 until pump 1 is on high, or off. MQTT bridge only |
| Pump 1 Low (switch) | Pump 1 low speed. Its "off" is pump 1 fully off, so from low it steps through high to off. MQTT bridge only |
| Pump 2 (switch) | Presses Pump 2 when it is not already in the state you chose. MQTT bridge only |
| Light (switch) | Presses Light until the light is on or off, about 7.5 s between presses. MQTT bridge only |

The button codes (`0x01`, `0x02`, `0x04`, `0x05`, `0x12`) were confirmed from the
topside's own presses in a capture. The bridge sends the same codes.

### Not supported

- Light colour, brightness and blend as direct controls. The light has one button: see
  [Known limits](#known-limits).
- Clock setting, filter cycles, heat mode, ClearRay and the menu. The maintenance
  countdowns are read only: reset them at the topside.
- Fahrenheit. The board gives no unit flag, and every capture is in °C. The definition is
  Celsius only.

## Hardware path

The bridge and the ESP32 both connect to the RS485 header on the control board. The
header is meant for a second topside panel and is usually free. It carries 12 V, 0 V, A
and B. Isolate the spa at its breaker before you open the equipment bay. Read
[Safety](../safety.md) first.

| Item | Value |
|---|---|
| Bus | RS485, 115200 baud, 8N1 |
| EW11A mode | TCP server, port `8899`, transparent |
| ESP32 | Any ESP32 with a 3.3 V RS485 transceiver. See [Hardware and wiring](../esphome/hardware.md) |
| Bus address the bridge sends from | A channel the board gives it on the first command. Set at run time, not by the definition |

Connect A to A and B to B. If no status frames arrive and the serial settings are right,
swap A and B: a swap does no damage. Power the adapter or the ESP32 from its own supply
unless you know the rating of the header's 12 V.

The EW11A accepts one TCP client at a time. Stop the v1 bridge, a monitor or any other
tool before you start spa2mqtt. The v1 bridge must be stopped in any case: it claims a
bus channel at start-up.

## Install with Docker Compose

Follow [Install with Docker Compose](../install/docker-compose.md). The defaults in
`.env.example` are for this tub. Set the addresses:

```ini
SPA_IP=192.168.1.100
SPA_PORT=8899
SPA_DEFINITION=jacuzzi_j235
SPA_TRANSMIT=false
MQTT_BROKER=192.168.1.7
MQTT_PORT=1883
MQTT_USERNAME=
MQTT_PASSWORD=
```

## Install with Portainer on Home Assistant OS

Follow [Install with Portainer](../install/portainer.md), method A, with the stack file
[`deploy/portainer-stack.yml`](https://github.com/srleach/spa2mqtt/blob/main/deploy/portainer-stack.yml)
and these variables:

| Variable | Value |
|---|---|
| `SPA_IP` | EW11A address, for example `192.168.1.100` |
| `SPA_PORT` | `8899`, the default |
| `SPA_DEFINITION` | `jacuzzi_j235`, the default |
| `SPA_TRANSMIT` | `false` |
| `MQTT_BROKER` | Broker address. For the Mosquitto add-on, use the Home Assistant host's LAN address: `core-mosquitto` does not resolve from a Portainer stack |
| `MQTT_PORT` | `1883` |
| `MQTT_USERNAME`, `MQTT_PASSWORD` | Broker login, if the broker needs one |
| `LOG_LEVEL` | `INFO` |

`SPA_IP` and `MQTT_BROKER` are required, and the stack refuses to deploy without them.

## Install with ESPHome

Follow [ESPHome](../esphome/index.md): [Hardware and wiring](../esphome/hardware.md), then
[Build and flash](../esphome/install.md). The package
[`esphome/packages/jacuzzi_j235.yaml`](https://github.com/srleach/spa2mqtt/blob/main/esphome/packages/jacuzzi_j235.yaml)
lists every J235 entity the component supports.

The component decodes the status frame only. It has no *Light Mode* sensor and none of
the switches. The buttons and *Temperature Set Control* are the same.

## Upgrade from the v1 bridge

Version 2 replaces the v1 bridge in place. It keeps the device (`185569045`), the
`unique_id`s and the discovery topics, so every entity keeps its ID and history. Your v1
`config.yml` and `VARIANT_DEFINITION` still work. Two changes matter:

- Buttons and *Temperature Set Control* are unavailable until you enable transmit. v1
  transmitted by default.
- *Main Pump Status* is pump 1 on **high**. *Circulation Pump Status* is pump 1 at any
  speed.

See [Upgrade from v1](../configuration.md#upgrade-from-v1) for the full list.

## Verify, receive-only first

With transmit off, the bridge and the ESP32 never write to the bus.

1. Run the read-only monitor once
   ([Getting started](../getting-started.md#3-first-run-read-only-monitor)). The checksum
   error count stays at or near zero. A high count means a wrong baud rate or swapped A
   and B.
2. In Home Assistant, open **Settings > Devices & services**. A device named
   *Jacuzzi J235* appears under **MQTT**, or under **ESPHome** for the component. The
   controls show as unavailable. That is expected.
3. Compare with the topside:

    | Check | How |
    |---|---|
    | Current Water Temperature | Same number as the topside display |
    | Target Water Temperature | Press Temp up twice at the topside: the first press opens the set screen, the second adds 0.5 °C. Then step back |
    | Pump 1 Speed | Press the pump 1 button three times: `low`, `high`, `off` |
    | Pump 2 | Press the pump 2 button on and off |
    | Heater Active | Raise the setpoint above the water temperature. Pump 1 starts on low, then the heater follows about a minute later |
    | Light Mode | Press the light button. MQTT bridge only |
    | Filter Change Days, Water Change Days, UV Lamp Days | The FC, H2O and UV values in the topside menu |

## Enable transmit

Read [Safety](../safety.md) first.

!!! warning "First commands on your tub"
    The channel claim works on the project's J235 with the MQTT bridge. Your board, adapter
    or ESP32 wiring may differ. Have someone at the topside for the first commands.

What the bridge or the ESP32 sends:

1. At start-up, nothing.
2. On the first command, a channel request. The J235's only polled channel (`0x10`) is
   the topside panel, and it answers every poll, so there is no free channel to reuse.
   spa2mqtt asks the board for a new one when the board offers it, about once a second,
   and acknowledges the answer.
3. Then one button press each time the board polls that channel. When nothing is queued,
   it stays silent.
4. If another device answers on the same channel, spa2mqtt goes back to listening.

For the MQTT bridge, set `SPA_TRANSMIT=true` and recreate the container or update the
stack. The log shows `TRANSMIT ENABLED`. For ESPHome, set `transmit: true` in the
`spa_bus:` block and install the firmware: the **Bus State** sensor shows `claiming`,
`requested`, then `ready (0x..)` on the first command.

Test in this order, one command at a time, and watch the topside after each:

1. **Pump 2 Button**, twice: on, then off.
2. **Light Button**, then wait ten seconds and press it again to turn the light off.
3. **Pump 1 Button**, three times: low, high, off.
4. **Temperature Increment**, twice, then **Temperature Decrement** once. The setpoint
   rises 0.5 °C and falls back.
5. **Temperature Set Control**, 0.5 °C up, then back.
6. The switches, last.

To stop, set transmit off again. If the topside shows an error, isolate the spa at the
breaker and wait before you switch it on again.

## Send captures back

A capture of something new on this tub helps, in particular a session with commands
and the menu. `spa2mqtt capture` is read-only and keeps only the frames that changed:

```bash
docker run --rm -it ghcr.io/srleach/spa2mqtt:2 spa2mqtt capture 192.168.1.100 -o j235.log
```

For a session with labels, use `tools/capture.py`. Stop the bridge first: the EW11A
accepts one client. See [Monitor and capture](../monitor-and-capture.md) for both, and
[Contribute a capture](../monitor-and-capture.md#contribute-a-capture) to share the file.

## Known limits

- **Celsius only.** The board's status gives no unit flag. Keep the topside in °C.
- **The first temperature press only opens the set screen.** *Temperature Increment* and
  *Temperature Decrement* behave like the topside. *Temperature Set Control* accounts for
  it.
- **Pump 1 Low may not turn off.** The board runs pump 1 low by itself to heat or filter.
  While it does, pressing pump 1 cannot reach off, and the switch gives up after a fixed
  number of presses.
- **The light has one button.** A press within a few seconds of the last one steps the
  colour. A press after a pause turns the light off. The *Light* switch waits about
  7.5 s between presses for that reason. There is no direct colour or brightness command.
- **ESPHome has no lights frame.** *Light Mode* and the switches are MQTT bridge only.

Open questions that a capture or a test at the tub would answer:

1. Where are the filter cycle settings and the heat mode? A capture while they are
   changed at the topside would settle it.
2. What does *Manual Circulation Call* show, if anything?
3. What are the button codes for ClearRay and the menu on this tub?

The [wire protocol](../protocol.md#9-known-inferred-unknown-summary) lists the unknown
bytes.
