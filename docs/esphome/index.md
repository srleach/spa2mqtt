# ESPHome component

`spa_bus` is an ESPHome external component. An external component is ESPHome code that lives
outside the ESPHome project and that ESPHome downloads when it compiles your device. `spa_bus`
runs the spa2mqtt decoder directly on an ESP32 that is wired to the tub's RS485 bus. RS485 is
the two-wire serial bus that the tub's control board uses to talk to its topside panel.

The ESP32 reads the status that the control board broadcasts about three times per second. It
decodes the status and publishes it to Home Assistant through the ESPHome native API. The
native API is the direct, encrypted link between an ESPHome device and Home Assistant.

## Why run it on ESPHome

The [MQTT bridge](../getting-started.md) needs three parts between the tub and Home
Assistant: an RS485-to-TCP adapter such as the EW11A, a Docker host, and an MQTT broker. The
ESPHome component replaces all three with one ESP32.

- **No adapter box and no vendor cloud.** The ESP32's own UART reads the bus. A UART is the
  serial port on the chip. Nothing depends on an adapter's firmware or app.
- **No MQTT broker.** Home Assistant discovers the device through the ESPHome integration.
  Entities appear in Home Assistant with no discovery topics to manage.
- **Fewer moving parts.** One device to power, update and back up. ESPHome updates it over
  the air.

The MQTT bridge is still the better choice when you already have an RS485-to-TCP adapter
installed, or when you want the `monitor` and `replay` tools. See
[Getting started](../getting-started.md) for the comparison.

## One set of tub definitions

A tub definition is a YAML file in the repository's
[`definitions/`](https://github.com/srleach/spa2mqtt/tree/main/definitions) folder. It
describes one tub model: where each value sits in the status frame, the button codes, and the
Home Assistant entities. The Python bridge reads the same files at run time.

The ESPHome component reads the definition at compile time. ESPHome downloads the whole
repository for the external component, so the component's Python code can open
`definitions/<name>.yaml`. It validates the file, then generates C++ code that loads the field
table and button codes into the firmware. This process is called code generation (codegen).

The result:

- A new tub needs a new definition file. It needs no new C++.
- A fix in a definition reaches both the bridge and the ESP32 at the next release.
- Each ESPHome entity names a definition entity with an `entity:` key. ESPHome checks at
  compile time that the key exists and that it has the right type, so a typo stops the build
  instead of producing a dead entity.

See [Tub definitions](../tub-definitions.md) for the file format.

## Features

- Decodes the Jacuzzi J235 status: water temperature, setpoint, pump states, heater, set mode
  and diagnostics.
- A ready-made package lists every J235 entity. A package is an ESPHome YAML file that you
  include in your own device file. You can also choose entities one at a time.
- A `bus_state` diagnostic sensor shows whether status frames arrive and, with transmit on,
  the state of the bus channel.
- Publishes each value when it changes, plus a heartbeat every 60 s so Home Assistant always
  holds a current value.
- Receive-only by default. The component sends nothing to the tub until you set
  `transmit: true`.
- With transmit on: topside button presses (temperature up and down, pumps, light) and a
  setpoint number that steps the temperature to a target.
- Optional `flow_control_pin` for RS485 transceivers that need a direction pin.

## Limits

!!! warning "Transmit is not tested on a real tub"
    The transmit path works against a simulated control board in the test suite. Nobody has
    yet tested it against a real J235. Leave `transmit: false` unless you want to help test
    it, and watch the tub when you first send a command.

- While `transmit: false`, the buttons and the setpoint number still appear in Home
  Assistant. They do nothing when you use them. The ESP32 logs a warning such as
  `transmit disabled (spa_bus.transmit: false); ignoring press 0x01`.
- One `spa_bus` hub per device. One ESP32 serves one tub.
- The component supports the "encrypted" Balboa-family protocol only. Boards with a
  different framing need a new codec. See the [wire protocol](../protocol.md).
- Only the J235 has a definition today.

## Next steps

1. [Hardware and wiring](hardware.md): what to buy and how to connect it.
2. [Build and flash](install.md): the device YAML, the first flash and the checks.
3. [Switch over from MQTT](migrate.md): move from the bridge and keep your entity history.
