# Project history: facts, findings and pivots

A reconstruction of how spa2mqtt got here, written as source material for an engineering
write-up. Dates come from git (author dates, Europe/London), GitHub PRs, the capture
fixtures and the Home Assistant registry. Context that only the owner can supply (why a
pivot happened) is marked **(owner)**; everything else can be checked against the commits
cited.

## TL;DR

* **May 2025**: two weeks of intense work turned a forked Sundance decoder into a Docker
  bridge (EW11A RS485-to-WiFi → MQTT → Home Assistant) for a Jacuzzi J235. Sensors worked; a
  few buttons worked "temporarily". Structure grew greedily around one tub, but with a
  stated goal of being pluggable for other Balboa-derived boards.
* **Mid 2025 to spring 2026**: dormant. In April 2026 a two-day burst produced five
  refactor/fix PRs that were never merged; some of their "discovered fields" were wrong.
* **Autumn 2026 (owner)**: colder air means a bigger water-to-air ΔT, more heat loss, more
  "heat refill" and higher running costs. The tub has to be *controlled*, not just watched.
  At the same time the owner had an ESP32 board with RS485 on board, and found that the EW11
  tries to phone home regularly with no way to turn it off. Hence ESPHome.
* **4 November 2026**: a full rebuild. The protocol was re-derived with citations. Both public
  "decryption" algorithms turned out to be the same cipher. A labelled raw capture from the
  tub confirmed or corrected every field the HA entities use. The bridge was rewritten around
  data-file tub definitions shared with a native ESPHome component.

## Prehistory: the shoulders stood on

| When | What | Why it matters |
|---|---|---|
| 2017 → | garbled1/pybalboa, ccutrer/balboa_worldwide_app: Balboa framing (0x7E, LEN, CRC-8 0x07) | The CRC routine in every later project is garbled1's. |
| 2023 | HyperActiveJ decodes a **Sundance 780** "encrypted" board: pairwise `xormsg` fold, C4 status, CC button codes 0xE1…, CTS channel squatting (`sundance780-jacuzzi-balboa-rs485-tcp`) | The decode that spa2mqtt used, with magic constants "hour XOR 6" and "temp XOR 2". |
| Mar 2023 – May 2024 | David Holland-Moritz (`dhmsjs/pyjacuzzi`) decompiles the Prolink app. In Dec 2023 he adds encrypted-board support via a different algorithm: a key byte plus a mod-64 key stream. srleach forks it (`65f4891`). | A second, apparently different, cipher model. Nobody had reconciled the two. |
| 12 May 2025 | `srleach/SpaControl` (`8a56368` … `ec631d8`): HJ's `sundanceRS485.py` plus an MQTT control class, tweaked for "additional Jacuzzi idle screen" | The first attempt: a working script, not a product. |

## Phase 1: spa2mqtt v1 (15–27 May 2025)

| Date | Commit / PR | Event |
|---|---|---|
| 15 May | `63057c3`, `61c2564`, `ed63b6f`, `bd4618e`, `c221d22` | Repo created; app stub; Docker; the **first YAML tub config**; "First Pass Conversion" from SpaControl. README concepts already say: *"move all logic into dependencies … behaviours into config files … new tubs & board types can be added simply"*. |
| 16 May | PR 1 `645e8b4` | Message/packet abstraction. `documentation/jacuzzi_encrypted/decoding.md` records **54 raw C4 frames** from the J235. These remained the only raw J235 frames until Nov 2026 (fixture **D1**). |
| 18 May | PR 3 `9a4d005`, PR 4 `1c1c25e`, PR 7 `01516b6`, PR 8 `2755850` | MQTT discovery via `ha-mqtt-discoverable` (bare `unique_id`s and the device `185569045` that HA still uses); J235 sensors (current/target temp, pump bits copied from Sundance code); maintenance sensors; change-driven publishing with heartbeat intervals; a debug harness writing **decoded** CSVs. |
| 18 May | `d99bf10` | First transmit code: "Introduce stub of sending pattern on CTS Receive". |
| 18 May | `6b19b0d` | First outside tub definition: a **J335 unencrypted** config from contributor @blackangel2109. Pluggability stops being hypothetical. |
| 19–20 May | `a7348ce`, `32049b2`, `7442570`, `bb4c340`, `59bc3b7` | Debug logging to file (captures **D2–D6**); simulated communicator; split into `base` (plain) and `jacuzzi_encrypted` families loaded by class name from the YAML (`family`, `communicator`, `spa`). |
| 21 May | `240e570`, `ea21601`; PR 12 (unmerged) | CTS detection fix; sending flows stubbed. A contributor's **unencrypted** board captured through a Prolink on port 4257, including direct set-temperature (0x20) commands. Now in `tests/fixtures/captures/unencrypted/`. |
| 25–27 May | `b302ddf`, `81786f3`, `32ffd0f`, PR 14, PR 15 `b0a5323` | Button keymaps; "temporary buttons working state"; config clean-up. Last commit on `main` before this rebuild. The debug CSVs are deleted from the tree (`d185ab1`) and survive only in history. |

