# Jacuzzi J345 (ProLink)

This guide sets up the MQTT bridge for a Jacuzzi J345: a J-300 series tub with an
**unencrypted** control board, reached through the original Jacuzzi ProLink Wi-Fi module.
Older threads and file names call this tub a "J335". The definition ID is `jacuzzi_j345`.

!!! warning "Nobody on the project has this tub"
    The definition was decoded from five logs that the tub's owner shared, and checked
    against [pyjacuzzi](https://github.com/dhmsjs/pyjacuzzi). The project has not run it
    against the tub. Start receive-only, compare every value with the topside, and
    [report what you see](#send-captures-back).

## What is supported

Each row has the evidence status from the definition. *Confirmed* means a capture shows a
command and the tub's reaction, or the same change from the topside in several captures.
*Inferred* means the captures agree with pyjacuzzi but nobody compared the value with the
tub. *Hypothesis* means a pattern in the data only. The
[plain protocol reference](../protocol-plain.md) has the bytes.

### Read

| Entity | Status | Notes |
|---|---|---|
| Current Water Temperature | Inferred | Whole °F. Never compared with the topside display |
| Target Water Temperature | Confirmed | Whole °F |
| Pump 1, Pump 2 | Confirmed | On or off. A low speed, if a pump has one, would read as off |
| Circulation Pump | Inferred | |
| Heater Active | Hypothesis | Follows the thermostat in the captures. No reference names the bit |
| Light Mode | Confirmed | `off`, a colour name, `blend` or `blend paused` |
| Light Brightness | Confirmed | Percent |
| Secondary Temperature, Flow Switch, CLEARRAY Days Remaining | Inferred | Diagnostics |
| Set Mode Active, Reminder Active, Celsius Mode, Display State, State Raw, Error Code, Light Red, Light Green, Light Blue | Mixed | Diagnostics, disabled by default |

### Control

All controls are unavailable until you [enable transmit](#enable-transmit).

| Entity | Status | What it sends |
|---|---|---|
| Temperature Set Control | Confirmed for 90, 100 and 101 °F | One set-temperature frame. Range 80 to 104 °F, step 1 |
| Pump 1 Button, Pump 2 Button | Confirmed | One button frame. Each press toggles the pump |
| Pump 1, Pump 2 (switches) | Confirmed | The same button frame, sent only when the pump is not already in the state you chose. One frame, no retry |
| Light White … Light Aqua (nine buttons) | Confirmed | One light frame that selects the colour |
| Light Brightness | Confirmed for 0, 20, 40, 60, 80, 100, with a colour already on | One light frame. `0` turns the lights off. Select a colour first: see [Known limits](#known-limits) |

### Not supported

- The ESPHome component. This tub is bridge-only.
- Temperature up and down buttons, the topside light and colour buttons, UV and the menu.
  Their codes come from a different tub.
- Clock setting, locks, filter cycles and heat mode.
- Pump 3 and the blower.
- Light blend mode as a control. pyjacuzzi notes that the board refuses it as a direct
  command. Raising the brightness from `0` may start it: see [Known limits](#known-limits).
- Celsius. The definition is Fahrenheit only, and the bridge refuses to send a setpoint
  while the tub reports Celsius mode.

## Hardware path

There is nothing to wire. The bridge connects to the ProLink module over your network.

| Item | Value |
|---|---|
| Address | The ProLink module's LAN address. Find it in your router's client list and give it a fixed lease |
| TCP port | `4257` |
| Adapter | None. Do not use the EW11A settings (port 8899) |
| Bus address the bridge sends from | `0x0A`, the ProLink's own address. Set by the definition |

The ProLink is assumed to serve one client at a time. Stop pyjacuzzi, the v1 bridge and
any other tool before you start spa2mqtt. Whether the official app can run at the same
time is unknown.

## Install with Docker Compose

Follow [Install with Docker Compose](../install/docker-compose.md) with these values in
`.env`:

```ini
SPA_IP=192.168.1.50
SPA_PORT=4257
SPA_DEFINITION=jacuzzi_j345
SPA_TRANSMIT=false
MQTT_BROKER=192.168.1.7
MQTT_PORT=1883
MQTT_USERNAME=
MQTT_PASSWORD=
```

## Install with Portainer on Home Assistant OS

Portainer under Home Assistant OS cannot mount files, so every setting is an environment
variable. Follow [Install with Portainer](../install/portainer.md), method A. Use the same
stack file,
[`deploy/portainer-stack.yml`](https://github.com/srleach/spa2mqtt/blob/main/deploy/portainer-stack.yml),
and set these variables:

| Variable | Value |
|---|---|
| `SPA_IP` | ProLink address, for example `192.168.1.50` |
| `SPA_PORT` | `4257` |
| `SPA_DEFINITION` | `jacuzzi_j345` |
| `SPA_TRANSMIT` | `false` |
| `MQTT_BROKER` | Broker address. For the Mosquitto add-on, use the Home Assistant host's LAN address: `core-mosquitto` does not resolve from a Portainer stack |
| `MQTT_PORT` | `1883` |
| `MQTT_USERNAME`, `MQTT_PASSWORD` | Broker login, if the broker needs one |
| `LOG_LEVEL` | `INFO` |

`SPA_PORT` and `SPA_DEFINITION` matter most: the defaults are for the J235 behind an
EW11A. `SPA_IP` and `MQTT_BROKER` are required, and the stack refuses to deploy without
them.

!!! note "Coming from the v1 debug image"
    The old name `jacuzzi_j335_unencrypted_farenheit` still selects this definition, and
    `VARIANT_DEFINITION` is still read. The stack file passes only the variables in the
    table, so set `SPA_DEFINITION` there.

The image must include this definition. If the log says
`unknown tub definition 'jacuzzi_j345'`, the image is older than this guide: update it
([Update](../install/portainer.md#update)).

## Verify, receive-only first

With `SPA_TRANSMIT=false` the bridge cannot change the tub. Nothing is written to the
ProLink.

1. In Home Assistant, open **Settings > Devices & services > MQTT**. A device named
   *Jacuzzi J345* appears within a few seconds. The controls show as unavailable. That is
   expected.
2. Stand at the tub, or ask someone to, and compare with the topside:

    | Check | How |
    |---|---|
    | Current Water Temperature | Same number as the topside display |
    | Target Water Temperature | Change the setpoint at the topside by 1 °F and back |
    | Pump 1, Pump 2 | Press each jets button on and off |
    | Circulation Pump | Is the circulation pump running? |
    | Heater Active | Does it match the heater indicator on the topside? |
    | Light Brightness | Switch the light on at the topside and step its brightness |

3. Report what matched and what did not in
   [discussion 13](https://github.com/srleach/spa2mqtt/discussions/13). A value that
   matches moves from inferred to confirmed. A value that does not match is just as useful.

The log names the fields that are still hypotheses at start-up. Any time the bridge decodes
is the tub's own clock. In the captures that clock runs about 51 minutes slow.

## Enable transmit

Read [Safety](../safety.md) first.

!!! danger "First commands on a tub the project has never driven"
    The frames the bridge sends are the frames pyjacuzzi sent to this tub in a captured
    session, byte for byte, and the test suite checks that. That shows the bytes are right.
    It does not show that the bridge's timing suits the ProLink. Have someone at the tub
    for the first commands.

What the bridge sends:

1. At start-up, nothing.
2. On the first command after each connection, one *connection check* frame
   (`7e 07 0a bf 19 01 00 95 7e`). pyjacuzzi sends this first, and the tub answers it.
   Whether commands need it is unknown.
3. Then one frame per command, at least four status frames (about 1.2 seconds) apart.
   There is no retry. The next status frame shows whether the tub obeyed.

Set `SPA_TRANSMIT=true` and update the stack. The log shows `TRANSMIT ENABLED`. Then test
in this order, one command at a time, and watch the topside after each:

1. **A light colour**, for example *Light Blue*. Then *Light Brightness* to `0` to turn
   the lights off.
2. **Pump 2 Button**, twice: on, then off.
3. **Pump 1 Button**, twice.
4. **Temperature Set Control**, 1 °F up, then back.

!!! note "Turn the lights off with brightness 0"
    A colour button writes all four light records in the tub. The topside changes only the
    first one. Set *Light Brightness* to `0` to clear all four.

To stop, set `SPA_TRANSMIT=false` and update the stack. If the topside shows an error,
isolate the spa at the breaker and wait before you switch it on again.

## Send captures back

A capture with the times of your actions settles the open questions below. The monitor is
read-only and can print the capture into the container log, so it works without a mounted
file.

1. Stop the `spa2mqtt` container.
2. In Portainer, select **Containers > Add container**. Set **Name** to
   `spa2mqtt-monitor` and **Image** to `ghcr.io/srleach/spa2mqtt:2`.
3. Under **Advanced container settings > Command & logging**, set **Command** to:

    ```text
    spa2mqtt monitor 192.168.1.50 -p 4257 -d jacuzzi_j345 --record -
    ```

    Set **Console** to **Interactive & TTY**. Under **Restart policy**, select **Never**.

4. Deploy the container and open its **Logs**. Turn **Display timestamps** off. Raise
   **Lines** from the default `100` to `5000` or more: the capture adds about four lines
   per second.
5. Do one thing at a time at the topside, about ten seconds apart, and write down the
   time of each: the displayed water temperature, each pump on and off, the light, the
   setpoint up and down.
6. Copy the whole log and post it in
   [discussion 13](https://github.com/srleach/spa2mqtt/discussions/13) with your notes.
   The log shows the ProLink's LAN address in the line that starts `spa2mqtt monitor:`
   and in every line that contains `connected to`. Remove the address from those lines,
   or delete them, before you post. Only the `RX` lines are needed.
7. Stop and remove `spa2mqtt-monitor`, then start `spa2mqtt` again.

The lines that matter look like `1748000000.123 RX 7e25ffaf16…`. The report lines between
them are ignored when the log is replayed.

## Known limits

- **Fahrenheit only.** Celsius mode on this board was never captured. Keep the topside in
  °F. If the *Celsius Mode* bit is set, the bridge refuses *Temperature Set Control* and
  logs a warning: pyjacuzzi sends half degrees Celsius in the same byte in that mode, so
  "80" would ask for 40 °C. The bridge also refuses the setpoint until it has decoded one
  status frame. The temperature readings would still be published with the °F unit and
  would be wrong.
- **The setpoint range is 80 to 104 °F.** These are the lowest and highest setpoints in any
  capture. Only 90, 100 and 101 were sent remotely. The bridge ignores a value outside the
  range and logs a warning. It does not clamp it.
- **Select a colour before you raise Light Brightness.** In the capture, every non-zero
  brightness command was sent while a colour was on. pyjacuzzi's source says that raising
  the brightness from 0 is how the lights enter blend mode (`src/jacuzziui.py` L487–499).
  So a non-zero brightness sent while the lights are off is expected to start the colour
  cycle, not a steady light. Nobody has seen this on this tub.
- **Light Brightness steps by 20.** Those are the values the capture shows accepted. The
  topside's own steps (100, 66, 33) still display correctly.

Open questions that a capture or a test at the tub would answer:

1. Is the connection check needed before commands work?
2. Does the ProLink accept a second TCP client, or the official app at the same time?
3. Does the water temperature match the topside? What does the second sensor measure?
4. Is *Heater Active* the heater? It rests on one bit that no reference names.
5. Does either pump have a low speed? Is there a pump 3, a blower or a UV button?
6. What does the tub do with a setpoint outside 80 to 104 °F? The bridge never sends one.
7. Does a non-zero brightness sent while the lights are off start blend mode, as
   pyjacuzzi's source says?
8. Why did the CLEARRAY counter fall from 364 to 0 in six days?

The [plain protocol reference](../protocol-plain.md#8-unknowns) lists the unknown bytes.
