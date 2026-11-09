# Jacuzzi "encrypted" RS485 protocol (J235 and Sundance-family boards)

This document describes the RS485 bus protocol spoken by the Jacuzzi J235 control board
(the "encrypted", Sundance-style variant of the Balboa protocol) as far as it is currently
understood. It is the reference for `spa2mqtt` and the `spa_bus` ESPHome component.

**Ground truth rule.** Where sources disagree, the captured dumps win. Every claim carries a
citation and a status:

| Status | Meaning |
|---|---|
| **Confirmed** | Verified against J235 dumps with an independent check (wall clock, physical plausibility, CRC, or two independent sources plus a dump). |
| **Inferred** | Consistent with all J235 dumps and at least one source, but no independent check yet. |
| **Hypothesis** | Claimed by a source or suggested by data, never observed exercising on a J235. |
| **Unknown** | No credible interpretation. |

Every dump-derived number below can be reproduced with
`python3 tools/research/analyze_captures.py <section>` (cited as **[A:section]**).

---

## 0. Sources

### Dumps (J235, this repo)

| Key | File | Provenance |
|---|---|---|
| **D1** | `tests/fixtures/captures/raw/2025-05-16_j235_c4_frames.log` | 54 raw wire frames transcribed from `documentation/jacuzzi_encrypted/decoding.md` (spa2mqtt `b0a5323`, lines 37–54 and every third line 65–170; committed `645e8b4` 2025-05-16 16:49 +0100). Only raw frames in existence. |
| **D2** | `tests/fixtures/captures/decoded/2025-05-18_debug_messages_old.csv` | 8 769 decoded C4 payloads (16 bytes, pairwise-fold decode, §3.2). Rows 1–8752 = `debug_messages.csv` as of `d99bf10` (2025-05-18); rows 8753–8769 are a later 2025-05-19 session appended to the same file. |
| **D3** | `…/decoded/2025-05-19T125834Z_epoch1747659514.csv` | 12 rows; recovered from history (deleted in `d185ab1`). Filename epoch = wall clock. |
| **D4** | `…/decoded/2025-05-19T130957Z_epoch1747660197.csv` | 260 rows; topside **menu navigation/editing** session (deleted in `d185ab1`). |
| **D5** | `…/decoded/2025-05-20T130850Z_epoch1747746530.csv` | 5 rows (deleted in `d185ab1`). |
| **D6** | `…/decoded/2025-05-20T131044Z_epoch1747746644.csv` | 32 rows (deleted in `d185ab1`). |
| **D8** | `tests/fixtures/captures/raw/2026-11-09T205918Z_j235_menu_values.log` | Raw wire capture, 75 s, 5 368 frames, idle, taken 2026-11-09 20:59 UTC with `spa2mqtt capture` (read-only). The owner read the topside menu just before: **FC 172, UV 148, H2O 172 changed to 150**, filter cycle 12 am / 4 / 1 hr, heat auto. |
| **D7** | `tests/fixtures/captures/raw/2026-11-04T220754Z_j235_labelled.log` | **Raw wire capture, 9 min, 51 242 frames, all message types**, with 37 owner-typed `MARK` labels for topside actions (pumps, temp up/down, lights, setpoint to 40). Taken 2026-11-04 22:07 UTC with `tools/capture.py` (receive-only) through the EW11A. Owner labels are typed shortly *after* each action. |

The decoded CSVs (D2–D6) contain the 16-byte pairwise-folded payload only: no headers, no
other message types, no timestamps per row. D7 has everything, so most statuses below rest on
D7 with D2–D6 as corroboration. `[A:labelled]` prints the D7 timeline used for each claim.

### Code and documentation

| Key | Repository @ commit | Notes |
|---|---|---|
| **S2M** | `srleach/spa2mqtt` @ `b0a5323` (legacy, tag/branch `legacy/pre-rewrite`) | Legacy implementation and J235 definition. Unmerged branches PR 16–20 (`b157d26`, `ebec593`, `fbf5cb5`, `b26e0ea`, `1f7ebbb`) also reviewed. |
| **SC** | `srleach/SpaControl` @ `ec631d8` | `pybalboa/sundanceRS485.py`: a modified copy of HyperActiveJ's decoder (older than HJ). |
| **HJ** | `HyperActiveJ/sundance780-jacuzzi-balboa-rs485-tcp` @ `fc38ab5` | Sundance 780 decoder plus `DECODING.md`. GitHub now redirects this repo to `pete-jorgensen/SundanceHotTub2MQTT` (same HEAD). History was rewritten to a single commit. |
| **PJ** | `dhmsjs/pyjacuzzi` @ `f9d6022` (fork `srleach/pyjacuzzi` @ `65f4891`) | Jacuzzi library with Prolink decompilation notes. Upstream has one protocol commit newer than the fork: `39c2834` (2026-11-03, temperature-scale ordering in the 0x16 parser). Line numbers are for the fork unless marked "up". |
| **JB** | `jackbrown1993/Jacuzzi-RS485` @ `96f3172` | Plain (0x16) Jacuzzi decoder derived from HJ/PJ. The plain-board page cites the later head `1840e3c`. |
| **IR** | `Iraithium/sundance-rs485-controller` @ `f444c9b` | ESPHome external component for Sundance (encrypted) boards: prior art for on-device work. |
| **AL** | `al1505/ALs-HA-SundanceMarin` @ `8bb04fb` | Sundance Marin 780 HA integration (CRC note only). |
| **HA** | Home Assistant entity registry, read 2026-11-04 | Current entity set and `unique_id`s (§10). |

---

## 1. Physical layer

