"""Suit permutations of observations and actions (man, pin and sou are interchangeable).

Fenghua scoring treats the three suits identically, and the Go encoder is suit-equivariant:
`internal/rl/observation_symmetry_test.go` proves that encoding a suit-permuted state equals
applying these maps to the original encoding, for planes, the action mask, event faces and
every scalar except the best-discard look-ahead block (33-35, 37, 40). That block breaks ties
by face order, so a permutation can name a different tied tile; `permute_rows` leaves it as
it is. Scalar 24 (the active discard's face / 41) is rebuilt from plane 28, the active-discard
one-hot, because 0 means both "no discard" and "1m".

A permutation `perm` sends suit block b (man 0, pin 1, sou 2 in the 42-face order) to block
perm[b]. Honors (27-33) and flowers (34-41) never move.
"""
from __future__ import annotations

from functools import lru_cache
from itertools import permutations

import numpy as np

from .action_catalog import CHII_BASE, CHII_COUNT, DISCARD_BASE, DISCARD_COUNT, PON_BASE

SUIT_PERMUTATIONS: tuple[tuple[int, int, int], ...] = tuple(permutations(range(3)))  # identity first
ACTIVE_DISCARD_PLANE = 28
ACTIVE_DISCARD_SCALAR = 24
FACES = 42
_FACE_SHIFT = 6
_FACE_BITS = 0x3F
_FACE_UNKNOWN = 63


@lru_cache(maxsize=None)
def face_map(perm: tuple[int, int, int]) -> np.ndarray:
    """m[f] = the face f becomes under perm (length 42)."""
    m = np.arange(FACES)
    for f in range(27):
        m[f] = perm[f // 9] * 9 + f % 9
    m.setflags(write=False)
    return m


@lru_cache(maxsize=None)
def action_map(perm: tuple[int, int, int], action_space: int = 204) -> np.ndarray:
    """m[a] = the action a becomes under perm (mirrors permuteActionID in the Go test)."""
    faces = face_map(perm)
    m = np.arange(action_space)
    for a in range(DISCARD_BASE, DISCARD_BASE + DISCARD_COUNT):
        m[a] = DISCARD_BASE + faces[a - DISCARD_BASE]
    for a in range(PON_BASE, CHII_BASE):  # pon and the three kan families: 34-face blocks
        base = PON_BASE + ((a - PON_BASE) // 34) * 34
        m[a] = base + faces[a - base]
    for a in range(CHII_BASE, CHII_BASE + CHII_COUNT):
        index = a - CHII_BASE
        m[a] = CHII_BASE + perm[index // 7] * 7 + index % 7
    m.setflags(write=False)
    return m


def permute_events(events: np.ndarray, perm: tuple[int, int, int]) -> np.ndarray:
    """Packed uint32 events with every known suited face remapped (63 = unknown stays)."""
    events = np.asarray(events, dtype=np.uint32)
    faces = (events >> _FACE_SHIFT) & _FACE_BITS
    table = np.append(face_map(perm), np.arange(FACES, _FACE_BITS + 1)).astype(np.uint32)
    return (events & ~np.uint32(_FACE_BITS << _FACE_SHIFT)) | (table[faces] << _FACE_SHIFT)


def permute_rows(planes: np.ndarray, scalars: np.ndarray, masks: np.ndarray, events: np.ndarray,
                 perm: tuple[int, int, int]):
    """Batch rows (planes [N, C, 42, W], scalars [N, S], masks [N, A], events [N, window])
    as the encoder would emit them for the suit-permuted state. Event lengths are unchanged."""
    faces = face_map(perm)
    inverse = np.argsort(faces)
    new_planes = np.ascontiguousarray(planes[:, :, inverse, :])
    actions = action_map(perm, masks.shape[1])
    new_masks = np.empty_like(masks)
    new_masks[:, actions] = masks
    new_scalars = np.array(scalars, copy=True)
    active = new_planes[:, ACTIVE_DISCARD_PLANE, :, 0]
    has_active = active.any(axis=1)
    new_scalars[has_active, ACTIVE_DISCARD_SCALAR] = (
        np.argmax(active[has_active], axis=1).astype(np.float32) / np.float32(FACES - 1))
    return new_planes, new_scalars, new_masks, permute_events(events, perm)


def unpermute_action_values(values: np.ndarray, perm: tuple[int, int, int]) -> np.ndarray:
    """Per-action values computed on the permuted rows, re-indexed to the original actions."""
    return values[:, action_map(perm, values.shape[1])]


def suit_averaged_log_probs(model, planes: np.ndarray, scalars: np.ndarray, masks: np.ndarray,
                            events: np.ndarray, lengths: np.ndarray, device="cpu"):
    """The suit-averaged policy for n rows: the mean over the six suit views of the model's
    masked log-probabilities, re-indexed to the original actions (illegal = -inf), and the
    mean value. `events` are packed uint32 [n, window] (window may be 0); `lengths` [n].

    One batched forward over the 6n permuted rows. Serving, review and the parity reference
    all use this, so every surface plays the same averaged policy."""
    import torch

    n = planes.shape[0]
    views = [permute_rows(planes, scalars, masks, events, perm) for perm in SUIT_PERMUTATIONS]
    p, s, m, e = (np.concatenate(parts) for parts in zip(*views))
    to = lambda a: torch.from_numpy(np.ascontiguousarray(a)).to(device)  # noqa: E731
    ev = ln = None
    if getattr(model, "wants_events", False):
        ev = to(e.astype(np.int64))
        ln = to(np.tile(np.asarray(lengths, dtype=np.int64), len(SUIT_PERMUTATIONS)))
    with torch.inference_mode():
        logits, values = model(to(p), to(s), to(m), events=ev, event_lengths=ln)
    logp = torch.log_softmax(logits.double(), dim=1).cpu().numpy()
    total = np.zeros((n, masks.shape[1]), dtype=np.float64)
    for k, perm in enumerate(SUIT_PERMUTATIONS):
        total += unpermute_action_values(logp[k * n:(k + 1) * n], perm)
    total /= len(SUIT_PERMUTATIONS)
    total[masks == 0] = -np.inf
    value = values.reshape(len(SUIT_PERMUTATIONS), n).double().mean(dim=0).cpu().numpy()
    return total, value
