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


def test_collect_b2b_forwards_chongci_config_to_bridge(monkeypatch):
    # The bridge must simulate under the SAME chongci values the hindsight
    # labels are computed with — a silent mismatch here mislabels every rank.
    import fh_mahjong_ai.oracle as oracle_mod
    from fh_mahjong_ai.bridge import build_bridge as real_build_bridge

    captured = {}

    def capturing_build_bridge(cfg):
        captured["cfg"] = cfg
        return real_build_bridge(cfg)

    monkeypatch.setattr(oracle_mod, "build_bridge", capturing_build_bridge)

    env = EnvConfig(bridge_kind="mock", event_history_window=8, oracle_observation=True,
                    max_steps_per_episode=16,
                    chongci_starting_score=3333, chongci_bust_threshold=111,
                    chongci_max_hands=7)
    model = PolicyValueNet(EnvConfig(bridge_kind="mock"),
                           ModelConfig(**_SMALL, event_window=8,
                                       privileged_critic=True, aux_heads=True))
    config = PPOConfig(device="cpu", matches_per_iter=1, max_steps_per_episode=16,
                       match_mode="chongci")
    from fh_mahjong_ai.oracle import collect_b2b_rollouts
    # The mock bridge never surfaces round outcomes, so the stale-bridge
    # capability guard fires after collection — config capture still happens.
    with pytest.raises(RuntimeError, match="no round outcomes"):
        collect_b2b_rollouts(env, model, config, base_seed=3)
    cfg = captured["cfg"]
    assert cfg.chongci_starting_score == 3333
    assert cfg.chongci_bust_threshold == 111
    assert cfg.chongci_max_hands == 7


def test_hindsight_rank_labels_use_reward_scale():
    # The Go env emits chongci rewards as score deltas / 1000: a seat whose
    # net reward is -2.5 (i.e. -2500 points) from a 2000-point start is
    # BUSTED (final -500 <= 0). Mixing raw points with reward-scale nets
    # reconstructed 1997.5 and labeled it ranked — the corrupted-label bug.
    from fh_mahjong_ai.oracle import _assemble_hindsight_labels

    rows = [(0, 0), (1, 0), (2, 0), (3, 0)]
    # Reward-scale final scores: start 2.0 (=2000 pts / 1000) + net deltas.
    final_scores = {0: 2.0 + 1.5, 1: 2.0 + 1.0, 2: 2.0 - 2.5, 3: 2.0 + 0.0}
    dealin, rank = _assemble_hindsight_labels(rows, {}, final_scores,
                                              bust_threshold=0.0, truncated=False)
    assert rank.tolist() == [0, 1, 4, 2]  # seat 2 busted, NOT ranked


def test_infer_model_config_rejects_b2b_checkpoints(tmp_path):
    # CheckpointPolicy.from_checkpoint relies on infer_model_config, which
    # cannot reconstruct B2b modules — it must fail with a CLEAR message
    # (B2c scope), not a cryptic load_state_dict error.
    import pytest as _pytest

    from fh_mahjong_ai.model import infer_model_config

    env39 = EnvConfig(bridge_kind="mock")
    model = PolicyValueNet(env39, ModelConfig(**_SMALL, event_window=8,
                                              privileged_critic=True, aux_heads=True))
    with _pytest.raises(RuntimeError, match="Spec B2c"):
        infer_model_config(model.state_dict())

    # Legacy checkpoints still infer fine.
    legacy = PolicyValueNet(env39, ModelConfig(**_SMALL))
    config = infer_model_config(legacy.state_dict())
    assert config.residual_blocks == 1