| Claim | Status | Evidence |
|---|---|---|
| Two-wire RS485, half duplex, shared by the board, topside panel(s) and add-on modules. | Confirmed | Legacy README wiring "12v +/, A/B" (S2M `README.md`); bus has several channels (§4). |
| **115200 baud, 8N1.** | Inferred | IR `README.md` L197 ("115200 8N1, required by the bus", Sundance). The J235 has been read through an EW11A RS485–WiFi bridge (port 8899, S2M `config.yml.example`); its serial settings are not recorded in this repo. Confirm from the EW11A web UI. |
| An EW11A in transparent TCP mode passes bytes unmodified (no escaping). | Confirmed | D1 and D7: 51 296 frames, 0 CRC errors, 0 resyncs [A:crc]. |
| Devices on the J235 bus: the board, one topside panel on channel 0x10, the (passive) EW11A. | Confirmed | D7 census: only 0x10 is ever polled and it answers every CTS [A:census]. |

## 2. Framing

```
 0     1     2      3     4      5 .. N-3     N-2   N-1
 7E | LEN | ADDR | MID | TYPE | payload ... | CRC | 7E
```

| Claim | Status | Evidence |
|---|---|---|
| Start and end flag 0x7E. | Confirmed | D1: all 54 frames [A:crc]; SC L242/L250; PJ `src/balboa.py` L10. |
| `LEN` counts from LEN through CRC: `LEN = total_frame_bytes − 2`. | Confirmed | D1 [A:crc] "LEN==len(frame)-2: True"; PJ `docs/ProlinkMessageParsing.txt` L4. |
| No byte stuffing or escaping. A 0x7E inside the payload is legal; the receiver must frame by LEN, not by scanning for 0x7E. | Confirmed (no escaping), Inferred (0x7E payload bytes) | PJ `balboa.py` L777–821 frames by length; D1 bodies are uniformly random per frame (key byte, §3.1), so payload 0x7E is unavoidable. Legacy S2M resynchronised on `7E <non-7E>`, which is correct. |
| CRC-8 over bytes `[1 .. N−3]` (LEN through last payload byte). | Confirmed | D1 54/54 [A:crc]; SC `balboa_calc_cs(data[1:len])` L249. |
| CRC parameters: **poly 0x07, init 0x02, no reflection, xorout 0x02** (textbook form). The legacy "augmented, register 0xB5" code is the same function. | Confirmed | [A:crc] "formulations agree=True"; garbled1 docstring in S2M `spas/base/packet/packet.py` L631–650. AL's "init 0xFF / xorout 0xFF" variant gives identical results (0x02⊕0xFF is a fixed point), per the upstream review. |
| Observed lengths: C4 `LEN=0x26` (33-byte payload), CA `LEN=0x22` (29-byte payload), CC `LEN=0x07` (2-byte payload), CTS 0x06 and new-client 0x00 `LEN=0x05` (empty payload). | Confirmed | D7 census [A:census]. |
| Consecutive frames each carry their own start and end flag (`… 7E 7E …`). | Confirmed | D7 raw stream. |
| Receivers should reject `LEN < 5` or `LEN > 64`. | Inferred (design choice) | IR accepts 5–64; S2M legacy accepted ≤128; the longest known frame is 0x26. |

## 3. Message types and the "encryption"

### 3.1 Type table

| TYPE | ADDR | MID | Direction | Meaning | Status | Evidence |
|---|---|---|---|---|---|---|
| 0xC4 | 0xFF | 0xAF | board → all | Status (encrypted) | Confirmed | D1 (all frames `FF AF C4`) |
| 0xCA | 0xFF | 0xAF | board → all | Lights status (encrypted), ≈ 1 Hz | Confirmed | D7: 542 frames; layout §3.5. |
| 0xCC | client | 0xBF | client → board | Button press (encrypted). The panel sends one in reply to **every** CTS; code 0x00 when idle. | Confirmed | D7: 24 177 CTS, 24 177 CC on 0x10 [A:census]; codes §3.4. |
| 0x00 | 0xFE | 0xBF | board → all | "Any new clients?" (new-client CTS), ≈ 1 Hz | Confirmed (exists, cadence); purpose Inferred | D7: 542 frames in 541 s; SC L16, L687–701; IR. |
| 0x01 | 0xFE | 0xBF | client → board | Channel assignment request, body `02 F1 73` | Hypothesis | SC L688–701 (`F1 73` "random magic"). |
| 0x02 | 0xFE? | 0xBF | board → client | Channel assignment response; channel in `payload[0]` | Hypothesis | SC L703–705. |
| 0x03 | channel | 0xBF | client → board | Channel assignment ack (empty body) | Hypothesis | SC L705–715. |
| 0x04 / 0x05 | channel | 0xBF | board ↔ client | Existing-client request / response (body `04 08 00`, meaning unknown) | Hypothesis | SC L716–730. Note SC/HJ/JB build this frame with an off-by-one (`bytearray(9)` then write index 9), so this path has probably never run successfully. |
| 0x06 | channel | 0xBF | board → client | Clear to send for that channel, ≈ 45 Hz to 0x10 | Confirmed | D7: each CTS is followed by the panel's CC [A:census]; SC L731–748. |
| 0x07 | channel | 0xBF | client → board | Nothing to send | Hypothesis | SC L23, L642–648 (built, never sent: L743 commented out). |
| 0x16 / 0x17 / 0x23 | | | | **Unencrypted** Jacuzzi status / button / lights. **Not used by the J235.** Documented for the J345 in [Wire protocol (plain boards)](protocol-plain.md). | Confirmed (not J235) | No such frames in D1; PJ L1617–1665 and HJ `DECODING.md` L275–303 treat these as plaintext on non-encrypted boards. The legacy S2M and SC route 0x16/0x23 through the XOR decoder, which is wrong (HJ upstream removed it for that reason). |

