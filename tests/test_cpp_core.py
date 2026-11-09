"""Compile the ESPHome component's framework-free core on the host and cross-check it
against the Python decoder on every raw capture fixture (docs/design.md §9)."""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from spa2mqtt.definitions import TubDefinition

from .conftest import CAPTURES, frames_of

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "esphome" / "components" / "spa_bus"
CXX = shutil.which("g++") or shutil.which("clang++")


def esphome_definition_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("spa_bus_definition", COMPONENT / "definition.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def replay_binary(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if CXX is None:
        pytest.skip("no C++ compiler")
    out = tmp_path_factory.mktemp("cpp")
    defn = esphome_definition_module().load("jacuzzi_j235")
    (out / "definition.inc").write_text("\n".join(esphome_definition_module().cpp_setup_lines(defn, "core")) + "\n")
    binary = out / "replay"
    cmd = [
        CXX,
        "-std=c++17",
        "-O1",
        "-Wall",
        "-Wextra",
        "-Werror",
        f"-I{COMPONENT}",
        f"-I{out}",
        str(ROOT / "tests" / "cpp" / "replay_main.cpp"),
        str(COMPONENT / "spa_protocol.cpp"),
        "-o",
        str(binary),
    ]
    subprocess.run(cmd, check=True)
    return binary


def test_cpp_self_checks(replay_binary: Path) -> None:
    subprocess.run([str(replay_binary)], check=True)


def test_esphome_loader_agrees_with_python_loader(j235: TubDefinition) -> None:
    mod = esphome_definition_module()
    raw = mod.load("jacuzzi_j235")
    assert mod.field_keys(raw) == list(j235.fields)
    assert {e["key"] for e in raw["entities"]} == {e.key for e in j235.entities}


@pytest.mark.parametrize("capture", sorted((CAPTURES / "raw").glob("*.log")), ids=lambda p: p.name)
def test_cpp_decode_matches_python(replay_binary: Path, capture: Path, j235: TubDefinition) -> None:
    proc = subprocess.run([str(replay_binary), str(capture)], check=True, capture_output=True, text=True)
    keys = list(j235.fields)
    cpp: dict[int, dict[str, object]] = {}
    for line in proc.stdout.splitlines():
        frame_s, idx_s, kind, value = line.split(" ", 3)
        parsed: object = {"B": lambda v: v == "1", "N": float, "E": str, "-": lambda v: None}[kind](value)
        cpp.setdefault(int(frame_s), {})[keys[int(idx_s)]] = parsed

    from spa2mqtt.tub import Tub

    tub = Tub(j235)
    py: dict[int, dict[str, object]] = {}

    def collect(changed: dict[str, object]) -> None:
        py[tub.state.status_frames] = {
            k: (float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else v) for k, v in changed.items()
        }

    tub.subscribe(collect)  # type: ignore[arg-type]
    for f in frames_of(capture):
        tub.on_frame(f)
    assert cpp == py
    assert "crc_errors=0" in proc.stderr


def test_esphome_keystream_matches_python(j235: TubDefinition) -> None:
    raw = esphome_definition_module().load("jacuzzi_j235")
    assert bytes(esphome_definition_module().keystream(raw)) == j235.status_stream


def test_esphome_rejects_the_plain_definition() -> None:
    mod = esphome_definition_module()
    with pytest.raises(mod.DefinitionError, match="not supported by spa_bus"):
        mod.load("jacuzzi_j345")


def test_generator_skips_bridge_only_definitions() -> None:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "gen_esphome_package.py"), "--check"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout
    assert "skipped jacuzzi_j345.yaml" in proc.stdout
    assert not (ROOT / "esphome" / "packages" / "jacuzzi_j345.yaml").exists()
    assert (ROOT / "esphome" / "packages" / "jacuzzi_j235.yaml").is_file()
