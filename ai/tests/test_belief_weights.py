import numpy as np
import torch
import torch.nn.functional as F

from fh_mahjong_ai.belief_weights import (effective_sample_size, normalized_weights, systematic_resample,
                                          world_log_likelihoods)


def test_log_likelihood_is_minus_the_heads_summed_training_bce():
    rng = np.random.default_rng(0)
    logits = torch.from_numpy(rng.normal(size=(12, 42)).astype(np.float32))
    planes = (rng.random((3, 12, 42, 1)) > 0.7).astype(np.float32)
    ll = world_log_likelihoods(logits, planes)
    for i in range(3):
        target = torch.from_numpy(planes[i, :, :, 0])
        bce = F.binary_cross_entropy_with_logits(logits, target, reduction="sum")
        assert abs(ll[i] + float(bce)) < 1e-3


def test_weights_ess_and_systematic_resampling():
    w = normalized_weights(np.array([0.0, 0.0, 0.0, 0.0]))
    assert np.allclose(w, 0.25) and abs(effective_sample_size(w) - 4.0) < 1e-9
    assert sorted(systematic_resample(w, 4, np.random.default_rng(1)).tolist()) == [0, 1, 2, 3]
    peaked = normalized_weights(np.array([-50.0, 0.0, -50.0]))
    assert systematic_resample(peaked, 5, np.random.default_rng(2)).tolist() == [1] * 5
    assert effective_sample_size(peaked) < 1.01
    a = systematic_resample(w, 4, np.random.default_rng(3))
    b = systematic_resample(w, 4, np.random.default_rng(3))
    assert np.array_equal(a, b)
