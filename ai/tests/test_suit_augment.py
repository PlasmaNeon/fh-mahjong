"""Suit-permutation augmentation in the batched B2b collector (PPOConfig.suit_augment)."""

import os

import numpy as np
import pytest
import torch

from conftest import SMALL_MODEL
from fh_mahjong_ai.batched_b2b import collect_b2b_rollouts_batched, make_b2b_pool
from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.ppo import PPOConfig
from fh_mahjong_ai.scripts.collect_bench import _digest_batch
from fh_mahjong_ai.suit_symmetry import SUIT_PERMUTATIONS, action_map

requires_go_lib = pytest.mark.skipif(
    not os.environ.get("FH_MAHJONG_BRIDGE_LIB"), reason="needs the Go bridge library"
)
MATCHES, SEED = 4, 3100


def _setup(suit_augment: bool):
    env = EnvConfig(bridge_kind="go", event_history_window=8, oracle_observation=True,
                    max_steps_per_episode=4000, chongci_max_hands=4)
    torch.manual_seed(0)
    model = PolicyValueNet(EnvConfig(bridge_kind="go"),
                           ModelConfig(**SMALL_MODEL, event_window=8, privileged_critic=True,
                                       aux_heads=True)).eval()
    cfg = PPOConfig(device="cpu", matches_per_iter=MATCHES, max_steps_per_episode=4000,
                    match_mode="chongci", collector="batched", suit_augment=suit_augment)
    return env, model, cfg


def _collect(suit_augment: bool, action_selection="greedy", inference_mode="per_row"):
    env, model, cfg = _setup(suit_augment)
    pool = make_b2b_pool(env, model, cfg, 3)
    try:
        batch = collect_b2b_rollouts_batched(env, model, cfg, base_seed=SEED, pool=pool,
                                             inference_mode=inference_mode,
                                             action_selection=action_selection)
    finally:
        pool.close()
    return batch, model


def test_inverse_action_maps_invert():
    for perm in SUIT_PERMUTATIONS:
        forward = action_map(perm)
        assert (np.argsort(forward)[forward] == np.arange(204)).all()


@requires_go_lib
def test_augmented_greedy_collection_is_legal_and_self_consistent():
    batch, model = _collect(True)
    assert batch.truncated_matches == 0
    rows = np.arange(batch.actions.shape[0])
    assert (batch.action_mask[rows, batch.actions] == 1).all()
    with torch.no_grad():
        logits, _ = model(torch.from_numpy(batch.planes), torch.from_numpy(batch.scalars),
                          torch.from_numpy(batch.action_mask),
                          events=torch.from_numpy(batch.events.astype(np.int64)),
                          event_lengths=torch.from_numpy(batch.event_lengths.astype(np.int64)))
    assert (torch.argmax(logits, dim=1).numpy() == batch.actions).all()


@requires_go_lib
@pytest.mark.parametrize("selection, mode", [("greedy", "per_row"), ("sample", "batched")])
def test_augmented_collection_is_deterministic(selection, mode):
    first, _ = _collect(True, selection, mode)
    second, _ = _collect(True, selection, mode)
    assert _digest_batch(SEED, MATCHES, first) == _digest_batch(SEED, MATCHES, second)


@requires_go_lib
def test_augmentation_changes_the_stored_views():
    off, _ = _collect(False)
    on, _ = _collect(True)
    # The two collections play different games after the first decision, but most first
    # decisions are stored in a non-identity view, so the stored planes cannot all agree.
    n = min(off.planes.shape[0], on.planes.shape[0])
    assert not np.array_equal(off.planes[:n], on.planes[:n])


def test_config_refuses_suit_augment_on_the_process_collector():
    with pytest.raises(ValueError, match="suit_augment"):
        PPOConfig(collector="process", suit_augment=True)


def test_cli_requires_the_batched_collector(monkeypatch, capsys, tmp_path):
    from fh_mahjong_ai.scripts import train_b2b as cli
    champion = tmp_path / "champion.pt"
    champion.write_bytes(b"")
    monkeypatch.setattr("sys.argv", ["fh-mj-train-b2b", "--suit-augment", "--champion", str(champion),
                                     "--checkpoint-dir", str(tmp_path), "--collector", "process"])
    with pytest.raises(SystemExit):
        cli.main()
    assert "--suit-augment requires --collector batched" in capsys.readouterr().err


def test_resume_echo_reads_legacy_states_as_unaugmented():
    from fh_mahjong_ai.train_state import _LEGACY_ECHO_PINNED_VALUES
    assert _LEGACY_ECHO_PINNED_VALUES["ppo_config"]["suit_augment"] is False