The address and MID semantics follow the Balboa convention: `MID=0xAF` is a board broadcast,
`0xBF` is client traffic, `ADDR=0xFE` is "unassigned client" and `0xFF` is broadcast
(Inferred: SC constants; PJ `docs/ProlinkMessageTypes.txt` L28). The Prolink module uses
fixed `ADDR=0x0A` (PJ L198–202). Sundance/J-series panels have been seen on 0x10 and 0x11
(SC L238 example; HJ `DECODING.md` L366).

### 3.2 Encryption of C4 (status)

> **Superseded for decoding by §3.3.** This section explains the two published models and how
> they relate. spa2mqtt 2.0 decoded with the pairwise fold. The current decode removes the key
> and a calibrated key stream and reads plaintext per byte (§3.3).

Two published models exist. **They are algebraically the same cipher.** This repo proves it
on D1. The first version of this document chose the pairwise fold because it is key-independent
and because it gave the right calendar day where pyjacuzzi's per-byte layout did not.

**Per-frame key byte.** `payload[0]` (frame byte 5) is a random per-frame key K. Every other
payload byte is `K ⊕ c_i` for a fixed per-state stream c. In D1, 49 distinct keys appear across
54 frames, but `payload ⊕ K` is identical for every frame in the same tub state [A:cipher].
(Confirmed.)

**Model A: key-stream decrypt** (PJ `src/jacuzzi.py` L221–292):

```
key1 = f[5] ^ 0x19            # 0x59 for CA, 0xDF for CC
key2 = LEN - 7
for i in 6 .. LEN-1:          # frame indices; CRC untouched
    key2 = (key2 - 1) mod 64
    P[i] = f[i] ^ key1 ^ key2
```

**Model B: pairwise fold** (HyperActiveJ `xormsg`, SC L262–267; legacy S2M):

```
d[j] = payload[2j] ^ payload[2j+1] ^ 1        for j = 0..15   (payload[32] is never used)
```

**Identity** (Confirmed on all 54 D1 frames [A:cipher]; independently derived in the upstream
review): `d[0] = P[6] ^ 0x06` and `d[j] = P[5+2j] ^ P[6+2j]` for j ≥ 1. Consequences:

* HJ's "hour XOR 6" is the key-stream constant. Model A's hour `P[6]` equals `d[0] ^ 6`.
* Model B values are XORs of **two adjacent** Model A bytes. HJ's "temperature XOR 2" is really
  `P[15] ^ P[16]` with `P[16] = 0x02` in every sample (D1; PJ samples). PJ's "minute
  `(P[27]&0x3F)^0x08` for some unknown reason" is `P[27] ^ P[28]` with `P[28] = 0x08`.
* **Which model gives the true field boundaries is not settled.** The evidence favours Model B:
  D1 was committed 2025-05-16 at 16:49 +0100, and its hour/minute read 11:35–11:38. Model B gives
  day-of-month 16, month 5. Model A gives `P[19]>>3 = 19`, three days in the future. Model B's
  day/month also matches wall clock on four further dates (D2–D6, §5). (Day field: Confirmed for
  Model B; refuted for Model A on J235.)
* Model B discards half the information (16 of 32 bytes). Fields that are not 1:1 with a folded
  byte may be invisible to it. This is the main reason raw captures are needed (§9).

**Encoding** (for transmit, §6): to send a folded payload d, pick any K and emit
`payload[0]=K, payload[2j+1]=payload[2j]^d[j]^1`. Model B decoding is insensitive to the choice
of the even bytes, but the board decodes with whatever it really uses, so outbound C4 encoding
is never needed and is not implemented.

### 3.3 Decryption: plaintext per byte (current decode)

**Method.** Remove the per-frame key, then remove a fixed key stream:

```
plain[i] = payload[i] ^ payload[0] ^ S[i]          (i = 1 .. 32; plain[0] = 0)
S[i]     = 0x19 ^ ((31 - i + adjust[i]) mod 64)     adjust[i] = -8 at i = 5, 6, 14, 15, 22; else 0
```

Every field is then a plain read of one byte (or some of its bits), with no per-field constant.
`S` is pyjacuzzi's key stream (`decrypt()`, key1 = `payload[0] ^ 0x19`, key2 counting down from
31) with five corrections. [A:decrypt] prints the table.

**Why per byte.** After the key is removed, varying data shows up in *both* bytes of some pairs
(D7: bytes 2 and 3, bytes 28 and 29). The fold merges each pair into one value, so it loses
information whenever both bytes change. This is what made the date undecodable from August to
December (§5 d7) and what made the "secondary temperature" and the display code look multiplexed.

**How the stream was established.**

| Byte | Field | Evidence for S[i] on the bits used | pyjacuzzi formula |
|---|---|---|---|
| 1 | hour | Wall clock D3–D6; pyjacuzzi labelled frame (2:40 PM) | correct |
| 2 | pump 1 running (bit 6), heat demand (bit 5), manual circ (bit 7) | D7 presses | correct on bits 5–7 |
| 3 | pump 2 (bit 2) | D7 presses | correct on bit 2 |
| 5 | day of week (bits 2–0), pump 1 speed (4–3), set mode (5) | Five dated J235 captures; D7 presses | **8 lower** |
| 6 | filter change days | D8 topside FC 172 (the formula gives 164); D7 177 five days earlier | **8 lower** |
| 10 | water temperature | D7 display 38.5 °C; pyjacuzzi label 102 °F | correct |
| 14 | day of month (bits 7–3) | D1 16 May, D7 4 Nov; pyjacuzzi label 18 May | **8 lower** |
| 15 | month (bits 3–0) | D1 May, D7 November; pyjacuzzi label May | **8 lower** |
| 16 | setpoint | D7 38.5 → 40.0 → 38.5; pyjacuzzi label 103 °F | correct |
| 19 | year − 2000 | 2025, 2026 (J235); pyjacuzzi label 2023 | correct |
| 21 | heater (bit 6) | D7 heating sequence | correct on bit 6 |
| 22 | minute | Wall clock D3–D6; pyjacuzzi label 2:40 PM | **8 lower** |
| 24 | water change days | D8 topside H2O 150 | correct |
| 27 | UV lamp days | D8 topside UV 148 | correct |

