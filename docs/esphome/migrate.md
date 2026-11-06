# Switch over from MQTT

This page moves an existing install from the MQTT bridge to the ESPHome component. If you
follow the steps in order, Home Assistant keeps the same entity IDs. Your dashboards,
automations and long-term statistics keep working.

## How the entity IDs survive

Home Assistant stores each entity in its entity registry under two names:

- The **unique ID** is the integration's own key for the entity. Home Assistant uses it to
  recognise the entity after a restart.
- The **entity ID**, such as `sensor.jacuzzi_j235_current_water_temperature`, is the name
  that dashboards, automations and history use.

Long-term statistics are stored against the entity ID. They follow the entity ID, so they
survive the switch if the new entity gets the old entity ID.

The ESPHome device is a new device in a different integration, so its entities get new unique
IDs. Home Assistant builds each new entity ID from the device's `friendly_name` and the
entity's `name`. With `friendly_name: Jacuzzi J235` and the names from the package, ESPHome
asks for exactly the IDs the MQTT bridge used.

Home Assistant gives an entity ID to only one entity at a time. While the MQTT entities still
exist, the ESPHome entities get a suffix such as `_2`. That is why you delete the MQTT device
before you adopt the ESP32.

| | Before | After |
|---|---|---|
| Device | `Jacuzzi J235`, MQTT integration | `Jacuzzi J235`, ESPHome integration |
| Entity IDs | `sensor.jacuzzi_j235_current_water_temperature`, ... | the same |
| History and long-term statistics | stored under the entity ID | the same records continue |
| Unique IDs | bare definition keys, for example `current_temperature` | ESPHome's own unique IDs |
| Device ID, area, device-based automations | MQTT device | new device: set the area again, and update automations that use device triggers or device actions |
| Commands | need `spa.transmit: true` on the bridge | need `transmit: true` on the ESP32 |

!!! note "Device-based automations"
    Automations built with the visual editor's **Device** triggers and actions refer to the
    device ID, which changes. Automations that use entity triggers and actions keep working.
    Look for device-based automations before you start, so you know what to fix afterwards.

## Before you start

1. Build and test the ESP32 firmware on the bench. Follow [Build and flash](install.md), but
   do not add the device to Home Assistant yet. This keeps the downtime short.
2. Make a Home Assistant backup. It is your fallback if a step goes wrong.
3. Note any entity that you renamed by hand in Home Assistant. A renamed entity ID is stored
   in the registry, and the ESP32 will not reproduce it. Rename the new entity to match after
   the switch.

## Steps

1. **Stop the bridge.** Stop the `spa2mqtt` container, for example with
   `docker compose stop spa2mqtt` or **Stop** on the Portainer stack. Two readers on the bus
   are harmless, but a running bridge would publish the MQTT device again after you delete
   it.
2. **Delete the MQTT device.** In Home Assistant, go to **Settings > Devices & services >
   MQTT**, open the **Jacuzzi J235** device, and select **Delete**. This releases the entity
   IDs. Home Assistant also clears the bridge's retained discovery messages, so the device
   does not come back.
3. **Install the ESP32.** Isolate the spa at its breaker, wire the ESP32 to the RS485 header
   as shown in [Hardware and wiring](hardware.md), close the covers and restore power.
4. **Adopt the ESP32.** In **Settings > Devices & services**, Home Assistant shows the
   discovered ESPHome device. Select **Configure** and enter the API key.
5. **Check the entity IDs.** Open the new device. Each entity ID should match the old one, for
   example `sensor.jacuzzi_j235_current_water_temperature`. If an entity ID has a `_2` suffix,
   the old entity was not deleted. Delete the old entity under **Settings > Entities**, then
   rename the new one to remove the suffix.
6. **Check the history.** Open the water temperature entity. The history graph should show
   the old MQTT values followed by the new ESPHome values.

If you used the MQTT entities only on a dashboard, nothing else needs to change.

## Roll back

You can go back to the MQTT bridge at any time.

1. In Home Assistant, delete the **Jacuzzi J235** ESPHome device under **Settings > Devices &
   services > ESPHome**. This releases the entity IDs again.
2. Power off the ESP32 or disconnect it from the bus. This is not needed for safety while
   it is receive-only, but it stops the device from appearing again.
3. Start the bridge container again. It republishes its MQTT discovery messages, and Home
   Assistant creates the entities with the old unique IDs and entity IDs.

!!! note "Restore order"
    The bridge's entities take the old entity IDs only if the ESPHome entities are gone
    first. Delete the ESPHome device before you start the bridge.
