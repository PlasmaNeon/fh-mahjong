"""LogProbEnsemble: several checkpoints played as the mean of their log-probabilities."""

import os

import numpy as np
import pytest
import torch

from conftest import small_model_config
from fh_mahjong_ai.batched_eval import evaluate_duplicate_seats_batched
from fh_mahjong_ai.config import EnvConfig
from fh_mahjong_ai.ensemble import LogProbEnsemble
from fh_mahjong_ai.model import PolicyValueNet

requires_go_lib = pytest.mark.skipif(
    not os.environ.get("FH_MAHJONG_BRIDGE_LIB"), reason="needs the Go bridge library"
)


def _net(seed: int, **kw) -> PolicyValueNet:
    torch.manual_seed(seed)
    return PolicyValueNet(EnvConfig(), small_model_config(**kw)).eval()


def _inputs(n=5):
    env = EnvConfig()
    rng = np.random.default_rng(3)
    planes = torch.from_numpy(rng.random((n, *env.plane_shape), dtype=np.float32))
    scalars = torch.from_numpy(rng.random((n, env.scalar_features), dtype=np.float32))
    mask = torch.from_numpy((rng.random((n, env.action_space_size)) < 0.3).astype(np.int8))
    mask[:, 5] = 1
    return planes, scalars, mask


@torch.no_grad()
def test_members_average_in_log_probability_space():
    a, b = _net(1), _net(2)
    planes, scalars, mask = _inputs()
    logits, value = LogProbEnsemble([a, b])(planes, scalars, mask)
    la, va = a(planes, scalars, mask)
    lb, vb = b(planes, scalars, mask)
    want = (torch.log_softmax(la, -1) + torch.log_softmax(lb, -1)) / 2
    legal = mask > 0
    assert torch.allclose(logits[legal], want[legal], atol=1e-6)
    assert (logits[~legal] == torch.finfo(torch.float32).min).all()
    assert torch.allclose(value, (va + vb) / 2, atol=1e-6)


@torch.no_grad()
def test_an_ensemble_of_one_net_twice_plays_that_net():
    a = _net(1)
    planes, scalars, mask = _inputs()
    logits, _ = LogProbEnsemble([a, a])(planes, scalars, mask)
    plain, _ = a(planes, scalars, mask)
    assert torch.equal(torch.argmax(logits, 1), torch.argmax(plain, 1))


def test_rejects_one_member_and_mismatched_event_windows():
    with pytest.raises(ValueError, match="two members"):
        LogProbEnsemble([_net(1)])
    with pytest.raises(ValueError, match="event_window"):
        LogProbEnsemble([_net(1, event_window=8), _net(2, event_window=16)])


@requires_go_lib
def test_ensemble_plays_the_batched_gate_with_suit_averaging():
    ensemble = LogProbEnsemble([_net(1, event_window=8), _net(2, event_window=8)])
    report = evaluate_duplicate_seats_batched(
        ensemble, seeds=[41, 42], match_mode="chongci", chongci_max_hands=4,
        max_steps_per_episode=4000, event_history_window=8, slots=2, symmetry="suits")
    assert report["truncation_rate"] == 0.0
    assert report["policy_transform"] == {"symmetry": "suits"}
