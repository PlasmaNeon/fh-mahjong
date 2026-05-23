"""Static labels for the 204-action Mahjong RL catalog."""
from __future__ import annotations


ACTION_PASS = 0
ACTION_TSUMO = 1
ACTION_RON = 2
ACTION_ACCEPT_HAITEI = 3
ACTION_REFUSE_HAITEI = 4
DISCARD_BASE = 5
DISCARD_COUNT = 42
PON_BASE = DISCARD_BASE + DISCARD_COUNT
PON_COUNT = 34
KAN_DIRECT_BASE = PON_BASE + PON_COUNT
KAN_MODE_COUNT = 34
KAN_CLOSED_BASE = KAN_DIRECT_BASE + KAN_MODE_COUNT
KAN_UPGRADED_BASE = KAN_CLOSED_BASE + KAN_MODE_COUNT
CHII_BASE = KAN_UPGRADED_BASE + KAN_MODE_COUNT
CHII_COUNT = 21


def action_family(action_id: int) -> str:
    action_id = int(action_id)
    if action_id == ACTION_PASS:
        return "pass"
    if action_id in (ACTION_TSUMO, ACTION_RON):
        return "win"
    if action_id in (ACTION_ACCEPT_HAITEI, ACTION_REFUSE_HAITEI):
        return "haitei"
    if DISCARD_BASE <= action_id < DISCARD_BASE + DISCARD_COUNT:
        return "discard"
    if PON_BASE <= action_id < PON_BASE + PON_COUNT:
        return "pon"
    if KAN_DIRECT_BASE <= action_id < KAN_UPGRADED_BASE + KAN_MODE_COUNT:
        return "kan"
    if CHII_BASE <= action_id < CHII_BASE + CHII_COUNT:
        return "chii"
    return "unknown"


def action_label(action_id: int) -> str:
    action_id = int(action_id)
    if action_id == ACTION_PASS:
        return "pass"
    if action_id == ACTION_TSUMO:
        return "tsumo"
    if action_id == ACTION_RON:
        return "ron"
    if action_id == ACTION_ACCEPT_HAITEI:
        return "accept_haitei"
    if action_id == ACTION_REFUSE_HAITEI:
        return "refuse_haitei"

    if DISCARD_BASE <= action_id < DISCARD_BASE + DISCARD_COUNT:
        return f"discard {tile_face_42_label(action_id - DISCARD_BASE)}"
    if PON_BASE <= action_id < PON_BASE + PON_COUNT:
        return f"pon {tile_face_34_label(action_id - PON_BASE)}"
    if KAN_DIRECT_BASE <= action_id < KAN_DIRECT_BASE + KAN_MODE_COUNT:
        return f"kan_direct {tile_face_34_label(action_id - KAN_DIRECT_BASE)}"
    if KAN_CLOSED_BASE <= action_id < KAN_CLOSED_BASE + KAN_MODE_COUNT:
        return f"kan_closed {tile_face_34_label(action_id - KAN_CLOSED_BASE)}"
    if KAN_UPGRADED_BASE <= action_id < KAN_UPGRADED_BASE + KAN_MODE_COUNT:
        return f"kan_upgraded {tile_face_34_label(action_id - KAN_UPGRADED_BASE)}"
    if CHII_BASE <= action_id < CHII_BASE + CHII_COUNT:
        return f"chii {chii_label(action_id - CHII_BASE)}"
    return f"unknown {action_id}"


def tile_face_34_label(index: int) -> str:
    if not 0 <= int(index) < 34:
        return f"invalid34:{index}"
    return tile_face_42_label(index)


def tile_face_42_label(index: int) -> str:
    index = int(index)
    if 0 <= index < 9:
        return f"{index + 1}m"
    if 9 <= index < 18:
        return f"{index - 8}p"
    if 18 <= index < 27:
        return f"{index - 17}s"
    if 27 <= index < 34:
        return f"{index - 26}z"
    if 34 <= index < 42:
        return f"flower{index - 33}"
    return f"invalid42:{index}"


def chii_label(index: int) -> str:
    index = int(index)
    if not 0 <= index < CHII_COUNT:
        return f"invalid-chii:{index}"
    suit = "m"
    offset = index
    if index >= 14:
        suit = "s"
        offset = index - 14
    elif index >= 7:
        suit = "p"
        offset = index - 7
    start = offset + 1
    return f"{start}{suit}{start + 1}{suit}{start + 2}{suit}"
