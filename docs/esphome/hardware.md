# Hardware and wiring

This page lists the parts you need and shows how to connect the ESP32 to the tub.

!!! danger "Mains voltage"
    A spa contains mains voltage and can deliver a large fault current. Turn off the spa at
    its breaker before you open the equipment bay or touch the control board. Check that the
    board is dead before you work on it. If you are not competent to work near mains wiring,
    get an electrician to do it. Read [Safety](../safety.md) first.

## What you need

| Part | Why you need it |
|---|---|
| An ESP32 board | Runs ESPHome and the `spa_bus` component. |
| An RS485 transceiver | Converts the bus's differential signal to the 3.3 V serial signal of the ESP32. A differential signal is carried as the voltage difference between two wires, A and B. |
| Twisted-pair cable | Carries A and B. Twisting the pair rejects electrical noise from pumps and heaters. |
| A DC power supply for the ESP32 | Powers the ESP32 independently of the tub. See [Power](#power). |
| A connector that fits the tub's RS485 header | Lets you unplug the ESP32 without cutting wires. |

You can use one of two hardware options.

=== "Waveshare ESP32-S3-ETH-8DI-8RO"

    The project's example device uses this board. It has an ESP32-S3, an onboard RS485
    transceiver, Ethernet, 8 relays and 8 digital inputs. The RS485 transceiver connects to
    GPIO17 (TX) and GPIO18 (RX).

    The example YAML sets no `flow_control_pin`, because the onboard transceiver switches
    between send and receive by itself. Check the board's schematic if you use a different
    revision.

    The ready-made device file is
    [`esphome/example-jacuzzibridge-esp.yaml`](https://github.com/srleach/spa2mqtt/blob/main/esphome/example-jacuzzibridge-esp.yaml).

=== "Any ESP32 and a transceiver module"

    Any ESP32 with a free UART works. Add a 3.3 V RS485 transceiver module, for example one
    based on a MAX3485 or SP3485 chip. Do not use a 5 V MAX485 module directly: its receive
    output can put 5 V on an ESP32 pin, and ESP32 pins tolerate 3.3 V only.

    - Connect the module's RO (receiver output) to the ESP32's RX pin.
    - Connect the module's DI (driver input) to the ESP32's TX pin.
    - Many modules have DE (driver enable) and RE (receiver enable) pins. DE turns on the
      transmitter. RE turns on the receiver. Tie them together and connect them to a spare
      GPIO, then set that GPIO as `flow_control_pin`. The component then turns the
      transmitter on only while it sends. Some modules switch direction automatically and
      have no DE/RE pins. Those need no `flow_control_pin`.

## The tub's RS485 header

The J235 control board has an RS485 header for a second topside panel. A topside panel is the
control panel on the rim of the tub. Most tubs have only one panel, so the second-panel header
is usually free. It is the intended place to attach a monitoring device.

The bus is shared. The control board, the topside panel and any add-on device sit on the same
two wires. The control board decides who may talk:

- The board broadcasts a status frame about three times per second. Every device on the bus
  hears it. This is all the ESP32 needs in receive-only mode.
- The board polls each panel channel in turn with a clear-to-send frame (CTS). A channel is a
  bus address that the board has given to one client. A client may transmit only in the short
  gap right after the CTS for its own channel.
- A new device must ask the board for a channel before it can send. The ESP32 does this only
  when transmit is enabled and you issue the first command.

A receive-only ESP32 never drives the bus, so it cannot collide with the topside panel. See
the [wire protocol](../protocol.md#4-bus-arbitration-and-addressing-state-machine) for the
details.

## Wiring

<div class="s2m-diagram" markdown="0">
--8<-- "assets/esphome/wiring.svg"
</div>

1. Connect header **A** to transceiver **A** (sometimes labelled A+ or D+).
2. Connect header **B** to transceiver **B** (sometimes labelled B- or D-).
3. Connect header **0 V** to the transceiver's ground. RS485 tolerates some ground
   difference, but a common ground keeps the signal within the transceiver's range and makes
   reception reliable.
4. Leave the header's **+12 V** unconnected unless you have read [Power](#power).

!!! note "A and B swapped"
    Manufacturers do not agree on which wire is A and which is B. If the ESP32 logs no status
    frames and the UART settings are correct, swap A and B. A swap does no damage.

!!! note "Termination"
    RS485 buses use a 120 ohm resistor at each end to stop signal reflections. The tub's own
    wiring is short and already works with its panel. Leave the transceiver's termination
    resistor or jumper off unless reception is unreliable.

## Power

The tub's header carries 12 V. The legacy wiring notes for the J235 list it as "12v +/, A/B":
a 12 V supply pair and the A/B pair. The current rating of that 12 V supply is not known. The
supply also feeds the topside panel. An ESP32 with Wi-Fi can draw short peaks of several
hundred milliamps. Overloading the supply could disturb the panel or the board.

Power the ESP32 from its own supply unless you know the header's rating.

- The Waveshare ESP32-S3-ETH-8DI-8RO takes 7-36 V DC on its power terminal, or 5 V over
  USB-C. Check your board's documentation for its input range before you connect any supply.
- Other ESP32 boards usually take 5 V over USB. Check the board's documentation.

If you decide to use the header's 12 V, use a board or a regulator that accepts 12 V, and add
a fuse in the 12 V line.

## UART settings

The bus runs at 115200 baud, 8 data bits, no parity, 1 stop bit (115200 8N1). The tub
definition sets the baud rate. ESPHome checks at compile time that your `uart:` block matches
it. The `uart:` defaults for data bits, parity and stop bits are already 8N1.

Set `logger: baud_rate: 0` on boards where the logger would share the bus UART. This keeps log
output off the RS485 pins. Logs still reach you over Wi-Fi through the API.

## Mounting

- Mount the ESP32 in a dry enclosure, away from the heater and the pumps. The equipment bay
  gets hot and humid.
- Route the low-voltage cable away from mains cables, and fix it so it cannot touch moving or
  hot parts.
- Close every cover before you restore power at the breaker.

Next: [Build and flash](install.md).
