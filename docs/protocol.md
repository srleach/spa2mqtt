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

The decoded CSVs (D2–D6) contain the 16-byte pairwise-folded payload only: no headers, no
other message types, no timestamps per row. That limits what they can prove (see §9).

### Code and documentation

| Key | Repository @ commit | Notes |
|---|---|---|
| **S2M** | `srleach/spa2mqtt` @ `b0a5323` (legacy, tag/branch `legacy/pre-rewrite`) | Legacy implementation and J235 definition. Unmerged branches PR 16–20 (`b157d26`, `ebec593`, `fbf5cb5`, `b26e0ea`, `1f7ebbb`) also reviewed. |
| **SC** | `srleach/SpaControl` @ `ec631d8` | `pybalboa/sundanceRS485.py`: a modified copy of HyperActiveJ's decoder (older than HJ). |
| **HJ** | `HyperActiveJ/sundance780-jacuzzi-balboa-rs485-tcp` @ `fc38ab5` | Sundance 780 decoder plus `DECODING.md`. GitHub now redirects this repo to `pete-jorgensen/SundanceHotTub2MQTT` (same HEAD). History was rewritten to a single commit. |
| **PJ** | `dhmsjs/pyjacuzzi` @ `f9d6022` (fork `srleach/pyjacuzzi` @ `65f4891`) | Jacuzzi library with Prolink decompilation notes. Upstream has one protocol commit newer than the fork: `39c2834` (2026-11-03, temperature-scale ordering in the 0x16 parser). Line numbers are for the fork unless marked "up". |
| **JB** | `jackbrown1993/Jacuzzi-RS485` @ `96f3172` | Plain (0x16) Jacuzzi decoder derived from HJ/PJ. |
| **IR** | `Iraithium/sundance-rs485-controller` @ `f444c9b` | ESPHome external component for Sundance (encrypted) boards: prior art for on-device work. |
| **AL** | `al1505/ALs-HA-SundanceMarin` @ `8bb04fb` | Sundance Marin 780 HA integration (CRC note only). |
| **HA** | Home Assistant entity registry, read 2026-11-04 | Current entity set and `unique_id`s (§10). |

---

## 1. Physical layer

| Claim | Status | Evidence |
|---|---|---|
| Two-wire RS485, half duplex, shared by the board, topside panel(s) and add-on modules. | Confirmed | Legacy README wiring "12v +/, A/B" (S2M `README.md`); bus has several channels (§4). |
| **115200 baud, 8N1.** | Inferred | IR `README.md` L197 ("115200 8N1, required by the bus", Sundance). The J235 has been read through an EW11A RS485–WiFi bridge (port 8899, S2M `config.yml.example`); its serial settings are not recorded in this repo. Confirm from the EW11A web UI. |
| An EW11A in transparent TCP mode passes bytes unmodified (no escaping). | Confirmed | D1 frames have valid CRCs and lengths [A:crc]. |

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
| Observed lengths: C4 `LEN=0x26` (40-byte frame, 33-byte payload); CC `LEN=0x07` (2-byte payload). | Confirmed (C4), Inferred (CC) | D1; CC from SC L238 example `7E 07 10 BF CC 65 85 A6 7E` (CRC valid [A:crc] style check, done in research notes). |
| Receivers should reject `LEN < 5` or `LEN > 64`. | Inferred (design choice) | IR accepts 5–64; S2M legacy accepted ≤128; the longest known frame is 0x26. |

## 3. Message types and the "encryption"

### 3.1 Type table

