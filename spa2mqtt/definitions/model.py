"""Typed, immutable view of a tub definition (schema: definitions/tub-definition.schema.json)."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dc_field
from typing import Literal

FieldValue = bool | int | float | str | None
Component = Literal["sensor", "binary_sensor", "text_sensor", "button", "number", "switch"]
Status = Literal["confirmed", "inferred", "hypothesis"]


@dataclass(frozen=True, slots=True)
class FieldDef:
    """One value in the decoded status payload. ``decode`` is the canonical transform
    (docs/design.md §4); the C++ implementation in spa_protocol.cpp must match it.
    ``frame`` names the payload it indexes: "status" or an extra frame (plain boards)."""

    key: str
    byte: int
    status: Status
    length: int = 1
    xor: int = 0
    bit: int | None = None
    shift: int = 0
    mask: int | None = None
    scale: float | None = None
    offset: float = 0.0
    invalid: frozenset[int] = frozenset()
    map: dict[int, str] | None = None
    evidence: str = ""
    description: str = ""
    frame: str = "status"

    @property
    def kind(self) -> Literal["bool", "enum", "number"]:
        if self.bit is not None:
            return "bool"
        if self.map is not None:
            return "enum"
        return "number"

    def decode(self, decoded: bytes) -> FieldValue:
        end = self.byte + self.length
        if end > len(decoded):
            return None
        raw = int.from_bytes(decoded[self.byte : end], "big") ^ self.xor
        if self.bit is not None:
            return bool((raw >> self.bit) & 1)
        raw >>= self.shift
        if self.mask is not None:
            raw &= self.mask
        if raw in self.invalid:
            return None
        if self.map is not None:
            return self.map.get(raw)
        if self.scale is None and self.offset == 0:
            return raw
        value = raw * (1.0 if self.scale is None else self.scale) + self.offset
        return int(value) if self.scale is None and float(value).is_integer() else value


@dataclass(frozen=True, slots=True)
class EntityDef:
    key: str
    component: Component
    name: str
    icon: str | None = None
    entity_category: str | None = None
    enabled_by_default: bool = True
    description: str = ""


@dataclass(frozen=True, slots=True)
class StateEntity(EntityDef):
    """sensor / binary_sensor / text_sensor bound to one field."""

    field: str = ""
    device_class: str | None = None
    unit_of_measurement: str | None = None
    state_class: str | None = None
    accuracy_decimals: int | None = None


@dataclass(frozen=True, slots=True)
class ButtonEntity(EntityDef):
    press: str = ""


@dataclass(frozen=True, slots=True)
class SwitchEntity(EntityDef):
    """An on/off state (a bit field) reached by pressing a toggle button until it reads right."""

    field: str = ""
    press: str = ""
    confirm_frames: int = 10
    max_presses: int = 3
    progress_field: str | None = None
    device_class: str | None = None


@dataclass(frozen=True, slots=True)
class StepperControl:
    up: str
    down: str
    confirm_frames: int = 3
    max_attempts: int = 40
    set_mode_field: str | None = None


@dataclass(frozen=True, slots=True)
class DirectControl:
    """A number set with one frame of a direct command (no presses, no retry)."""

    command: str


@dataclass(frozen=True, slots=True)
class NumberEntity(EntityDef):
    field: str = ""
    control: StepperControl | DirectControl = dc_field(default_factory=lambda: StepperControl("", ""))
    min: float = 0.0
    max: float = 100.0
    step: float = 1.0
    mode: str | None = None
    device_class: str | None = None
    unit_of_measurement: str | None = None


@dataclass(frozen=True, slots=True)
class BusConfig:
    baud: int = 115200
    client_mid: int = 0xBF
    channel_request_magic: tuple[int, int] = (0xF1, 0x73)
    dormant_channel_threshold: int = 5
    mode: Literal["claim", "direct"] = "claim"
    client_address: int | None = None  # direct: ADDR of every frame sent
    hello: str | None = None  # direct: command sent once per connection before the first command
    send_gap_frames: int = 4  # direct: status frames between two sent frames


@dataclass(frozen=True, slots=True)
class ExtraFrame:
    """A second periodic board frame whose payload fields may index (plain boards)."""

    type: int
    length: int


@dataclass(frozen=True, slots=True)
class ButtonMeta:
    status: Status
    evidence: str = ""
    description: str = ""


@dataclass(frozen=True, slots=True)
class DirectCommand:
    """A command with its own frame type. ``payload`` is fixed bytes with at most one
    ``None`` slot, which :meth:`build` fills with a value in ``minimum..maximum``."""

    key: str
    type: int
    payload: tuple[int | None, ...]
    status: Status
    minimum: int | None = None
    maximum: int | None = None
    evidence: str = ""
    description: str = ""
    # status bit fields that must read exactly this before the command may be sent
    requires: tuple[tuple[str, bool], ...] = ()

    @property
    def takes_value(self) -> bool:
        return None in self.payload

    def build(self, value: int | None = None) -> bytes:
        if not self.takes_value:
            if value is not None:
                raise ValueError(f"command {self.key!r} takes no value")
            return bytes(b for b in self.payload if b is not None)
        if value is None:
            raise ValueError(f"command {self.key!r} needs a value")
        assert self.minimum is not None and self.maximum is not None
        if isinstance(value, bool) or not isinstance(value, int) or not self.minimum <= value <= self.maximum:
            raise ValueError(f"command {self.key!r}: {value!r} is outside {self.minimum}..{self.maximum}")
        return bytes(value if b is None else b for b in self.payload)


@dataclass(frozen=True, slots=True)
class TubDefinition:
    id: str
    name: str
    manufacturer: str
    model: str
    protocol: str
    temperature_unit: str
    status_type: int
    status_length: int
    status_decode: str
    command_type: int | None
    buttons: dict[str, int]
    fields: dict[str, FieldDef]
    entities: tuple[EntityDef, ...]
    bus: BusConfig = BusConfig()
    fold_template: bytes | None = None
    status_stream: bytes | None = None  # decrypt: per-byte key stream S
    aliases: tuple[str, ...] = ()
    description: str = ""
    source_path: str = ""
    command_encode: str | None = None
    direct_commands: dict[str, DirectCommand] = dc_field(default_factory=dict)
    button_meta: dict[str, ButtonMeta] = dc_field(default_factory=dict)
    extra_frames: dict[str, ExtraFrame] = dc_field(default_factory=dict)
    device_name: str = ""  # Home Assistant identity defaults (ha: in the definition)
    device_identifier: str = ""

    def entity(self, key: str) -> EntityDef:
        for e in self.entities:
            if e.key == key:
                return e
        raise KeyError(key)

    def extra_frame_for(self, frame_type: int) -> tuple[str, ExtraFrame] | None:
        for name, extra in self.extra_frames.items():
            if extra.type == frame_type:
                return name, extra
        return None

    def decode_status(self, decoded: bytes) -> dict[str, FieldValue]:
        """Decode an already-unkeyed (or folded, per ``status_decode``) payload."""
        return {k: f.decode(decoded) for k, f in self.fields.items() if f.frame == "status"}

    def decode_frame(self, name: str, payload: bytes) -> dict[str, FieldValue]:
        """Decode the fields that index the extra frame ``name`` (always plaintext)."""
        return {k: f.decode(payload) for k, f in self.fields.items() if f.frame == name}

    def decode_payload(self, payload: bytes) -> bytes:
        """Raw status payload -> the bytes the field map indexes (per ``status_decode``)."""
        from ..protocol.cipher import decrypt, fold, unkey

        if self.status_decode == "decrypt":
            assert self.status_stream is not None
            return decrypt(payload, self.status_stream)
        if self.status_decode == "unkey":
            return unkey(payload)
        if self.status_decode == "fold":
            return fold(payload)
        if self.status_decode == "plain":
            return payload
        raise ValueError(f"unknown status decode {self.status_decode!r}")

    def byte_masks(self) -> dict[int, int]:
        """Which bits of which decoded byte each field reads (for :func:`unkeyed_from_fold`)."""
        masks: dict[int, int] = {}
        for f in self.fields.values():
            if f.frame != "status":
                continue
            if f.bit is not None:
                width_mask = 1 << f.bit
            else:
                width_mask = (f.mask if f.mask is not None else (1 << (8 * f.length)) - 1) << f.shift
            for k in range(f.length):
                byte = f.byte + f.length - 1 - k
                masks[byte] = masks.get(byte, 0) | ((width_mask >> (8 * k)) & 0xFF)
        return masks
