"""Streaming frame decoder.

Frames are delimited by 0x7E but framed by LEN: payload bytes may legitimately equal 0x7E
(the per-frame cipher key is random), and there is no byte stuffing (docs/protocol.md §2).
The decoder therefore looks for ``7E <LEN>``, waits for LEN+2 bytes, and accepts the frame
only if the end flag and CRC both check out. Otherwise it drops one byte and resynchronises.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .crc import crc8
from .frame import FLAG, MAX_LEN, MIN_LEN, Frame


@dataclass
class DecoderStats:
    frames: int = 0
    crc_errors: int = 0
    resyncs: int = 0
    bytes_dropped: int = 0


@dataclass
class FrameDecoder:
    stats: DecoderStats = field(default_factory=DecoderStats)
    _buf: bytearray = field(default_factory=bytearray)

    def feed(self, data: bytes) -> list[Frame]:
        self._buf += data
        out: list[Frame] = []
        buf = self._buf
        i = 0
        while True:
            start = buf.find(FLAG, i)
            if start < 0:
                self.stats.bytes_dropped += len(buf) - i
                i = len(buf)
                break
            if start > i:
                self.stats.bytes_dropped += start - i
            if start + 1 >= len(buf):
                i = start
                break
            length = buf[start + 1]
            if length == FLAG:
                # "7E 7E": previous end flag followed by a start flag.
                i = start + 1
                continue
            if length < MIN_LEN or length > MAX_LEN:
                self.stats.resyncs += 1
                i = start + 1
                continue
            end = start + length + 1  # index of the closing flag
            if end >= len(buf):
                i = start
                break  # wait for more bytes
            if buf[end] != FLAG:
                self.stats.resyncs += 1
                i = start + 1
                continue
            if crc8(buf[start + 1 : end - 1]) != buf[end - 1]:
                self.stats.crc_errors += 1
                i = start + 1
                continue
            out.append(
                Frame(
                    addr=buf[start + 2],
                    mid=buf[start + 3],
                    type=buf[start + 4],
                    payload=bytes(buf[start + 5 : end - 1]),
                )
            )
            self.stats.frames += 1
            # Leave the closing flag in place: some buses share it as the next start flag.
            i = end
        del buf[:i]
        if len(buf) > 4 * MAX_LEN:  # unbounded garbage without any flag pattern
            self.stats.bytes_dropped += len(buf) - MAX_LEN
            del buf[: len(buf) - MAX_LEN]
        return out
