"""Search-teacher diagnostic (worklog/specs/20261005-search-teacher-diagnostic.md).

At contested discard decisions of self-play, compares the suit-averaged policy's choice with 12 search rules
against true-state ground truth: each top-3 candidate played to the end of the hand on the real wall.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Callable

import numpy as np
import torch

from .action_catalog import DISCARD_BASE, DISCARD_COUNT
from .belief_weights import effective_sample_size, normalized_weights, systematic_resample, world_log_likelihoods
from .envpool import PoolCommand
from .evaluate import _t_critical_975
from .searchpool import GoSearchPool
from .suit_symmetry import suit_averaged_log_probs

SAMPLERS = ("uniform", "belief")
HORIZONS = ("next", "hand")
MARGINS = (0.0, 1.0, 2.0)
RULES = tuple((s, h, z) for s in SAMPLERS for h in HORIZONS for z in MARGINS)
PRIMARY = ("belief", "next", 1.0)


def rule_name(rule) -> str:
    sampler, horizon, z = rule
    return f"{sampler}/{horizon}/z{int(z)}"


@dataclass(frozen=True)
class DiagnosticConfig:
    candidates: int = 3
    worlds: int = 32
    pool_worlds: int = 256
    contested_min: float = 0.10
    keep_every: int = 5
    gamma: float = 0.99
    max_rollout_decisions: int = 4000
    pool_seed: int = 1
    resample_seed: int = 1


class Forward:
    """Batched greedy actions, values, belief logits and suit-averaged probabilities for one model."""

    def __init__(self, model, device: str) -> None:
        self.model = model.to(device).eval()
        self.device = device
        self.window = int(model.model_config.event_window)
        self.policy_channels = int(model.policy_channels)

    def _events(self, grid, counts, n):
        if not self.model.wants_events:
            return None, None
        if grid is None:
            grid = np.zeros((n, self.window), dtype=np.uint32)
            counts = np.zeros(n, dtype=np.int64)
        ev = torch.from_numpy(np.ascontiguousarray(grid[:, : self.window]).astype(np.int64)).to(self.device)
        ln = torch.from_numpy(np.minimum(np.asarray(counts, dtype=np.int64), self.window)).to(self.device)
        return ev, ln

    def rows(self, planes, scalars, masks, grid, counts):
        to = lambda a: torch.from_numpy(np.ascontiguousarray(a)).to(self.device)  # noqa: E731
        ev, ln = self._events(grid, counts, len(planes))
        with torch.inference_mode():
            logits, values = self.model(to(planes), to(scalars), to(masks), events=ev, event_lengths=ln)
        return logits.argmax(dim=1).cpu().numpy(), values.double().cpu().numpy()

    def observation_arrays(self, obs):
        hist = np.asarray(obs.event_history, dtype=np.uint32)[-self.window:] if self.window else np.zeros(0)
        grid = np.zeros((1, max(self.window, 1)), dtype=np.uint32)
        grid[0, : hist.size] = hist
        return obs.planes[None], obs.scalars[None], obs.action_mask[None], grid, np.array([hist.size])

    def greedy(self, obs) -> int:
        actions, _ = self.rows(*self.observation_arrays(obs))
        return int(actions[0])

    def suit_averaged_probs(self, obs) -> np.ndarray:
        planes, scalars, masks, grid, counts = self.observation_arrays(obs)
        log_probs, _ = suit_averaged_log_probs(self.model, planes, scalars, masks, grid[:, : self.window],
                                               counts, device=self.device)
        return np.exp(log_probs[0])

    def belief_logits(self, obs) -> torch.Tensor:
        planes, scalars, _, grid, counts = self.observation_arrays(obs)
        ev, ln = self._events(grid, counts, 1)
        with torch.inference_mode():
            features = self.model.encode(torch.from_numpy(planes).to(self.device),
                                         torch.from_numpy(scalars).to(self.device), ev, ln)
            return self.model.aux_predictions(features)["belief"][0]


def play_out(pool, forward: Forward, actions: list[int], root_seat: int, horizon: str, gamma: float) -> np.ndarray:
    """Each clone plays its action, then every seat plays greedy; scores are the root seat's.

    horizon="hand": rewards summed to the end of the hand. horizon="next": rewards to the root seat's next
    decision, plus gamma * the value there (the privileged critic when the pool emits oracle planes)."""
    scores = np.zeros(len(actions), dtype=np.float64)
    live = set(range(len(actions)))
    result = pool.step([PoolCommand(slot=i, action_id=int(a)) for i, a in enumerate(actions)])
    while True:
        act, value, commands = [], [], []
        for meta in result.slots:
            i = int(meta.slot)
            if i not in live:
                continue
            if meta.error:
                raise RuntimeError(f"search clone {i} failed: {meta.error}")
            if len(meta.step_rewards):
                scores[i] += float(meta.step_rewards[root_seat])
            hand_over = meta.terminated or meta.round_outcome is not None
            if meta.terminated or meta.truncated or (horizon == "hand" and hand_over):
                live.discard(i)
            elif horizon == "next" and meta.has_observation and int(meta.seat) == root_seat:
                value.append(i)
                live.discard(i)
            elif meta.has_observation:
                act.append(i)
        for group, use in ((value, "value"), (act, "act")):
            if not group:
                continue
            rows = [result.row_of_slot[i] for i in group]
            grid = None if result.event_grid is None else result.event_grid[rows]
            counts = None if result.event_counts is None else result.event_counts[rows]
            actions_out, values = forward.rows(result.planes[rows], result.scalars[rows],
                                               result.action_masks[rows], grid, counts)
            if use == "value":
                for i, v in zip(group, values):
                    scores[i] += gamma * float(v)
            else:
                commands = [PoolCommand(slot=i, action_id=int(a)) for i, a in zip(group, actions_out)]
        if not live:
            return scores
        if not commands:
            raise RuntimeError("search rollout stalled: live clones without rows")
        result = pool.step(commands)


def rule_choice(scores: np.ndarray, z: float, weights=None) -> int:
    """Index of the chosen candidate: the best weighted-mean score, if its paired gain over candidate 0
    (the suit-averaged greedy choice) exceeds z standard errors; otherwise 0.

    `weights` are the distinct worlds' multiplicities (normalized; equal when None). The SE uses the
    effective number of worlds n_eff = 1 / sum(w^2), so duplicated worlds never count as independent
    samples; with fewer than two distinct worlds only the margin-free rule (z = 0) may override."""
    scores = np.asarray(scores, dtype=np.float64)
    w = (np.full(scores.shape[1], 1.0 / scores.shape[1]) if weights is None
         else np.asarray(weights, dtype=np.float64) / np.sum(weights))
    best = int(np.argmax(scores @ w))
    if best == 0:
        return 0
    d = scores[best] - scores[0]
    mean = float(d @ w)
    if mean <= 0:
        return 0
    if z == 0:
        return best
    n_eff = 1.0 / float(np.sum(w * w))
    if scores.shape[1] < 2 or n_eff <= 1.0:
        return 0
    variance = float(w @ (d - mean) ** 2) * n_eff / (n_eff - 1.0)
    return best if mean > z * np.sqrt(variance / n_eff) else 0


def clustered_mean_ci(deltas: np.ndarray, clusters: np.ndarray, critical: float) -> tuple[float, float]:
    """Mean of deltas and its half-width clustered by `clusters` (ratio estimator over cluster sums)."""
    deltas = np.asarray(deltas, dtype=np.float64)
    n = deltas.size
    mean = float(deltas.mean())
    keys = np.unique(clusters)
    if keys.size < 2:
        return mean, float("inf")
    sums = np.array([np.sum(deltas[clusters == k] - mean) for k in keys])
    se = np.sqrt(keys.size / (keys.size - 1) * np.sum(sums ** 2)) / n
    return mean, float(critical * se)

def _contested(obs, probs: np.ndarray, cfg: DiagnosticConfig) -> list[int]:
    discards = np.arange(DISCARD_BASE, DISCARD_BASE + DISCARD_COUNT)
    legal = discards[obs.action_mask[discards] > 0]
    if legal.size < 2:
        return []
    order = legal[np.argsort(-probs[legal], kind="stable")][: cfg.candidates]
    if probs[order[1]] < cfg.contested_min:
        return []
    return [int(a) for a in order if probs[a] > 0]


def _world_ids(bridge, forward, obs, cfg, rng) -> tuple[list[int], float]:
    weigh = GoSearchPool(bridge, clones=cfg.pool_worlds, seed=cfg.pool_seed, max_rollout_decisions=1,
                         oracle_planes=True, root_seat=int(obs.seat))
    try:
        roots = weigh.root_observations()
    finally:
        weigh.close()
    pc = forward.policy_channels
    weights = normalized_weights(world_log_likelihoods(forward.belief_logits(obs), roots.planes[:, pc:pc + 12]))
    return systematic_resample(weights, cfg.worlds, rng).tolist(), effective_sample_size(weights)


def analyse_state(bridge, forward: Forward, obs, candidates: list[int], cfg: DiagnosticConfig, rng) -> dict:
    seat = int(obs.seat)
    truth_pool = GoSearchPool(bridge, clones=len(candidates), seed=cfg.pool_seed,
                              max_rollout_decisions=cfg.max_rollout_decisions, true_state=True, root_seat=seat)
    try:
        truth = play_out(truth_pool, forward, candidates, seat, "hand", cfg.gamma)
    finally:
        truth_pool.close()
    belief_ids, ess = _world_ids(bridge, forward, obs, cfg, rng)
    # Resampling repeats worlds and a world's rollout is deterministic, so each distinct world runs
    # once and carries its multiplicity as a weight.
    distinct, counts = np.unique(np.asarray(belief_ids, dtype=np.int64), return_counts=True)
    ids = {"uniform": list(range(cfg.worlds)), "belief": distinct.tolist()}
    weights = {"uniform": [1.0 / cfg.worlds] * cfg.worlds, "belief": (counts / counts.sum()).tolist()}
    scores = {}
    for sampler in SAMPLERS:
        for horizon in HORIZONS:
            worlds = len(ids[sampler])
            pool = GoSearchPool(bridge, clones=len(candidates) * worlds, seed=cfg.pool_seed,
                                max_rollout_decisions=cfg.max_rollout_decisions, determinizations=worlds,
                                root_seat=seat, oracle_planes=(horizon == "next"),
                                determinization_ids=ids[sampler])
            try:
                actions = [c for c in candidates for _ in range(worlds)]
                flat = play_out(pool, forward, actions, seat, horizon, cfg.gamma)
            finally:
                pool.close()
            scores[f"{sampler}/{horizon}"] = flat.reshape(len(candidates), worlds).tolist()
    return {"root_seat": seat, "candidates": candidates, "truth": truth.tolist(), "scores": scores, "ess": ess,
            "weights": weights, "distinct_worlds": int(distinct.size)}


def run_diagnostic(bridge, forward: Forward, cfg: DiagnosticConfig, states: int, seed_base: int,
                   sink: Callable[[dict], None]) -> None:
    rng = np.random.default_rng(cfg.resample_seed)
    seed, kept, seen = seed_base, 0, 0
    obs = bridge.reset(seed=seed)
    while kept < states:
        discards = obs.action_mask[DISCARD_BASE:DISCARD_BASE + DISCARD_COUNT]
        candidates = (_contested(obs, forward.suit_averaged_probs(obs), cfg)
                      if np.count_nonzero(discards) >= 2 else [])
        if candidates:
            seen += 1
            if seen % cfg.keep_every == 0:
                record = analyse_state(bridge, forward, obs, candidates, cfg, rng)
                record.update(state=kept, game_seed=seed)
                sink(record)
                kept += 1
        step = bridge.step(forward.greedy(obs))
        if step.terminated or step.truncated:
            seed += 1
            obs = bridge.reset(seed=seed)
        else:
            obs = step.observation


def summarize(records: list[dict]) -> dict:
    clusters = np.array([r["game_seed"] for r in records])
    games = np.unique(clusters).size
    primary_critical = _t_critical_975(games - 1)
    bonferroni = statistics.NormalDist().inv_cdf(1 - 0.05 / 11 / 2)
    truths = [np.asarray(r["truth"], dtype=np.float64) for r in records]
    greedy_best = float(np.mean([t[0] == t.max() for t in truths]))
    rules = {}
    for rule in RULES:
        sampler, horizon, z = rule
        choices = np.array([rule_choice(np.asarray(r["scores"][f"{sampler}/{horizon}"]), z,
                                        (r.get("weights") or {}).get(sampler)) for r in records])
        deltas = np.array([t[c] - t[0] for t, c in zip(truths, choices)])
        critical = primary_critical if rule == PRIMARY else bonferroni
        mean, half = clustered_mean_ci(deltas, clusters, critical)
        overrides = choices != 0
        rules[rule_name(rule)] = {
            "mean_delta": mean, "ci_half_width": half, "ci_lower": mean - half,
            "override_rate": float(overrides.mean()),
            "mean_delta_when_overriding": float(deltas[overrides].mean()) if overrides.any() else 0.0,
            "hindsight_best_rate": float(np.mean([t[c] == t.max() for t, c in zip(truths, choices)])),
        }
    primary = rule_name(PRIMARY)
    others = [name for name in rules if name != primary and rules[name]["ci_lower"] > 0]
    ess = np.array([r["ess"] for r in records if r.get("ess") is not None])
    distinct = np.array([r["distinct_worlds"] for r in records if r.get("distinct_worlds") is not None])
    return {"states": len(records), "games": int(games), "greedy_hindsight_best_rate": greedy_best,
            "primary": primary, "go": bool(rules[primary]["ci_lower"] > 0), "other_qualifying": others,
            "ess_quantiles": (np.quantile(ess, [0.1, 0.5, 0.9]).tolist() if ess.size else None),
            "distinct_world_quantiles": (np.quantile(distinct, [0.1, 0.5, 0.9]).tolist() if distinct.size else None),
            "rules": rules}
