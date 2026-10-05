"""Belief-head importance weights for re-dealt worlds (search-teacher diagnostic).

A world's weight is its likelihood under the belief head at the root: the Bernoulli likelihood of its opponent
threshold planes, the target the head trains on (ppo.py belief loss). Self-normalized, then resampled.
"""
from __future__ import annotations

import numpy as np
import torch
import torch.nn.functional as F


def world_log_likelihoods(belief_logits: torch.Tensor, oracle_planes: np.ndarray) -> np.ndarray:
    """Log-likelihood of each world's opponent threshold planes [n, 12, 42, 1] under logits [12, 42]."""
    target = torch.from_numpy((np.asarray(oracle_planes)[..., 0] > 0).astype(np.float32)).to(belief_logits.device)
    logits = belief_logits.float().unsqueeze(0).expand_as(target)
    bce = F.binary_cross_entropy_with_logits(logits, target, reduction="none").sum(dim=(1, 2))
    return (-bce).double().cpu().numpy()


def normalized_weights(log_likelihoods: np.ndarray) -> np.ndarray:
    ll = np.asarray(log_likelihoods, dtype=np.float64)
    w = np.exp(ll - ll.max())
    return w / w.sum()


def effective_sample_size(weights: np.ndarray) -> float:
    w = np.asarray(weights, dtype=np.float64)
    return float(1.0 / np.sum(w * w))


def systematic_resample(weights: np.ndarray, count: int, rng: np.random.Generator) -> np.ndarray:
    positions = (rng.random() + np.arange(count)) / count
    cumulative = np.cumsum(np.asarray(weights, dtype=np.float64))
    cumulative[-1] = 1.0
    return np.searchsorted(cumulative, positions, side="right").astype(np.int64)
