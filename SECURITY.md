# Security policy

## Supported versions

Only the latest release (the highest `vX.Y.Z` tag and the matching `ghcr.io/srleach/spa2mqtt`
image) receives fixes.

## Reporting a vulnerability

Please do not open a public issue. Use GitHub's private vulnerability reporting:
**Security > Report a vulnerability** on this repository. Include the version, how you run
spa2mqtt (Docker, ESPHome), and steps to reproduce.

You can expect a first reply within 14 days. This is a hobby project maintained in spare time.

## Scope

In scope: anything that lets a third party make spa2mqtt transmit on the RS485 bus while
`transmit` is off, bypass the command checks when it is on, read MQTT or Wi-Fi credentials,
or run code in the container or on the ESP32.

Physical and electrical safety of a spa installation is out of scope for this policy; see
the [safety page](https://srleach.github.io/spa2mqtt/safety/).
