import numpy as np
import pytest
import torch

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.oracle import build_b2b_model, collect_b2b_rollouts, train_b2b
from fh_mahjong_ai.ppo import PPOConfig
from fh_mahjong_ai.storage import save_checkpoint

_SMALL = dict(channels=16, residual_blocks=1, plane_feature_dim=32, scalar_hidden_dim=16,
              trunk_hidden_dim=32, value_hidden_dim=16, q_hidden_dim=16)


def _champion(tmp_path):
    env39 = EnvConfig(bridge_kind="mock")
    model = PolicyValueNet(env39, ModelConfig(**_SMALL))
    path = tmp_path / "champion.pt"
    save_checkpoint(path, model)
    return env39, path


def test_warm_start_logit_equivalence(tmp_path):
    env39, champion_path = _champion(tmp_path)
    champion = PolicyValueNet(env39, ModelConfig(**_SMALL))
    from fh_mahjong_ai.storage import load_checkpoint
    load_checkpoint(champion_path, champion)
    champion.eval()

    b2b_config = ModelConfig(**_SMALL, event_window=16, privileged_critic=True, aux_heads=True)
    model = build_b2b_model(env39, b2b_config, champion_path)
    model.eval()

    rng = np.random.default_rng(3)
    planes39 = torch.from_numpy(rng.random((4, 39, 42, 1), dtype=np.float32))
    planes51 = torch.cat([planes39, torch.from_numpy(rng.random((4, 12, 42, 1), dtype=np.float32))], dim=1)
    scalars = torch.from_numpy(rng.random((4, 58), dtype=np.float32))
    mask = torch.ones((4, 204), dtype=torch.int8)
    events = torch.from_numpy(rng.integers(0, 0x10000, size=(4, 16), dtype=np.uint32).astype(np.int64))
    lengths = torch.full((4,), 16, dtype=torch.int64)

    with torch.no_grad():
        ref, _ = champion(planes39, scalars, mask)
        got51, _ = model(planes51, scalars, mask, events=events, event_lengths=lengths)
        got39, _ = model(planes39, scalars, mask, events=events, event_lengths=lengths)
    assert torch.allclose(ref, got51, atol=1e-5)
    assert torch.allclose(ref, got39, atol=1e-5)


def test_collect_b2b_records_events_and_labels(tmp_path):
    # Model construction needs a 39ch (oracle_observation=False) EnvConfig — the
    # privileged-critic branch assumes exactly 39 policy channels so it can
    # slice the trailing 12 oracle channels out of a 51ch observation at
    # inference time; see oracle._b2b_model_env_config.
    env39 = EnvConfig(bridge_kind="mock", event_history_window=8)
    env = EnvConfig(bridge_kind="mock", event_history_window=8, oracle_observation=True,
                    max_steps_per_episode=32)
    model = PolicyValueNet(env39, ModelConfig(**_SMALL, event_window=8,
                                              privileged_critic=True, aux_heads=True))
    config = PPOConfig(device="cpu", matches_per_iter=2, max_steps_per_episode=32,
                       match_mode="classic")
    batch = collect_b2b_rollouts(env, model, config, base_seed=11)
    n = len(batch)
    assert batch.planes.shape[1] == 51
    assert batch.events.shape == (n, 8) and batch.events.dtype == np.uint32
    assert batch.event_lengths.shape == (n,)
    assert np.all(batch.event_lengths <= 8)
    assert batch.dealin_labels.shape == (n,)
    assert set(np.unique(batch.rank_labels)).issubset({-1, 0, 1, 2, 3, 4})


def test_hindsight_label_assembly_fixture():
    # Pure-function check on the label assembler with a scripted match:
    # 2 hands; hand 0 ends in a ron paid by seat 2; hand 1 is a draw.
    from fh_mahjong_ai.oracle import _assemble_hindsight_labels

    # rows: (seat, hand_id) in emission order for a 3-seat toy
    rows = [(0, 0), (2, 0), (2, 0), (1, 1), (2, 1)]
    hand_outcomes = {0: {"is_draw": False, "win_type_name": "ACTION_RON", "discarder_seat": 2},
                     1: {"is_draw": True, "win_type_name": "ACTION_UNKNOWN", "discarder_seat": 0}}
    final_scores = {0: 2500.0, 1: 2000.0, 2: -100.0, 3: 1600.0}
    dealin, rank = _assemble_hindsight_labels(rows, hand_outcomes, final_scores,
                                              bust_threshold=0.0, truncated=False)
    assert dealin.tolist() == [0.0, 1.0, 1.0, 0.0, 0.0]
    # scores: seat0=2500 (rank0), seat1=2000 (rank1), seat3=1600 (rank2), seat2 busted (4)
    assert rank.tolist() == [0, 4, 4, 1, 4]

    dealin_t, rank_t = _assemble_hindsight_labels(rows, hand_outcomes, final_scores,
                                                  bust_threshold=0.0, truncated=True)
    assert rank_t.tolist() == [-1] * 5
    assert dealin_t.tolist() == [0.0, 1.0, 1.0, 0.0, 0.0]  # deal-in survives truncation


def test_train_b2b_two_iters_mock(tmp_path):
    env39, champion_path = _champion(tmp_path)
    env = EnvConfig(bridge_kind="mock", event_history_window=8, oracle_observation=True,
                    max_steps_per_episode=16)
    config = PPOConfig(device="cpu", iterations=2, matches_per_iter=2,
                       max_steps_per_episode=16, ppo_epochs=1, minibatch_size=8,
                       num_workers=1, match_mode="classic")
    history = train_b2b(env, ModelConfig(**_SMALL, event_window=8, privileged_critic=True,
                                         aux_heads=True),
                        champion_path, tmp_path / "ckpt", config, base_seed=5)
    assert len(history) == 2
    assert (tmp_path / "ckpt" / "iter_002.pt").exists()
    for key in ("belief_loss", "dealin_loss", "rank_loss"):
        assert key in history[0]
