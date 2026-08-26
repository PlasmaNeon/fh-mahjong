import hashlib
import re

import numpy as np
import pytest
import torch

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.train_b2b import build_b2b_model, collect_b2b_rollouts, train_b2b
from fh_mahjong_ai.ppo import PPOConfig
from fh_mahjong_ai.storage import save_checkpoint
from conftest import SMALL_MODEL



def _champion(tmp_path):
    env39 = EnvConfig(bridge_kind="mock")
    model = PolicyValueNet(env39, ModelConfig(**SMALL_MODEL))
    path = tmp_path / "champion.pt"
    save_checkpoint(path, model)
    return env39, path


def test_warm_start_logit_equivalence(tmp_path):
    env39, champion_path = _champion(tmp_path)
    champion = PolicyValueNet(env39, ModelConfig(**SMALL_MODEL))
    from fh_mahjong_ai.storage import load_checkpoint
    load_checkpoint(champion_path, champion)
    champion.eval()

    b2b_config = ModelConfig(**SMALL_MODEL, event_window=16, privileged_critic=True, aux_heads=True)
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
    model = PolicyValueNet(env39, ModelConfig(**SMALL_MODEL, event_window=8,
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
    from fh_mahjong_ai.train_b2b import _assemble_hindsight_labels

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
    history = train_b2b(env, ModelConfig(**SMALL_MODEL, event_window=8, privileged_critic=True,
                                         aux_heads=True),
                        champion_path, tmp_path / "ckpt", config, base_seed=5)
    assert len(history) == 2
    assert (tmp_path / "ckpt" / "iter_002.pt").exists()
    for key in ("belief_loss", "dealin_loss", "rank_loss"):
        assert key in history[0]
    # mortal-scale-scratch: the default (champion warm-start) construction path
    # records its own provenance too, not just --scratch runs.
    payload = torch.load(tmp_path / "ckpt" / "iter_002.pt", map_location="cpu")
    assert payload["metadata"]["init"] == {"kind": "champion",
                                          "bc_checkpoint_sha256": None,
                                          "bc_checkpoint_path": None}


def test_iteration_rollout_released_before_next_collect(tmp_path, monkeypatch):
    """Amendment 8 (data-scale-960) lifetime gauntlet: at entry to iteration
    2's collection, after test-side garbage collection, the ENTIRE previous
    iteration's rollout must be unreachable — the RolloutBatch object, every
    required and optional field array, and the derived advantages/returns.

    Before the `del batch, advantages, returns` fix in train_b2b's loop this
    test FAILS (verified against the pre-fix tree: the loop locals keep ~17GiB
    of iteration N's rollout alive through the whole of iteration N+1's
    collection at 960 matches — the breach that killed the lap at iteration
    2). Only test-side gc is used; the production fix is plain rebinding."""
    import gc
    import weakref

    from fh_mahjong_ai import train_b2b as train_b2b_mod
    from fh_mahjong_ai.ppo import RolloutBatch as _RB

    refs: list = []
    calls = {"n": 0}
    real_collect = train_b2b_mod.collect_b2b_rollouts
    real_gae = train_b2b_mod.compute_gae
    field_names = (
        "planes", "scalars", "action_mask", "actions", "old_logprobs",
        "values", "rewards", "dones", "events", "event_lengths",
        "dealin_labels", "rank_labels",
    )

    def wrapped_collect(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            gc.collect()
            alive = [r for r in refs if r() is not None]
            assert refs and not alive, (
                f"{len(alive)} of {len(refs)} prior-iteration references "
                "still alive at entry to iteration 2 collection "
                "(Amendment 8 lifetime violation)")
        batch = real_collect(*args, **kwargs)
        if calls["n"] == 1:
            refs.append(weakref.ref(batch))
            for name in field_names:
                arr = getattr(batch, name)
                if arr is not None:
                    refs.append(weakref.ref(arr))
        return batch

    def wrapped_gae(rewards, values, dones, gamma, lam):
        adv, ret = real_gae(rewards, values, dones, gamma, lam)
        if calls["n"] == 1:
            refs.append(weakref.ref(adv))
            refs.append(weakref.ref(ret))
        return adv, ret

    monkeypatch.setattr(train_b2b_mod, "collect_b2b_rollouts", wrapped_collect)
    monkeypatch.setattr(train_b2b_mod, "compute_gae", wrapped_gae)

    env39, champion_path = _champion(tmp_path)
    env = EnvConfig(bridge_kind="mock", event_history_window=8, oracle_observation=True,
                    max_steps_per_episode=16)
    config = PPOConfig(device="cpu", iterations=2, matches_per_iter=2,
                       max_steps_per_episode=16, ppo_epochs=1, minibatch_size=8,
                       num_workers=1, match_mode="classic")
    history = train_b2b(env, ModelConfig(**SMALL_MODEL, event_window=8, privileged_critic=True,
                                         aux_heads=True),
                        champion_path, tmp_path / "ckpt", config, base_seed=5)
    assert calls["n"] == 2
    assert len(history) == 2
    # Optional-field weakrefs registered: batch + 12 fields + adv + ret = 15.
    assert len(refs) == 15


def test_collect_b2b_forwards_chongci_config_to_bridge(monkeypatch):
    # The bridge must simulate under the SAME chongci values the hindsight
    # labels are computed with — a silent mismatch here mislabels every rank.
    from fh_mahjong_ai import train_b2b as train_b2b_mod
    from fh_mahjong_ai.bridge import build_bridge as real_build_bridge

    captured = {}

    def capturing_build_bridge(cfg):
        captured["cfg"] = cfg
        return real_build_bridge(cfg)

    monkeypatch.setattr(train_b2b_mod, "build_bridge", capturing_build_bridge)

    env = EnvConfig(bridge_kind="mock", event_history_window=8, oracle_observation=True,
                    max_steps_per_episode=16,
                    chongci_starting_score=3333, chongci_bust_threshold=111,
                    chongci_max_hands=7)
    model = PolicyValueNet(EnvConfig(bridge_kind="mock"),
                           ModelConfig(**SMALL_MODEL, event_window=8,
                                       privileged_critic=True, aux_heads=True))
    config = PPOConfig(device="cpu", matches_per_iter=1, max_steps_per_episode=16,
                       match_mode="chongci")
    from fh_mahjong_ai.train_b2b import collect_b2b_rollouts
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
    from fh_mahjong_ai.train_b2b import _assemble_hindsight_labels

    rows = [(0, 0), (1, 0), (2, 0), (3, 0)]
    # Reward-scale final scores: start 2.0 (=2000 pts / 1000) + net deltas.
    final_scores = {0: 2.0 + 1.5, 1: 2.0 + 1.0, 2: 2.0 - 2.5, 3: 2.0 + 0.0}
    dealin, rank = _assemble_hindsight_labels(rows, {}, final_scores,
                                              bust_threshold=0.0, truncated=False)
    assert rank.tolist() == [0, 1, 4, 2]  # seat 2 busted, NOT ranked


def test_infer_model_config_rejects_b2b_checkpoints(tmp_path):
    # CheckpointPolicy.from_checkpoint relies on infer_model_config, which
    # cannot reconstruct B2b modules — it must fail with a CLEAR message
    # telling the caller to re-save with metadata or pass explicit flags, not
    # a cryptic load_state_dict error.
    import pytest as _pytest

    from fh_mahjong_ai.model import infer_model_config

    env39 = EnvConfig(bridge_kind="mock")
    model = PolicyValueNet(env39, ModelConfig(**SMALL_MODEL, event_window=8,
                                              privileged_critic=True, aux_heads=True))
    with _pytest.raises(RuntimeError, match="no usable metadata"):
        infer_model_config(model.state_dict())

    # Legacy checkpoints still infer fine.
    legacy = PolicyValueNet(env39, ModelConfig(**SMALL_MODEL))
    config = infer_model_config(legacy.state_dict())
    assert config.residual_blocks == 1


def test_rank_labels_include_pre_first_decision_rewards(monkeypatch):
    # A payout landing BEFORE a seat's first decision (e.g. dealer tsumo on
    # the opening hand) must still count toward that seat's final score for
    # rank labels — the transition-crediting buffers drop it by design.
    from fh_mahjong_ai import train_b2b as train_b2b_mod
    from fh_mahjong_ai.train_b2b import collect_b2b_rollouts
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

    monkeypatch.setattr(train_b2b_mod, "MahjongEnv", _ScriptedEnv)
    monkeypatch.setattr(train_b2b_mod, "build_bridge", lambda cfg: None)

    env = EnvConfig(bridge_kind="mock", event_history_window=8, oracle_observation=True,
                    max_steps_per_episode=16)
    model = PolicyValueNet(EnvConfig(bridge_kind="mock"),
                           ModelConfig(**SMALL_MODEL, event_window=8,
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
    from fh_mahjong_ai import train_b2b as train_b2b_mod
    from fh_mahjong_ai.train_b2b import collect_b2b_rollouts
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

    monkeypatch.setattr(train_b2b_mod, "MahjongEnv", _DriftEnv)
    monkeypatch.setattr(train_b2b_mod, "build_bridge", lambda cfg: None)

    env = EnvConfig(bridge_kind="mock", event_history_window=8, oracle_observation=True,
                    max_steps_per_episode=64)
    model = PolicyValueNet(EnvConfig(bridge_kind="mock"),
                           ModelConfig(**SMALL_MODEL, event_window=8,
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
    from fh_mahjong_ai import train_b2b as train_b2b_mod
    from fh_mahjong_ai.train_b2b import collect_b2b_rollouts
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

    monkeypatch.setattr(train_b2b_mod, "MahjongEnv", _NoOutcomeEnv)
    monkeypatch.setattr(train_b2b_mod, "build_bridge", lambda cfg: None)

    env = EnvConfig(bridge_kind="mock", event_history_window=8, oracle_observation=True,
                    max_steps_per_episode=16)
    model = PolicyValueNet(EnvConfig(bridge_kind="mock"),
                           ModelConfig(**SMALL_MODEL, event_window=8,
                                       privileged_critic=True, aux_heads=True))
    config = PPOConfig(device="cpu", matches_per_iter=1, max_steps_per_episode=16,
                       match_mode="chongci")
    with pytest.raises(RuntimeError, match="rebuild it"):
        collect_b2b_rollouts(env, model, config, base_seed=5)


def test_rank_labels_share_competition_rank_on_ties():
    # Tied scores share a rank (competition ranking, matching the engine's
    # standings) — an arbitrary tiebreak would teach one tied leader that it
    # finished second, injecting contradictory gradients.
    from fh_mahjong_ai.train_b2b import _assemble_hindsight_labels

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


def test_warm_start_rejects_architecture_mismatch(tmp_path):
    # A 2-block B2b config warm-started from a 4-block champion silently
    # dropped champion layers (step-0 logits drifted) — it must fail closed.
    import pytest as _pytest

    env39 = EnvConfig(bridge_kind="mock")
    champion4 = PolicyValueNet(env39, ModelConfig(**{**SMALL_MODEL, "residual_blocks": 2}))
    path = tmp_path / "champion4.pt"
    from fh_mahjong_ai.storage import save_checkpoint as _save
    _save(path, champion4)

    mismatched = ModelConfig(**SMALL_MODEL, event_window=8, privileged_critic=True, aux_heads=True)
    assert mismatched.residual_blocks == 1  # differs from the 2-block champion
    with _pytest.raises(RuntimeError, match="architecturally incompatible"):
        build_b2b_model(env39, mismatched, path)


def test_train_b2b_halts_on_truncation_rate(tmp_path, monkeypatch):
    # Truncated matches keep censored returns; a rising truncation rate is
    # the stall-exploit signature and must halt the run loudly.
    from fh_mahjong_ai import train_b2b as train_b2b_mod
    from fh_mahjong_ai.train_b2b import train_b2b
    from fh_mahjong_ai.ppo import RolloutBatch

    def _all_truncated_collect(env_config, model, config, base_seed):
        n = 8
        rng = np.random.default_rng(0)
        return RolloutBatch(
            planes=rng.random((n, 51, 42, 1), dtype=np.float32),
            scalars=rng.random((n, 58), dtype=np.float32),
            action_mask=np.ones((n, 204), dtype=np.int8),
            actions=rng.integers(0, 204, size=n),
            old_logprobs=(rng.random(n) * -1).astype(np.float32),
            values=rng.random(n).astype(np.float32),
            rewards=rng.random(n).astype(np.float32),
            dones=np.ones(n, dtype=np.float32),
            truncated_matches=2,  # 2 of 2 matches truncated
            events=rng.integers(0, 0x10000, size=(n, 8), dtype=np.uint32),
            event_lengths=rng.integers(0, 9, size=n).astype(np.int32),
            dealin_labels=np.zeros(n, dtype=np.float32),
            rank_labels=np.full(n, -1, dtype=np.int64),
        )

    monkeypatch.setattr(train_b2b_mod, "collect_b2b_rollouts", _all_truncated_collect)

    env39, champion_path = _champion(tmp_path)
    env = EnvConfig(bridge_kind="mock", event_history_window=8, oracle_observation=True,
                    max_steps_per_episode=16)
    config = PPOConfig(device="cpu", iterations=1, matches_per_iter=2,
                       max_steps_per_episode=16, ppo_epochs=1, minibatch_size=8,
                       num_workers=1, match_mode="chongci")
    with pytest.raises(RuntimeError, match="truncation rate"):
        train_b2b(env, ModelConfig(**SMALL_MODEL, event_window=8, privileged_critic=True,
                                   aux_heads=True),
                  champion_path, tmp_path / "ckpt2", config, base_seed=9)


from fh_mahjong_ai.placement_bonus import PLACEMENT_RESHAPE_VALUES, placement_utilities


_GO_ENV = dict(bridge_kind="go", event_history_window=8, oracle_observation=True,
               # 4000 truncates a full 50-hand chongci match for this seed/model
               # (verified empirically); 20000 completes both matches cleanly so
               # the "on" test exercises the intended untruncated-terminal path.
               max_steps_per_episode=20000)


def _go_collect(lam, values, matches=2, seed=4242):
    env = EnvConfig(**_GO_ENV)
    # Fixed model-init seed so two calls with the same base_seed produce
    # identical weights — collect_b2b_rollouts's per-match torch.manual_seed
    # only controls action sampling, not the model constructed by the caller
    # before collect_b2b_rollouts is ever invoked.
    torch.manual_seed(0)
    model = PolicyValueNet(EnvConfig(bridge_kind="go"),
                           ModelConfig(**SMALL_MODEL, event_window=8,
                                       privileged_critic=True, aux_heads=True))
    cfg = PPOConfig(device="cpu", matches_per_iter=matches, max_steps_per_episode=20000,
                    match_mode="chongci", placement_bonus_values=values,
                    placement_bonus_lambda=lam)
    return collect_b2b_rollouts(env, model, cfg, base_seed=seed)


def _segments(batch):
    """Row index of each done=1, i.e. each seat-block's last row, in order."""
    return np.flatnonzero(batch.dones == 1.0)


def test_bonus_off_is_byte_identical_and_has_telemetry():
    a = _go_collect(0.0, None)
    b = _go_collect(0.0, None)
    assert np.array_equal(a.rewards, b.rewards)
    assert a.match_telemetry is not None and len(a.match_telemetry) == 2
    t = a.match_telemetry[0]
    assert set(t) >= {"seed", "final_scores", "trajectory_returns", "utilities", "bonus", "tied_seats_surplus", "busts"}
    assert t["seed"] == 4242 and np.allclose(t["bonus"], 0.0)


def test_bonus_attaches_once_per_seat_on_own_last_row_and_sums_to_zero():
    off = _go_collect(0.0, None)
    on = _go_collect(0.7, PLACEMENT_RESHAPE_VALUES)
    assert off.rewards.shape == on.rewards.shape
    assert np.array_equal(off.dones, on.dones)
    diff = on.rewards - off.rewards
    ends = _segments(off)
    # every non-terminal row untouched
    mask = np.ones_like(diff, dtype=bool); mask[ends] = False
    assert np.array_equal(diff[mask], np.zeros(mask.sum(), np.float32))
    # terminal rows carry exactly lambda*utility, in seat order per match
    expected = np.concatenate([0.7 * placement_utilities(t["final_scores"]) for t in on.match_telemetry])
    assert np.allclose(diff[ends], expected.astype(np.float32), atol=1e-6)
    for t in on.match_telemetry:
        assert abs(sum(t["bonus"])) < 1e-6
        assert np.allclose(t["bonus"], 0.7 * np.asarray(t["utilities"]))
    # everything else byte-identical
    for name in ("planes", "scalars", "action_mask", "actions", "old_logprobs", "values",
                 "events", "event_lengths", "dealin_labels", "rank_labels"):
        assert np.array_equal(getattr(off, name), getattr(on, name)), name


def test_bonus_fails_closed_on_truncation():
    env = EnvConfig(**{**_GO_ENV, "max_steps_per_episode": 8})
    model = PolicyValueNet(EnvConfig(bridge_kind="go"),
                           ModelConfig(**SMALL_MODEL, event_window=8,
                                       privileged_critic=True, aux_heads=True))
    cfg = PPOConfig(device="cpu", matches_per_iter=1, max_steps_per_episode=8,
                    match_mode="chongci", placement_bonus_values=PLACEMENT_RESHAPE_VALUES,
                    placement_bonus_lambda=0.5)
    with pytest.raises(RuntimeError, match="placement bonus.*truncat"):
        collect_b2b_rollouts(env, model, cfg, base_seed=1)


def test_bonus_fails_closed_on_zero_decision_seat_or_passes():
    env = EnvConfig(bridge_kind="mock", event_history_window=8, oracle_observation=True,
                    max_steps_per_episode=3)
    model = PolicyValueNet(EnvConfig(bridge_kind="mock"),
                           ModelConfig(**SMALL_MODEL, event_window=8,
                                       privileged_critic=True, aux_heads=True))
    cfg = PPOConfig(device="cpu", matches_per_iter=1, max_steps_per_episode=3,
                    match_mode="classic", placement_bonus_values=PLACEMENT_RESHAPE_VALUES,
                    placement_bonus_lambda=0.5)
    try:
        batch = collect_b2b_rollouts(env, model, cfg, base_seed=0)
    except RuntimeError as e:
        assert "placement bonus" in str(e)
        return
    assert int((batch.dones == 1).sum()) == 4


def test_checkpoint_metadata_records_objective(tmp_path):
    env39, champion_path = _champion(tmp_path)
    env = EnvConfig(bridge_kind="mock", event_history_window=8, oracle_observation=True,
                    max_steps_per_episode=16)
    config = PPOConfig(device="cpu", iterations=2, matches_per_iter=2,
                       max_steps_per_episode=16, ppo_epochs=1, minibatch_size=8,
                       num_workers=1, match_mode="classic")
    history = train_b2b(env, ModelConfig(**SMALL_MODEL, event_window=8, privileged_critic=True,
                                         aux_heads=True),
                        champion_path, tmp_path / "ckpt", config, base_seed=5)
    payload = torch.load(tmp_path / "ckpt" / "iter_001.pt", map_location="cpu")
    obj = payload["metadata"]["objective"]
    assert obj == {"placement_bonus_values": None, "placement_bonus_lambda": 0.0,
                   "placement_bonus_calibration_digest": ""}


def test_cli_placement_bonus_args_roundtrip():
    import argparse
    from fh_mahjong_ai.placement_bonus_args import add_placement_bonus_args, placement_bonus_kwargs
    p = argparse.ArgumentParser(); add_placement_bonus_args(p)
    a = p.parse_args(["--placement-bonus-values", "0.86", "0.35", "-0.05", "-1.16",
                      "--placement-bonus-lambda", "0.42", "--placement-bonus-calibration-digest", "abc"])
    assert placement_bonus_kwargs(a) == {"placement_bonus_values": (0.86, 0.35, -0.05, -1.16),
                                         "placement_bonus_lambda": 0.42,
                                         "placement_bonus_calibration_digest": "abc"}
    assert placement_bonus_kwargs(p.parse_args([])) == {"placement_bonus_values": None,
                                                        "placement_bonus_lambda": 0.0,
                                                        "placement_bonus_calibration_digest": ""}
    with pytest.raises(SystemExit):
        placement_bonus_kwargs(p.parse_args(["--placement-bonus-lambda", "0.5"]))  # lambda without values is an error


def test_cli_placement_bonus_args_rejects_non_centered_values():
    import argparse
    from fh_mahjong_ai.placement_bonus import PLACEMENT_RESHAPE_VALUES
    from fh_mahjong_ai.placement_bonus_args import add_placement_bonus_args, placement_bonus_kwargs
    p = argparse.ArgumentParser(); add_placement_bonus_args(p)
    with pytest.raises(SystemExit):
        placement_bonus_kwargs(p.parse_args(["--placement-bonus-values", "10", "5", "1", "-10"]))
    # The registered centered vector (|mean| ~= 2.5e-11) must still be accepted.
    a = p.parse_args(["--placement-bonus-values", *[str(v) for v in PLACEMENT_RESHAPE_VALUES]])
    assert placement_bonus_kwargs(a)["placement_bonus_values"] == tuple(PLACEMENT_RESHAPE_VALUES)


def test_bonus_fails_closed_on_reset_terminal(monkeypatch):
    # A four-seat terminal standing can arrive AT reset (e.g. a pre-play
    # resolution) before any decision loop ever runs. With the bonus on this
    # must fail closed like the other terminal-rank-missing paths; with the
    # bonus off it stays today's silent-skip behavior — the collection still
    # succeeds off a second, normal match.
    from fh_mahjong_ai import train_b2b as train_b2b_mod
    from fh_mahjong_ai.types import Observation, StepResult

    rng = np.random.default_rng(7)

    def _obs(seat=0):
        mask = np.zeros(204, dtype=np.int8)
        mask[:4] = 1
        return Observation(seat=seat, planes=rng.random((51, 42, 1), dtype=np.float32),
                           scalars=rng.random(58, dtype=np.float32), action_mask=mask,
                           event_history=np.asarray([0x140], dtype=np.uint32))

    class _TerminatedResetEnv:
        """The FIRST match's reset() itself reports a terminated four-seat
        standing — no decision loop runs for it. The SECOND match is a
        normal single-seat completed match, so the bonus-off case can prove
        the reset-terminal match is silently skipped rather than the whole
        collection failing outright."""

        def __init__(self, cfg, bridge=None):
            self.last_reset_result = None
            self._match = 0
            self._t = 0

        def reset(self, seed=None):
            self._match += 1
            self._t = 0
            terminated_at_reset = self._match == 1
            self.last_reset_result = StepResult(
                observation=_obs(0), rewards=np.zeros(4, dtype=np.float32),
                terminated=terminated_at_reset, truncated=False, info={})
            return _obs(0)

        def step(self, action):
            if self._match == 1:
                raise AssertionError(
                    "step() should never be called: match 1 ends at reset")
            self._t += 1
            terminated = self._t >= 4
            info = ({"round_outcome": {"is_draw": True, "winner_seat": 0,
                                       "win_type_name": "ACTION_UNKNOWN",
                                       "discarder_seat": 0}} if terminated else {})
            return StepResult(observation=_obs(0), rewards=np.zeros(4, dtype=np.float32),
                              terminated=terminated, truncated=False, info=info)

    monkeypatch.setattr(train_b2b_mod, "MahjongEnv", _TerminatedResetEnv)
    monkeypatch.setattr(train_b2b_mod, "build_bridge", lambda cfg: None)

    env = EnvConfig(bridge_kind="mock", event_history_window=8, oracle_observation=True,
                    max_steps_per_episode=16)
    model = PolicyValueNet(EnvConfig(bridge_kind="mock"),
                           ModelConfig(**SMALL_MODEL, event_window=8,
                                       privileged_critic=True, aux_heads=True))

    cfg_on = PPOConfig(device="cpu", matches_per_iter=1, max_steps_per_episode=16,
                       match_mode="chongci", placement_bonus_values=PLACEMENT_RESHAPE_VALUES,
                       placement_bonus_lambda=0.5)
    with pytest.raises(RuntimeError, match="placement bonus.*reset"):
        collect_b2b_rollouts(env, model, cfg_on, base_seed=0)

    cfg_off = PPOConfig(device="cpu", matches_per_iter=2, max_steps_per_episode=16,
                        match_mode="chongci")
    batch = collect_b2b_rollouts(env, model, cfg_off, base_seed=0)
    assert batch.match_telemetry is not None and len(batch.match_telemetry) == 1
    assert int((batch.dones == 1).sum()) == 1


# ---------------------------------------------------------------------------
# mortal-scale-scratch: the random-init construction path (`--scratch`).
# ---------------------------------------------------------------------------


def _bc_checkpoint(tmp_path, model_config):
    """A BC-stage checkpoint: full net, saved with model_config metadata (Task 2 format)."""
    from fh_mahjong_ai.storage import model_config_metadata
    model = PolicyValueNet(EnvConfig(bridge_kind="mock"), model_config)
    path = tmp_path / "bc.pt"
    save_checkpoint(path, model, metadata={"model_config": model_config_metadata(model_config)})
    return model, path


def test_build_scratch_model_is_random_init_with_full_config(tmp_path):
    from fh_mahjong_ai.train_b2b import build_scratch_model
    cfg = ModelConfig(**SMALL_MODEL, kernel_width=1, event_window=8, privileged_critic=True, aux_heads=True)
    a = build_scratch_model(EnvConfig(bridge_kind="mock"), cfg)
    b = build_scratch_model(EnvConfig(bridge_kind="mock"), cfg)
    assert a.model_config == cfg
    assert tuple(a.state_dict()["plane_stem.0.weight"].shape[2:]) == (3, 1)
    assert not torch.equal(a.trunk[0].weight, b.trunk[0].weight)  # no anchor, no parity


def test_build_scratch_model_init_from_bc_loads_exactly_the_bc_prefixes(tmp_path):
    from fh_mahjong_ai.train_b2b import SCRATCH_BC_PREFIXES, build_scratch_model
    cfg = ModelConfig(**SMALL_MODEL, kernel_width=1, event_window=8, privileged_critic=True, aux_heads=True)
    bc_model, bc_path = _bc_checkpoint(tmp_path, cfg)
    model = build_scratch_model(EnvConfig(bridge_kind="mock"), cfg, bc_checkpoint=bc_path)
    bc_sd, sd = bc_model.state_dict(), model.state_dict()
    event_dim = model.event_encoder.output_dim
    for key in sd:
        if not key.startswith(SCRATCH_BC_PREFIXES):
            continue
        if key == "trunk.0.weight":
            # The one deliberate exception (fix round 1, I1): trunk.0's leading
            # plane+scalar columns are BC's verbatim, but its trailing event
            # columns are zeroed rather than copied -- BC never trained them
            # (it runs with events=None) and this net's event encoder is new.
            # See test_..._step0_logits_equal_bc_policy for why that matters.
            assert torch.equal(sd[key][:, :-event_dim], bc_sd[key][:, :-event_dim]), key
            assert torch.equal(sd[key][:, -event_dim:],
                               torch.zeros_like(sd[key][:, -event_dim:])), key
            continue
        assert torch.equal(sd[key], bc_sd[key]), key
    assert not torch.equal(sd["value_head.0.weight"], bc_sd["value_head.0.weight"])
    assert not torch.equal(sd["event_encoder.gru.weight_ih_l0"], bc_sd["event_encoder.gru.weight_ih_l0"])


def test_build_scratch_model_init_from_bc_step0_logits_equal_bc_policy(tmp_path):
    """Fix round 1, I1: BC trains with `events=None`, which feeds the trunk a
    ZERO event vector -- so trunk.0's trailing event columns reach us at BC's
    untouched random init while THIS net's event encoder is brand new and
    outputs nonzero features. Copying those columns verbatim would make step 0
    noise, not the BC policy. They are zeroed on load, so identical
    planes/scalars give identical logits with a live event encoder feeding
    random events. Values are NOT asserted: the value head stays random."""
    from fh_mahjong_ai.train_b2b import build_scratch_model
    cfg = ModelConfig(**SMALL_MODEL, kernel_width=1, event_window=8, privileged_critic=True, aux_heads=True)
    bc_model, bc_path = _bc_checkpoint(tmp_path, cfg)
    bc_model.eval()
    model = build_scratch_model(EnvConfig(bridge_kind="mock"), cfg, bc_checkpoint=bc_path)

    rng = np.random.default_rng(7)
    planes = torch.from_numpy(rng.random((4, 39, 42, 1), dtype=np.float32))
    scalars = torch.from_numpy(rng.random((4, 58), dtype=np.float32))
    mask = torch.ones((4, 204), dtype=torch.int8)
    events = torch.from_numpy(rng.integers(0, 0x10000, size=(4, 8), dtype=np.uint32).astype(np.int64))
    lengths = torch.full((4,), 8, dtype=torch.int64)

    with torch.no_grad():
        ref, _ = bc_model(planes, scalars, mask)  # BC's own forward: events=None
        got, _ = model(planes, scalars, mask, events=events, event_lengths=lengths)
        event_features = model.event_encoder(events, lengths)
    assert torch.allclose(ref, got, atol=1e-5)
    # Parity comes from the zeroed COLUMNS, not from a dead encoder.
    assert not torch.equal(event_features, torch.zeros_like(event_features))
    assert torch.equal(model.trunk[0].weight[:, -model.event_encoder.output_dim:],
                       torch.zeros_like(model.trunk[0].weight[:, -model.event_encoder.output_dim:]))


def test_build_scratch_model_rejects_growth_blocks(tmp_path):
    """Fix round 1, M1: `growth.` tensors are outside SCRATCH_BC_PREFIXES, so a
    grown scratch net would take a silent partial load from --init-from-bc."""
    from fh_mahjong_ai.train_b2b import build_scratch_model
    cfg = ModelConfig(**SMALL_MODEL, kernel_width=1, event_window=8, privileged_critic=True,
                      aux_heads=True, growth_blocks=2)
    with pytest.raises(ValueError, match="growth_blocks"):
        build_scratch_model(EnvConfig(bridge_kind="mock"), cfg)


def test_build_scratch_model_init_from_bc_rejects_missing_file(tmp_path):
    """Fix round 1, M5: a mistyped --init-from-bc names the flag and the path."""
    from fh_mahjong_ai.train_b2b import build_scratch_model
    cfg = ModelConfig(**SMALL_MODEL, kernel_width=1, event_window=8, privileged_critic=True, aux_heads=True)
    missing = tmp_path / "not-a-checkpoint.pt"
    with pytest.raises(FileNotFoundError, match="init-from-bc"):
        build_scratch_model(EnvConfig(bridge_kind="mock"), cfg, bc_checkpoint=missing)
    with pytest.raises(FileNotFoundError, match=re.escape(str(missing))):
        build_scratch_model(EnvConfig(bridge_kind="mock"), cfg, bc_checkpoint=missing)
    # A directory is not a checkpoint either.
    with pytest.raises(FileNotFoundError, match="init-from-bc"):
        build_scratch_model(EnvConfig(bridge_kind="mock"), cfg, bc_checkpoint=tmp_path)


def test_build_scratch_model_init_from_bc_rejects_shape_mismatch(tmp_path):
    from fh_mahjong_ai.train_b2b import build_scratch_model
    bc_cfg = ModelConfig(**SMALL_MODEL, kernel_width=3, event_window=8, privileged_critic=True, aux_heads=True)
    _, bc_path = _bc_checkpoint(tmp_path, bc_cfg)
    cfg = ModelConfig(**SMALL_MODEL, kernel_width=1, event_window=8, privileged_critic=True, aux_heads=True)
    with pytest.raises(RuntimeError, match="init-from-bc"):
        build_scratch_model(EnvConfig(bridge_kind="mock"), cfg, bc_checkpoint=bc_path)


def test_build_scratch_model_init_from_bc_rejects_missing_prefix(tmp_path):
    from fh_mahjong_ai.train_b2b import build_scratch_model
    cfg = ModelConfig(**SMALL_MODEL, kernel_width=1, event_window=8, privileged_critic=True, aux_heads=True)
    _, bc_path = _bc_checkpoint(tmp_path, cfg)
    payload = torch.load(bc_path, map_location="cpu")
    del payload["model"]["policy_head.weight"]
    torch.save(payload, bc_path)
    with pytest.raises(RuntimeError, match="policy_head.weight"):
        build_scratch_model(EnvConfig(bridge_kind="mock"), cfg, bc_checkpoint=bc_path)


def test_train_b2b_scratch_two_iters_mock_records_init(tmp_path):
    env = EnvConfig(bridge_kind="mock", event_history_window=8, oracle_observation=True,
                    max_steps_per_episode=16)
    config = PPOConfig(device="cpu", iterations=2, matches_per_iter=2,
                       max_steps_per_episode=16, ppo_epochs=1, minibatch_size=8,
                       num_workers=1, match_mode="classic")
    cfg = ModelConfig(**SMALL_MODEL, kernel_width=1, event_window=8, privileged_critic=True, aux_heads=True)
    _, bc_path = _bc_checkpoint(tmp_path, cfg)
    ckpt_dir = tmp_path / "run"
    history = train_b2b(env, cfg, None, ckpt_dir, config, base_seed=3,
                        scratch=True, init_from_bc=bc_path)
    assert len(history) == 2
    payload = torch.load(ckpt_dir / "iter_002.pt", map_location="cpu")
    assert payload["metadata"]["init"]["kind"] == "scratch"
    assert len(payload["metadata"]["init"]["bc_checkpoint_sha256"]) == 64
    # M4: the digest names the exact bytes build_scratch_model loaded, and the
    # path is recorded alongside it so a bare hash can be resolved back by hand.
    assert payload["metadata"]["init"]["bc_checkpoint_sha256"] == \
        hashlib.sha256(bc_path.read_bytes()).hexdigest()
    assert payload["metadata"]["init"]["bc_checkpoint_path"] == str(bc_path)
    assert payload["metadata"]["model_config"]["kernel_width"] == 1


def test_train_b2b_scratch_rejects_champion_and_surgeries(tmp_path):
    env39, champion_path = _champion(tmp_path)
    env = EnvConfig(bridge_kind="mock", event_history_window=8, oracle_observation=True,
                    max_steps_per_episode=16)
    config = PPOConfig(device="cpu", iterations=1, matches_per_iter=2, max_steps_per_episode=16,
                       ppo_epochs=1, minibatch_size=8, num_workers=1, match_mode="classic")
    cfg = ModelConfig(**SMALL_MODEL, event_window=8, privileged_critic=True, aux_heads=True)
    with pytest.raises(ValueError, match="combined with a champion"):
        train_b2b(env, cfg, champion_path, tmp_path / "a", config, scratch=True)
    with pytest.raises(ValueError, match="growth_blocks/widen_event_hidden"):
        train_b2b(env, cfg, None, tmp_path / "b", config, scratch=True, growth_blocks=1)
    with pytest.raises(ValueError, match="required unless scratch"):
        train_b2b(env, cfg, None, tmp_path / "c", config, scratch=False)  # no champion, no scratch
    # Fix round 2, M6: the two remaining library-level guards. --init-from-bc
    # without --scratch would otherwise be silently ignored on a champion
    # warm-start, and --scratch + --widen-event-hidden reaches the SAME
    # rejection as --model-growth-blocks (both surgeries need an anchor).
    _, bc_path = _bc_checkpoint(tmp_path, cfg)
    with pytest.raises(ValueError, match="init_from_bc requires"):
        train_b2b(env, cfg, champion_path, tmp_path / "d", config, scratch=False,
                  init_from_bc=bc_path)
    with pytest.raises(ValueError, match="growth_blocks/widen_event_hidden"):
        train_b2b(env, cfg, None, tmp_path / "e", config, scratch=True, widen_event_hidden=8)


# ---------------------------------------------------------------------------
# mortal-scale-scratch Amendment 1 §6: two-group learning-rate schedule.
# ---------------------------------------------------------------------------


def test_split_bc_parameter_groups_partitions_all_parameters():
    from fh_mahjong_ai.train_b2b import SCRATCH_BC_PREFIXES, split_bc_parameter_groups
    cfg = ModelConfig(**SMALL_MODEL, kernel_width=1, event_window=8, privileged_critic=True, aux_heads=True)
    model = PolicyValueNet(EnvConfig(bridge_kind="mock"), cfg)
    bc, heads = split_bc_parameter_groups(model)
    assert len(bc) + len(heads) == len(list(model.parameters()))
    names = dict(model.named_parameters())
    bc_ids = {id(p) for p in bc}
    for name, p in names.items():
        assert (id(p) in bc_ids) == name.startswith(SCRATCH_BC_PREFIXES), name
    assert any(n.startswith("event_encoder.") for n, p in names.items() if id(p) not in bc_ids)
    assert any(n.startswith("value_head.") for n, p in names.items() if id(p) not in bc_ids)


def test_lr_schedule_switches_after_head_lr_iters_and_keeps_moments():
    from fh_mahjong_ai.train_b2b import apply_lr_schedule, build_optimizer
    cfg = ModelConfig(**SMALL_MODEL, kernel_width=1, event_window=8, privileged_critic=True, aux_heads=True)
    model = PolicyValueNet(EnvConfig(bridge_kind="mock"), cfg)
    config = PPOConfig(lr=2e-5, head_lr=2e-4, head_lr_iters=25)
    opt = build_optimizer(model, config)
    assert len(opt.param_groups) == 2
    assert apply_lr_schedule(opt, config, 1) == {"lr_bc": 2e-5, "lr_heads": 2e-4}
    assert apply_lr_schedule(opt, config, 25) == {"lr_bc": 2e-5, "lr_heads": 2e-4}
    # take one step so moments exist, then switch
    loss = sum(p.sum() for p in model.parameters())
    loss.backward(); opt.step()
    state_before = {k: v["exp_avg"].clone() for k, v in opt.state.items() if "exp_avg" in v}
    assert apply_lr_schedule(opt, config, 26) == {"lr_bc": 2e-5, "lr_heads": 2e-5}
    assert opt.param_groups[1]["lr"] == 2e-5
    for k, v in opt.state.items():
        assert torch.equal(v["exp_avg"], state_before[k])


def test_build_optimizer_single_group_by_default():
    from fh_mahjong_ai.train_b2b import apply_lr_schedule, build_optimizer
    model = PolicyValueNet(EnvConfig(bridge_kind="mock"), ModelConfig(**SMALL_MODEL))
    opt = build_optimizer(model, PPOConfig(lr=3e-5))
    assert len(opt.param_groups) == 1 and opt.param_groups[0]["lr"] == 3e-5
    assert apply_lr_schedule(opt, PPOConfig(lr=3e-5), 7) == {"lr_bc": 3e-5, "lr_heads": 3e-5}


def test_train_b2b_head_lr_requires_init_from_bc(tmp_path):
    env = EnvConfig(bridge_kind="mock", event_history_window=8, oracle_observation=True, max_steps_per_episode=16)
    config = PPOConfig(device="cpu", iterations=1, matches_per_iter=2, max_steps_per_episode=16,
                       ppo_epochs=1, minibatch_size=8, num_workers=1, match_mode="classic", head_lr=2e-4, head_lr_iters=1)
    cfg = ModelConfig(**SMALL_MODEL, kernel_width=1, event_window=8, privileged_critic=True, aux_heads=True)
    with pytest.raises(ValueError, match="head_lr"):
        train_b2b(env, cfg, None, tmp_path / "run", config, scratch=True)


def test_train_b2b_records_lr_telemetry_with_schedule(tmp_path):
    env = EnvConfig(bridge_kind="mock", event_history_window=8, oracle_observation=True, max_steps_per_episode=16)
    config = PPOConfig(device="cpu", iterations=3, matches_per_iter=2, max_steps_per_episode=16,
                       ppo_epochs=1, minibatch_size=8, num_workers=1, match_mode="classic",
                       lr=2e-5, head_lr=2e-4, head_lr_iters=2)
    cfg = ModelConfig(**SMALL_MODEL, kernel_width=1, event_window=8, privileged_critic=True, aux_heads=True)
    _, bc_path = _bc_checkpoint(tmp_path, cfg)
    history = train_b2b(env, cfg, None, tmp_path / "run", config, base_seed=5, scratch=True, init_from_bc=bc_path)
    assert [h["lr_heads"] for h in history] == [2e-4, 2e-4, 2e-5]
    assert all(h["lr_bc"] == 2e-5 for h in history)
