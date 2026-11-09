# Monitor and capture

Two tools let you look at the bus without any risk to the tub. Neither one can transmit.

- **`spa2mqtt monitor`** decodes the live bus and prints the values to your terminal. Use
  it to check wiring, check a tub definition, and watch what changes when you press a
  topside button.
- **`tools/capture.py`** records the raw bytes of the bus to a file, with labels that you
  type. Use it to collect evidence for a new tub definition or a bug report.

Both need a connection to the bus. Most RS485-to-TCP adapters, the EW11A included, accept
only one TCP client. Stop the bridge before you run either tool.

## spa2mqtt monitor

```bash
spa2mqtt monitor HOST [options]
spa2mqtt monitor --serial DEVICE [options]
spa2mqtt monitor --replay CAPTURE [options]
```

In Docker, put the same command after the image name:

```bash
docker run --rm -it ghcr.io/srleach/spa2mqtt:2 spa2mqtt monitor 192.168.1.100
```

### Why it cannot transmit

The monitor has three separate guards. Each one alone stops a write:

1. The tub model runs with transmit off, so the bus state machine never produces a frame.
2. The monitor creates no bus writer, so no code path in it can send.
3. The connection is wrapped in a read-only transport, whose write method raises an
   error.

The monitor also never connects to MQTT, so Home Assistant sees nothing.

### Options

| Option | Default | Meaning |
|---|---|---|
| `HOST` | | Address of the RS485-to-TCP adapter |
| `-p`, `--port PORT` | `8899` | TCP port of the adapter |
| `--serial DEVICE` | | Read a USB RS485 adapter, for example `/dev/ttyUSB0`, instead of TCP. Needs the `serial` extra |
| `--replay CAPTURE` | | Decode a capture file instead of the live bus |
| `--speed N` | `0` | Replay speed. `0` is as fast as possible, `1` is real time |
| `-d`, `--definition ID` | `jacuzzi_j235` | Tub definition ID or file path |
| `-i`, `--interval SECONDS` | `10` | Seconds between full reports |
| `--describe` | off | Show each field's note in the reports |
| `--quiet-changes` | off | Print only the periodic reports, not each change |
| `--json` | off | Print JSON lines instead of text, for scripts |
| `--record FILE` | | Also append the raw bytes to `FILE`, in the capture format below. `--record -` writes them to standard output, between the reports |

Give exactly one source: `HOST`, `--serial` or `--replay`.

In the container image the working directory is read-only for the unprivileged user. To
record, mount a directory and run as your own user:

```bash
docker run --rm -it --user "$(id -u):$(id -g)" -v "$PWD:/captures" \
  ghcr.io/srleach/spa2mqtt:2 spa2mqtt monitor 192.168.1.100 --record /captures/session.log
```

Where you cannot mount a directory, for example Portainer under Home Assistant OS, use
`--record -`. The capture lines then appear in the container log, mixed with the reports.
Copy the log into a file: `spa2mqtt replay` and `spa2mqtt monitor --replay` read the
capture lines and skip everything else.

### What it prints

The monitor prints a full report at once, and then one every `--interval` seconds. A
report contains:

- the latest raw status frame and its decoded payload,
- every field of the definition, with its value and its evidence status (confirmed,
  inferred or hypothesis),
- frame rates per message type,
- the checksum error count.

Between reports, the monitor prints each value change and each topside button press as it
happens. Press Ctrl-C to stop. The monitor prints a last report when it stops.

A rising checksum error count means the bytes are damaged on the way. Check the baud rate
(115200, 8N1) and the A and B wires.

## tools/capture.py

`capture.py` records raw bus traffic from an RS485-to-TCP adapter. It has no send call
at all. The labels that you type go to the log file only.

```bash
git clone https://github.com/srleach/spa2mqtt.git && cd spa2mqtt
python3 tools/capture.py 192.168.1.100 8899
```

The tool needs only the Python standard library. It writes `spa-capture-<time>.log` in
the current folder.

While it runs, type a short label and press Enter just before each action at the topside,
for example `pump 1 press` or `set 38.5 to 39.0`. Labels mark the moment in the file, so
you can match each change in the bytes to what you did. Press Ctrl-C to stop.

### File format

Each line is one record:

```text
<unix time> RX <hex bytes exactly as received>
<unix time> MARK <label>
```

`spa2mqtt monitor --record FILE` writes the same format. Captures in this format play
back with `spa2mqtt replay FILE` and with `spa2mqtt monitor --replay FILE`.

### A good capture

1. Start the capture with the tub idle. Let it run for about one minute.
2. Note the topside display: water temperature, setpoint and clock. Type them as a label.
3. Do one action at a time. Type a label first, do the action, then wait about ten
   seconds.
4. Cover each button: each pump, the light, setpoint up and down.
5. Stop with Ctrl-C.

## Contribute a capture

Captures of other tubs, or of a J235 doing something new, help the project. A capture
contains only bus bytes, times and your labels. It contains no network addresses or
passwords. Read your labels before you share the file.

1. Open an [issue](https://github.com/srleach/spa2mqtt/issues) and attach the capture.
   Name the tub model, the board, and what the labels mean.
2. Or open a pull request that adds the file to
   [`tests/fixtures/captures/raw/`](https://github.com/srleach/spa2mqtt/tree/main/tests/fixtures/captures/raw).
   The test suite replays every capture there through the decoder. Add the expected
   values to `tests/test_replay.py` if you know them. That folder is for tubs of the
   encrypted family, because its captures are also decoded with the J235 definition. A
   capture of another family goes in its own folder under `tests/fixtures/captures/`.

To decode a capture yourself:

```bash
spa2mqtt replay spa-capture-1762466000.log
spa2mqtt monitor --replay spa-capture-1762466000.log --describe
```

`replay` prints each state change with its frame number. `monitor --replay` prints the
full reports.