def test_rank_labels_include_pre_first_decision_rewards(monkeypatch):
    # A payout landing BEFORE a seat's first decision (e.g. dealer tsumo on
    # the opening hand) must still count toward that seat's final score for
    # rank labels — the transition-crediting buffers drop it by design.
    import fh_mahjong_ai.oracle as oracle_mod
    from fh_mahjong_ai.oracle import collect_b2b_rollouts
    from fh_mahjong_ai.types import Observation, StepResult

    rng = np.random.default_rng(0)

    def _obs(seat):
        mask = np.zeros(204, dtype=np.int8)
        mask[:4] = 1
        return Observation(
            seat=seat,
            planes=rng.random((51, 42, 1), dtype=np.float32),
            scalars=rng.random(58, dtype=np.float32),
            action_mask=mask,
            event_history=np.asarray([0x140], dtype=np.uint32),
        )

    class _ScriptedEnv:
        """Seat 0 acts twice; seat 1's only decision comes AFTER a step whose
        rewards already paid seat 3 (who never acts). Match ends on step 3."""

        def __init__(self, cfg, bridge=None):
            self.last_reset_result = None
            self._t = 0

        def reset(self, seed=None):
            self._t = 0
            self.last_reset_result = StepResult(
                observation=_obs(0), rewards=np.zeros(4, dtype=np.float32),
                terminated=False, truncated=False, info={})
            return _obs(0)

        def step(self, action):
            self._t += 1
            if self._t == 1:
                # Seat 3 gets paid before ever acting; seat 0 loses.
                return StepResult(observation=_obs(1),
                                  rewards=np.asarray([-1.0, 0.0, 0.0, 1.0], dtype=np.float32),
                                  terminated=False, truncated=False, info={})
            if self._t == 2:
                return StepResult(observation=_obs(0),
                                  rewards=np.zeros(4, dtype=np.float32),
                                  terminated=False, truncated=False, info={})
            return StepResult(observation=_obs(0),
                              rewards=np.zeros(4, dtype=np.float32),
                              terminated=True, truncated=False,
                              info={"round_outcome": {"is_draw": True, "winner_seat": 0,
                                                      "win_type_name": "ACTION_UNKNOWN",
                                                      "discarder_seat": 0}})

    monkeypatch.setattr(oracle_mod, "MahjongEnv", _ScriptedEnv)
    monkeypatch.setattr(oracle_mod, "build_bridge", lambda cfg: None)

    env = EnvConfig(bridge_kind="mock", event_history_window=8, oracle_observation=True,
                    max_steps_per_episode=16)
    model = PolicyValueNet(EnvConfig(bridge_kind="mock"),
                           ModelConfig(**_SMALL, event_window=8,
                                       privileged_critic=True, aux_heads=True))
    config = PPOConfig(device="cpu", matches_per_iter=1, max_steps_per_episode=16,
                       match_mode="chongci")
    batch = collect_b2b_rollouts(env, model, config, base_seed=1)
    # Final scores (reward scale, start 2.0): seat0 = 1.0, seat3 = 3.0,
    # seats 1/2 = 2.0. Ranks: seat3=0, {seat1,seat2}={1,2} by seat order,
    # seat0=3. Rows are seat-contiguous: seat 0 has 2 rows, seat 1 has 1.
    assert batch.rank_labels.tolist() == [3, 3, 1]


def test_rank_labels_exact_at_bust_threshold(monkeypatch):
    # float32 reward accumulation must not flip an exact-threshold bust:
    # 20 deltas of -0.1 (float32) sum to ~-2.0000001; integer-point rounding
    # reconstructs exactly -2000, so start 2000 -> final 0 <= 0 -> BUSTED.
    import fh_mahjong_ai.oracle as oracle_mod
    from fh_mahjong_ai.oracle import collect_b2b_rollouts
    from fh_mahjong_ai.types import Observation, StepResult

    rng = np.random.default_rng(1)

    def _obs(seat):
        mask = np.zeros(204, dtype=np.int8)
        mask[:4] = 1
        return Observation(
            seat=seat,
            planes=rng.random((51, 42, 1), dtype=np.float32),
            scalars=rng.random(58, dtype=np.float32),
            action_mask=mask,
            event_history=np.asarray([0x140], dtype=np.uint32),
        )

    class _DriftEnv:
        def __init__(self, cfg, bridge=None):
            self.last_reset_result = None
            self._t = 0

        def reset(self, seed=None):
            self._t = 0
            self.last_reset_result = StepResult(
                observation=_obs(0), rewards=np.zeros(4, dtype=np.float32),
                terminated=False, truncated=False, info={})
            return _obs(0)

        def step(self, action):
            self._t += 1
            rewards = np.asarray([np.float32(-0.1), np.float32(0.1), 0.0, 0.0], dtype=np.float32)
            terminated = self._t >= 20
            info = ({"round_outcome": {"is_draw": True, "winner_seat": 0,
                                       "win_type_name": "ACTION_UNKNOWN", "discarder_seat": 0}}
                    if terminated else {})
            return StepResult(observation=_obs(0), rewards=rewards,
                              terminated=terminated, truncated=False, info=info)

    monkeypatch.setattr(oracle_mod, "MahjongEnv", _DriftEnv)
    monkeypatch.setattr(oracle_mod, "build_bridge", lambda cfg: None)

    env = EnvConfig(bridge_kind="mock", event_history_window=8, oracle_observation=True,
                    max_steps_per_episode=64)
    model = PolicyValueNet(EnvConfig(bridge_kind="mock"),
                           ModelConfig(**_SMALL, event_window=8,
                                       privileged_critic=True, aux_heads=True))
    config = PPOConfig(device="cpu", matches_per_iter=1, max_steps_per_episode=64,
                       match_mode="chongci")
    batch = collect_b2b_rollouts(env, model, config, base_seed=2)
    # Seat 0 ends at exactly the bust threshold (2000 - 2000 = 0 <= 0): BUSTED.
    assert set(batch.rank_labels[:1].tolist()) == {4}