**State at the end of Phase 1.** Temperature and setpoint were reliable. The pump bits were
copied from Sundance code and never seen to change on the J235. Setpoint control pressed
Temp up/down `(target − current)/0.5` times. Start-up auto-claimed a bus channel, so the
bridge **could transmit without any user action**. The architecture had pluggable intent,
but the plumbing still contained a lot of J235 code paths.

## Phase 2: dormancy and the April 2026 burst

| Date | Event |
|---|---|
| Jun 2025 – Mar 2026 | No commits. The bridge ran as-is. |
| sometime before Nov 2026 | Two entities, **`heater_active`** and **`manual_circulation_call`**, appear in HA under the same MQTT device. They are in no git ref, so they came from a local, unpushed definition. |
| 9–10 Apr 2026 | PRs 16–20 (`b157d26`, `ebec593`, `fbf5cb5`, `b26e0ea`, `1f7ebbb`): a "protocol abstraction layer", a packet capture mode, "discovered fields", HA entity tweaks and unit tests. None were merged. **Later shown to be wrong** (Nov 2026): water temp needs no XOR; byte 10 is a pump map (it is heater plus flags); byte 14 is the hour (values 22–27 at 20:00). |

## Phase 3: autumn 2026, the pivot to control and to ESPHome

**Why (owner).**

1. **Running cost.** As outside temperature falls, ΔT between water and air rises, heat loss
   rises, and the heater "refills" heat more often. Reacting to that (scheduling setpoints,
   watching heater duty) needs *reliable control* and *trustworthy heater/pump state*.
   Display-only telemetry is not enough.
2. **Hardware.** The owner acquired an ESP32 board with RS485 on board (HA holds an ESPHome
   config `jacuzzibridge-esp` for a Waveshare ESP32-S3-ETH-8DI-8RO; an archived config puts its
   RS485 UART on GPIO17/18).
3. **The EW11 phones home.** The owner found that the EW11 RS485-to-WiFi bridge attempts to
   contact an external service regularly, with no apparent setting to disable it. A
   cloud-chatty black box on the tub's control bus is an unwelcome dependency. An ESP running
   ESPHome removes it and talks to HA natively.

The HA recorder shows the MQTT entities `unavailable` on 25 October 2026 and again on
4 November 2026.

### 4 November 2026: research

