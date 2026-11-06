# Configuration

This page lists every setting of the MQTT bridge. The ESPHome component has its own
settings in the device YAML. See [ESPHome](esphome/index.md).

## Where settings come from

The bridge reads settings from two places:

1. **`config.yml`.** A YAML file. The container reads `/app/config.yml`. Outside Docker,
   `spa2mqtt run` reads `config.yml` in the current folder, or the file given with
   `-c FILE`. The file is optional. Without it, the bridge uses the defaults and the
   environment variables. Start from
   [`config.yml.example`](https://github.com/srleach/spa2mqtt/blob/main/config.yml.example).
2. **Environment variables.** They cover the settings that change from one install to
   the next. An environment variable overrides the same setting in `config.yml`.

An empty environment variable counts as unset, with one exception: `SPA_TRANSMIT`. If
`SPA_TRANSMIT` exists at all, it decides transmit, and an empty value means `false`. This
can only switch transmit off, never on, so it fails safe.

## Environment variables

| Variable | `config.yml` key | Default | Meaning |
|---|---|---|---|
| `SPA_IP` | `spa.transport.host` | `192.168.1.100` | Address of the RS485-to-TCP adapter |
| `SPA_PORT` | `spa.transport.port` | `8899` | TCP port of the adapter |
| `SPA_DEFINITION` | `spa.definition` | `jacuzzi_j235` | Tub definition ID, alias or file path. See [Tub definitions](tub-definitions.md) |
| `VARIANT_DEFINITION` | `spa.definition` | | v1 name of `SPA_DEFINITION`. `SPA_DEFINITION` wins if both are set |
| `SPA_TRANSMIT` | `spa.transmit` | `false` | Allow commands to the tub. See [Transmit](#transmit) |
| `MQTT_BROKER` | `mqtt.broker` | `localhost` | MQTT broker address |
| `MQTT_PORT` | `mqtt.port` | `1883` | MQTT broker port |
| `MQTT_USERNAME` | `mqtt.username` | none | Broker user name |
| `MQTT_PASSWORD` | `mqtt.password` | none | Broker password |
| `LOG_LEVEL` | `log_level` | `INFO` | `DEBUG`, `INFO`, `WARNING` or `ERROR` |

Boolean values accept `true`, `1`, `yes` and `on` (any case). Every other value means
`false`.

The Compose files also use `SPA2MQTT_TAG` to choose the image tag. The bridge itself does
not read it. See [Releases and versions](releases.md).

## config.yml keys

```yaml
spa:
  definition: jacuzzi_j235
  transport:
    type: tcp
    host: 192.168.1.100
    port: 8899
  transmit: false

mqtt:
  broker: 192.168.1.7
  port: 1883
  username: user
  password: pass

ha:
  discovery_prefix: homeassistant
  base_topic: spa2mqtt
  device_name: Jacuzzi J235
  device_identifier: "185569045"
  unique_id_prefix: ""
  legacy_topics: true
  heartbeat: 60
  heartbeat_overrides:
    secondary_pump_status: 90
    circulation_pump_status: 90

log_level: INFO
```

### spa

| Key | Default | Meaning |
|---|---|---|
| `spa.definition` | `jacuzzi_j235` | Tub definition: a built-in ID, an alias such as `jacuzzi_j235_encrypted`, or a path to your own YAML file. `spa2mqtt definitions` lists the built-in ones |
| `spa.transport.type` | `tcp` | `tcp` for an RS485-to-TCP adapter, `serial` for a USB RS485 adapter, `replay` to play back a capture file |
| `spa.transport.host` | `192.168.1.100` | `tcp`: adapter address |
| `spa.transport.port` | `8899` | `tcp`: adapter TCP port |
| `spa.transport.device` | `/dev/ttyUSB0` | `serial`: device path. In Docker, also pass the device into the container |
| `spa.transport.baud` | `115200` | `serial`: baud rate |
| `spa.transport.path` | empty | `replay`: capture file to play back |
| `spa.transport.speed` | `1.0` | `replay`: playback speed. `1.0` is real time, `0` is as fast as possible |
| `spa.transmit` | `false` | Allow commands to the tub. See [Transmit](#transmit) |

The `serial` transport needs the `serial` extra. The container image includes it. Outside
Docker, install it with `pip install "spa2mqtt[serial]"`. The image runs as an unprivileged
user, so pass the device into the container and add the group that owns it, usually
`dialout`.

### mqtt

| Key | Default | Meaning |
|---|---|---|
| `mqtt.broker` | `localhost` | Broker address. `mqtt.host` is accepted as another name |
| `mqtt.port` | `1883` | Broker port |
| `mqtt.username` | none | Broker user name |
| `mqtt.password` | none | Broker password |

### ha

These keys control how the bridge appears in Home Assistant. MQTT discovery is the Home
Assistant feature that creates entities from retained config messages on the broker.

| Key | Default | Meaning |
|---|---|---|
| `ha.discovery_prefix` | `homeassistant` | Discovery prefix that Home Assistant listens on |
| `ha.base_topic` | `spa2mqtt` | First part of the state and command topics, for example `spa2mqtt/jacuzzi_j235/...` |
| `ha.device_name` | `Jacuzzi J235` | Device name in Home Assistant. With `legacy_topics`, it is also part of the discovery topics |
| `ha.device_identifier` | `185569045` | Device identifier. The default is the device that the v1 bridge created, so an upgrade keeps it |
| `ha.unique_id_prefix` | empty | Text put in front of every entity `unique_id`. See [unique_id_prefix](#unique_id_prefix) |
| `ha.legacy_topics` | `true` | Publish discovery to the topics that v1 used. See [Legacy topics](#legacy-topics) |
| `ha.heartbeat` | `60` | Seconds between re-publishes of unchanged values |
| `ha.heartbeat_overrides` | none | Per-field heartbeat, as `field: seconds` |

### Other keys

| Key | Default | Meaning |
|---|---|---|
| `log_level` | `INFO` | Log level |

## Transmit

Transmit is off by default. With transmit off:

- The bridge never writes to the bus.
- Buttons and the setpoint number still appear in Home Assistant, so their identities stay
  the same. They show as unavailable.
- Commands that reach the bridge anyway are dropped with a warning in the log.

With transmit on:

- The log shows `TRANSMIT ENABLED` at start-up.
- The bridge still sends nothing at start-up.
- On the first command from Home Assistant, it claims a client channel on the bus, the same
  way a second topside panel does. Then it sends the button press.
- For a setpoint change, it presses up or down one step at a time and checks the status
  after each press, until the setpoint matches the target.

Read [Safety](safety.md) before you enable transmit.

## unique_id_prefix

Home Assistant uses each entity's `unique_id` to remember its entity ID, name and area.
The default empty prefix gives bare IDs such as `current_temperature`. These are the IDs
that the v1 bridge used, so an upgrade from v1 keeps every entity.

On a fresh install, set a prefix such as `spa_` if another MQTT integration could use the
same bare IDs. Two entities with the same `unique_id` cannot both exist. Choose the prefix
before the first start: a change later creates new entities and leaves the old ones behind.

## Legacy topics

The v1 bridge published discovery messages to
`<discovery_prefix>/<component>/<device_name>/<entity_name>/config`, with unsafe
characters replaced by `-`. Discovery messages are retained on the broker. With
`legacy_topics: true`, the bridge publishes to those same topics, so it replaces the old
retained messages in place. Without that, Home Assistant would keep the v1 config as well
and could show duplicate entities.

Keep the default if you upgrade from v1. On a fresh install the setting does no harm.
Because the topic contains `device_name` and the entity name, changing either one moves
the discovery topic.

## Upgrade from v1

The v1 bridge is kept on the `legacy/pre-rewrite` branch. Version 2 is built to replace it
in place:

- Your v1 `config.yml` keeps working. The keys in the table below and the environment
  variables `SPA_IP`, `SPA_PORT`, `VARIANT_DEFINITION` and `MQTT_*` are still read.
- Home Assistant identities stay the same: the same device (`185569045`), the same
  `unique_id`s, and discovery on the same topics. Retained configs are replaced in place,
  and entity IDs do not change.
- **Behaviour change:** buttons and *Temperature Set Control* are unavailable until you
  enable transmit. v1 transmitted by default.
- State topics move from `hmd/...` to `spa2mqtt/jacuzzi_j235/...`. Home Assistant follows
  the change through discovery, so you do nothing.
- New entities: *Pump 1 Speed*, *Light Button*, and diagnostics that are disabled by
  default.
- *Main Pump Status* is pump 1 on **high**. *Circulation Pump Status* is pump 1 running at
  any speed, because the J235 circulates on pump 1 low.

Stop the v1 container before you start version 2. v1 transmits at start-up, and the
adapter may accept only one TCP client.

## Legacy v1 keys

A v1 `config.yml` keeps working. The bridge logs a deprecation warning for `spa.config` and `spa.connection`.

| v1 key | New key |
|---|---|
| `spa.config` | `spa.definition` |
| `spa.connection.spa_address` | `spa.transport.host` |
| `spa.connection.spa_port` | `spa.transport.port` |
| `sensor_update_intervals.default` | `ha.heartbeat` |
| `sensor_update_intervals.overrides` | `ha.heartbeat_overrides` |
