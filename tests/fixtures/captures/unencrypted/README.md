# Jacuzzi J345 captures (plain protocol, ProLink)

Five logs from one **Jacuzzi J345** (J-300 series, unencrypted board), reached through the
original Jacuzzi ProLink module on TCP port 4257, not an EW11A. A community member with
this tub shared them in GitHub discussions 6 and 13 and PR 11; thank you. Older notes call
the tub a "J335": the owner says J345.

They are the evidence for `definitions/jacuzzi_j345.yaml` and
[docs/protocol-plain.md](../../../../docs/protocol-plain.md). `tests/test_plain_j345.py`
replays all five and checks every line the definition cites. The keys below are the ones
the definition and the docs use (`S L8` is line 8 of S).

| Key | File | Content |
|---|---|---|
| S | `2025-05-21_pyjacuzzi_prolink_session.txt` | pyjacuzzi session: 26 sent commands (`Sending:`) and the tub's replies (`New msg:`). pyjacuzzi logs a received frame only when it differs from the last one of its type. 82 lines, 59 frames. |
| D | `2025-05-21_spa2mqtt_debug_0x16.txt` | spa2mqtt v1 debug log, receive only: pumps and setpoint changed at the topside. 167 lines, 163 frames. |
| X1 | `2025-05-20T1551Z_spa2mqtt_debug_idle.txt` | v1 debug log, idle tub, circulation pump off. 100 frames. |
| X2 | `2025-05-20T2207Z_spa2mqtt_debug_lights.txt` | v1 debug log, light colours and brightness changed at the topside. 100 frames. |
| X3 | `2025-05-28T0044Z_spa2mqtt_debug_panel.txt` | v1 debug log, every topside function, a CLEARRAY reset, an hour rollover. 1716 lines, 1711 frames. |

S and D were recovered from the unmerged spa2mqtt branch for PR 12 (`338b575`, "Add
captures", 2025-05-27). X1, X2 and X3 are the owner's other thread attachments.

**Redaction rule.** Line endings are normalised to LF, and the adapter's LAN address is
replaced with the documentation address `192.0.2.1` (RFC 5737). No other byte is changed,
and no line is added or removed, so line numbers match the original attachments.

**Formats.** These are the two legacy log shapes (`<time>_: <hex>` and pyjacuzzi's
`<time>:INFO:Sending: <hex>` / `New msg: <hex>`), not the `.log` capture format. Only the
tests parse them (`plain_lines` in `tests/conftest.py`). New captures should use
`spa2mqtt monitor --record`.

Do not move these files into `captures/raw/`: that directory feeds the J235 C++ parity
tests.
