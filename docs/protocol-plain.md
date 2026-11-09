# Jacuzzi plain protocol (unencrypted boards, via ProLink)

This document describes the protocol of **unencrypted** Jacuzzi boards as far as one tub
shows it: a Jacuzzi J345 (J-300 series) reached through the Jacuzzi ProLink module. It is
the reference for `definitions/jacuzzi_j345.yaml` and for the bridge's direct bus mode. The
J235 does not use these frames: see the [wire protocol](protocol.md) for the encrypted
boards.

**Ground truth rule.** Where sources disagree, the captured dumps win. Statuses mean the
same as in the [wire protocol](protocol.md), with this tub in place of the J235. Nobody on
the project has this tub, so no claim here was checked by the project against the tub
itself. The checks are the owner's captures, pyjacuzzi's code, and the tub's recorded
reaction to commands that pyjacuzzi sent.

**Index convention.** `p[n]` is payload byte `n`, counted from 0 at the first byte after
`TYPE`. A field's `byte: n` in the definition uses the same index. pyjacuzzi and
jackbrown1993 index the whole frame: their `data[k]` is `p[k-5]`.

---

## 0. Sources

### Dumps (one J345, this repo)

All five files are in `tests/fixtures/captures/unencrypted/`. `tests/test_plain_j345.py`
replays them and asserts the values cited below. "S L8 → L9" means: sent on line 8 of S,
effect seen on line 9.

| Key | File | Provenance |
|---|---|---|
| **S** | `2025-05-21_pyjacuzzi_prolink_session.txt` | pyjacuzzi session log: 26 sent frames and 33 received. pyjacuzzi logs a received frame only when it differs from the previous one of its type |
| **D** | `2025-05-21_spa2mqtt_debug_0x16.txt` | spa2mqtt v1 debug log, receive only, every frame: 125 status, 38 lights |
| **X1** | `2025-05-20T1551Z_spa2mqtt_debug_idle.txt` | v1 debug log, idle tub: 100 frames |
| **X2** | `2025-05-20T2207Z_spa2mqtt_debug_lights.txt` | v1 debug log, lights changed at the topside: 100 frames |
| **X3** | `2025-05-28T0044Z_spa2mqtt_debug_panel.txt` | v1 debug log, every topside function: 1 316 status, 395 lights |

The LAN address in the logs is replaced with `192.0.2.1`. Nothing else is changed.

### Code and documentation

| Key | Repository @ commit | Notes |
|---|---|---|
| **PJ** | `dhmsjs/pyjacuzzi` @ `f9d6022` | `src/jacuzzi.py`, `src/balboa.py`, `src/jacuzziui.py`, `docs/ProlinkMessageTypes.txt`, `docs/ProlinkMessageParsing.txt`. Drove this tub successfully (S) |
| **JB** | `jackbrown1993/Jacuzzi-RS485` @ `1840e3c` | `app/jacuzziRS485.py`: plain 0x16/0x17 decode on a different tub's bus |
| **HJ** | `HyperActiveJ/sundance780-jacuzzi-balboa-rs485-tcp` @ `9a1df08` | `DECODING.md` §3.9: plain 0x16 support withdrawn; one foreign J-series frame |

## 1. Framing