def test_zero_outcome_chongci_collection_fails_fast(monkeypatch):
    # A bridge predating chongci round-outcome delivery yields completed
    # matches with zero outcomes — the collector must refuse, not silently
    # train the deal-in head on all-negative labels.
    import fh_mahjong_ai.oracle as oracle_mod
    from fh_mahjong_ai.oracle import collect_b2b_rollouts
    from fh_mahjong_ai.types import Observation, StepResult

    rng = np.random.default_rng(4)

    def _obs(seat):
        mask = np.zeros(204, dtype=np.int8)
        mask[:4] = 1
        return Observation(seat=seat, planes=rng.random((51, 42, 1), dtype=np.float32),
                           scalars=rng.random(58, dtype=np.float32), action_mask=mask,
                           event_history=np.asarray([0x140], dtype=np.uint32))

    class _NoOutcomeEnv:
        def __init__(self, cfg, bridge=None):
            self.last_reset_result = None
            self._t = 0

        def reset(self, seed=None):
            self._t = 0
            self.last_reset_result = StepResult(observation=_obs(0),
                                                rewards=np.zeros(4, dtype=np.float32),
                                                terminated=False, truncated=False, info={})
            return _obs(0)

        def step(self, action):
            self._t += 1
            return StepResult(observation=_obs(0), rewards=np.zeros(4, dtype=np.float32),
                              terminated=self._t >= 4, truncated=False, info={})

    monkeypatch.setattr(oracle_mod, "MahjongEnv", _NoOutcomeEnv)
    monkeypatch.setattr(oracle_mod, "build_bridge", lambda cfg: None)

    env = EnvConfig(bridge_kind="mock", event_history_window=8, oracle_observation=True,
                    max_steps_per_episode=16)
    model = PolicyValueNet(EnvConfig(bridge_kind="mock"),
                           ModelConfig(**_SMALL, event_window=8,
                                       privileged_critic=True, aux_heads=True))
    config = PPOConfig(device="cpu", matches_per_iter=1, max_steps_per_episode=16,
                       match_mode="chongci")
    with pytest.raises(RuntimeError, match="rebuild it"):
        collect_b2b_rollouts(env, model, config, base_seed=5)


def test_rank_labels_share_competition_rank_on_ties():
    # Tied scores share a rank (competition ranking, matching the engine's
    # standings) — an arbitrary tiebreak would teach one tied leader that it
    # finished second, injecting contradictory gradients.
    from fh_mahjong_ai.oracle import _assemble_hindsight_labels

    rows = [(0, 0), (1, 0), (2, 0), (3, 0)]
    # Two-way tie at the top.
    _, rank = _assemble_hindsight_labels(rows, {}, {0: 3000.0, 1: 3000.0, 2: 1000.0, 3: 500.0},
                                         bust_threshold=0.0, truncated=False)
    assert rank.tolist() == [0, 0, 2, 3]

    # Four-way tie: everyone shares rank 0.
    _, rank4 = _assemble_hindsight_labels(rows, {}, {k: 2000.0 for k in range(4)},
                                          bust_threshold=0.0, truncated=False)
    assert rank4.tolist() == [0, 0, 0, 0]

    # Tie below a bust: busted seat stays class 4, tie shares rank above it.
    _, rankb = _assemble_hindsight_labels(rows, {}, {0: 1500.0, 1: 1500.0, 2: -100.0, 3: 4000.0},
                                          bust_threshold=0.0, truncated=False)
    assert rankb.tolist() == [1, 1, 4, 0]
