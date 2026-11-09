# Install with Portainer

Portainer is a web interface for Docker. In Portainer, a *stack* is a group of containers
defined by a Docker Compose file. This guide gives two ways to deploy spa2mqtt as a stack.

| Method | Use it when |
|---|---|
| [A. Stack from the published image](#a-stack-from-the-published-image) | Normal use. Fast, nothing to build. |
| [B. Stack from the repository](#b-stack-from-the-repository-build) | Fallback. The host cannot pull from `ghcr.io`, or you want to run a branch that has no image. |

Both methods take every setting from environment variables and use no bind mounts. A bind
mount maps a file from the host into the container. Portainer under Home Assistant OS
keeps its stack files in a folder that the host cannot see, and the host's `/data` is
read-only. A bind mount there fails with `mkdir /data: read-only file system`. Environment
variables avoid that problem.

!!! tip "Check the bus first"
    Run the read-only monitor once before you install. See
    [Run the read-only monitor](#run-the-read-only-monitor) below.

## A. Stack from the published image

1. In Portainer, open your environment and select **Stacks > Add stack**.
2. Set **Name** to `spa2mqtt`.
3. Select **Web editor**. Paste the contents of
   [`deploy/portainer-stack.yml`](https://github.com/srleach/spa2mqtt/blob/main/deploy/portainer-stack.yml):

    ```yaml
    --8<-- "portainer-stack.yml"
    ```

4. Below the editor, find **Environment variables**. Select **Add an environment
   variable** for each value in the table. You can also select **Advanced mode** and
   paste `NAME=value` lines.

    | Variable | Required | Example | Meaning |
    |---|---|---|---|
    | `SPA_IP` | Yes | `192.168.1.100` | Address of the RS485-to-TCP adapter (or the ProLink module) |
    | `MQTT_BROKER` | Yes | `192.168.1.7` | Address of the MQTT broker |
    | `MQTT_USERNAME` | If the broker needs a login | `spa` | Broker user name |
    | `MQTT_PASSWORD` | If the broker needs a login | | Broker password |
    | `SPA_PORT` | No | `8899` | TCP port of the adapter. `4257` for a ProLink module |
    | `SPA_DEFINITION` | No | `jacuzzi_j235` | Tub definition. `jacuzzi_j345` for a J345 |
    | `SPA_TRANSMIT` | No | `false` | Leave `false` until you have read [Safety](../safety.md) |
    | `LOG_LEVEL` | No | `INFO` | `DEBUG` for more detail |
    | `SPA2MQTT_TAG` | No | `2` | Image tag. See [Releases and versions](../releases.md) |

    The stack refuses to deploy if `SPA_IP` or `MQTT_BROKER` is missing. This stops a
    container that would only log connection errors.

    For a Jacuzzi J345 with a ProLink module, the [J345 guide](../tubs/jacuzzi-j345.md)
    lists the values.

5. Select **Deploy the stack**.

In Home Assistant, open **Settings > Devices & services > MQTT**. A device named after
the tub definition, for example *Jacuzzi J235*, appears within a few seconds. Its buttons and the setpoint show as
unavailable while transmit is off. That is expected.

!!! note "Home Assistant OS host addresses"
    If the MQTT broker is the Mosquitto add-on on the same Home Assistant OS host, set
    `MQTT_BROKER` to the host's LAN address. The name `core-mosquitto` resolves only on
    the add-on network, not on the network that Portainer stacks use.

### Update

The tag `2` follows every 2.x.y release. To get the newest image for the tag:

1. Open **Stacks > spa2mqtt**.
2. Select **Editor**, then **Update the stack**.
3. Turn on **Re-pull image and redeploy**, then select **Update**.

Without the re-pull option, Portainer reuses the image that it already has. On some
Portainer versions the same action is named **Pull and redeploy**.

### Roll back or pin a version

Set `SPA2MQTT_TAG` to a full version, for example `2.0.0`, then update the stack. The
container stays on that version until you change the variable.

## B. Stack from the repository (build)

This method makes Portainer clone the repository and build the image on the Docker host.
Building takes a few minutes and needs internet access to PyPI and Docker Hub.

1. Select **Stacks > Add stack**, set **Name** to `spa2mqtt`, and select **Repository**.
2. Set **Repository URL** to `https://github.com/srleach/spa2mqtt`.
3. Set **Repository reference** to a release tag such as `refs/tags/v2.0.0`. A tag gives
   you a known version. `refs/heads/main` builds the newest code.
4. Set **Compose path** to `docker-compose.yml`. This is the development compose file at
   the repository root. It builds from source and has no bind mounts.
5. Add the same **Environment variables** as in method A. `SPA2MQTT_TAG` has no effect
   here.
6. Select **Deploy the stack**.

To update, change the reference if needed, then select **Pull and redeploy** on the stack
page. Portainer fetches the repository again and rebuilds the image.

## Set or change environment variables

Open **Stacks > spa2mqtt > Editor**. The **Environment variables** section is below the
compose editor. Change a value, then select **Update the stack**. Portainer recreates the
container with the new values.

## Read the logs

1. Open **Containers** and select `spa2mqtt`.
2. Select **Logs**.
3. Turn on **Auto-refresh logs** to follow new lines.

The log shows the adapter and broker connections, warnings, and whether transmit is
enabled.

## Run the read-only monitor

The monitor decodes the bus and never transmits. Stop the `spa2mqtt` container first,
because most adapters accept only one TCP client.

1. Open **Containers**, select `spa2mqtt`, and select **Stop**.
2. Select **Containers > Add container**.
3. Set **Name** to `spa2mqtt-monitor` and **Image** to `ghcr.io/srleach/spa2mqtt:2`.
4. Under **Advanced container settings > Command & logging**, set **Command** to
   `spa2mqtt monitor 192.168.1.100` (your adapter's address). Add `-p PORT` and
   `-d DEFINITION` if yours are not `8899` and `jacuzzi_j235`, for example
   `spa2mqtt monitor 192.168.1.50 -p 4257 -d jacuzzi_j345`. Set **Console** to
   **Interactive & TTY**.
5. Under **Restart policy**, select **Never**.
6. Select **Deploy the container**, then open its **Logs**. A report appears at once and
   then every 10 seconds.
7. When you are done, stop and remove `spa2mqtt-monitor`, then start `spa2mqtt` again.

If you have a shell on the Docker host, this one line does the same:

```bash
docker run --rm -it ghcr.io/srleach/spa2mqtt:2 spa2mqtt monitor 192.168.1.100
```

## Enable transmit

Read [Safety](../safety.md) first. Then set `SPA_TRANSMIT` to `true` in the stack's
environment variables and update the stack. The log shows `TRANSMIT ENABLED`. To go back
to receive-only, set it to `false` and update the stack again.

## Limits of an environment-only setup

The `ha:` settings (`unique_id_prefix`, `legacy_topics`, `device_name` and others) and a
USB serial adapter need a `config.yml`, and Portainer under Home Assistant OS cannot mount
one. The defaults suit almost every install: the device name and identifier come from the
tub definition. If you need to change them, run spa2mqtt with
[Docker Compose](docker-compose.md) on a host that allows bind mounts.