Status: **Confirmed** on the bits listed, for the J235. Bytes not listed use the formula without
correction and are unverified. pyjacuzzi's own "minute `(b & 0x3F) ^ 0x08` for some unknown
reason" is the byte-22 correction.

**Cross-check on other tubs.** The same stream, calibrated only on the J235, decodes every raw
C4 frame published by other projects [A:decrypt], `tests/test_replay.py`:

| Frame | Plaintext | Check |
|---|---|---|
| HyperActiveJ Sundance 780 docstring sample (`fc38ab5`) | 14:17 Thu 14/04/2022, water 96 °F, set 90 °F | Thursday is right for that date; HyperActiveJ's first commits are 15–16 Apr 2022 |
| pyjacuzzi `jacuzzi.py` L1124, labelled "05/18/23 2:40PM, WS 103, WT 102" | 14:40 Thu 18/05/2023, water 102, set 103 | Every labelled value matches |
| pyjacuzzi `jacuzzi.py` L246 | 13:37 Tue 09/05/2023, water 96, set 97 | Valid date and weekday |

The fold reads the year of the first two as 2023 and 2022, both wrong. Status: the cipher and
stream are **Confirmed** to be shared by the J235, another encrypted Jacuzzi and the Sundance 780.

**Agreement with the fold.** On all 1 858 raw J235 frames, the plaintext fields equal the old fold
result wherever the fold was right (`test_per_byte_agrees_with_fold_on_every_raw_frame`). The
differences are the corrections: the November day of month, and two pump-start frames in which
the fold mixed the pump flag into the secondary value.

**Plaintext field map (J235).** The fold field `d[j]` of §5 is `plain[2j] ^ plain[2j+1]` (with
constants), so §5 remains the record of the evidence. The plaintext positions are:

| Byte | Field | Status |
|---|---|---|
| 1 | hour (24 h) | Confirmed |
| 2 | bit 7 manual circulation (hypothesis); bit 6 pump 1 running; bit 5 heat demand (hypothesis) | Confirmed (bit 6) |
| 3 | bit 2 pump 2 | Confirmed |
| 5 | bits 2–0 day of week (0 = Sunday); bits 4–3 pump 1 speed; bit 5 set mode | Confirmed |
| 6 | filter change days (topside FC): D8 172, D7 177, D1 127 | Confirmed |
| 10 | water temperature, raw (°C × 2 on this tub) | Confirmed |
| 14 | bits 7–3 day of month | Confirmed |
| 15 | bits 3–0 month | Confirmed |
| 16 | setpoint, raw | Confirmed |
| 19 | year − 2000 | Confirmed |
| 21 | bit 6 heater | Confirmed |
| 22 | minute | Confirmed |
| 24 | water change days (topside H2O): D8 150, D7 177, D1 177 | Confirmed |
| 26 | 0 normal screen, 1 temperature-set screen | Confirmed |
| 27 | UV lamp days (topside UV): D8 148, D7 153, D1 77. Read before as a display code | Confirmed |
| 28 | secondary value (meaning unknown) | Hypothesis |
| 29 | bit 5 follows pump 1 (the flag that HyperActiveJ saw as "+32 while circulating") | Inferred |

### 3.4 Encryption of CC (button command)

`payload = [K, K ^ 0xE0 ^ code]`, i.e. **button code = payload[0] ^ payload[1] ^ 0xE0**.
(**Confirmed**: in D7 the panel's 24 177 CC frames use a random K every time, and every labelled
press decodes to the expected code [A:labelled].)

* HJ sends `[0xE0|code, 0x00]` (SC L245–248: `data[5]=val`, `data[6]=0`, with val 225 etc.).
* PJ sends key 0x00 then Model A with key1 0xDF on a 1-byte body, which gives
  `[0x00, code ^ 0xDF ^ 0x3F] = [0x00, code ^ 0xE0]` (PJ L294–346).
* SC's idle-panel example `7E 07 10 BF CC 65 85 A6 7E` decodes to code 0x00 ("no button")
  (0x65^0x85^0xE0 = 0).
* HJ's observed panel frames decode to P2 (0xE5) and P1 (0xE4) under this rule (HJ
  `DECODING.md` L366–369, per the upstream review).

Plain codes are shared with the unencrypted Jacuzzi 0x17/0x1A commands:

| Code | HJ value (`0xE0|code`) | Function | Status |
|---|---|---|---|
| 0x00 | 224 | none / idle (sent by the panel on every CTS) | **Confirmed** (D7) |
| 0x01 | 225 | Temp up. The first press only enters set mode; later presses step +0.5 °C | **Confirmed** (D7 t≈210, 238–239, 454) |
| 0x02 | 226 | Temp down (same set-mode behaviour) | **Confirmed** (D7 t≈272–273, 482–484) |
| 0x04 | 228 | Pump 1: off → low → high → off | **Confirmed** (D7 t≈90, 119, 143) |
| 0x05 | 229 | Pump 2: off ↔ on | **Confirmed** (D7 t≈181, 196) |
| 0x12 | 242 | Light: each press steps off → blend → colours → off (§3.5) | **Confirmed** (D7 t≈294–414) |
| 0x0F | 239 | ClearRay (UV) / circulation | Hypothesis (HJ, JB). PJ docs say 0x0E (internally inconsistent). Not on the J235 topside. |
| 0x11 | 241 | Light on/off | Hypothesis. The J235 panel never sent it; its single light button is 0x12. |
| 0x1E | 254 | Menu | Hypothesis (defined in HJ, never sent; HJ warns against brute-forcing codes) |