| Finding | How it was established | Consequence |
|---|---|---|
| Captures in history | `git log --diff-filter=D` found four deleted decoded CSVs; PR 12 had unencrypted captures | Recovered into `tests/fixtures/captures/` with ISO-dated names (the repo `.gitignore` had been hiding `*.log`/`*-debug_messages.csv`). |
| **CRC-8 is textbook** | garbled1's bit-by-bit "register 0xB5, augmented" routine equals poly 0x07, init 0x02, xorout 0x02 on every frame | A 256-entry table in Python and C++. |
| **The "encryption" is a per-frame random key byte** | In D1 the first payload byte differs in 49 of 54 frames, yet `payload ⊕ key` is identical within a state | The obfuscation is cosmetic. |
| **Both published decrypt models are the same cipher** | Algebra plus a check on all 54 frames: HJ fold `d[j] = P[5+2j] ⊕ P[6+2j]` of pyjacuzzi's plaintext; "hour XOR 6" is the key-stream constant; "temp XOR 2" and "minute ^0x08" are neighbouring constant bytes | The magic constants are explained. The fold was chosen as canonical because it gave the right calendar day (16 May, the commit date) where pyjacuzzi's per-byte model gave 19 May. Upstream HJ independently reached the same identity. |
| Tub clock vs wall clock | Filename epochs of D3–D6 vs decoded hour/minute | Hour/minute/day confirmed. The tub was on GMT, ~3 min fast, in May 2025. |
| Heating curve | D2: 37.5 → 38.0 → 38.5 around a 38.0 setpoint with the heater bit clearing | The temp XOR stands. The April "no XOR" claim would mean a 2.5 °C jump in 10 minutes. |
| Upstream drift | HJ's repo was rewritten and redirected; its Jacuzzi 0x16 support was removed as "silently mis-decoded"; pyjacuzzi upstream added one temperature-scale commit (`39c2834`, 2026-11-03); Iraithium has a Sundance ESPHome component | Confirms that 0x16 is plain (not J235). Proves ESP32 feasibility. Bus is 115200 8N1. |
| Legacy code transmits at start-up | Reading `claim_channel_when_ready` | New safety rule: never transmit unless `transmit: true`, and never at start-up. |

### 4 November 2026: the labelled capture (D7)

The owner ran `tools/capture.py` (receive-only; it has no socket write) against the EW11A and
worked through a scripted list of topside actions, typing a label for each. Result: 9 minutes,
**51 242 frames, 0 CRC errors**, 37 labels.

| Finding | Evidence |
|---|---|
| Only the topside (channel 0x10) is on the bus. It answers **every** CTS (~45 Hz) with a CC, code 0x00 when idle. A new-client poll 0x00 runs at ~1 Hz. C4 status at 3.3 Hz, CA lights at 1 Hz. | Census |
| No dormant channel exists, so HJ-style "squatting" cannot work on this install. Commands need the 0x00/0x01 channel request. | Census |
| Pump 1 is 2-speed: `d2` bits 4–3 = off/low/high. `d1` bit 6 = pump 1 running (the J235 circulates on pump 1 low). Pump 2 = `d1` bit 2. | Presses at t≈90/119/143/181/196 |
| The legacy entities' bits were right; their names were broader than their meaning ("Main Pump Status" = pump 1 **high**). | Same |
| Button codes 0x01/0x02/0x04/0x05/0x12 confirmed. The CC encoding is `[K, K ⊕ 0xE0 ⊕ code]`. | 24 177 CC frames, random K |
| **The first Temp press only enters set mode**, so the v1 controller was always one press short. | `d2` bit 5 and `d13` 0x98 at t≈210 |
| Heating sequence: pump 1 low → `d1` bit 5 → heater bit `d10.6` | t≈454–513 |
| Lights layout (mode, R/G/B, brightness) matched HJ's map. The owner's colour names were the independent check. | t≈294–414 |
| Date packing `d7 = (day << 3) ⊕ month`: explains May, HJ's "January", and November's 0x2B. Months 8–12 can't be separated from the fold alone. | D1–D7 |

### 4 November 2026: the rebuild