| TYPE | ADDR | MID | Direction | Meaning | Status | Evidence |
|---|---|---|---|---|---|---|
| 0xC4 | 0xFF | 0xAF | board → all | Status (encrypted) | Confirmed | D1 (all frames `FF AF C4`) |
| 0xCA | 0xFF | 0xAF | board → all | Lights status (encrypted) | Hypothesis on J235 | SC L27, L563–589; HJ; PJ L1554. Not in any J235 dump. |
| 0xCC | client | 0xBF | client → board | Button press (encrypted) | Inferred | SC L224–255 (sends), L749–770 (observes); PJ L311–317. No J235 CC frame captured. |
| 0x00 | 0xFE | 0xBF | board → all | "Any new clients?" (new-client CTS) | Hypothesis | SC L16, L687–701; IR; ccutrer-derived docs. |
| 0x01 | 0xFE | 0xBF | client → board | Channel assignment request, body `02 F1 73` | Hypothesis | SC L688–701 (`F1 73` "random magic"). |
| 0x02 | 0xFE? | 0xBF | board → client | Channel assignment response; channel in `payload[0]` | Hypothesis | SC L703–705. |
| 0x03 | channel | 0xBF | client → board | Channel assignment ack (empty body) | Hypothesis | SC L705–715. |
| 0x04 / 0x05 | channel | 0xBF | board ↔ client | Existing-client request / response (body `04 08 00`, meaning unknown) | Hypothesis | SC L716–730. Note SC/HJ/JB build this frame with an off-by-one (`bytearray(9)` then write index 9), so this path has probably never run successfully. |
| 0x06 | channel | 0xBF | board → client | Clear to send for that channel | Inferred | SC L731–748 (HJ sent successfully on CTS for Sundance and J-series per its README history). |
| 0x07 | channel | 0xBF | client → board | Nothing to send | Hypothesis | SC L23, L642–648 (built, never sent: L743 commented out). |
| 0x16 / 0x17 / 0x23 | | | | **Unencrypted** Jacuzzi status / button / lights. **Not used by the J235.** | Confirmed (not J235) | No such frames in D1; PJ L1617–1665 and HJ `DECODING.md` L275–303 treat these as plaintext on non-encrypted boards. The legacy S2M and SC route 0x16/0x23 through the XOR decoder, which is wrong (HJ upstream removed it for that reason). |

The address and MID semantics follow the Balboa convention: `MID=0xAF` is a board broadcast,
`0xBF` is client traffic, `ADDR=0xFE` is "unassigned client" and `0xFF` is broadcast
(Inferred: SC constants; PJ `docs/ProlinkMessageTypes.txt` L28). The Prolink module uses
fixed `ADDR=0x0A` (PJ L198–202). Sundance/J-series panels have been seen on 0x10 and 0x11
(SC L238 example; HJ `DECODING.md` L366).

### 3.2 Encryption of C4 (status)

Two published models exist. **They are algebraically the same cipher.** This repo proves it
on D1 and uses the pairwise fold as the canonical decode because it is key-independent and
because it gives the right calendar day where the per-byte model does not.

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

### 3.3 Encryption of CC (button command)

`payload = [K, K ^ 0xE0 ^ code]`, i.e. **button code = payload[0] ^ payload[1] ^ 0xE0**.
(Inferred.)

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
| 0x00 | 224 | none / idle (sent by panels on every CTS) | Inferred |
| 0x01 | 225 | Temp up | Inferred (used by legacy S2M; PJ: "pump 1 & setpoint change known to work") |
| 0x02 | 226 | Temp down | Inferred |
| 0x04 | 228 | Pump 1 | Inferred (PJ readme L28–30) |
| 0x05 | 229 | Pump 2 | Inferred |
| 0x0F | 239 | ClearRay (UV) / circulation | Hypothesis (HJ, JB). PJ docs say 0x0E (internally inconsistent). |
| 0x11 | 241 | Light on/off | Hypothesis |
| 0x12 | 242 | Light colour | Hypothesis |
| 0x1E | 254 | Menu | Hypothesis (defined in HJ, never sent; HJ warns against brute-forcing codes) |

The J235 has no direct "set temperature" command on the encrypted bus. Setpoint changes are made
by pressing Temp up/down and watching the reported setpoint (§7). (Inferred: SC
L209, L259, L405–415; PJ L399–458 "no command to set an arbitrary value".)

### 3.4 Lights (CA)

The CA layout is decoded with the same fold (14 bytes). HJ assigns brightness=f1, blue=f2,
mode=f4, green=f6, red=f8, cycle=f9; PJ (Model A) gives P6/P10/P13/P18/P22/P24. These agree
under the identity apart from brightness. **No CA frame exists in any J235 dump. Status: Hypothesis.**
The J235 entity set does not use lights.

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
| "Dormant channel" reuse: after 5 CC observations, take the lowest polled channel that never sends CC. | Hypothesis (works on Sundance per HJ; untested on J235) | SC L46–48, L749–760; IR uses 5 CTS frames. |
| Channel request `7E 08 FE BF 01 02 F1 73 cs 7E` sent in response to 0x00. | Hypothesis | SC L687–701. |
| After CTS the client should answer immediately; no deadline is documented. HJ over TCP (EW11A) worked, so the window is at least tens of ms. | Inferred | SC L742–748; HJ sets TCP_NODELAY (SC L193). IR waits 50 µs for DE/RE turnaround. |
| An idle client may stay silent on CTS. HJ never sends NTS (0x07). | Inferred | SC L743 commented out. |
| The legacy S2M bridge **claims a channel and may send 0x01/0x03 automatically at start-up**, even if no button is pressed. | Confirmed (code) | S2M `spas/jacuzzi_encrypted/spa/jacuzzi_encrypted_spa.py` L51–88, L1182–1188. The rewrite does not do this (design.md §Safety). |

