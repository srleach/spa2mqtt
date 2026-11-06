# Unencrypted Jacuzzi captures (not J235)

Recovered from the unmerged spa2mqtt branch for PR 12 (`338b575`, "Add captures", 2025-05-27).
Both files were captured on 2025-05-21 from an **unencrypted** Jacuzzi board (plain types
0x16 status, 0x23 lights, Prolink address 0x0A), reached through a Prolink module on TCP
port 4257, not an EW11A. They were contributed by a community member with an unencrypted
board; thank you. The adapter's LAN address in the debug log is replaced with the
documentation address `192.0.2.1` (RFC 5737); no other bytes are changed. They are not used by the J235 tests. They are kept as evidence for a
future `plain` codec / definition (docs/design.md §1 non-goals).

* `2025-05-21_spa2mqtt_debug_0x16.txt`: legacy spa2mqtt debug log (`<timestamp>_: <hex>`).
* `2025-05-21_pyjacuzzi_prolink_session.txt`: a pyjacuzzi-style session log, including sent
  commands, e.g. direct set-temperature `7e060abf205a937e` (type 0x20).
