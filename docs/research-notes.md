# Research notes

Companion to [`protocol.md`](protocol.md). This file records **where the information came
from, where sources conflict and how each conflict was resolved, and what is still open**.
The protocol facts themselves live in `protocol.md`.

## Sources reviewed

| Source | What it contributed | Reliability notes |
|---|---|---|
| `srleach/spa2mqtt` @ `b0a5323` (legacy) | Working J235 decode (pairwise fold), button codes, HA entity definitions, channel-claim logic | Field offsets copied from HJ; some (pumps) never verified on J235. Debug CSVs are the main J235 evidence. |
| spa2mqtt history | Four decoded captures deleted in `d185ab1`; earlier versions of `debug_messages.csv` (`cf05bf5`, `302f691`, `d99bf10`) | Recovered into `tests/fixtures/captures/decoded/`. |
| spa2mqtt unmerged PRs 16–20 (April 2026) | Protocol abstraction attempt, capture mode, "discovered fields" | PR 17/19 field claims (temp without XOR, d10 = pump map, d14 = hour) are **refuted by the dumps** (protocol.md §5). Capture-mode idea kept (as `tools/capture.py`). |
| `srleach/SpaControl` @ `ec631d8` | Copy of HyperActiveJ's `sundanceRS485.py` with local edits (named maintenance fields, tempscale experiment) | Older than current HJ upstream. Still routes unencrypted 0x16/0x23 through the XOR decoder. |
| `srleach/pyjacuzzi` @ `65f4891` / upstream `dhmsjs/pyjacuzzi` @ `f9d6022` | Key-stream decrypt model; Prolink decompilation; unencrypted Jacuzzi field maps; command and timing notes | Encrypted support was written without a board to test on (readme 12/8/23). Upstream `39c2834` (2026-11-03) changes only temperature-scale handling for 0x16. |
| `HyperActiveJ/sundance780-jacuzzi-balboa-rs485-tcp` @ `fc38ab5` (now `pete-jorgensen/SundanceHotTub2MQTT`) | Upstream decoder and a detailed `DECODING.md`; removed Jacuzzi 0x16 handling; f13 alert encoding; temp2 rework | History rewritten into a single commit, so intermediate changes are not attributable. The repo linked from the legacy README, `HyperActiveJ/SundanceJacuzzi_HomeAssistant_TCP_RS485`, returns 404. |
| Issue #1 on the HJ repo ("Add suport for jacuzzi 335") | J-series 0x17 frame examples; byte-14 flow observation | Only a paraphrase was available to the review. Not relied on for any Confirmed claim. |
| `jackbrown1993/Jacuzzi-RS485` @ `96f3172` | Unencrypted 0x16/0x17 decode; plain button codes | Unencrypted boards only. |
| `Iraithium/sundance-rs485-controller` @ `f444c9b` | Existing ESPHome external component for Sundance (encrypted) boards: frame sizes 5–64, 115200 8N1, DE/RE timing, retry limits | Uses HJ's older field map. Good prior art for on-device feasibility. No code copied. |
| `al1505/ALs-HA-SundanceMarin` @ `8bb04fb` | CRC variant claim (equivalent), 500 ms command spacing | Non-encrypted Sundance. |
| Not relevant | `dewbot6/esphome-jacuzzi-j300` (different, non-Balboa panel bus); `ezeek/jacuzzi-mqtt-bridge` (copy of PJ) | – |
| **Owner raw capture D7** (2026-11-04, `tools/capture.py`, receive-only, labelled) | 51 242 frames of every message type with 37 action labels. Settles the pump bits, button codes, set-mode behaviour, lights layout, heating sequence, bus population and cadence | Highest-value evidence. Labels are typed shortly after each action. |
| Home Assistant (read-only, 2026-11-04) | Entity registry (unique_ids), device record, ESPHome device configs | Two entities (`heater_active`, `manual_circulation_call`) exist in HA but not in git. |

## Conflicts and resolutions