| Decision | Rationale |
|---|---|
| **Tub definitions are data** (`definitions/*.yaml` + JSON Schema): message type, field map with transforms and an evidence status, buttons, entities | The May 2025 goal, finally without per-tub code. A new Balboa-family tub is a YAML file. A new cipher family is one codec in Python and C++. |
| Layers: transport → protocol → tub (sans-IO bus state machine, setpoint controller) → HA | Each layer testable alone. The bus logic is pure, so a mock board can drive it. |
| **Transmit off by default**; one marked TX choke point; lazy channel claim; command entities unavailable while off; a static test asserts nothing else writes | The owner's "never touch the real bus during development" constraint, and a lesson from v1's start-up transmit. |
| **Keep HA identities**: same device id, bare `unique_id`s, and discovery published to the *exact* `ha-mqtt-discoverable` topics | Retained configs are replaced in place: no duplicates, no orphans, no entity renames. |
| Drop `ha-mqtt-discoverable` for raw paho | Needed exact topic control; one fewer heavy dependency. |
| Closed-loop setpoint control (one press in flight, confirm in the next status frames, retry, bounded attempts) | Directly serves the running-cost goal: setpoint automations must land reliably. |
| **Native ESPHome component** reading the *same* YAML at compile time; a framework-free C++ core tested on the host against the same fixtures | No EW11, no cloud, no sidecar. One source of truth for both runtimes. |
| Old implementation on branch `legacy/pre-rewrite` | Rollback until the switch-over. |

### 4 November 2026: per-byte decryption and giving back

| Finding | Evidence | Consequence |
|---|---|---|
| The fold loses data. With the per-frame key removed, both bytes of some pairs change. | D7: bytes 2 and 3, bytes 28 and 29 | Decode per byte, not per pair. |
| One key stream decodes everything: pyjacuzzi's formula with four bytes corrected by −8. | Wall clock, topside labels, D1 and D7 | `decode: decrypt` in the definition; no per-field XORs. |
| The same stream decodes the Sundance 780 and another encrypted Jacuzzi. | HyperActiveJ's sample frame (14 Apr 2022); a pyjacuzzi frame labelled by its author | The August–December date gap closes, the fold's year is shown to be wrong on other tubs, and a definition written for one board fits the family. |
| Correction: the fold's weekday was right all along. The "off by one" on foreign frames came from the fold's wrong year. | Same frames | Docs corrected. |

An issue for HyperActiveJ's repository (now pete-jorgensen/SundanceHotTub2MQTT) was drafted. It
answers the open question in their `DECODING.md` §3.8 and includes a standalone decoder, tested on
their own sample frame. That is the first thing this project has given back to the work it is
built on.

### 9 November 2026: a second tub, on someone else's evidence

| Decision | Rationale |
|---|---|
| **Jacuzzi J345 (plain protocol through a ProLink module)**: `definitions/jacuzzi_j345.yaml`, decoded from the contributor's five May 2025 logs (three more recovered from the threads into `tests/fixtures/captures/unencrypted/`) | The tub from the 18 May 2025 "J335" config. Its owner had asked for progress in December 2025. The model name was settled from the owner's own words: J345. |
| A direct bus mode: fixed address 0x0A, no channel claim, one frame per four status frames | The ProLink stream has no clear-to-send. pyjacuzzi wrote straight to the socket and it worked. |
| Transmit limited to frames the pyjacuzzi capture shows working, reproduced byte for byte in tests | Nobody on the project can test this tub. |
| Home Assistant device name and identifier default from the definition | Environment-only installs could not set them, and the second tub would have appeared as "Jacuzzi J235". |
| Bridge only: ESPHome rejects the protocol | Nobody has wired an ESP32 to a plain board. |

## Threads worth telling in the write-up

* **Pluggability as a slow-burning requirement.** README concepts (May 2025) → class-name
  loading per family (May 2025) → a contributor's J335 config (18 May 2025) → "protocol
  abstraction" (Apr 2026) → schema-validated data files shared by two runtimes (Nov 2026).
* **Folklore vs evidence.** Three generations of magic XOR constants turned out to be one
  cipher seen through a lossy fold. The decisive tests were mundane: commit dates, filename
  epochs and the owner typing "p1 press 2" into a terminal.
* **The value of a labelled capture.** Eighteen months of guessing about pump bits were settled
  by nine minutes of receive-only capture with a script of topside actions.
* **Giving back.** The labelled capture answered a question that HyperActiveJ had asked in
  writing, and the fix decodes their own sample frame. Posting it upstream closes the loop.
* **Safety as design.** Receive-only by default, one choke point, and a static test.
  Development never transmitted to the real tub.
