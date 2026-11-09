# Install with Docker Compose

This guide runs the MQTT bridge from the published container image with Docker Compose.
Docker Compose is the Docker tool that starts containers from a YAML file. You need a
Docker host that can reach your RS485-to-TCP adapter and your MQTT broker.

The image is `ghcr.io/srleach/spa2mqtt`. It is built for `linux/amd64`, `linux/arm64`
and `linux/arm/v7`, so it runs on a PC, a Raspberry Pi or most NAS devices.

!!! tip "Check the bus first"
    Run the read-only monitor once before you install. It proves that the adapter and the
    tub definition work. See [Getting started](../getting-started.md#3-first-run-read-only-monitor).

## 1. Get the files

You need two files from the repository's
[`deploy/`](https://github.com/srleach/spa2mqtt/tree/main/deploy) folder. Put them in a
new folder on the Docker host, for example `~/spa2mqtt`.

```bash
mkdir -p ~/spa2mqtt && cd ~/spa2mqtt
curl -fsSLO https://raw.githubusercontent.com/srleach/spa2mqtt/main/deploy/docker-compose.yml
curl -fsSL -o .env https://raw.githubusercontent.com/srleach/spa2mqtt/main/deploy/.env.example
```

- `docker-compose.yml` describes the container. You do not need to edit it.
- `.env` holds your settings. Docker Compose reads it for two reasons: to choose the
  image tag, and to pass the settings into the container as environment variables.

## 2. Edit the settings

Open `.env` and set at least these values:

| Variable | Set it to |
|---|---|
| `SPA_IP` | The address of your RS485-to-TCP adapter |
| `SPA_PORT` | The adapter's TCP port (8899 for an EW11A in its usual setup) |
| `MQTT_BROKER` | The address of the MQTT broker that Home Assistant uses |
| `MQTT_USERNAME`, `MQTT_PASSWORD` | The broker login, or empty for an open broker |

Leave `SPA_TRANSMIT=false` for now. The bridge then only listens to the tub. See
[Configuration](../configuration.md) for every setting.

`.env` contains your MQTT password. Make it readable only by you:

```bash
chmod 600 .env
```

### Optional: use a config.yml

Some settings have no environment variable, for example the `ha:` section
(`unique_id_prefix`, `legacy_topics`, `device_name`) and a USB serial adapter. For those,
create a `config.yml` next to `docker-compose.yml` and uncomment the `volumes:` lines in
`docker-compose.yml`. The container reads it at `/app/config.yml`. Values in `.env` still
override the same values in `config.yml`.

```bash
curl -fsSL -o config.yml https://raw.githubusercontent.com/srleach/spa2mqtt/main/config.yml.example
```

The container runs as an unprivileged user (user ID 10001), so that user must be able to
read the file. A file with mode `600` owned by your own account fails to load. Keep the
MQTT password in `.env` and make `config.yml` world-readable with `chmod 644 config.yml`.

## 3. Start it

```bash
docker compose up -d
```

Docker pulls the image and starts the container in the background. The container
restarts by itself after a reboot or a crash (`restart: unless-stopped`).

In Home Assistant, open **Settings > Devices & services > MQTT**. A device named after
the tub definition, for example *Jacuzzi J235*, appears within a few seconds. Its buttons and the setpoint show as
unavailable while transmit is off. That is expected.

## Read the logs

The logs show the connection to the adapter and the broker, and every warning.

```bash
docker compose logs -f spa2mqtt
```

Press Ctrl-C to stop following. To see more detail, set `LOG_LEVEL=DEBUG` in `.env` and
run `docker compose up -d` again.

## Run the read-only monitor

The monitor decodes the bus to your terminal and never transmits. Stop the bridge first,
because most adapters accept only one TCP client.

```bash
docker compose stop spa2mqtt
docker compose run --rm spa2mqtt spa2mqtt monitor 192.168.1.100
docker compose start spa2mqtt
```

The monitor does not read `.env`. Add `-p PORT` and `-d DEFINITION` if yours are not
`8899` and `jacuzzi_j235`. For a Jacuzzi J345 behind a ProLink module:

```bash
docker compose run --rm spa2mqtt spa2mqtt monitor 192.168.1.50 -p 4257 -d jacuzzi_j345
```

The [J345 guide](../tubs/jacuzzi-j345.md) has the `.env` values for that tub.

See [Monitor and capture](../monitor-and-capture.md) for the monitor's options.

## Upgrade

`SPA2MQTT_TAG=2` follows the newest 2.x.y release. A new major version (3.0.0) can
contain breaking changes, so the tag does not move to it by itself. To upgrade within the
pinned tag:

```bash
docker compose pull
docker compose up -d
```

`pull` downloads the newest image for the tag. `up -d` recreates the container only if
the image changed. To remove old images afterwards, run `docker image prune`.

Read the [release notes](https://github.com/srleach/spa2mqtt/releases) before you change
the major version.

## Roll back

Every release has its own image tag. To go back, pin the version you want in `.env`:

```bash
SPA2MQTT_TAG=2.0.0
```

Then run `docker compose up -d`. The container stays on that version until you change the
line again. See [Releases and versions](../releases.md) for the tag scheme.

## Enable transmit

Transmit lets Home Assistant press the tub's buttons and change the setpoint. Enable it
only after the decoded values match the topside, and read [Safety](../safety.md) first.

1. In `.env`, set `SPA_TRANSMIT=true`.
2. Run `docker compose up -d`. Compose recreates the container with the new value.
3. Check the log. It shows `TRANSMIT ENABLED: commands from Home Assistant will be sent to
   the tub`.

The bridge still sends nothing at start-up. It claims a bus channel only when the first
command arrives from Home Assistant. To go back to receive-only, set `SPA_TRANSMIT=false`
and run `docker compose up -d` again.

## Stop and remove

```bash
docker compose down
```

This removes the container. Home Assistant marks the entities unavailable. The device
stays in Home Assistant until you delete it there.