## 5. C4 status field map (J235)

Index = folded byte `d[j]` (Model B). The equivalent Model A bytes are `P[5+2j]` and `P[6+2j]`.
"Bit n" counts from LSB 0. Scale 0.5 assumes °C, the only mode ever observed on this tub (§8).

| d | Field | Transform | Status | Evidence |
|---|---|---|---|---|
| 0 | Hour (24 h) | `d0 ^ 0x06` | **Confirmed** | [A:clock]: D3 13:01 vs wall 12:58Z; D4 13:12 vs 13:09Z; D5 13:11 vs 13:08Z; D6 13:13 vs 13:10Z (tub clock is on GMT, not BST, and ~3 min fast). D2 rows run 17:46→21:31 monotonically [A:timeline]. |
| 1 | bit 7: manual circulation call | `(d1>>7)&1` | Hypothesis | SC L341 `MANUAL_CIRC = 7`; HJ upstream keeps f1.b7 "manual/ClearRay". Never set in any J235 dump. |
| 1 | bit 6: circulation pump running | `(d1>>6)&1` | Inferred | Set in D2 rows 1–277 (heating window, with d10.b6/b7) and clear at idle [A:timeline]; SC L356. HJ upstream moved "circ running" to f4.b6, but on J235 d4 is constant 0x05 even while d1.b6 is set (D2), so f4.b6 does not apply here. |
| 1 | bit 5 | – | Unknown | Set together with bit 6 in D2 rows 1–277. HJ upstream calls f1.b5/b6 "diagnostics that lag circulation". |
| 1 | bits 3–2: pump 2 | `(d1>>2)&1` (legacy); PJ: 2-bit level | Hypothesis | SC L339/L355 `PUMP_2_BIT_SHIFT = 2`; PJ `P[8]` bits 3:2. **Never set in any J235 dump** (no jets were used during capture). |
| 2 | bits 2–0: day of week (0 = Sunday) | `d2 & 7` | Inferred | [A:clock]: 18 May 2025 (Sun) → 0, 19 May (Mon) → 1, 20 May (Tue) → 2; D1 (16 May, Fri) → 5. Third-party samples disagree by one day (HJ, PJ sample frames), so J235-only. |
| 2 | bit 3 | – | Unknown | Set only in D2 rows 1–277 (heating window). |
| 2 | bits 5–4: pump 1 | `(d2>>4)&1` (legacy); PJ: 2-bit level off/low/high | Hypothesis | SC L354 (`pump0 = d2 bit 4`); PJ `P[10]` bits 5:4. Never set in any J235 dump. |
| 2 | bit 5 (menu) | – | Unknown | Set in D4 rows 122–124, 138–140, 154–159 while a menu value is being edited (d13 = 112). Conflicts with "pump 1 bits 5–4". |
| 3 | Menu-editable maintenance value | raw | Unknown | D4: changed 130 → 120 → 118 → 90 as the user edited values in the menu [A:timeline]. D2 118, D3 111, D5/D6 101. SC names d3 "water life remaining days"; the legacy definition (commented out) tried `xor 14`. Neither explains D4. |
| 4 | constant 0x05 | – | Unknown | 0x05 in every J235 row [A:profile]. |
| 5 | Water temperature | `(d5 ^ 0x02) × 0.5` °C | **Confirmed** (value); transform has a caveat | D2 heating window: 37.5 → 38.0 → 38.5 around a 38.0 setpoint, heater bit clearing at setpoint. Without the XOR the reading would jump 36.5 → 39.0 in 10 minutes, which is physically implausible. Model A `P[15] = 76` (38.0) in D1. Caveat: `^2` is really `^P[16]`, constant 0x02 in all samples. The unmerged PR 17/19 removed the XOR; this is refuted. |
| 6 | constant 0x20 | – | Hypothesis: heat mode | HJ `DECODING.md`: 32 = AUTO (34 ECO, 36 DAY). 0x20 in every J235 row. |
| 7 | Day of month | `d7 >> 3` | **Confirmed** | [A:clock]: 18, 19, 19, 20, 20 on the matching dates; D1 → 16 (commit date). HJ upstream: stepped 17→18→19 across midnights. |
| 7 | Month (1–7 only?) | `d7 & 7` | Inferred, incomplete | 5 on every May capture. HJ saw 1 while its tub believed it was 19 January. Three bits cannot hold months 8–12. **Open question (§9).** |
| 8 | Setpoint | `d8 × 0.5` °C | Inferred | 76 → 38.0 in every row (D1–D6); matches the HA number entity range (20–40, step 0.5). No setpoint change has been captured. |
| 9 | Year − 2000 | raw | Inferred | 25 in every 2025 J235 row; PJ sample frame → 22, HJ sample → 23. Model A `P[24]` (PJ L1163). |
| 10 | bit 6: heater on | `(d10>>6)&1` | **Inferred (strong)** | D2 rows 1–51: set while water < setpoint (37.5); clears when 38.0 is reached [A:timeline]. SC L327 "= 64 when Heat on"; PJ `P[26]` bit 6. |
| 10 | bit 7 | – | Hypothesis: auto circulation / heater run-on | D2 rows 47–277: set after the heater bit clears and while d1.b6 stays set; clears when circulation stops. HJ upstream: f10.b7 = AUTO circulation. The unmerged PR 17 read d10 as "pump status 64/128/192"; that interpretation contradicts the heater evidence above. |
| 11 | Minute | raw | **Confirmed** | [A:clock] against filename epochs (consistent +3 min tub offset). |
| 12 | – | raw | Unknown | 175 (18 May), 179 (19 May), 178 (20 May). SC names it "filter life remaining days". |
| 13 | Display / menu state | raw | Inferred (it is display state); value meaning Unknown | D4: 99 idle → 100/109/114 entering the menu → 113/112 while editing → back to 99 [A:timeline]. Idle value differs by day: 90, 99, 98. HJ upstream: bit 7 = alert showing, low bits = alert day count (Sundance). |
| 14 | Secondary temperature? | HJ: `(d14 & 0x7F)`, +32 while circulating | Hypothesis | D2: 3–4 while circulating (35–36 with +32), 27 → 22 over an evening with pumps off, 34–35 the next midday. Plausibly a second sensor in whole °C. PR 17 used d14 as "hour"; this is refuted (values 24–27 at 20:00–21:00). The SC README claim that `d14 & 1` = °C flag is refuted (alternates 24/25 with no unit change). |
| 15 | Menu value being edited | raw | Inferred | 0 except in D4 rows 109–159 (values 120…160 while d13 = 112/113). |
| (P37) | 33rd payload byte | – | Unknown | Never decoded by Model B; 0x00 in D1 (Model A). |

