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
| Home Assistant (read-only, 2026-11-04) | Entity registry (unique_ids), device record, ESPHome device configs | Two entities (`heater_active`, `manual_circulation_call`) exist in HA but not in git. |

## Conflicts and resolutions

| # | Conflict | Resolution | Evidence |
|---|---|---|---|
| 1 | **Cipher model.** HJ folds pairs (`b[2j]^b[2j+1]^1`) with ad-hoc XORs; PJ uses key byte plus a mod-64 key stream. | Proven algebraically identical. HJ fields are XORs of adjacent PJ bytes. The fold is the canonical decode: it is key-independent, and on J235 it gives the correct calendar day while PJ's per-byte day does not. | `analyze_captures.py cipher`; protocol.md §3.2 |
| 2 | **Water temperature XOR.** Legacy definition: `xor 0x02`. PR 17/19: no XOR. | XOR 0x02 kept. Without it the D2 heating curve jumps 2.5 °C in 10 min, and heating would stop 1 °C above the setpoint. | D2 rows 1–277 |
| 3 | **Byte d10.** Legacy debug map: heater bit 6. PR 17: "pump status 0/64/128/192". | Bit 6 = heater (set only below setpoint). Bit 7 = unknown, probably auto circulation (HJ upstream). | D2 timeline |
| 4 | **Byte d14.** PR 17: hour. SC README: bit 0 = °C flag. HJ: secondary temperature. | Hour and °C flag refuted. Secondary temperature kept as a hypothesis. | D2: values 22–27 at 20–21 h; bit 0 toggles without a unit change |
| 5 | **Circulation bit.** SC: d1 bit 6. HJ upstream: d4 bit 6. | d1 bit 6 for J235 (d4 is constant 0x05 on J235 even while circulating). | D2 |
| 6 | **Month.** HJ upstream: `f7&7` "cannot be right" (read 1 in August). | HJ's tub believed it was January 19 at the time, so its own data is consistent with `f7&7` = month. Still unresolved for months 8–12 (three bits). | HJ `DECODING.md` §3.3; D2–D6 |
| 7 | **Day of week.** PJ: Model A `P[20] & 7` ("not sure"). | Folded `d2 & 7` (Sunday = 0) on J235, matching four dated captures. Third-party frames are off by one, so J235-only. | `analyze_captures.py clock` |
| 8 | **Is 0x16 encrypted?** Legacy S2M and SC route 0x16/0x23 to the XOR decoder. | No. 0x16/0x17/0x23 are the plaintext Jacuzzi protocol; the J235 does not use them. The rewrite does not decode them as encrypted. | PJ L1617–1665; HJ upstream removal |
| 9 | **ClearRay code.** PJ docs 0x0E; HJ/JB 0x0F. | 0x0F (two independent sources; PJ text is internally inconsistent). Not exposed until confirmed on J235. | protocol.md §3.3 |
| 10 | **Status cadence.** "About every minute" (issue paraphrase) vs "very high rate" (PJ). | ≈ 3.3 Hz on J235. | D2: 200 rows per full minute |
| 11 | **`decoding.md` decoded values.** The doc's "post-decoding" lines all show minute 0x26. | The first 18 frames actually decode to minute 0x23; the doc copy-pasted the decode. Fixture keeps the raw frames, not the doc's decode. | `analyze_captures.py cipher` |

## Bugs found in prior code (for the record)

* Legacy S2M `Communicator.establish_transport` calls `logger.error("…", str(e))` with a stray
  argument. `Spa.send_buffer`/`channels_seen` are class-level mutable defaults shared across
  instances. `queue_button_command(send_immediately=True)` *queues* and `False` *sends now*
  (inverted). `MQTTControl` dictionaries are class attributes.
* Legacy S2M auto-claims a channel and may transmit 0x01/0x03 at start-up with no user action.
* SC/HJ/JB existing-client response writes `data[9]` into a 9-byte buffer (IndexError).

## Open questions

1. Month encoding for August–December (capture in November pending).
2. Pump 1 / pump 2 status bits and speed levels. No J235 dump has jets running.
3. Manual circulation (d1 bit 7) and the meaning of d1 bit 5, d2 bit 3, d10 bit 7.
4. d3 / d12 / d13: maintenance counters. Need the reminder values read from the topside
   at capture time.
5. d14 secondary temperature: unit and offset.
6. CC on J235: confirm the panel channel(s), the idle code 0x00 and the button codes by
   observing topside presses in a raw capture (receive-only).
7. Channel assignment on J235 (0x00/0x01/0x02/0x03). Can only be tested by transmitting,
   which is out of scope for development; the code path exists but is disabled by default.
8. EW11A serial settings (expected 115200 8N1).
9. Whether Model A or Model B reflects the real plaintext layout. A capture with values
   changing in *both* bytes of a pair would decide it.

## Raw-capture request (sent to the owner)

A receive-only capture using `tools/capture.py`, with labelled topside actions. The script is
in `tools/capture.py`; the action list is in the PR description.
