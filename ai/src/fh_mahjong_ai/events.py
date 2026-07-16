"""Packed public-event codec — the Python mirror of internal/rl/eventcodec.go.

Bit layout (wire-stable; change BOTH files or neither):
    bits  0-3  event type
    bits  4-5  actor seat relative to observer (0=self,1=right,2=across,3=left)
    bits  6-11 face index 0-41; 63 = unknown (masked opponent draw)
    bits 12-13 from-seat relative to observer (calls only; 0 otherwise)
    bit  14    tsumogiri flag
    bit  15    haitei flag
    bits 16-31 reserved, always zero
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

import numpy as np

EVENT_DRAW = 0
EVENT_DISCARD = 1
EVENT_CHII = 2
EVENT_PON = 3
EVENT_KAN_OPEN = 4
EVENT_KAN_CLOSED = 5
EVENT_KAN_UPGRADE = 6
EVENT_FLOWER = 7
NUM_EVENT_TYPES = 8

FACE_UNKNOWN = 63

_SEAT_SHIFT = 4
_FACE_SHIFT = 6
_FROM_SHIFT = 12
_TSUMOGIRI_BIT = 1 << 14
_HAITEI_BIT = 1 << 15
_RESERVED_MASK = ~0xFFFF & 0xFFFFFFFF


@dataclass(frozen=True)
class Event:
    type: int
    rel_seat: int
    face: int
    rel_from: int
    tsumogiri: bool
    haitei: bool


def encode_event(event: Event) -> int:
    packed = event.type & 0xF
    packed |= (event.rel_seat & 0x3) << _SEAT_SHIFT
    packed |= (event.face & 0x3F) << _FACE_SHIFT
    packed |= (event.rel_from & 0x3) << _FROM_SHIFT
    if event.tsumogiri:
        packed |= _TSUMOGIRI_BIT
    if event.haitei:
        packed |= _HAITEI_BIT
    return packed


def decode_event(packed: int) -> Event:
    packed = int(packed)
    if packed & _RESERVED_MASK:
        raise ValueError(f"reserved bits set in packed event 0x{packed:08X}")
    return Event(
        type=packed & 0xF,
        rel_seat=(packed >> _SEAT_SHIFT) & 0x3,
        face=(packed >> _FACE_SHIFT) & 0x3F,
        rel_from=(packed >> _FROM_SHIFT) & 0x3,
        tsumogiri=bool(packed & _TSUMOGIRI_BIT),
        haitei=bool(packed & _HAITEI_BIT),
    )


def decode_history(packed: np.ndarray) -> List[Event]:
    return [decode_event(value) for value in np.asarray(packed, dtype=np.uint32).tolist()]


def event_to_token(event: Event) -> int:
    """Embedding index for B2's event encoder: (type, rel_seat, face) -> [0, 2048).

    Flags and rel_from ride as separate small features next to the token
    embedding — they carry too little mass to burn vocabulary on.
    """
    return (event.type * 4 + event.rel_seat) * 64 + event.face