| # | Conflict | Resolution | Evidence |
|---|---|---|---|
| 1 | **Cipher model.** HJ folds pairs (`b[2j]^b[2j+1]^1`) with ad-hoc XORs; PJ uses key byte plus a mod-64 key stream. | Proven algebraically identical. HJ fields are XORs of adjacent PJ bytes. The fold is the canonical decode: it is key-independent, and on J235 it gives the correct calendar day while PJ's per-byte day does not. | `analyze_captures.py cipher`; protocol.md §3.2 |
| 2 | **Water temperature XOR.** Legacy definition: `xor 0x02`. PR 17/19: no XOR. | XOR 0x02 kept. Without it the D2 heating curve jumps 2.5 °C in 10 min, and heating would stop 1 °C above the setpoint. | D2 rows 1–277 |
| 3 | **Byte d10.** Legacy debug map: heater bit 6. PR 17: "pump status 0/64/128/192". | Bit 6 = heater (set only below setpoint). Bit 7 = unknown, probably auto circulation (HJ upstream). | D2 timeline |
| 4 | **Byte d14.** PR 17: hour. SC README: bit 0 = °C flag. HJ: secondary temperature. | Hour and °C flag refuted. Secondary temperature kept as a hypothesis. | D2: values 22–27 at 20–21 h; bit 0 toggles without a unit change |
| 5 | **Circulation bit.** SC: d1 bit 6. HJ upstream: d4 bit 6. | d1 bit 6 for J235 (d4 is constant 0x05 on J235 even while circulating). | D2 |
| 6 | **Month.** HJ upstream: `f7&7` "cannot be right" (read 1 in August). | Resolved: `d7 = (day << 3) XOR month` (4-bit month). It fits May (D1–D6), HJ's "January 19" and D7's 4 November (0x2B). For months 8–12, day bit 0 and month bit 3 collide in the fold, so the fold alone cannot decode dates then. | HJ `DECODING.md` §3.3; D2–D7 |
| 7 | **Day of week.** PJ: Model A `P[20] & 7` ("not sure"). | Plaintext byte 5 bits 2–0 (Sunday = 0), equal to folded `d2 & 7`. Right on five dated J235 captures and on all three foreign frames. (An earlier version said the foreign frames were off by one; that was the fold's wrong year, not the weekday.) | `analyze_captures.py clock`, `decrypt` |
| 8 | **Is 0x16 encrypted?** Legacy S2M and SC route 0x16/0x23 to the XOR decoder. | No. 0x16/0x17/0x23 are the plaintext Jacuzzi protocol; the J235 does not use them. The rewrite does not decode them as encrypted. | PJ L1617–1665; HJ upstream removal |
| 9 | **ClearRay code.** PJ docs 0x0E; HJ/JB 0x0F. | 0x0F (two independent sources; PJ text is internally inconsistent). Not exposed until confirmed on J235. | protocol.md §3.3 |
| 10 | **Status cadence.** "About every minute" (issue paraphrase) vs "very high rate" (PJ). | ≈ 3.3 Hz on J235. | D7: 1 804 C4 in 541 s; D2: 200 rows per full minute |
| 12 | **Pump bits.** Legacy definition: main pump = d2 bit 4, secondary = d1 bit 2, circulation = d1 bit 6. PJ: pump 1 is 2 bits. | All three legacy bits are right, but their meaning is narrower: d1.6 = pump 1 running (any speed); d2 bits 4–3 = pump 1 speed (bit 4 = high); d1.2 = pump 2. | D7 t≈90–196 |
| 13 | **Light codes.** HJ: 0xF1 light on, 0xF2 colour. | The J235 topside has one light button that sends 0x12 (HJ 0xF2) and steps through the modes. 0x11 is never sent. | D7 t≈294–414 |
| 14 | **First temp press.** Legacy: N presses for N half-degrees. | The first press only enters set mode (d2 bit 5, d13 0x98). The legacy controller was always one press short. | D7 t≈210, 238 |
| 16 | **Fold vs per byte.** spa2mqtt 2.0 and HJ decode with the fold; HJ `DECODING.md` §3.8 asks whether the first byte of each pair is a key, a nonce or a second data channel. | Answered with raw captures: `payload[0]` is a per-frame nonce, and after removing it both bytes of a pair can carry data. Decoding now removes the nonce and a key stream (pyjacuzzi's formula with four corrections) and reads plaintext per byte. It fixes the August–December date and the year on foreign frames, and it is shared with the Sundance 780. | protocol.md §3.3; `analyze_captures.py decrypt` |
| 15 | **Dormant channel reuse.** HJ/IR rely on it. | Not possible on this install: the only polled channel (0x10, the topside) answers every CTS. A client must use the 0x00/0x01 request. | D7 census |
| 11 | **`decoding.md` decoded values.** The doc's "post-decoding" lines all show minute 0x26. | The first 18 frames actually decode to minute 0x23; the doc copy-pasted the decode. Fixture keeps the raw frames, not the doc's decode. | `analyze_captures.py cipher` |

## Bugs found in prior code (for the record)

* Legacy S2M `Communicator.establish_transport` calls `logger.error("…", str(e))` with a stray
  argument. `Spa.send_buffer`/`channels_seen` are class-level mutable defaults shared across
  instances. `queue_button_command(send_immediately=True)` *queues* and `False` *sends now*
  (inverted). `MQTTControl` dictionaries are class attributes.
* Legacy S2M auto-claims a channel and may transmit 0x01/0x03 at start-up with no user action.
* SC/HJ/JB existing-client response writes `data[9]` into a 9-byte buffer (IndexError).

## Open questions

Resolved by D7: pump bits and speeds, button codes, the lights layout, the panel channel,
cadence, and the month encoding (explained, but not decodable for months 8–12 from the fold).

1. ~~Day/month for August–December~~: resolved by per-byte decryption (protocol.md §3.3).
2. Manual circulation (d1 bit 7) and the meaning of d1 bit 5 (heat demand?) and d10 bit 7.
3. d3 / d12 and the d13 code space: maintenance counters and display codes. Needs the reminder
   values read from the topside menu during a capture.
4. d14 underlying value (the pump-1 flag is understood).
5. Channel assignment on J235 (0x00/0x01/0x02/0x03). Can only be tested by transmitting,
   which is out of scope for development. The code path exists but is disabled by default.
6. EW11A serial settings (expected 115200 8N1).
7. ~~Whether Model A or Model B reflects the real plaintext layout~~: per byte, with a corrected
   key stream (protocol.md §3.3). Still open: the key stream at bytes not yet tied to a known field.
8. The meaning of plaintext bytes 27 (display or alert code) and 28 (secondary value).

## The plain-protocol tub (Jacuzzi J345, November 2026)

The facts are in [`protocol-plain.md`](protocol-plain.md). This section records how they
were settled.

**Model name.** The first outside definition (May 2025) and discussion 13 call the tub a
"J335". That wording is srleach's, written before the owner's first reply. The owner wrote
"J345" twice: "My tub is Jacuzzi J345 that's not encrypted using the original ProLink
adapter" (discussion 6, 18 May 2025) and "unencrypted J345 (my tub)" (discussion 13,
10 December 2025). The definition is `jacuzzi_j345`. The legacy name
`jacuzzi_j335_unencrypted_farenheit` is kept as an alias, because the owner's stack sets it.

**Evidence base.** Five logs from the owner (keys S, D, X1–X3 in `protocol-plain.md` §0).
S is the important one: a pyjacuzzi session with 26 sent commands and the tub's reaction
to each. D and X1–X3 are receive-only logs of topside actions. The pre-rewrite definition
was not used: it read 0xC4 offsets and XOR constants on a board that sends 0x16 plaintext.

| # | Conflict or question | Resolution | Evidence |
|---|---|---|---|
| P1 | **Indexing.** PJ and JB index the whole frame; the definition indexes the payload. | PJ `data[n]` is payload byte `n − 5`. Every PJ line cited in the definition was re-read with that offset. | PJ `jacuzzi.py` L857–868 against S L5 |
| P2 | **Heater.** PJ reads heat state from `p[5]` bits 5–4; they are always 0 on this tub. | The only heater candidate is `p[11]` bit 0, which follows the thermostat in three captures. Status: hypothesis. PJ L965 labels those bits "isUVOn". | D L143; X3 L1299; S L11, L14 |
| P3 | **How to get a turn to send.** JB waits for a CTS on its channel; PJ just writes. | The ProLink stream has no CTS at all, and PJ's 26 writes all worked. The bridge uses a direct mode with spacing. The owner had reported that JB's project could read but not control. | D, X1–X3 census; S; JB `jacuzziRS485.py` L200–205 |
| P4 | **Setpoint path.** The J235 steps with temp up/down presses. | Those button codes (0x01, 0x02) were never seen on this tub. The direct set-temperature frame (0x20) was, three times. The definition has no temp buttons. | S L8–L14 |
| P5 | **Which light record.** PJ's command writes four records; the topside writes one. | Decode record 0, the one both change. Records 1–3 are undecoded. | X2, X3; S L27 |

**Reference drift.** JB's head is now `1840e3c` (7 November 2026); `protocol.md` cites
`96f3172`. HJ's repository is at `9a1df08` and has withdrawn its plain 0x16 support
(`DECODING.md` §3.9). PJ is unchanged at `f9d6022`, whose parent is the `39c2834` commit
that `protocol.md` mentions.

**Open.** The list is `protocol-plain.md` §8. The first three would be settled by the
owner's first receive-only run and first transmit test: whether the connection check is
needed, whether the decoded temperatures match the topside, and whether the heater bit is
the heater.

## Raw-capture request (sent to the owner)

A receive-only capture using `tools/capture.py`, with labelled topside actions. The result is D7
(`tests/fixtures/captures/raw/2026-11-04T220754Z_j235_labelled.log`). A follow-up capture
reading the maintenance reminder values from the menu would close question 3.