The J235 has no direct "set temperature" command on the encrypted bus. Setpoint changes are made
by pressing Temp up/down and watching the reported setpoint (§7). (Inferred: SC
L209, L259, L405–415; PJ L399–458 "no command to set an arbitrary value".)

### 3.5 Lights (CA)

The CA payload (29 bytes) folds to 14 bytes `c0..c13`. HJ's assignment is confirmed by D7,
with the owner's colour labels as the independent check [A:labelled]:

| c | Meaning | Status | Evidence (D7) |
|---|---|---|---|
| 0 | constant 0xBD | Unknown | – |
| 1 | brightness / on: 0x64 (100) on, 0 off | Confirmed | t≈294 on, 307 off |
| 2 | blue level | Confirmed | "blue" → c2=FF; "cyan" → c2=c6=7F; "white" → c2=c6=c8=55 |
| 3, 5 | constants 0x64, 0xFF | Unknown | – |
| 4 | mode: 0x80 blend, 0xFF transition, 0x01 white, 0x02 blue, 0x03 green, 0x06 red, 0x07 violet, 0x08 amber ("green" to the owner), 0x09 aqua | Confirmed | press sequence t≈294–414; matches HJ `DECODING.md` map |
| 6 | green level | Confirmed | "deep green" → c6=FF |
| 8 | red level | Confirmed | "red" → c8=FF; "magenta" → c2=c8=7F |
| 9 | 0x02 while blending, 0x04 at step, 0 static | Inferred (blend phase/speed) | – |
| 7, 10–13 | 0 | Unknown | – |

Blend mode animates c2/c6/c8 about once a second.

**Light button timing** (Confirmed, D7 t≈294–516 [A:labelled]). A 0x12 press steps to the next
mode only while it follows the previous light press closely: presses 0.6–3.5 s apart stepped
blend → blend paused → blue → violet → red → amber → green → aqua → white. A press 5.2 s or more
after the last one turned the light off (t≈306.1, 323.9, 340.6, 357.3, 373.4, 393.6, 408.6), and a
press while off turned it on in blend. The owner's label at t≈442: "light changes in steps only
for few secs then toggles off". The J235 definition reads c1 bit 6 as *Light* (on/off) and c4 as
*Light Mode*; the *Light* switch waits ≈ 7.5 s between presses so that a press which only
stepped the colour is followed by one that turns the light off.

## 4. Bus arbitration and addressing (state machine)

The board polls every client channel with CTS (0x06). A client may transmit **only** in the
gap immediately after the CTS addressed to its channel. Panels answer every CTS with a CC
(code 0x00 when idle). (Inferred: SC L731–770; IR.)

```
                 (passive listener: never transmits)
 LISTEN ────────────────────────────────────────────────────────────────┐
   │ observe CTS(0x06) channels  → known_channels                       │
   │ observe CC(0xCC) channels   → active_channels                      │
   ▼ a command is queued AND transmit is enabled                        │
 CLAIM ── after ≥5 CC frames observed: pick lowest channel in           │
   │      known_channels \ active_channels ("dormant") ──► READY        │
   │      none dormant: on next 0x00 send 0x01 request (F1 73)          │
   ▼                                                                     │
 REQUESTED ── 0x02 response: channel = payload[0]; send 0x03 ack ──► READY
 READY ── on CTS(our channel): send one queued CC, else nothing         │
   │      on CC from another device on our channel → conflict ─────────┘ (back to LISTEN)
```

| Claim | Status | Evidence |
|---|---|---|
| "Dormant channel" reuse: after 5 CC observations, take the lowest polled channel that never sends CC. | Hypothesis; **not applicable to this J235 install** | SC L46–48, L749–760; IR uses 5 CTS frames. D7: the only polled channel (0x10) answers every CTS, so there is no dormant channel and a new client must use the 0x00/0x01 request. |
| Channel request `7E 08 FE BF 01 02 F1 73 cs 7E` sent in response to 0x00. | Hypothesis | SC L687–701. |
| After CTS the client should answer immediately; no deadline is documented. HJ over TCP (EW11A) worked, so the window is at least tens of ms. | Inferred | SC L742–748; HJ sets TCP_NODELAY (SC L193). IR waits 50 µs for DE/RE turnaround. |
| An idle client may stay silent on CTS. HJ never sends NTS (0x07). | Inferred | SC L743 commented out. |
| The legacy S2M bridge **claims a channel and may send 0x01/0x03 automatically at start-up**, even if no button is pressed. | Confirmed (code) | S2M `spas/jacuzzi_encrypted/spa/jacuzzi_encrypted_spa.py` L51–88, L1182–1188. The rewrite does not do this (design.md §Safety). |

## 5. C4 status field map (J235)

Index = folded byte `d[j]` (Model B). The equivalent Model A bytes are `P[5+2j]` and `P[6+2j]`.
"Bit n" counts from LSB 0. Scale 0.5 assumes °C, the only mode ever observed on this tub (§8).
"D7 t≈N" refers to seconds into the labelled capture, printed by [A:labelled].

