# Build and flash

This page builds the ESPHome firmware for the tub bridge, flashes it, and checks that it
receives the tub's status. Wire the hardware first: see [Hardware and wiring](hardware.md).

Use a current ESPHome release. The project's CI checks the component against the latest
ESPHome release, and these examples were checked with ESPHome 2026.10. You can use the ESPHome Device Builder add-on in Home
Assistant, or the `esphome` command line tool. The steps are the same in both.

The complete example device file is
[`esphome/example-jacuzzibridge-esp.yaml`](https://github.com/srleach/spa2mqtt/blob/main/esphome/example-jacuzzibridge-esp.yaml).
The steps below explain each part of it.

## 1. Add the secrets

ESPHome reads `!secret` values from a file called `secrets.yaml` in the same folder as your
device file. Secrets keep passwords and keys out of the device file, so you can share the
device file safely.

```yaml title="secrets.yaml"
wifi_ssid: "YourNetwork"
wifi_password: "your-wifi-password"
jacuzzibridge_api_key: "base64-key-from-esphome.io"
```

`jacuzzibridge_api_key` encrypts the link between the ESP32 and Home Assistant. Generate a
new random key on the
[ESPHome native API page](https://esphome.io/components/api/#configuration-variables), or with
`openssl rand -base64 32`. Do not reuse a key from another device.

## 2. Create the device file

Start with the device basics. `friendly_name` sets the device name in Home Assistant, and
Home Assistant builds each entity ID from it. Keep `Jacuzzi J235` if you plan to
[switch over from the MQTT bridge](migrate.md), because the entity IDs then stay the same.

```yaml title="jacuzzibridge-esp.yaml"
esphome:
  name: jacuzzibridge-esp
  friendly_name: Jacuzzi J235

esp32:
  variant: esp32s3          # match your board
  framework:
    type: arduino

wifi:
  ssid: !secret wifi_ssid
  password: !secret wifi_password

logger:
  baud_rate: 0              # keep log output off the UART; logs still reach you over the API

api:
  encryption:
    key: !secret jacuzzibridge_api_key

ota:
  - platform: esphome
```

## 3. Add the component, pinned to a release

`external_components` tells ESPHome where to download `spa_bus`. Pin it to a release tag such
as `v2.0.0`. Find the latest tag on the
[releases page](https://github.com/srleach/spa2mqtt/releases).

```yaml
external_components:
  - source: github://srleach/spa2mqtt@v2.0.0
    components: [spa_bus]
```

Pinning matters for three reasons:

- **Repeatable builds.** A tag always points to the same code. If you build from `main`
  instead, a rebuild months later can pick up changes you did not test.
- **Matching definitions.** The component reads the tub definition from the same download.
  The tag fixes the definition too.
- **Controlled updates.** You update by changing the tag on purpose, after you read the
  release notes. See [Releases and versions](../releases.md) for what a version number change
  means.

## 4. Add the entities

### Option A: the package with every entity

A package is a YAML file that ESPHome merges into your device file. The J235 package lists
every entity in the J235 definition. Use the same tag as the component, because the package
names entity keys that this version of the component must know.

```yaml
packages:
  spa_entities: github://srleach/spa2mqtt/esphome/packages/jacuzzi_j235.yaml@v2.0.0
```

The package gives each entity an `id` such as `spa_current_temperature`. To change one entity,
declare it again in your device file with the same `id`. ESPHome merges your settings over
the package's settings.

### Option B: choose entities one at a time

Leave out `packages:` and declare only the entities you want. Each one uses
`platform: spa_bus` and an `entity:` key from the tub definition. ESPHome stops the build if
the key does not exist, or if it belongs to a different platform.

```yaml
sensor:
  - platform: spa_bus
    entity: current_temperature
    name: Current Water Temperature
    device_class: temperature
    unit_of_measurement: °C
    state_class: measurement
    accuracy_decimals: 1

binary_sensor:
  - platform: spa_bus
    entity: heater_active
    name: Heater Active
    device_class: heat

text_sensor:
  - platform: spa_bus
    entity: pump_1_speed
    name: Pump 1 Speed
```

| Platform | J235 entity keys |
|---|---|
| `sensor` | `current_temperature`, `setpoint_temperature`, `display_state`, `secondary_value_raw` |
| `binary_sensor` | `circulation_pump_status`, `secondary_pump_status`, `main_pump_status`, `manual_circulation_call`, `heater_active`, `set_mode_active` |
| `text_sensor` | `pump_1_speed` |
| `button` | `temperature_increment`, `temperature_decrement`, `pump_1_button`, `pump_2_button`, `light_button` |
| `number` | `temperature_set_control` |

Keep the `name` values from the package if you want the same entity IDs as the MQTT bridge.

## 5. Add the UART and the hub

The `uart:` block configures the ESP32 serial port that connects to the RS485 transceiver. The
`spa_bus:` block is the hub. The hub reads the UART, decodes the frames and feeds every
`spa_bus` entity.

```yaml
uart:
  - id: spa_uart
    tx_pin: GPIO17          # to the transceiver's DI
    rx_pin: GPIO18          # from the transceiver's RO
    baud_rate: 115200
    rx_buffer_size: 512

spa_bus:
  id: spa
  uart_id: spa_uart
  definition: jacuzzi_j235  # a definition name, or a path to your own definition YAML
  transmit: false           # receive-only; see "Enable transmit" below
  heartbeat: 60s            # republish every entity this often, even without a change
  # flow_control_pin: GPIO21   # only if your transceiver has DE/RE wired to a GPIO
  bus_state:
    name: Bus State
```

| Key | Default | Meaning |
|---|---|---|
| `definition` | required | Tub definition name or alias from `definitions/`, or a path to a `.yaml` file relative to the device file. |
| `transmit` | `false` | Allow the component to send to the tub. |
| `flow_control_pin` | none | GPIO that drives the transceiver's DE/RE pins while sending. |
| `heartbeat` | `60s` | Interval for republishing every value. |
| `bus_state` | none | Diagnostic text sensor with the link state. Takes the usual text sensor options. |

The larger `rx_buffer_size` gives the ESP32 room to hold a burst of bus traffic while Wi-Fi
is busy.

## 6. First flash over USB

The first flash must use a USB cable, because the chip does not yet run ESPHome and cannot
accept an update over the network.

=== "Command line"

    ```bash
    esphome run jacuzzibridge-esp.yaml
    ```

    Choose the USB serial port when ESPHome asks.

=== "ESPHome Device Builder"

    Open the device, select **Install**, then **Plug into the computer running ESPHome
    Device Builder** or **Plug into this computer**.

Some ESP32-S3 boards need the BOOT button held while you plug in the cable, to enter the
download mode.

After the first flash, ESPHome updates the device over Wi-Fi (OTA, over-the-air). You do not
need the cable again unless the firmware fails to start. You can do the first flash on the
bench before you install the ESP32 in the tub.

## 7. Check the logs

Watch the logs with `esphome logs jacuzzibridge-esp.yaml`, or select **Logs** in the Device
Builder. With the ESP32 wired to the tub, you should see:

```text
[C][spa_bus]: Spa bus:
[C][spa_bus]:   Transmit: disabled (receive-only)
[C][spa_bus]:   Fields: ...
[I][spa_bus]: receiving status frames
```

- `receiving status frames` means that the ESP32 decodes valid status frames from the control
  board. The entities now have values.
- The **Bus State** sensor shows `receive-only`. That is the normal state while
  `transmit: false`.
- `Bus State` shows `no status` and the log shows `no status frames for 10000 ms` if no valid
  status frame arrives for 10 s. Check the wiring, swap A and B, and check the baud rate.
- The configuration dump also prints frame and CRC error counts. CRC (cyclic redundancy check)
  errors mean that frames arrive damaged. A few at start-up are normal. A steady rise points to
  a wiring or ground problem.

Then add the device in Home Assistant. Home Assistant usually discovers it and shows a
notification. Select **Configure** and enter the API key from `secrets.yaml`.

## Before the repository is public

!!! note "Private repository"
    While `srleach/spa2mqtt` is private, the `github://` shorthand cannot download it. Use the
    long git form with a GitHub token. Create a fine-grained personal access token with
    read-only **Contents** access to this one repository. Store it in `secrets.yaml` as
    `github_token`.

```yaml
external_components:
  - source:
      type: git
      url: https://github.com/srleach/spa2mqtt
      ref: v2.0.0
      username: your-github-user
      password: !secret github_token
    components: [spa_bus]

packages:
  spa_entities:
    url: https://github.com/srleach/spa2mqtt
    ref: v2.0.0
    username: your-github-user
    password: !secret github_token
    files: [esphome/packages/jacuzzi_j235.yaml]
```

ESPHome also accepts the token inside the URL, as
`https://<token>@github.com/srleach/spa2mqtt`. The `username` and `password` form is better,
because the token stays in `secrets.yaml` and out of the device file. Switch back to the
`github://` shorthand when the repository is public, and revoke the token.

## Enable transmit

!!! warning "Untested on a real tub"
    The transmit path is tested against a simulated control board only. Enable it only if you
    accept that risk, and stay near the tub the first time.

With `transmit: false`, the buttons and the **Temperature Set Control** number appear in Home
Assistant but do nothing. The log shows
`transmit disabled (spa_bus.transmit: false); ignoring press 0x01`.

To enable transmit:

1. Set `transmit: true` in the `spa_bus:` block.
2. If your transceiver has DE/RE wired to a GPIO, set `flow_control_pin`.
3. Install the new firmware over the air.

Enabling transmit sends nothing by itself. The ESP32 stays silent until you press a button or
change the setpoint. On the first command:

1. The **Bus State** sensor changes from `listening` to `claiming`. The ESP32 looks for a
   free channel on the bus.
2. The J235 has no free channel, so the ESP32 sends a channel request when the board next
   offers one. **Bus State** shows `requested`.
3. The board answers with a channel number. **Bus State** shows `ready`, followed by the
   channel, for example `ready (0x11)`.
4. The ESP32 sends the queued button press in its channel's time slot. The topside reacts as
   if you had pressed its button.

The setpoint number presses Temp up or Temp down until the tub's setpoint matches the target.
The first press on the J235 only opens the set screen, so the component waits for the set
screen to appear before it steps. See the
[wire protocol](../protocol.md#7a-set-mode-where-it-is-visible-and-how-it-was-validated)
for how this was worked out.

To go back to receive-only, set `transmit: false` and install the firmware again.
