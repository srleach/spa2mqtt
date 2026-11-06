# Safety

Read this page before you wire anything into a spa, and again before you enable transmit.

## Electrical safety

!!! danger "Mains voltage and water"
    A spa controller runs on mains voltage and can deliver a large fault current. Water
    makes a shock more likely and more severe.

- **Isolate the spa before you open it.** Switch off the spa's breaker or isolator at the
  supply, not only at the topside. The topside does not disconnect mains from the board.
- **Check that it is dead.** Use a suitable voltage tester before you touch anything in
  the control box.
- **Use only the RS485 header.** The header on the control board is intended for a second
  topside panel. Do not take power or signals from any other point on the board.
- **Keep low-voltage parts dry and fixed.** Mount the adapter or ESP32 in an enclosure,
  away from water and away from mains terminals. Route the bus cable so that it cannot
  touch mains parts.
- **Follow local rules.** In many countries, work inside fixed mains equipment needs a
  qualified electrician. If you are not sure, ask one.
- **Your risk.** Wiring anything into a spa is at your own risk. This project gives no
  warranty.

## Receive-only by default

Both the MQTT bridge and the ESPHome component start with transmit **off**. With transmit
off:

- Nothing is ever written to the bus. The bridge, the monitor and the capture tool only
  listen.
- Buttons and the temperature setpoint still appear in Home Assistant, so their identities
  stay the same. The MQTT bridge shows them as unavailable. ESPHome logs a warning when you
  press one.
- A wrong setting or a wrong tub definition can show wrong values. It cannot change the tub.

You enable transmit on purpose, with `SPA_TRANSMIT=true` or `spa.transmit: true` for the
bridge, or `transmit: true` in the ESPHome `spa_bus:` block.

The read-only tools never transmit, whatever the setting:

- `spa2mqtt monitor` runs receive-only and wraps its connection so that any write fails.
- `spa2mqtt replay` reads a file and has no bus at all.
- `tools/capture.py` contains no send call.

## One choke point for every write

Every write to the bus goes through one function:

- Python: `BusWriter.send()` in `spa2mqtt/tub/bus.py`.
- ESPHome: `SpaBus::transmit_frame_()` in `esphome/components/spa_bus/spa_bus.cpp`.

Each is marked `TRANSMITS` in the source. A test asserts that no other Python module
writes to the transport. If transmit is off, the Python writer raises an error and the
C++ function returns before it writes. One choke point makes the transmit path easy to review:
you check one function, not the whole code base.

## What enabling transmit does

When you enable transmit:

1. At start-up, nothing changes on the bus. The bridge logs `TRANSMIT ENABLED`, and the
   command entities become available in Home Assistant.
2. On the **first command** from Home Assistant, the bridge claims a client channel on
   the bus. It does this the same way a second topside panel does: it takes a polled channel
   that no device uses, or it asks the board for a new channel and acknowledges the answer. From then on, the board polls that channel.
3. When the board polls the channel, the bridge sends one queued button press. When
   nothing is queued, it stays silent.
4. A setpoint change is a series of single up or down presses. After each press the bridge
   waits for status frames that confirm the change, and it gives up after a fixed number of
   attempts.
5. If another device answers on the same channel, the bridge sees the conflict and goes
   back to listening.

The v1 bridge claimed a channel at start-up even when no one pressed a button. Version 2
does not.

The transmit path is tested against a simulated board. It is not yet confirmed on a real
J235. Watch the first commands at the topside.

## Rules for testing

- **Never leave transmit on while you test an unknown or changed tub definition.** A wrong
  button code, bus address or channel setting could send a command that you did not
  intend, or disturb the topside panel's own traffic. Test with transmit off until every
  value matches the topside.
- Test new definitions with `spa2mqtt monitor` and replayed captures first. See
  [Monitor and capture](monitor-and-capture.md).
- Enable transmit when someone can watch the topside. Press one button at a time and check
  the result.
- If anything unexpected happens, set transmit off again and restart. If the topside
  shows an error, isolate the spa at the breaker and wait before you switch it on again.
- Do not automate heating or pumps from Home Assistant until manual commands have worked
  reliably for some time.
