"""Suit permutations of observations and actions (`suit_symmetry`). The Go test
internal/rl/observation_symmetry_test.go proves the encoder equivariance these maps assume."""

import os

import numpy as np
import pytest
import torch

from conftest import small_model_config
from fh_mahjong_ai.action_catalog import CHII_BASE, DISCARD_BASE, KAN_CLOSED_BASE, PON_BASE
from fh_mahjong_ai.batched_eval import evaluate_duplicate_seats_batched
from fh_mahjong_ai.bridge import build_bridge
from fh_mahjong_ai.config import EnvConfig
from fh_mahjong_ai.env import MahjongEnv
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.scripts.compare_reports import paired_comparison
from fh_mahjong_ai.suit_symmetry import (
    SUIT_PERMUTATIONS, action_map, face_map, permute_rows, unpermute_action_values,
)

requires_go_lib = pytest.mark.skipif(
    not os.environ.get("FH_MAHJONG_BRIDGE_LIB"), reason="needs the Go bridge library"
)
SWAP_MAN_PIN = (1, 0, 2)


def _inverse(perm):
    inv = [0, 0, 0]
    for b, target in enumerate(perm):
        inv[target] = b
    return tuple(inv)


@pytest.mark.parametrize("perm", SUIT_PERMUTATIONS)
def test_maps_are_permutations_that_invert(perm):
    faces, actions = face_map(perm), action_map(perm)
    assert sorted(faces) == list(range(42)) and sorted(actions) == list(range(204))
    inv = _inverse(perm)
    assert (face_map(inv)[faces] == np.arange(42)).all()
    assert (action_map(inv)[actions] == np.arange(204)).all()


def test_identity_is_identity():
    assert (action_map(SUIT_PERMUTATIONS[0]) == np.arange(204)).all()


def test_known_images_under_a_man_pin_swap():
    m = action_map(SWAP_MAN_PIN)
    assert m[DISCARD_BASE + 0] == DISCARD_BASE + 9        # discard 1m -> 1p
    assert m[DISCARD_BASE + 18] == DISCARD_BASE + 18      # 1s stays
    assert m[DISCARD_BASE + 27] == DISCARD_BASE + 27      # east stays
    assert m[DISCARD_BASE + 40] == DISCARD_BASE + 40      # a flower stays
    assert m[PON_BASE + 8] == PON_BASE + 17               # pon 9m -> 9p
    assert m[KAN_CLOSED_BASE + 12] == KAN_CLOSED_BASE + 3  # closed kan 4p -> 4m
    assert m[CHII_BASE + 0] == CHII_BASE + 7              # chii 123m -> 123p
    assert m[CHII_BASE + 16] == CHII_BASE + 16            # chii 345s stays
    assert all(m[a] == a for a in range(DISCARD_BASE))    # pass / wins / haitei


def _real_rows(n=60):
    cfg = EnvConfig(bridge_kind="go", learning_seats=(0, 1, 2, 3), auto_play_heuristics=False,
                    match_mode="chongci", chongci_max_hands=4, max_steps_per_episode=4000,
                    event_history_window=16)
    env = MahjongEnv(cfg, build_bridge(cfg))
    rng = np.random.default_rng(5)
    rows = {"planes": [], "scalars": [], "masks": [], "events": []}
    obs = env.reset(seed=77)
    while len(rows["planes"]) < n:
        ev = np.zeros(16, dtype=np.uint32)
        hist = np.asarray(obs.event_history, dtype=np.uint32)[-16:]
        ev[:hist.size] = hist
        rows["planes"].append(obs.planes)
        rows["scalars"].append(obs.scalars)
        rows["masks"].append(obs.action_mask)
        rows["events"].append(ev)
        legal = np.flatnonzero(obs.action_mask)
        step = env.step(int(rng.choice(legal)))
        if step.terminated or step.truncated:
            obs = env.reset(seed=int(rng.integers(1, 10_000)))
        else:
            obs = step.observation
    env.close()
    return tuple(np.stack(rows[k]) for k in ("planes", "scalars", "masks", "events"))


@requires_go_lib
def test_identity_leaves_real_rows_unchanged_including_scalar_24():
    planes, scalars, masks, events = _real_rows()
    assert (scalars[:, 24] > 0).any()  # the sample includes active discards
    p, s, m, e = permute_rows(planes, scalars, masks, events, SUIT_PERMUTATIONS[0])
    assert np.array_equal(p, planes) and np.array_equal(s, scalars)
    assert np.array_equal(m, masks) and np.array_equal(e, events)


@requires_go_lib
@pytest.mark.parametrize("perm", SUIT_PERMUTATIONS[1:])
def test_permuting_then_inverting_restores_real_rows(perm):
    planes, scalars, masks, events = _real_rows()
    once = permute_rows(planes, scalars, masks, events, perm)
    back = permute_rows(*once, _inverse(perm))
    for original, restored in zip((planes, scalars, masks, events), back):
        assert np.array_equal(original, restored)
    assert (once[2].sum(axis=1) == masks.sum(axis=1)).all()


def test_unpermute_action_values_reindexes_to_original_actions():
    values = np.arange(204, dtype=np.float64)[None, :]
    back = unpermute_action_values(values, SWAP_MAN_PIN)
    assert back[0, DISCARD_BASE + 0] == DISCARD_BASE + 9


@requires_go_lib
def test_symmetric_eval_plays_legal_moves_and_pairs_with_the_plain_report():
    torch.manual_seed(7)
    model = PolicyValueNet(EnvConfig(), small_model_config(event_window=8)).eval()
    kw = dict(seeds=[41, 42, 43], match_mode="chongci", chongci_max_hands=4,
              max_steps_per_episode=4000, event_history_window=8, slots=3)
    plain = evaluate_duplicate_seats_batched(model, **kw)
    symmetric = evaluate_duplicate_seats_batched(model, symmetry="suits", **kw)
    assert symmetric["policy_transform"] == {"symmetry": "suits"}
    assert "policy_transform" not in plain
    assert symmetric["truncation_rate"] == 0.0
    result = paired_comparison(symmetric, plain)
    assert result["config_check"] == "strict"


def test_rejects_unknown_symmetry():
    with pytest.raises(ValueError, match="symmetry"):
        evaluate_duplicate_seats_batched(PolicyValueNet(EnvConfig(), small_model_config()),
                                         seeds=[1], symmetry="dihedral")
