"""Serving the suit-averaged policy: CheckpointPolicy(symmetry="suits"), the parity gate's
reference, the review's evaluate_batch, and agreement with the batched evaluator."""

import os
from pathlib import Path

import numpy as np
import pytest
import torch

from conftest import SMALL_MODEL
from fh_mahjong_ai.batched_eval import _GreedyForward
from fh_mahjong_ai.bridge import build_bridge
from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.env import MahjongEnv
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.policies import SuitAveragedGreedyPolicy
from fh_mahjong_ai.scripts.serving_parity import run_serving_parity
from fh_mahjong_ai.serving import CheckpointPolicy
from fh_mahjong_ai.storage import model_config_metadata, save_checkpoint

requires_go_lib = pytest.mark.skipif(
    not os.environ.get("FH_MAHJONG_BRIDGE_LIB"), reason="needs the Go bridge library"
)
WINDOW = 8


def _model(window=WINDOW) -> PolicyValueNet:
    torch.manual_seed(3)
    return PolicyValueNet(EnvConfig(), ModelConfig(**dict(SMALL_MODEL, event_window=window))).eval()


def _policy(model, symmetry="suits") -> CheckpointPolicy:
    return CheckpointPolicy(model=model, checkpoint_path=Path("m.pt"), checkpoint_step=1,
                            symmetry=symmetry)


def _observations(n=40, window=WINDOW):
    cfg = EnvConfig(bridge_kind="go", learning_seats=(0, 1, 2, 3), auto_play_heuristics=False,
                    match_mode="chongci", chongci_max_hands=4, max_steps_per_episode=4000,
                    event_history_window=window)
    env = MahjongEnv(cfg, build_bridge(cfg))
    rng = np.random.default_rng(9)
    out, obs = [], env.reset(seed=123)
    while len(out) < n:
        out.append(obs)
        step = env.step(int(rng.choice(np.flatnonzero(obs.action_mask))))
        obs = env.reset(seed=int(rng.integers(1, 9999))) if (step.terminated or step.truncated) else step.observation
    env.close()
    return out


def test_rejects_unknown_symmetry():
    with pytest.raises(ValueError, match="symmetry"):
        _policy(_model(), symmetry="dihedral")


@requires_go_lib
def test_served_suit_policy_matches_the_reference_and_the_batched_evaluator():
    model = _model()
    served = _policy(model)
    reference = SuitAveragedGreedyPolicy(model)
    batched = _GreedyForward(model, "cpu", "per_row", 1, symmetry="suits")
    for obs in _observations():
        action = served.choose(obs, return_logits=True)
        assert action.action_id in obs.legal_actions
        assert np.isfinite(action.logits).all() and np.isfinite(action.value)
        logp, _ = reference.log_probs(obs)
        assert action.action_id == reference.choose(obs).action_id
        legal = obs.action_mask.astype(bool)
        assert np.max(np.abs(action.logits[legal] - logp[legal])) < 1e-5
        history = np.asarray(obs.event_history, dtype=np.uint32)[-WINDOW:]
        events = np.zeros((1, WINDOW), dtype=np.uint32)
        events[0, :history.size] = history
        expected = batched(obs.planes[None], obs.scalars[None], obs.action_mask[None], events,
                           np.asarray([history.size]))
        assert action.action_id == expected[0]


@requires_go_lib
def test_evaluate_batch_returns_the_suit_averaged_distribution():
    model = _model()
    served = _policy(model)
    observations = _observations(12)
    planes = np.stack([o.planes for o in observations])
    scalars = np.stack([o.scalars for o in observations])
    masks = np.stack([o.action_mask for o in observations])
    events = np.zeros((len(observations), WINDOW), dtype=np.int64)
    lengths = np.zeros(len(observations), dtype=np.int32)
    for i, o in enumerate(observations):
        h = np.asarray(o.event_history, dtype=np.int64)[-WINDOW:]
        events[i, :h.size] = h
        lengths[i] = h.size
    probs, values = served.evaluate_batch(planes, scalars, masks, events=events, event_lengths=lengths)
    assert np.allclose(probs.sum(axis=1), 1.0, atol=1e-5)
    assert (probs[masks == 0] == 0).all()
    for i, o in enumerate(observations):
        assert int(np.argmax(probs[i])) == served.choose(o).action_id


def test_plain_policy_is_unchanged_by_the_option():
    model = _model(window=0)
    plain = _policy(model, symmetry="none")
    assert plain.symmetry == "none"


@requires_go_lib
def test_in_process_parity_passes_for_the_suit_averaged_policy(tmp_path):
    config = ModelConfig(**dict(SMALL_MODEL, event_window=WINDOW))
    path = tmp_path / "model.pt"
    save_checkpoint(path, PolicyValueNet(EnvConfig(), config), step=1,
                    metadata={"model_config": model_config_metadata(config)})
    report = run_serving_parity(checkpoint=path, event_history_window=WINDOW, episodes=2,
                                start_seed=500, bridge_kind="go", match_mode="chongci",
                                max_decisions=60, symmetry="suits")
    assert report.all_agree and report.decisions_checked > 0
    assert report.max_logit_diff <= 1e-4