| d | Field | Transform | Status | Evidence |
|---|---|---|---|---|
| 0 | Hour (24 h) | `d0 ^ 0x06` | **Confirmed** | [A:clock]: D3 13:01 vs wall 12:58Z; D4 13:12 vs 13:09Z; D5 13:11 vs 13:08Z; D6 13:13 vs 13:10Z. D2 runs 17:46→21:31 monotonically. In D7 the tub clock reads 21:31 at 22:07 UTC, so it has drifted since May, but hour and minute roll over consistently. |
| 1 | bit 7: manual circulation call | `(d1>>7)&1` | Hypothesis | SC L341 `MANUAL_CIRC = 7`. Never set in any J235 dump, D7 included. |
| 1 | bit 6: **pump 1 running (any speed)** | `(d1>>6)&1` | **Confirmed** | D7: set ≈ 0.5 s after the pump-1 press that starts low speed (t≈90.8), stays set through high, clears on off (t≈143.8). Also set when heating starts pump 1 low (t≈454.5). On the J235, pump 1 low is the circulation/heating mode (PJ `jacuzzi.py` L925–936: "J-235 has no circ pump"). This is what the legacy "Circulation Pump Status" entity has always shown. |
| 1 | bit 5: heat demand / flow proven? | `(d1>>5)&1` | Inferred (sequence), meaning Hypothesis | D7: in the heating sequence, pump 1 low starts at t≈454.5, d1 bit 5 at t≈496.1, heater bit at t≈512.8. D2 rows 1–277 (heating) also show it. Never set when pumps are run manually. |
| 1 | bit 2: **pump 2 on** | `(d1>>2)&1` | **Confirmed** | D7: set by the pump-2 press at t≈181.2, cleared by the next at t≈195.6. Single speed. SC L339/L355. |
| 2 | bits 2–0: **day of week** (0 = Sunday) | `d2 & 7` | **Confirmed** | [A:clock]: 18 May 2025 (Sun) 0, 19 May (Mon) 1, 20 May (Tue) 2, 16 May (Fri) 5; D7 4 Nov 2026 (Wed) 3. Also right on the three foreign frames (§3.3). An earlier version of this document said the foreign frames disagreed by one day; that came from pairing them with the fold's wrong year. |
| 2 | bits 4–3: **pump 1 speed** (0 off, 1 low, 2 high) | `(d2>>3) & 3` | **Confirmed** | D7: press 1 → 0x03→0x0B (low), press 2 → 0x13 (high), press 3 → 0x03 (off) at t≈90/119/143. Heating starts low (t≈454.5); D2's heating window has bit 3 set. The legacy "main pump" bit (`d2` bit 4) is therefore "pump 1 on high". |
| 2 | bit 5: **set mode active** (topside temperature edit) | `(d2>>5)&1` | **Confirmed** | D7: set by the first temp press and cleared ≈ 5 s after the last (t≈209.9–215.2, 238.2–244.5, 454.5–458.1). D4: set while menu values were edited. |
| 3 | Menu-editable maintenance value | raw | Unknown | D4: changed 130 → 120 → 118 → 90 as the user edited values in the menu. D2 118, D3 111, D5/D6 101, D7 0x4B (75). SC names d3 "water life remaining days". **Resolved by §3.3:** plaintext byte 6 is the filter change countdown (D8). |
| 4 | constant 0x05 | – | Unknown | 0x05 in every J235 row, D7 included. HJ's "f4 bit 6 = circulation" never occurs on the J235. |
| 5 | **Water temperature** | `(d5 ^ 0x02) × 0.5` °C | **Confirmed** | D7: 0x4F → 38.5 °C matches the owner's "display 38.5C" mark (t≈50); flickers 38.0/38.5. D2: a heating curve 37.5 → 38.5 around a 38.0 setpoint. Without the XOR the D2 reading would jump 2.5 °C in 10 min, so the XOR stays and PR 17/19 are refuted. Caveat: `^2` is really `^P[16]` (§3.2), constant in all samples. |
| 6 | constant 0x20 | – | Hypothesis: heat mode | HJ `DECODING.md`: 32 = AUTO (34 ECO, 36 DAY). 0x20 in every J235 row, D7 included. |
| 7 | **Day of month / month**, packed as `(day << 3) XOR month` | day = `d7 >> 3` **only when month ≤ 7**; month low 3 bits = `d7 & 7`. **Resolved by §3.3:** plaintext byte 14 is the day and byte 15 the month | **Confirmed**; fold ambiguous for months 8–12 | D2–D6 (May) and D1 (16 May) decode exactly. D7 (4 Nov, Wed) has d7 = 0x2B = (4<<3) ^ 11: bit 3 carries both day bit 0 and month bit 3, so the fold cannot separate them (`d7>>3` gives 5). HJ's January 19 reading fits too. Model A (key-stream) might separate them but its per-byte key stream is wrong at these offsets (§3.2). |
| 8 | **Setpoint** | `d8 × 0.5` °C | **Confirmed** | D7: 0x4D → 38.5 at the "setpoint 38.5c" mark (t≈76); each Temp-up step adds 1 (0.5 °C) up to 0x50 (40.0, t≈469.6); steps back down to 0x4D. |
| 9 | Year − 2000 | raw | **Confirmed** | 25 in every 2025 J235 row; 26 (0x1A) in D7 (2026); PJ sample 22, HJ sample 23. |
| 10 | bit 6: **heater on** | `(d10>>6)&1` | **Confirmed** | D7: after raising the setpoint above the water temperature, heater on at t≈512.8 following pump 1 low and d1 bit 5 (§5 d1). D2 rows 1–51: set only while water < setpoint. SC L327; PJ `P[26]` bit 6. |
| 10 | bit 7 | – | Hypothesis: heater run-on / auto circulation | D2 rows 47–277 (after the heater bit clears, pump 1 still low). Not exercised in D7. PR 17's "pump map" reading of d10 is refuted by D7 (pumps never touch d10). |
| 11 | Minute | raw | **Confirmed** | [A:clock] against filename epochs; D7 increments once a minute. |
| 12 | – | raw | Unknown | 175 (18 May), 179 (19 May), 178 (20 May), 0xB1 (177, D7). SC names it "filter life remaining days". **Resolved by §3.3:** plaintext byte 24 is the water change countdown (D8). |
| 13 | **Display / menu state** | raw | Confirmed (it is display state); individual codes Inferred | D7: 0x99 (153) idle, 0x98 while in set mode, the same frames as d2 bit 5. D4: 99 → 100/109/114 in the menu → 113/112 editing → back. Idle value differs by day (90, 99, 98, 153), so the code space is not fully understood. |
| 14 | **Secondary value** XOR a pump-1 flag | `d14 ^ 0x20` while pump 1 runs | Inferred (flag); value meaning Unknown | D7: bit 5 flips in the same frame as each pump-1 start/stop (t≈90.3, 143.2, 151.8, 154.7, 454.5) while the underlying value keeps counting: 18 → 28 (pump on, 53 s) → 34 (off, 2 min). Under the §3.2 identity this is a flag bit in P[34] XORed onto a value in P[33] (PJ's samples show P[34] = 0x38 vs 0x18 with pump 1). HJ's "+32 while circulating" is the same effect. The value is not °C water (38.5) and not a clock. Exposed raw, disabled by default. PR 17's "hour" reading is refuted. |
| 15 | Menu value being edited | raw | Inferred | 0 except in D4 rows 109–159 (values 120…160 while d13 = 112/113). |
| (P37) | 33rd payload byte | – | Unknown | Never decoded by Model B. |

## 6. Commands (transmit path)

| Claim | Status | Evidence |
|---|---|---|
| Frame: `7E 07 <chan> BF CC <K> <K^0xE0^code> <crc> 7E`. | Inferred | §3.4. |
| One frame = one press. Pump buttons cycle off → low → high → off (2-speed pump 1) or off → on → off. | Inferred | PJ L663–700 (plain boards); legacy S2M exposes raw "pump button" presses for this reason. |
| Send only in the CTS slot for the client's own channel. | Inferred | §4. |
| There is no acknowledgement. Success is observed only through the next status frames. HJ retries after 2 status frames without change; IR retries after 5, up to 8 attempts. | Inferred | SC L50, L405–430 `CHECKS_BEFORE_RETRY = 2`; IR `sundance_spa.h`. |

## 7. Timing

| Claim | Status | Evidence |
|---|---|---|
| C4 status is broadcast ≈ 3.3 times per second (≈ 300 ms). | **Confirmed** | D7: 1 804 C4 in 541 s; D2: 200 rows per full minute. |
| CA lights ≈ 1 Hz; new-client 0x00 ≈ 1 Hz; CTS to 0x10 ≈ 45 Hz, each answered by a CC. | Confirmed | D7 [A:census]. |
| A topside press is reflected in the next C4 frame (≤ 300 ms). | Confirmed | D7: CC and the C4 change share a capture chunk timestamp, e.g. t≈239.3 [A:labelled]. |
| Set mode (after the first temp press) times out ≈ 5 s after the last press. | Confirmed | D7: 5 of 6 periods end 5.2–5.5 s after the last press [A:setmode]. |
| One period ended early, 3.6 s after the last press, in the same frame that pump 1 started for heating. | Hypothesis: heat-call start closes the set screen | D7 t≈454.5–458.1 [A:setmode]; one occurrence only. |
| C4 repeats unchanged between state changes; consumers must de-duplicate. | Confirmed | D2 runs of up to 2 313 identical rows [A:timeline]. |
| No status for > 10 s means the link is down (Prolink rule). | Inferred | PJ `docs/ProlinkMessageParsing.txt` L1439–1453. |
| The setpoint loop should allow ≥ 2 status frames (≈ 0.6 s) between presses and give up after a bounded number of attempts. | Inferred (design) | HJ/IR retry constants; PJ waits 1 s between presses. |
| Topside behaviour: the first Temp up/down press only enters set mode; each further press within ≈ 5 s changes the setpoint by 0.5 °C. | **Confirmed** | D7 t≈210 (enter only), 238–239 (enter + step), 454 (enter + 2 steps). The legacy `(target − current)/0.5` press count was always one short. |

## 7a. Set mode: where it is visible, and how it was validated

Set mode is the topside state entered by the first Temp up/down press, in which further
presses step the setpoint. It is visible **only in the C4 status broadcast**. Every check below
comes from D7 [A:setmode].

| Check | Result | Status |
|---|---|---|
| Two independent indicators | d2 bit 5 and d13 (0x98 instead of 0x99) agree on **all 1 804** status frames: 119 in set mode, 1 685 not. They come from different byte pairs on the wire. | Confirmed |
| Cause | All 6 periods start in the same capture chunk as a Temp up/down CC from the topside. No temp press falls outside a period. The setpoint never changes outside a period. | Confirmed |
| First press only enters set mode | In every period, setpoint steps = presses − 1 (1→0, 2→1, 2→1, 3→2, 2→1, 4→3). | Confirmed |
| Timeout | 5 of 6 periods end 5.2–5.5 s after the last press. The sixth ends after 3.6 s (§7). | Confirmed (≈ 5 s) |
| Other message types | CA lights frames continue unchanged. The topside's CC frames carry only the presses, then code 0x00. The 0x00 new-client poll continues. No new address or message type appears. | Confirmed |
| Bus cadence | 13.40 CTS polls per status frame both inside and outside set mode. (Per-second rates differ by ~5 %, an artefact of per-chunk capture timestamps.) | Confirmed |

The broadcast placement suggests that the board drives every panel's display from C4, so a
second topside would flash the same set screen. That is a hypothesis: no install with two panels
has been captured.

**Consequence for control.** `SetpointController` reads the set-mode field named by the
definition (`control.set_mode_field`). A press that turns set mode on is the "wake" press, and
the next press follows on the next status frame. Without the field, the controller falls back to
waiting `confirm_frames` and retrying. Both paths also wait while the press is still queued for a
bus slot. Without that wait, a slow channel grant made the fallback queue duplicate presses and
overshoot (regression test `test_slow_channel_grant_does_not_duplicate_presses`).

## 8. Units

The J235 in D1–D6 reports in °C ×2. Every value is consistent with that: setpoint 76 → 38.0 °C,
water 37.5–38.5 °C. (Confirmed for this tub.) No known field on encrypted boards gives the
unit flag: PJ upstream `39c2834` explicitly leaves it undetermined for C4. Unit is therefore a
**configuration value** in the tub definition, not a decoded field.

## 9. Known / inferred / unknown summary

| Area | Known (Confirmed) | Inferred | Unknown / Hypothesis |
|---|---|---|---|
| Framing | 0x7E flags, LEN semantics, CRC-8 (0x07/0x02/0x02), no escaping, own flags per frame | Valid LEN range 5–64 | – |
| Cipher | Per-frame key byte; fold ⇔ key-stream identity; key stream with four corrections (§3.3), shared with the Sundance 780 and another encrypted Jacuzzi; CC `[K, K^0xE0^code]` | – | Key stream at bytes not yet tied to a known field |
| Status C4 | Hour, minute, day of week, day, month, year, water temp, setpoint, heater, pump 1 running + speed, pump 2, set mode, set screen, cadence, filter / water / UV countdowns (bytes 6, 24, 27) | heat-demand sequence; pump-1 flag in byte 29 | Manual circ; d10.7; d4, d6; heat mode and filter cycle settings; secondary value byte 28 |
| Lights CA | brightness, mode codes, R/G/B positions, ≈ 1 Hz | c9 blend phase | c0, c3, c5, c7, c10–13 |
| Commands | 0x00 idle, 0x01/0x02 temp, 0x04 pump 1, 0x05 pump 2, 0x12 light; press semantics; set-mode first press | – | ClearRay 0x0F, 0x11, menu 0x1E on J235 |
| Bus | Channel 0x10 = topside; CTS ≈ 45 Hz, CC on every CTS; 0x00 ≈ 1 Hz; C4 ≈ 3.3 Hz | CTS-slot rule | Channel request/ack exchange on J235; CTS deadline; 0x04/0x05 semantics |
| Physical | EW11A transparent bridging | 115200 8N1 | – |

**Still open after D8:** the filter cycle settings and heat mode (need a capture while they
are changed at the topside), manual circulation and the J235 channel-request handshake. The
FC, H2O and UV countdowns are resolved (bytes 6, 24, 27). In the fold (§5) they sit in d3, d12
and d13: SC's names for d3 and d12 ("water life", "filter life") are swapped, and the "display
state" in d13 is mostly the UV countdown.
The handshake can only be observed by transmitting, which is out of scope for development.
`tools/capture.py` produces the capture format; drop files into `tests/fixtures/captures/raw/`
and the replay tests pick them up.

## 10. Home Assistant identities in use today

Read from the HA entity registry on 2026-11-04 (all `platform: mqtt`, one device
`Jacuzzi J235`, identifiers `185569045`):

| entity_id | unique_id | Decoded from (this document) |
|---|---|---|
| `sensor.jacuzzi_j235_current_water_temperature` | `current_temperature` | d5 |
| `sensor.jacuzzi_j235_target_water_temperature` | `setpoint_temperature` | d8 |
| `binary_sensor.jacuzzi_j235_circulation_pump_status` | `circulation_pump_status` | d1 bit 6 = pump 1 running, any speed (Confirmed) |
| `binary_sensor.jacuzzi_j235_main_pump_status` | `main_pump_status` | d2 bit 4 = pump 1 on **high** (Confirmed) |
| `binary_sensor.jacuzzi_j235_secondary_pump_status` | `secondary_pump_status` | d1 bit 2 = pump 2 (Confirmed) |
| `binary_sensor.jacuzzi_j235_manual_circulation_call` | `manual_circulation_call` | d1 bit 7 (Hypothesis) |
| `binary_sensor.jacuzzi_j235_heater_active` | `heater_active` | d10 bit 6 (Confirmed) |
| `button.jacuzzi_j235_temperature_increment` | `temperature_increment` | CC code 0x01 |
| `button.jacuzzi_j235_temperature_decrement` | `temperature_decrement` | CC code 0x02 |
| `button.jacuzzi_j235_pump_1_button` | `pump_1_button` | CC code 0x04 |
| `button.jacuzzi_j235_pump_2_button` | `pump_2_button` | CC code 0x05 |
| `number.jacuzzi_j235_temperature_set_control` | `temperature_set_control` | setpoint loop over 0x01/0x02 |

`manual_circulation_call` and `heater_active` exist in HA but in no git ref of this repo. They
came from an unpublished local definition. Their bit positions above are taken from the
legacy `dev/debug_parser.py` field map (`Man Circ` d1 bit 7, `Heater?` d10 bit 6) and from the
evidence in §5.