## 6. Commands (transmit path)

| Claim | Status | Evidence |
|---|---|---|
| Frame: `7E 07 <chan> BF CC <K> <K^0xE0^code> <crc> 7E`. | Inferred | §3.3. |
| One frame = one press. Pump buttons cycle off → low → high → off (2-speed pump 1) or off → on → off. | Inferred | PJ L663–700 (plain boards); legacy S2M exposes raw "pump button" presses for this reason. |
| Send only in the CTS slot for the client's own channel. | Inferred | §4. |
| There is no acknowledgement. Success is observed only through the next status frames. HJ retries after 2 status frames without change; IR retries after 5, up to 8 attempts. | Inferred | SC L50, L405–430 `CHECKS_BEFORE_RETRY = 2`; IR `sundance_spa.h`. |

## 7. Timing

| Claim | Status | Evidence |
|---|---|---|
| C4 status is broadcast ≈ 3.3 times per second (200 frames per full minute). | Inferred (assumes the logger captured every frame) | D2: every interior minute in rows 2020–8740 holds exactly 200 rows (`analyze_captures.py profile/timeline`; per-minute count in research notes). |
| C4 repeats unchanged between state changes; consumers must de-duplicate. | Confirmed | D2 runs of up to 2 313 identical rows [A:timeline]. |
| No status for > 10 s means the link is down (Prolink rule). | Inferred | PJ `docs/ProlinkMessageParsing.txt` L1439–1453. |
| The setpoint loop should allow ≥ 2 status frames (≈ 0.6 s) between presses and give up after a bounded number of attempts. | Inferred (design) | HJ/IR retry constants; PJ waits 1 s between presses. |
| Topside behaviour: one Temp up/down press changes the setpoint by 0.5 °C. A first press may only wake the display. | Hypothesis | Legacy S2M assumes `(target − current)/0.5` presses; not yet captured. |

