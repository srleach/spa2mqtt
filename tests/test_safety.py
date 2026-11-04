"""Static guarantees about the transmit path (docs/design.md §2)."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "spa2mqtt"
ALLOWED_WRITERS = {PKG / "tub" / "bus.py"}  # BusWriter.send
TRANSPORT_DIR = PKG / "transport"


def _write_calls(path: Path) -> list[int]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    lines = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "write":
            target = ast.unparse(node.func.value)
            if "transport" in target:
                lines.append(node.lineno)
    return lines


def test_only_buswriter_writes_to_a_transport() -> None:
    offenders = {}
    for path in PKG.rglob("*.py"):
        if path in ALLOWED_WRITERS or path.parent == TRANSPORT_DIR:
            continue
        if lines := _write_calls(path):
            offenders[str(path.relative_to(ROOT))] = lines
    assert offenders == {}


def test_transmitting_code_is_marked() -> None:
    for path in (PKG / "tub" / "bus.py", TRANSPORT_DIR / "tcp.py", TRANSPORT_DIR / "serial.py"):
        assert "TRANSMITS" in path.read_text(encoding="utf-8"), path


def test_capture_tool_never_sends() -> None:
    src = (ROOT / "tools" / "capture.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    calls = {n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert not calls & {"send", "sendall", "sendto"}


def test_transmit_defaults_off() -> None:
    from spa2mqtt.config import AppConfig, load_config

    assert AppConfig().transmit is False
    assert load_config(None, env={}).transmit is False