The frame is the same as on the encrypted boards ([wire protocol §2](protocol.md#2-framing)):

```
 7E | LEN | ADDR | MID | TYPE | payload ... | CRC | 7E
```

| Claim | Status | Evidence |
|---|---|---|
| `LEN` = total bytes − 2. CRC-8 (poly 0x07, init 0x02, xorout 0x02) over LEN through the last payload byte. | Confirmed | All 2 133 frames in S, D, X1–X3 decode with the existing decoder: 0 CRC errors, 0 resyncs |
| The payload is plaintext: no per-frame key, no key stream. | Confirmed | Identical states give identical frames (D L6–L75 repeat one frame); S: a sent `20 5a` appears as `p[9] = 5a` |
| `spa2mqtt.protocol` needs no change for these frames. | Confirmed | `Frame.encode()` reproduces every captured frame, sent and received |

## 2. Frame types

| TYPE | ADDR | MID | Direction | Payload | Meaning | Status | Evidence |
|---|---|---|---|---|---|---|---|
| 0x16 | 0xFF | 0xAF | board → all | 32 | Status, about every 0.3 s | Confirmed | S: 13, D: 125, X3: 1 316 |
| 0x23 | 0xFF | 0xAF | board → all | 28 | Lights, about every 1.0 s | Confirmed | S: 19, D: 38, X3: 395 |
| 0x17 | 0x0A | 0xBF | client → board | 1 | Button press | Confirmed for codes 04, 05 | S L17, L22 |
| 0x19 | 0x0A | 0xBF | client → board | 2 | Panel request (PJ: primary filter cycle) | Inferred | S L3; PJ L1760–1762 |
| 0x1B | 0x0A | 0xBF | board → client | 2 | Reply to 0x19 | Inferred | S L4, 96 ms after L3 |
| 0x20 | 0x0A | 0xBF | client → board | 1 | Set temperature | Confirmed | S L8, L10, L13 |
| 0x21 | 0x0A | 0xBF | client → board | 8 | Set lights | Confirmed for the payloads in §5 | S L26–L78 |

No other type appears. In particular the four receive-only captures (2 074 frames) contain
no clear-to-send (0x06), no new-client poll (0x00) and no channel traffic (§6).

## 3. Status 0x16 (32 payload bytes)

Reference frame, S L5:

```
p:  0  1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31
   13 22 75 05 19 08 00 64 fa 50 00 00 00 02 00 00 66 01 1c 01 6c 80 00 80 00 00 00 00 00 00 00 00
```

| p | Field | Decode | Status | Evidence |
|---|---|---|---|---|
| 0 | `hour`, 24 h | raw | Confirmed | X3 L1403 → L1663 rolls `13 3b` to `14 00`. The tub clock is about 51 min behind wall clock in all five captures. PJ L857 |
| 1 | `minute` | raw | Confirmed | S L18 → L19 → L53: `22`, `23`, `24`, 60 s apart. PJ L858 |
| 2 bits 7–5 | `day_of_week`, 1 = Monday | shift 5, mask 0x07 | Confirmed | `75` = 3 on Wed 21 May (S, D); `54` = 2 on Tue 20 May (X1, X2); `5b` = 2 on Tue 27 May (X3). PJ L862 |
| 2 bits 4–0 | `day_of_month` | mask 0x1F | Confirmed | 21, 20, 27 in the same frames. PJ L863 |
| 3 | `month` | raw | Inferred | `05` in every capture. PJ L867. One month observed |
| 4 | `year` − 2000 | offset 2000 | Inferred | `19` = 2025. PJ L868. One year observed |
| 5 | `state_raw` | raw | Hypothesis | `08` while the setpoint (80, 90) was far below the water temperature with the circulation pump off (S L5, L9). `02` from the frame where the setpoint reached the water temperature (S L11), and everywhere else. PJ L874–876 splits it into filter mode, heat mode and "spa state" |
| 6 | `error_code` | raw | Hypothesis | Always `00`. PJ L888 only |
| 7 | `water_temperature`, °F | raw; `ff` = no reading | Inferred | 100–102, stable while the setpoint moved (S L9–L14). PJ L891. No topside reading was recorded |
| 8 | Unknown | | Unknown | `fa` in every frame, and in HJ's foreign frame |
| 9 | `setpoint`, °F | raw | Confirmed | S L8 → L9 `5a`, L10 → L11 `64`, L13 → L14 `65`. Topside: D L143, X3 L1241 |
| 10 bits 1–0 | `circulation_pump` (0 off, 2 on) | bit 1 | Inferred | `00` → `02` at S L11; `00` in X1. PJ L933–944. Never commanded |
| 10 bits 3–2 | `pump_1` (0 off, 2 on) | bit 3 | Confirmed | S L22 → L23 on, L24 → L25 off. Topside: D L76, L103; X3 L1118 |
| 10 bits 5–4 | `pump_2` (0 off, 2 on) | bit 5 | Confirmed | S L17 → L18 on, L20 → L21 off. Topside: D L110, L130; X3 L1153 |
| 10 bits 7–6 | Pump 3 per PJ | | Hypothesis, not decoded | Never non-zero. PJ L914 |
| 11 bit 0 | `heater` | bit 0 | Hypothesis | On when the topside raised the setpoint to water + 2 (D L143, `14` → `15`). Off when the setpoint fell below the water temperature (X3 L1299, `15` → `14`). Off at setpoint − water = 0 and 1 (S L11, L14). No source names this bit: PJ L965 calls bits 1–0 "isUVOn" |
| 11 bit 1 | Unknown | | Unknown | Set with the circulation pump; clears about 0.3 s after a jet pump starts and stays clear (S L18, D L77, X3 L1118) |
| 11 bits 2, 4 | Unknown | | Unknown | Set whenever the circulation pump runs. PJ L962–965: "blower", "primary", marked uncertain |
| 12 bit 0 | `flow_switch` | bit 0 | Inferred | `00` → `01` 308 ms after the circulation pump started (S L11 → L12). `00` in X1. PJ L985–992 |
| 13 bit 0 | `celsius_mode` | bit 0 | Inferred | Always 0. PJ L899–902. Values 80–104 are only plausible as °F |
| 13 bits 2–1 | Clock format per PJ | | Hypothesis, not decoded | `01` here. PJ L997 |
| 13 bit 7 | `reminder` | bit 7 | Hypothesis | Set while `p[19..20]` was `0007` (X1) or `0000` (X3 L6). Clear after the CLEARRAY reset (X3 L1542) |
| 14 | Unknown | | Unknown | `00` |
| 15 bit 7 | `set_mode`: the topside is editing a value | bit 7 | Inferred | D L136 on with `p[29]` = 1, setpoint changes at L143, off at L164. X3 L1235–L1313. Also set during a menu edit (X3 L1534). Not set by a remote 0x20 (S L9, L11, L14) |
| 15 bits 3–0 | Locks per PJ | | Hypothesis, not decoded | Always 0. PJ L1016–1027 |
| 16 | `secondary_temperature`, °F | raw | Inferred | `66`/`65` against water `64` (S L14–L16); `61`/`60` with the circulation pump off (X1). PJ L1049 |
| 17–18 | Unknown | | Unknown | `01 1c`, also in HJ's foreign frame |
| 19–20 | `clearray_days`, big-endian | 2 bytes | Inferred | 7 (X1) → 365 (X2) → 364 next day (S, D). X3: 0, then 365 after a topside menu sequence (L1542). The fall from 364 to 0 in six days is unexplained. PJ L1056–1059 |
| 21–24 | Unknown | | Unknown | `80 00 80 00`. PJ: "water time", "outer filter time" |
| 25–27 | Unknown | | Unknown | `00 00 00` |
| 28 | `display_aux` | raw | Hypothesis | `ff` (X1), `03` (X3 until L1611), else `00` |
| 29 | `display_state` | raw | Inferred for 0 and 1 | `01` exactly while `set_mode` is on in D (L136–L163). Steps `07` … `2d` during topside menu use (X3 L1477–L1604) |
| 30–31 | Value shown during a menu edit | | Hypothesis, not decoded | `01 6d` for one frame (X3 L1534) |

Each pump field is two bits wide, and only the values 0 and 2 were seen. The definition
reads the high bit. A low speed (value 1), if a pump has one, would read as off.

## 4. Lights 0x23 (28 payload bytes)

Four 7-byte records. Record `k` is `p[7k .. 7k+6]`:

| Offset | Field | Status | Evidence |
|---|---|---|---|
| 0 | Mode: `00` off, `01`–`09` colours, `80` blend, `ff` blend paused | Confirmed (record 0) | Every `21 1f MM` command gives mode `MM` in the next frame (§5). `80`, `ff` from the topside: X3 L1354, L1376. PJ L1546 |
| 1 | Sub-mode: `02`, then `04`, only in blend | Unknown | X2 L19; X3 L1354, L1363 |
| 2 | Brightness, percent | Confirmed | `21 2f … LL` gives `LL` (S L63 → L64 and following). The topside steps `64`, `42`, `21` (X2 L32, L45). PJ L1547 |
| 3, 4, 5 | Red, green, blue | Confirmed | Match the commanded colour (S L27–L55). PJ L1548–1550 |
| 6 | Tail: `00`, or `ff` in an untouched record | Unknown | X1 L2 |

The definition decodes **record 0 only**: `light_mode`, `light_brightness`, `light_red`,
`light_green`, `light_blue`.

- The topside changes record 0 only (X2, X3).
- pyjacuzzi's 0x21 commands set all four records to the same values (S L27 onward).
- D L5 shows record 0 off while records 1–3 still hold blue (mode `02`, brightness 60),
  apparently left by an earlier remote command that is not in the captures: D predates S
  by about 13 hours. A brightness command of 0 clears all four (S L58).
- Which lamps records 1–3 drive is unknown.

Colours, with the RGB the tub reported at brightness 60:

| Mode | Name | RGB | Named by |
|---|---|---|---|
| 01 | white | 55 55 55 | RGB only |
| 02 | blue | 00 00 ff | PJ |
| 03 | green | 00 ff 00 | PJ |
| 04 | yellow | 7f 7f 00 | RGB only |
| 05 | orange | aa 55 00 | PJ |
| 06 | red | ff 00 00 | PJ |
| 07 | violet | 7f 00 7f | PJ |
| 08 | amber | 92 6d 00 | RGB only |
| 09 | aqua | 00 7f 7f | PJ |

Nobody confirmed white, yellow or amber by eye.

## 5. Commands

Every command is sent to `ADDR 0x0A`, `MID 0xBF`, in plaintext. These are the complete
frames from S. `Frame(0x0A, 0xBF, type, payload).encode()` reproduces each one, and
`tests/test_plain_j345.py` asserts that the bridge emits exactly these bytes.

| Command | Frame | S line (sent → seen) | Tub's reaction |
|---|---|---|---|
| Panel request | `7e 07 0a bf 19 01 00 95 7e` | 3 → 4 | Reply `7e 07 0a bf 1b 13 0c 1a 7e` after 96 ms |
| Set temperature 90 °F | `7e 06 0a bf 20 5a 93 7e` | 8 → 9 | `p[9]` `50` → `5a` |
| Set temperature 100 °F | `7e 06 0a bf 20 64 29 7e` | 10 → 11 | `p[9]` → `64`; circulation pump starts |
| Set temperature 101 °F | `7e 06 0a bf 20 65 2e 7e` | 13 → 14 | `p[9]` → `65` |
| Button, pump 1 | `7e 06 0a bf 17 04 9c 7e` | 22 → 23, 24 → 25 | `p[10]` `02` → `0a` → `02` |
| Button, pump 2 | `7e 06 0a bf 17 05 9b 7e` | 17 → 18, 20 → 21 | `p[10]` `02` → `22` → `02` |
| Light colour `MM` | `7e 0d 0a bf 21 1f MM 00 00 00 00 ff 00 CRC 7e` | below | All four records show mode `MM` |
| Light brightness `LL` | `7e 0d 0a bf 21 2f 01 00 00 00 00 LL 00 CRC 7e` | below | Brightness = `LL`; `00` turns every record off |

| Colour `MM` | CRC | Sent on S line | | Brightness `LL` | CRC | Sent on S line |
|---|---|---|---|---|---|---|
| 01 white | 77 | 26, 47 | | 00 (off) | f9 | 57, 78 |
| 02 blue | 11 | 29, 60 | | 14 (20) | fa | 63 |
| 03 green | ce | 32 | | 28 (40) | ff | 66 |
| 04 yellow | dd | 50 | | 3c (60) | fc | 69 |
| 05 orange | 02 | 35 | | 50 (80) | f5 | 72 |
| 06 red | 64 | 38 | | 64 (100) | 58 | 75 |
| 07 violet | bb | 41 | | | | |
| 08 amber | 42 | 54 | | | | |
| 09 aqua | 9d | 44 | | | | |

Notes:

- All 26 sends took effect on the first attempt. The tub reacts within one status period
  (95–374 ms); light changes show within one lights period.
- The `01` after `2f` is not a mode: the mode stayed `02` (S L64).
- The `ff` brightness in a colour command left the brightness at 60. Whether 60 is a
  default or the previous value is unknown.
- PJ `jacuzziui.py` L482–500: the board refuses mode 0 (turn off with brightness 0) and
  refuses blend (`80`) as a direct command. PJ L487–499 enters blend by sending brightness
  0 and then a non-zero brightness. So a non-zero brightness command sent while the lights
  are off is expected to start blend mode. In S every non-zero brightness (L63–L75) was
  sent while the mode was `02`, so this is not proven on this tub.
- PJ `jacuzzi.py` L394–397 doubles the set-temperature value when the tub is in Celsius
  (half degrees C in the same byte). No capture shows Celsius mode. The definition's
  `requires: {celsius_mode: false}` makes the bridge refuse the 0x20 command unless the
  last status frame has `p[13]` bit 0 clear.

**Not proven on this tub.** spa2mqtt does not send any of these:

- 0x17 codes `01` temp up, `02` temp down, `11` light, `12` colour, `0f` UV, `1e` menu
  (JB `jacuzziRS485.py` L100–107, another tub).
- Set time (0x18), locks (0x1F), filter commands (0x1B/0x1C), module-ident request (0x04),
  0x1A buttons (PJ only).
- Any 0x20 value other than `5a`, `64`, `65`. The definition offers 80–104 °F, the lowest
  and highest setpoints any capture shows (S L5, X3 L1241), with the same one-byte
  encoding. How the tub treats a value outside its own range is unknown, so the bridge
  never builds one.

## 6. Transport: the ProLink module

| Claim | Status | Evidence |
|---|---|---|
| The ProLink serves the bus as raw frames on **TCP port 4257**. | Confirmed | Every log of this tub; PJ `ProlinkMessageParsing.txt` L846, L919 |
| The ProLink has the fixed bus address **0x0A**. | Confirmed | All 26 sent frames and the 0x1B reply in S; PJ L198–202 |
| The stream carries **no clear-to-send and no channel traffic**. The ProLink appears to arbitrate the bus itself. | Confirmed (absence), Inferred (reason) | D, X1–X3: 2 074 frames, all `FF AF 16` or `FF AF 23`. The v1 logger printed every frame of every type |
| A client may write a command at any time, with no wait for a poll. | Inferred | PJ `balboa.py` L210 opens a bare socket and sends on user action; S: 26 of 26 sends worked |
| pyjacuzzi sends `0x19 01 00` 13 ms after connecting. | Confirmed | S L2 → L3. Whether later commands depend on it is unknown: no capture has a command without it |
| pyjacuzzi spaces repeated presses 1.0 s apart. | Confirmed (source) | PJ L703–707. The two closest sends in S are 1.96 s apart |
| The ProLink may sleep while the tub is idle. | Hypothesis | PJ `readme.md` items 6–7. The bridge reconnects after 30 s of silence |

Corroboration for the missing clear-to-send: the owner reported that JB's project showed
temperatures on this tub but could not change anything. JB waits for a clear-to-send on
its channel (`jacuzziRS485.py` L200–205), which this stream never delivers.

What is on the RS485 bus *behind* the ProLink is unknown. An EW11A or ESP32 wired to this
board might see clear-to-send frames and need the channel claim of the encrypted boards.
Nobody has tried, so the loader rejects a plain definition with `bus.mode: claim`.

## 7. What spa2mqtt sends

The definition selects `bus.mode: direct` ([design §6](design.md#6-bus-state-machine-and-setpoint-control)).
With transmit on:

1. Nothing is sent at start-up or on connect.
2. A command from Home Assistant is queued (at most 8; more are dropped with a warning).
   A number outside its range is refused, not clamped. A setpoint is refused unless the
   last status frame shows Fahrenheit.
3. On the next status frame, the bridge sends the `connection_check` frame (0x19) if it
   has not sent it on this TCP connection. `bus.hello` in the definition names it; without
   that key it is never sent.
4. Four status frames later (about 1.2 s) it sends the queued frame, and so on: one frame
   per four status frames.
5. Nothing is retried. A reconnect drops the queue and re-arms the connection check.

Every frame goes through `BusWriter.send()`, so `SPA_TRANSMIT=false` blocks all of it.

## 8. Unknowns

1. Whether the 0x19 connection check is needed before commands work.
2. Whether the ProLink accepts more than one TCP client, or the official app at the same
   time.
3. Whether a direct RS485 tap on this board needs the clear-to-send and channel-claim
   exchange.
4. Water temperature (`p[7]`) and the second sensor (`p[16]`) against the topside display.
5. The heater bit (`p[11]` bit 0) and `p[11]` bits 1, 2 and 4.
6. `p[5]` (`08` against `02`), and the heat-mode and filter-mode fields PJ places there.
7. Pump low speed, pump 3, blower, UV.
8. The tub's handling of setpoints other than 90, 100 and 101 °F, and of out-of-range
   values.
9. Celsius mode: `p[13]` bit 0 and any half-degree encoding.
10. Light records 1–3, the tail and sub-mode bytes, the `1f`/`2f` selector byte, and why
    pyjacuzzi's command writes four records while the topside writes one.
11. Whether a non-zero brightness command sent while the lights are off starts blend mode
    (PJ `jacuzziui.py` L487–499 says so).
12. The 0x1B reply `13 0c`. PJ reads it as filter start hour 19 and duration 12 h. The hour
    equals the tub's clock hour at that moment, which may be a coincidence.
13. `p[8]` (`fa`), `p[17..18]` (`01 1c`), `p[21..24]` (`80 00 80 00`), `p[28..31]` beyond
    "0 normal, 1 setpoint edit", and the CLEARRAY counter's fall from 364 to 0 in six days.
14. Month and year: seen for May 2025 only.