## 8. Units

The J235 in D1–D6 reports in °C ×2. Every value is consistent with that: setpoint 76 → 38.0 °C,
water 37.5–38.5 °C. (Confirmed for this tub.) No known field on encrypted boards gives the
unit flag: PJ upstream `39c2834` explicitly leaves it undetermined for C4. Unit is therefore a
**configuration value** in the tub definition, not a decoded field.

## 9. Known / inferred / unknown summary

| Area | Known (Confirmed) | Inferred | Unknown / Hypothesis |
|---|---|---|---|
| Framing | 0x7E flags, LEN semantics, CRC-8 (0x07/0x02/0x02), no escaping | Valid LEN range 5–64 | – |
| Cipher | Per-frame key byte; fold ⇔ key-stream identity; fold gives correct clock/date | CC encoding `[K, K^0xE0^code]` | True field boundaries (Model A vs B); the P16/P28 "constants" |
| Status C4 | Hour, minute, day, water temp, cadence and de-dup | Setpoint, heater bit, circ bit, year, day-of-week, display/menu state, menu edit value | Month for Aug–Dec; pump 1/pump 2 bits; manual circ; d3, d4, d6, d12, d14, P37 |
| Lights CA | – | – | Whole layout on J235 |
| Commands | – | Temp ±, Pump 1/2 codes; press-per-frame semantics | ClearRay, light, menu codes on J235 |
| Bus | – | CTS slot rule; idle silence is OK | Channel request/ack exchange on J235; CTS deadline; 0x04/0x05 semantics |
| Physical | – | 115200 8N1 | – |

**What would settle most of the open questions:** a raw capture (all message types) with a
labelled sequence of topside actions: pump 1 low/high/off, pump 2, temp up/down, light, menu
reminder values. A capture taken in a month ≥ 8 (e.g. November) settles the month question.
`tools/capture.py` produces exactly this format; drop the file into
`tests/fixtures/captures/raw/` and the replay tests pick it up.

## 10. Home Assistant identities in use today

Read from the HA entity registry on 2026-11-04 (all `platform: mqtt`, one device
`Jacuzzi J235`, identifiers `185569045`):

| entity_id | unique_id | Decoded from (this document) |
|---|---|---|
| `sensor.jacuzzi_j235_current_water_temperature` | `current_temperature` | d5 |
| `sensor.jacuzzi_j235_target_water_temperature` | `setpoint_temperature` | d8 |
| `binary_sensor.jacuzzi_j235_circulation_pump_status` | `circulation_pump_status` | d1 bit 6 |
| `binary_sensor.jacuzzi_j235_main_pump_status` | `main_pump_status` | d2 bit 4 (Hypothesis) |
| `binary_sensor.jacuzzi_j235_secondary_pump_status` | `secondary_pump_status` | d1 bit 2 (Hypothesis) |
| `binary_sensor.jacuzzi_j235_manual_circulation_call` | `manual_circulation_call` | d1 bit 7 (Hypothesis) |
| `binary_sensor.jacuzzi_j235_heater_active` | `heater_active` | d10 bit 6 |
| `button.jacuzzi_j235_temperature_increment` | `temperature_increment` | CC code 0x01 |
| `button.jacuzzi_j235_temperature_decrement` | `temperature_decrement` | CC code 0x02 |
| `button.jacuzzi_j235_pump_1_button` | `pump_1_button` | CC code 0x04 |
| `button.jacuzzi_j235_pump_2_button` | `pump_2_button` | CC code 0x05 |
| `number.jacuzzi_j235_temperature_set_control` | `temperature_set_control` | setpoint loop over 0x01/0x02 |

`manual_circulation_call` and `heater_active` exist in HA but in no git ref of this repo. They
came from an unpublished local definition. Their bit positions above are taken from the
legacy `dev/debug_parser.py` field map (`Man Circ` d1 bit 7, `Heater?` d10 bit 6) and from the
evidence in §5.
