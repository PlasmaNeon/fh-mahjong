"""Evaluation utilities for comparing a learned policy against baselines."""
from __future__ import annotations

import hashlib
import inspect
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence

import numpy as np
import torch
from torch import nn

from .action_catalog import action_family
from .bridge import build_bridge, resolve_bridge_library_path
from .config import EnvConfig
from .data import placement_shaped_returns
from .env import MahjongEnv
from .policies import TorchGreedyPolicy
from .types import Transition


def episode_reward_vector(episode, fallback_rewards, num_seats: int = 4, reset_rewards=None) -> np.ndarray:
    """Total per-seat reward summed over an episode's transitions, plus the
    pre-first-decision reset reward when provided. With dense per-step rewards
    this recovers the full match outcome; with sparse terminal-only rewards it
    equals the terminal reward. Empty episodes (reset-terminated) fall back to
    the provided terminal rewards."""
    if not episode:
        return np.asarray(fallback_rewards, dtype=np.float32)
    total = np.zeros(num_seats, dtype=np.float32)
    for t in episode:
        r = np.asarray(t.rewards, dtype=np.float32)
        n = min(num_seats, r.shape[-1]) if r.ndim >= 1 else 0
        total[:n] += r[:n]
    if reset_rewards is not None:
        rr = np.asarray(reset_rewards, dtype=np.float32)
        n = min(num_seats, rr.shape[-1]) if rr.ndim >= 1 else 0
        total[:n] += rr[:n]
    return total


# Placement values by rank (1st..4th). Mirrors the PPO training side
# (PPOConfig.grp_placement_values); kept in sync so the duplicate-seat
# mean_placement gate matches the training reward, including the worst-placement
# score assigned to step-limit truncations.
_EVAL_PLACEMENT_VALUES = (1.0, 1.0 / 3.0, -1.0 / 3.0, -1.0)


def episode_placement(episode, fallback_rewards, learning_seat, placement_values, reset_rewards=None) -> float:
    """The learning seat's placement value (rank) from the episode's per-seat net.

    Includes the reset reward (score from any reset-time autoplay before the
    learning seat's first decision) so placement ranks on the TRUE final net —
    matching both the net `mean_reward` metric and the training-side
    realized_placement (collect_rollouts seeds cum_net with the reset reward).
    """
    net = episode_reward_vector(episode, fallback_rewards, num_seats=4, reset_rewards=reset_rewards)
    shaped = placement_shaped_returns(np.asarray(net, dtype=np.float32)[None, :], placement_values)
    return float(shaped[0, learning_seat])


def reward_summary(rewards: Sequence[float]) -> Dict[str, Any]:
    values = [float(reward) for reward in rewards]
    if not values:
        return {
            "count": 0,
            "sum": 0.0,
            "mean": 0.0,
            "std": 0.0,
            "min": 0.0,
            "max": 0.0,
            "positive_count": 0,
            "zero_count": 0,
            "negative_count": 0,
            "positive_rate": 0.0,
            "zero_rate": 0.0,
            "negative_rate": 0.0,
            "sem": 0.0,
            "ci95": 0.0,
        }

    array = np.asarray(values, dtype=np.float32)
    count = int(array.size)
    positive_count = int(np.sum(array > 0))
    zero_count = int(np.sum(array == 0))
    negative_count = int(np.sum(array < 0))
    sem = float(np.std(array, ddof=1) / np.sqrt(count)) if count > 1 else 0.0
    return {
        "count": count,
        "sum": float(np.sum(array)),
        "mean": float(np.mean(array)),
        "std": float(np.std(array)),
        "min": float(np.min(array)),
        "max": float(np.max(array)),
        "positive_count": positive_count,
        "zero_count": zero_count,
        "negative_count": negative_count,
        "positive_rate": positive_count / count,
        "zero_rate": zero_count / count,
        "negative_rate": negative_count / count,
        "sem": sem,
        "ci95": 1.96 * sem,
    }


# Small-df lookup for the two-sided 95% Student-t critical value; the
# Cornish-Fisher series below is accurate to ~1e-3 only for df >= 5.
_T_CRITICAL_975_SMALL_DF = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776}


def _t_critical_975(df: int) -> float:
    """Two-sided 95% Student-t critical value (numpy-only, no scipy)."""
    if df <= 0:
        return float("inf")
    if df in _T_CRITICAL_975_SMALL_DF:
        return _T_CRITICAL_975_SMALL_DF[df]
    z = 1.959963984540054
    g1 = (z**3 + z) / 4.0
    g2 = (5 * z**5 + 16 * z**3 + 3 * z) / 96.0
    g3 = (3 * z**7 + 19 * z**5 + 17 * z**3 - 15 * z) / 384.0
    return float(z + g1 / df + g2 / df**2 + g3 / df**3)


def clustered_placement_stats(per_seat_placements: Sequence[Sequence[float]]) -> Dict[str, Any]:
    """Wall-seed-clustered placement statistics for duplicate-seat evals.

    ``per_seat_placements`` holds one sequence per rotated seat, each ordered
    by the SHARED seed list. The wall seed is the independent sampling unit;
    the seat rotations of one seed are correlated replicates, so the interval
    is a t-interval over per-seed means, not over the flattened placements.
    ``cluster_design_effect`` is the ratio of the clustered to the naive
    variance of the mean (>1 = positive within-seed correlation).
    """
    empty = {
        "per_seed_mean_placements": [],
        "mean_placement_clustered": 0.0,
        "mean_placement_sem_clustered": 0.0,
        "mean_placement_ci95_clustered": 0.0,
        "cluster_design_effect": 0.0,
        "num_seeds": 0,
    }
    rows = [list(map(float, seat)) for seat in per_seat_placements]
    if not rows:
        return empty
    lengths = {len(row) for row in rows}
    if len(lengths) != 1:
        raise ValueError(
            f"per-seat placement lists must share one length (one entry per seed); got lengths {sorted(lengths)}"
        )
    num_seeds = lengths.pop()
    if num_seeds == 0:
        return empty

    matrix = np.asarray(rows, dtype=np.float64)  # (seats, seeds)
    seed_means = matrix.mean(axis=0)
    mean = float(seed_means.mean())
    if num_seeds < 2:
        return {
            "per_seed_mean_placements": [float(v) for v in seed_means],
            "mean_placement_clustered": mean,
            "mean_placement_sem_clustered": 0.0,
            "mean_placement_ci95_clustered": 0.0,
            "cluster_design_effect": 0.0,
            "num_seeds": num_seeds,
        }

    clustered_sem = float(np.std(seed_means, ddof=1) / np.sqrt(num_seeds))
    flat = matrix.reshape(-1)
    naive_var_of_mean = float(np.var(flat, ddof=1) / flat.size) if flat.size > 1 else 0.0
    design_effect = (clustered_sem**2 / naive_var_of_mean) if naive_var_of_mean > 0 else 0.0
    return {
        "per_seed_mean_placements": [float(v) for v in seed_means],
        "mean_placement_clustered": mean,
        "mean_placement_sem_clustered": clustered_sem,
        "mean_placement_ci95_clustered": _t_critical_975(num_seeds - 1) * clustered_sem,
        "cluster_design_effect": design_effect,
        "num_seeds": num_seeds,
    }


def _snapshot_bridge_library(
    bridge_kind: str, bridge_library_path: Optional[str]
) -> tuple[Optional[str], Optional[str], Optional[Any]]:
    """Copy the resolved Go bridge library to a private snapshot.

    Returns (effective library path, sha256 of that artifact, snapshot holder
    to cleanup). The digest and every bridge dlopen then refer to the SAME
    immutable bytes — a concurrent rebuild of the source library between
    hashing and loading cannot make a report attest a binary other than the
    one actually evaluated. Non-Go bridges and unreadable libraries pass
    through unchanged with no digest.
    """
    if bridge_kind != "go":
        return bridge_library_path, None, None
    try:
        source = resolve_bridge_library_path(bridge_library_path)
        data = Path(source).read_bytes()
    except OSError:
        return bridge_library_path, None, None
    digest = hashlib.sha256(data).hexdigest()
    holder = tempfile.TemporaryDirectory(prefix="fh-bridge-snapshot-")
    snapshot = Path(holder.name) / Path(source).name
    snapshot.write_bytes(data)
    return str(snapshot), digest, holder


def _bridge_library_digest(bridge_kind: str, bridge_library_path: Optional[str]) -> Optional[str]:
    """SHA-256 provenance of the Go simulator library behind this eval.

    Recorded in duplicate-seat reports so fh-mj-compare can refuse to treat
    simulator drift as checkpoint quality. None for non-Go bridges and when
    the library cannot be read.
    """
    if bridge_kind != "go":
        return None
    try:
        path = resolve_bridge_library_path(bridge_library_path)
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def _clustered_report_fields(seat_reports: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """The three clustered fields added to duplicate-seat reports.

    Falls back to empty stats (instead of raising) when seat reports are
    ragged — a defensive path only; duplicate-seat runs always evaluate the
    identical seed list on every seat.
    """
    per_seat = [
        [float(p) for p in report.get("per_episode_placements", [])]
        for report in seat_reports
    ]
    try:
        stats = clustered_placement_stats(per_seat)
    except ValueError:
        stats = clustered_placement_stats([])
    return {
        "per_seed_mean_placements": stats["per_seed_mean_placements"],
        "mean_placement_ci95_clustered": stats["mean_placement_ci95_clustered"],
        "cluster_design_effect": stats["cluster_design_effect"],
    }


def action_family_rates(action_counts: Counter[str]) -> Dict[str, float]:
    total = sum(action_counts.values())
    if total == 0:
        return {}
    return {
        family: count / total
        for family, count in sorted(action_counts.items())
    }


def summarize_policy_choices(choice_infos: Sequence[dict[str, Any]]) -> Dict[str, Any]:
    source_counts: Counter[str] = Counter()
    intervention_source_counts: Counter[str] = Counter()
    intervention_anchor_family_counts: Counter[str] = Counter()
    intervention_chosen_family_counts: Counter[str] = Counter()
    q_margins: list[float] = []
    first_candidate: Optional[dict[str, Any]] = None
    first_intervention: Optional[dict[str, Any]] = None
    for info in choice_infos:
        source = info.get("source")
        if source is not None:
            source_counts[str(source)] += 1
        source_text = str(source) if source is not None else ""
        is_intervention = source_text not in {"", "anchor", "same"}
        q_margin = info.get("q_margin")
        if q_margin is not None:
            q_margins.append(float(q_margin))
        if first_candidate is None and source == "candidate":
            first_candidate = {
                "anchor_action_id": info.get("anchor_action_id"),
                "anchor_action_label": info.get("anchor_action_label"),
                "candidate_action_id": info.get("candidate_action_id"),
                "candidate_action_label": info.get("candidate_action_label"),
                "chosen_action_label": info.get("chosen_action_label"),
                "q_margin": float(q_margin) if q_margin is not None else None,
                "candidate_q": info.get("candidate_q"),
                "anchor_action_q": info.get("anchor_action_q"),
            }
        if is_intervention:
            intervention_source_counts[source_text] += 1
            anchor_action_id = info.get("anchor_action_id")
            chosen_action_id = info.get("chosen_action_id", info.get("candidate_action_id"))
            if anchor_action_id is not None:
                intervention_anchor_family_counts[action_family(int(anchor_action_id))] += 1
            if chosen_action_id is not None:
                intervention_chosen_family_counts[action_family(int(chosen_action_id))] += 1
            if first_intervention is None:
                first_intervention = {
                    "source": source_text,
                    "anchor_action_id": anchor_action_id,
                    "anchor_action_label": info.get("anchor_action_label"),
                    "chosen_action_id": chosen_action_id,
                    "chosen_action_label": info.get("chosen_action_label", info.get("candidate_action_label")),
                    "q_margin": float(q_margin) if q_margin is not None else None,
                    "anchor_risk": info.get("anchor_risk"),
                    "chosen_risk": info.get("chosen_risk"),
                    "risk_reduction": info.get("risk_reduction"),
                    "anchor_severity": info.get("anchor_severity"),
                    "chosen_severity": info.get("chosen_severity"),
                }
    candidate_count = int(source_counts.get("candidate", 0))
    intervention_count = int(sum(intervention_source_counts.values()))
    return {
        "decision_count": len(choice_infos),
        "source_counts": dict(sorted(source_counts.items())),
        "source_rates": action_family_rates(source_counts),
        "candidate_override_count": candidate_count,
        "candidate_override_rate": candidate_count / len(choice_infos) if choice_infos else 0.0,
        "intervention_count": intervention_count,
        "intervention_rate": intervention_count / len(choice_infos) if choice_infos else 0.0,
        "intervention_source_counts": dict(sorted(intervention_source_counts.items())),
        "intervention_source_rates": action_family_rates(intervention_source_counts),
        "intervention_anchor_family_counts": dict(sorted(intervention_anchor_family_counts.items())),
        "intervention_anchor_family_rates": action_family_rates(intervention_anchor_family_counts),
        "intervention_chosen_family_counts": dict(sorted(intervention_chosen_family_counts.items())),
        "intervention_chosen_family_rates": action_family_rates(intervention_chosen_family_counts),
        "q_margin_summary": reward_summary(q_margins),
        "first_candidate_override": first_candidate,
        "first_intervention": first_intervention,
    }


def summarize_policy_episode_outcomes(episode_summaries: Sequence[dict[str, Any]]) -> Dict[str, Any]:
    no_candidate_rewards: list[float] = []
    candidate_rewards: list[float] = []
    no_intervention_rewards: list[float] = []
    intervention_rewards: list[float] = []
    candidate_bucket_rewards: dict[str, list[float]] = {
        "0": [],
        "1": [],
        "2-4": [],
        "5+": [],
    }
    intervention_bucket_rewards: dict[str, list[float]] = {
        "0": [],
        "1": [],
        "2-4": [],
        "5+": [],
    }
    for summary in episode_summaries:
        reward = float(summary["reward"])
        count = int(summary.get("candidate_override_count", 0))
        intervention_count = int(summary.get("intervention_count", count))
        if count == 0:
            no_candidate_rewards.append(reward)
            candidate_bucket_rewards["0"].append(reward)
        else:
            candidate_rewards.append(reward)
            if count == 1:
                candidate_bucket_rewards["1"].append(reward)
            elif count <= 4:
                candidate_bucket_rewards["2-4"].append(reward)
            else:
                candidate_bucket_rewards["5+"].append(reward)
        if intervention_count == 0:
            no_intervention_rewards.append(reward)
            intervention_bucket_rewards["0"].append(reward)
        else:
            intervention_rewards.append(reward)
            if intervention_count == 1:
                intervention_bucket_rewards["1"].append(reward)
            elif intervention_count <= 4:
                intervention_bucket_rewards["2-4"].append(reward)
            else:
                intervention_bucket_rewards["5+"].append(reward)
    return {
        "no_candidate_override_reward": reward_summary(no_candidate_rewards),
        "candidate_override_reward": reward_summary(candidate_rewards),
        "no_intervention_reward": reward_summary(no_intervention_rewards),
        "intervention_reward": reward_summary(intervention_rewards),
        "by_intervention_count": {
            bucket: reward_summary(rewards)
            for bucket, rewards in intervention_bucket_rewards.items()
        },
        "by_candidate_override_count": {
            bucket: reward_summary(rewards)
            for bucket, rewards in candidate_bucket_rewards.items()
        },
    }


def summarize_large_loss_episodes(
    episode_summaries: Sequence[dict[str, Any]],
    large_loss_threshold: float,
) -> list[dict[str, Any]]:
    return [
        {
            "seed": int(summary["seed"]),
            "seat": int(summary["seat"]),
            "reward": float(summary["reward"]),
            "large_loss_threshold": float(large_loss_threshold),
        }
        for summary in episode_summaries
        if bool(summary.get("large_loss", False))
    ]


def outcome_rates(outcome_counts: Counter[str]) -> Dict[str, float]:
    total = sum(outcome_counts.values())
    if total == 0:
        return {}
    return {
        name: count / total
        for name, count in sorted(outcome_counts.items())
    }


def update_outcome_counts(outcome_counts: Counter[str], outcome: Optional[dict[str, Any]], learning_seat: int) -> None:
    if not outcome:
        outcome_counts["unknown"] += 1
        return

    if bool(outcome.get("is_draw", False)):
        outcome_counts["draw"] += 1
        return

    winner = int(outcome.get("winner_seat", -1))
    discarder = int(outcome.get("discarder_seat", -1))
    win_type_name = str(outcome.get("win_type_name", ""))

    if win_type_name == "ACTION_TSUMO":
        if winner == learning_seat:
            outcome_counts["tsumo_win"] += 1
        else:
            outcome_counts["tsumo_loss"] += 1
        return

    if win_type_name == "ACTION_RON":
        if winner == learning_seat:
            outcome_counts["ron_win"] += 1
        elif discarder == learning_seat:
            outcome_counts["deal_in"] += 1
        else:
            outcome_counts["ron_other_loss"] += 1
        return

    outcome_counts["other"] += 1


def _normalize_match_mode(match_mode: str) -> str:
    normalized = match_mode.lower()
    if normalized not in {"classic", "chongci"}:
        raise ValueError(f"unsupported match_mode={match_mode!r}; expected 'classic' or 'chongci'")
    return normalized


def _default_large_loss_threshold(match_mode: str) -> float:
    if match_mode == "chongci":
        return -1.0
    return -16.0


def _chongci_report_config(
    match_mode: str,
    starting_score: int,
    bust_threshold: int,
    max_hands: int,
) -> Optional[dict[str, int]]:
    if match_mode != "chongci":
        return None
    return {
        "starting_score": int(starting_score),
        "bust_threshold": int(bust_threshold),
        "max_hands": int(max_hands),
    }


def compute_action_agreement(
    model: nn.Module,
    transitions: List[Transition],
    device: str = "cpu",
    batch_size: int = 1024,
) -> Dict[str, Any]:
    """Compute how often the model's argmax action matches the expert's action.

    Returns dict with aggregate and action-family agreement metrics.
    """
    model.eval()
    exact_matches = 0
    top3_matches = 0
    total = len(transitions)
    families: dict[str, dict[str, int]] = {}

    if total == 0:
        return {
            "agreement_rate": 0.0,
            "top3_agreement_rate": 0.0,
            "total_transitions": 0,
            "action_family_counts": {},
            "family_agreement": {},
        }

    batches = (
        {
            "planes": np.stack([t.observation.planes for t in transitions[start : start + max(1, batch_size)]]).astype(
                np.float32,
                copy=False,
            ),
            "scalars": np.stack([t.observation.scalars for t in transitions[start : start + max(1, batch_size)]]).astype(
                np.float32,
                copy=False,
            ),
            "action_mask": np.stack(
                [t.observation.action_mask for t in transitions[start : start + max(1, batch_size)]]
            ).astype(np.int8, copy=False),
            "action_ids": np.asarray(
                [t.action_id for t in transitions[start : start + max(1, batch_size)]],
                dtype=np.int64,
            ),
        }
        for start in range(0, total, max(1, batch_size))
    )
    return compute_action_agreement_from_batches(model, batches, device=device)


def compute_action_agreement_from_batches(
    model: nn.Module,
    batches: Iterator[dict[str, np.ndarray]],
    device: str = "cpu",
) -> Dict[str, Any]:
    """Compute action agreement from pre-batched observation/action arrays."""
    if getattr(model, "wants_events", False):
        raise ValueError(
            "offline action agreement cannot evaluate an event-enabled model: "
            "offline datasets carry no event histories (the model would silently "
            "run with zeroed event features)"
        )
    model.eval()
    exact_matches = 0
    top3_matches = 0
    total = 0
    families: dict[str, dict[str, int]] = {}

    with torch.inference_mode():
        for batch in batches:
            action_ids = np.asarray(batch["action_ids"], dtype=np.int64)
            if action_ids.size == 0:
                continue

            planes = torch.from_numpy(np.asarray(batch["planes"], dtype=np.float32)).to(device)
            scalars = torch.from_numpy(np.asarray(batch["scalars"], dtype=np.float32)).to(device)
            mask = torch.from_numpy(np.asarray(batch["action_mask"], dtype=np.int8)).to(device)

            logits, _ = model(planes, scalars, mask)
            top_actions_tensor = torch.topk(logits, k=min(3, logits.shape[1]), dim=1).indices.cpu()
            top_actions = top_actions_tensor.numpy()
            predicted_actions = top_actions[:, 0]

            exact_batch = predicted_actions == action_ids
            top3_batch = (top_actions == action_ids[:, None]).any(axis=1)
            exact_matches += int(exact_batch.sum())
            top3_matches += int(top3_batch.sum())
            total += int(action_ids.size)

            for index, action_id in enumerate(action_ids.tolist()):
                family = action_family(int(action_id))
                family_stats = families.setdefault(family, {"total": 0, "exact": 0, "top3": 0})
                family_stats["total"] += 1
                if bool(exact_batch[index]):
                    family_stats["exact"] += 1
                if bool(top3_batch[index]):
                    family_stats["top3"] += 1

    if total == 0:
        return {
            "agreement_rate": 0.0,
            "top3_agreement_rate": 0.0,
            "total_transitions": 0,
            "action_family_counts": {},
            "family_agreement": {},
        }

    family_agreement = {
        family: {
            "total": counts["total"],
            "agreement_rate": counts["exact"] / counts["total"],
            "top3_agreement_rate": counts["top3"] / counts["total"],
        }
        for family, counts in sorted(families.items())
    }

    return {
        "agreement_rate": exact_matches / total,
        "top3_agreement_rate": top3_matches / total,
        "total_transitions": total,
        "action_family_counts": {
            family: counts["total"]
            for family, counts in sorted(families.items())
        },
        "family_agreement": family_agreement,
    }


def evaluate_policy_online(
    policy: Any,
    episodes: int,
    seeds: List[int],
    bridge_kind: str = "go",
    bridge_library_path: Optional[str] = None,
    learning_seat: int = 0,
    large_loss_threshold: Optional[float] = None,
    match_mode: str = "classic",
    chongci_starting_score: int = 2000,
    chongci_bust_threshold: int = 0,
    chongci_max_hands: int = 50,
    max_steps_per_episode: Optional[int] = None,
    oracle_observation: bool = False,
    event_history_window: int = 0,
    policy_factory: Optional[Any] = None,
) -> Dict[str, Any]:
    """Run a policy for one seat against heuristic opponents.

    ``policy`` is used as-is when given. Pass ``policy=None`` with
    ``policy_factory`` (called as ``policy_factory(bridge)``) when the policy
    itself needs the seat's live bridge (e.g. a search policy whose rollout
    pool clones the bridge's current decision point) -- the bridge does not
    exist until this function builds it below, so it cannot be threaded
    through an eagerly-constructed ``policy`` argument.

    Returns aggregate reward and action-frequency metrics.
    """
    normalized_match_mode = _normalize_match_mode(match_mode)
    resolved_large_loss_threshold = (
        float(large_loss_threshold)
        if large_loss_threshold is not None
        else _default_large_loss_threshold(normalized_match_mode)
    )
    config = EnvConfig(
        bridge_kind=bridge_kind,
        bridge_library_path=bridge_library_path,
        learning_seats=(learning_seat,),
        auto_play_heuristics=True,
        match_mode=normalized_match_mode,
        chongci_starting_score=chongci_starting_score,
        chongci_bust_threshold=chongci_bust_threshold,
        chongci_max_hands=chongci_max_hands,
        oracle_observation=oracle_observation,
        event_history_window=event_history_window,
    )
    if max_steps_per_episode is not None:
        config.max_steps_per_episode = int(max_steps_per_episode)
    bridge = build_bridge(config)
    env = MahjongEnv(config, bridge)
    if policy is None:
        if policy_factory is None:
            raise ValueError("evaluate_policy_online requires either policy or policy_factory")
        policy = policy_factory(bridge)

    seat_rewards: List[float] = []
    seat_placements: list[float] = []
    action_counts: Counter[str] = Counter()
    outcome_counts: Counter[str] = Counter()
    choice_source_counts: Counter[str] = Counter()
    q_margins: list[float] = []
    policy_episode_summaries: list[dict[str, Any]] = []
    episode_summaries: list[dict[str, Any]] = []
    wins = 0
    large_losses = 0
    truncations = 0

    def record_episode(
        seed: int,
        rewards: np.ndarray,
        episode: list[Transition],
        choice_infos: Sequence[dict[str, Any]],
        outcome: Optional[dict[str, Any]],
        truncated: bool = False,
        reset_rewards=None,
    ) -> None:
        nonlocal wins, large_losses, truncations
        reward = float(episode_reward_vector(episode, rewards, reset_rewards=reset_rewards)[learning_seat])
        seat_rewards.append(reward)
        # A truncated (step-limit) episode has no final standings. Score it as the
        # WORST placement value — matching the training reward for truncations
        # (collect_rollouts) — rather than excluding it. Excluding would let a policy
        # improve mean_placement (the gate metric vs the anchor) by driving losing
        # matches into the step limit, censoring those losses from the comparison.
        if truncated:
            truncations += 1
            placement = float(min(_EVAL_PLACEMENT_VALUES))
        else:
            placement = episode_placement(episode, rewards, learning_seat,
                                          _EVAL_PLACEMENT_VALUES,
                                          reset_rewards=reset_rewards)
        seat_placements.append(placement)
        if reward > 0:
            wins += 1
        if reward <= resolved_large_loss_threshold:
            large_losses += 1
        action_counts.update(action_family(t.action_id) for t in episode)
        if outcome is None and normalized_match_mode == "chongci":
            outcome_counts["match_truncated" if truncated else "match_end"] += 1
        else:
            update_outcome_counts(outcome_counts, outcome, learning_seat)
        policy_summary = summarize_policy_choices(choice_infos)
        policy_summary.update(
            {
                "seed": int(seed),
                "seat": int(learning_seat),
                "reward": reward,
                "large_loss": reward <= resolved_large_loss_threshold,
                "truncated": bool(truncated),
            }
        )
        policy_episode_summaries.append(policy_summary)
        episode_summaries.append(
            {
                "seed": int(seed),
                "seat": int(learning_seat),
                "reward": reward,
                "large_loss": reward <= resolved_large_loss_threshold,
                "action_family_counts": dict(sorted(Counter(action_family(t.action_id) for t in episode).items())),
                "decision_count": len(episode),
                "truncated": bool(truncated),
            }
        )

    try:
        for i in range(episodes):
            seed = seeds[i] if i < len(seeds) else seeds[-1] + i
            episode: list[Transition] = []
            episode_choice_infos: list[dict[str, Any]] = []
            observation = env.reset(seed=seed)
            reset_result = env.last_reset_result
            episode_reset_rewards = (
                np.asarray(reset_result.rewards, dtype=np.float32)
                if reset_result is not None else None
            )
            if reset_result is not None and (reset_result.terminated or reset_result.truncated):
                record_episode(
                    seed,
                    reset_result.rewards,
                    episode,
                    episode_choice_infos,
                    reset_result.info.get("round_outcome"),
                    truncated=reset_result.truncated,
                )
                continue
            if not observation.legal_actions:
                continue

            while True:
                choice = policy.choose(observation)
                choice_info = choice.info or {}
                source = choice_info.get("source")
                if source is not None:
                    choice_source_counts[str(source)] += 1
                q_margin = choice_info.get("q_margin")
                if q_margin is not None:
                    q_margins.append(float(q_margin))
                episode_choice_infos.append(choice_info)
                step_result = env.step(choice.action_id)
                episode.append(
                    Transition(
                        observation=observation,
                        action_id=choice.action_id,
                        rewards=step_result.rewards,
                        next_observation=step_result.observation,
                        terminated=step_result.terminated,
                        truncated=step_result.truncated,
                        info=step_result.info,
                    )
                )

                observation = step_result.observation
                if step_result.terminated or step_result.truncated:
                    record_episode(
                        seed,
                        step_result.rewards,
                        episode,
                        episode_choice_infos,
                        step_result.info.get("round_outcome"),
                        truncated=step_result.truncated,
                        reset_rewards=episode_reset_rewards,
                    )
                    break
                if not observation.legal_actions:
                    break
    finally:
        env.close()

    completed = len(seat_rewards)
    rewards = reward_summary(seat_rewards)
    placement_summary = reward_summary(seat_placements)
    positive_reward_count = int(rewards["positive_count"])
    zero_reward_count = int(rewards["zero_count"])
    negative_reward_count = int(rewards["negative_count"])
    return {
        "match_mode": normalized_match_mode,
        "chongci_config": _chongci_report_config(
            normalized_match_mode,
            chongci_starting_score,
            chongci_bust_threshold,
            chongci_max_hands,
        ),
        "seat": learning_seat,
        "avg_reward": round(float(rewards["mean"]), 2),
        "mean_reward": rewards["mean"],
        "mean_reward_sem": rewards["sem"],
        "mean_reward_ci95": rewards["ci95"],
        "reward_sum": rewards["sum"],
        "reward_summary": rewards,
        "win_count": wins,
        "win_rate": wins / completed if completed else 0.0,
        "win_metric_note": (
            "Backward-compatible reward-positive count; for chongci this is final match net-positive rate, "
            "not single-hand win rate."
            if normalized_match_mode == "chongci"
            else "Reward-positive single-round result."
        ),
        "positive_reward_count": positive_reward_count,
        "positive_reward_rate": rewards["positive_rate"],
        "zero_reward_count": zero_reward_count,
        "zero_reward_rate": rewards["zero_rate"],
        "negative_reward_count": negative_reward_count,
        "negative_reward_rate": rewards["negative_rate"],
        "large_loss_count": large_losses,
        "large_loss_rate": large_losses / completed if completed else 0.0,
        "large_loss_threshold": resolved_large_loss_threshold,
        "episodes": completed,
        "per_episode_rewards": seat_rewards,
        "per_episode_placements": seat_placements,
        "mean_placement": placement_summary["mean"],
        "mean_placement_ci95": placement_summary["ci95"],
        # Placement now scores every completed episode (truncations as worst), so the
        # sample equals `episodes`; surfaced explicitly alongside the truncation rate
        # so any step-limit stalling is visible rather than silently censored.
        "placement_count": len(seat_placements),
        "truncation_count": truncations,
        "truncation_rate": truncations / completed if completed else 0.0,
        "action_family_counts": dict(sorted(action_counts.items())),
        "action_family_rates": action_family_rates(action_counts),
        "round_outcome_counts": dict(sorted(outcome_counts.items())),
        "round_outcome_rates": outcome_rates(outcome_counts),
        "policy_choice_counts": dict(sorted(choice_source_counts.items())),
        "policy_choice_rates": action_family_rates(choice_source_counts),
        "policy_q_margins": q_margins,
        "policy_q_margin_summary": reward_summary(q_margins),
        "policy_episode_summaries": policy_episode_summaries,
        "policy_episode_outcome_summary": summarize_policy_episode_outcomes(policy_episode_summaries),
        "episode_summaries": episode_summaries,
        "large_loss_episodes": summarize_large_loss_episodes(episode_summaries, resolved_large_loss_threshold),
    }


def evaluate_online(
    model: nn.Module,
    episodes: int,
    seeds: List[int],
    bridge_kind: str = "go",
    bridge_library_path: Optional[str] = None,
    device: str = "cpu",
    learning_seat: int = 0,
    large_loss_threshold: Optional[float] = None,
    match_mode: str = "classic",
    chongci_starting_score: int = 2000,
    chongci_bust_threshold: int = 0,
    chongci_max_hands: int = 50,
    max_steps_per_episode: Optional[int] = None,
    oracle_observation: bool = False,
    event_history_window: int = 0,
) -> Dict[str, Any]:
    """Run a model's greedy policy for one seat against heuristic opponents."""
    policy = TorchGreedyPolicy(model, device=device)
    return evaluate_policy_online(
        policy=policy,
        episodes=episodes,
        seeds=seeds,
        bridge_kind=bridge_kind,
        bridge_library_path=bridge_library_path,
        learning_seat=learning_seat,
        large_loss_threshold=large_loss_threshold,
        match_mode=match_mode,
        chongci_starting_score=chongci_starting_score,
        chongci_bust_threshold=chongci_bust_threshold,
        chongci_max_hands=chongci_max_hands,
        max_steps_per_episode=max_steps_per_episode,
        oracle_observation=oracle_observation,
        event_history_window=event_history_window,
    )


def _invoke_seat_policy_factory(factory: Any, seat: int, bridge: Any) -> Any:
    """Call a duplicate-seat ``policy_factory``, passing the seat's live bridge
    too when the factory accepts it.

    Existing factories (e.g. the sampling path's ``sampled_policy_factory(seat)``)
    take one argument and are called exactly as before -- just lazily, after
    ``evaluate_policy_online`` has built the bridge instead of before it exists,
    which has no observable effect since they don't touch the bridge. A factory
    declared with two parameters (``factory(seat, bridge)``) additionally
    receives that seat's bridge instance, e.g. so a search policy's rollout
    pool can clone the live decision point.
    """
    try:
        sig = inspect.signature(factory)
    except (TypeError, ValueError):
        return factory(seat)
    required = 0
    for p in sig.parameters.values():
        if p.kind == inspect.Parameter.VAR_POSITIONAL:
            # *args factories are today's 1-arg callers (e.g. sampled_policy_factory);
            # treat as needing exactly the seat, not the bridge too.
            continue
        if (
            p.default is inspect.Parameter.empty
            and p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        ):
            required += 1
    if required >= 2:
        return factory(seat, bridge)
    return factory(seat)


def evaluate_duplicate_seats_policy(
    policy_factory: Any,
    seeds: Sequence[int],
    seats: Iterable[int] = (0, 1, 2, 3),
    bridge_kind: str = "go",
    bridge_library_path: Optional[str] = None,
    large_loss_threshold: Optional[float] = None,
    match_mode: str = "classic",
    chongci_starting_score: int = 2000,
    chongci_bust_threshold: int = 0,
    chongci_max_hands: int = 50,
    max_steps_per_episode: Optional[int] = None,
    oracle_observation: bool = False,
    event_history_window: int = 0,
) -> Dict[str, Any]:
    """Evaluate a policy factory with the learning agent rotated through seats."""
    normalized_match_mode = _normalize_match_mode(match_mode)
    # Snapshot the bridge library BEFORE the eval loop: the digest and every
    # bridge dlopen refer to the same immutable copy (see
    # _snapshot_bridge_library), so a concurrent rebuild cannot make the
    # report attest a binary other than the one evaluated.
    bridge_library_path, bridge_lib_sha256, _bridge_snapshot = _snapshot_bridge_library(
        bridge_kind, bridge_library_path
    )
    seat_list = list(seats)
    seat_reports = []
    all_rewards: list[float] = []
    all_placements: list[float] = []
    action_counts: Counter[str] = Counter()
    outcome_counts: Counter[str] = Counter()
    choice_source_counts: Counter[str] = Counter()
    q_margins: list[float] = []
    policy_episode_summaries: list[dict[str, Any]] = []
    episode_summaries: list[dict[str, Any]] = []
    wins = 0
    large_losses = 0
    completed = 0
    truncations = 0

    try:
        for seat in seat_list:
            report = evaluate_policy_online(
                policy=None,
                policy_factory=lambda bridge, _seat=seat: _invoke_seat_policy_factory(policy_factory, _seat, bridge),
                episodes=len(seeds),
                seeds=list(seeds),
                bridge_kind=bridge_kind,
                bridge_library_path=bridge_library_path,
                learning_seat=seat,
                large_loss_threshold=large_loss_threshold,
                match_mode=normalized_match_mode,
                chongci_starting_score=chongci_starting_score,
                chongci_bust_threshold=chongci_bust_threshold,
                chongci_max_hands=chongci_max_hands,
                max_steps_per_episode=max_steps_per_episode,
                oracle_observation=oracle_observation,
                event_history_window=event_history_window,
            )
            seat_reports.append(report)
            all_rewards.extend(float(reward) for reward in report["per_episode_rewards"])
            all_placements.extend(float(p) for p in report.get("per_episode_placements", []))
            action_counts.update(report["action_family_counts"])
            outcome_counts.update(report.get("round_outcome_counts", {}))
            choice_source_counts.update(report.get("policy_choice_counts", {}))
            q_margins.extend(float(value) for value in report.get("policy_q_margins", []))
            policy_episode_summaries.extend(report.get("policy_episode_summaries", []))
            episode_summaries.extend(report.get("episode_summaries", []))
            wins += int(report["win_count"])
            large_losses += int(report["large_loss_count"])
            completed += int(report["episodes"])
            truncations += int(report.get("truncation_count", 0))

    finally:
        if _bridge_snapshot is not None:
            _bridge_snapshot.cleanup()
    rewards = reward_summary(all_rewards)
    placements = reward_summary(all_placements)
    seat_summary = {
        str(report["seat"]): {
            "episodes": report["episodes"],
            "mean_reward": report["mean_reward"],
            "reward_sum": report["reward_sum"],
            "win_rate": report["win_rate"],
            "positive_reward_rate": report["positive_reward_rate"],
            "negative_reward_rate": report["negative_reward_rate"],
            "large_loss_rate": report["large_loss_rate"],
            "action_family_rates": report["action_family_rates"],
            "round_outcome_rates": report.get("round_outcome_rates", {}),
            "policy_choice_rates": report.get("policy_choice_rates", {}),
        }
        for report in seat_reports
    }
    return {
        "match_mode": normalized_match_mode,
        "chongci_config": _chongci_report_config(
            normalized_match_mode,
            chongci_starting_score,
            chongci_bust_threshold,
            chongci_max_hands,
        ),
        "seeds": list(seeds),
        "seats": seat_list,
        "max_steps_per_episode": max_steps_per_episode,
        "oracle_observation": oracle_observation,
        "event_history_window": event_history_window,
        "bridge_lib_sha256": bridge_lib_sha256,
        "avg_reward": round(float(rewards["mean"]), 2),
        "mean_reward": rewards["mean"],
        "mean_reward_sem": rewards["sem"],
        "mean_reward_ci95": rewards["ci95"],
        "reward_sum": rewards["sum"],
        "reward_summary": rewards,
        "win_count": wins,
        "win_rate": wins / completed if completed else 0.0,
        "win_metric_note": (
            "Backward-compatible reward-positive count; for chongci this is final match net-positive rate, "
            "not single-hand win rate."
            if normalized_match_mode == "chongci"
            else "Reward-positive single-round result."
        ),
        "positive_reward_count": int(rewards["positive_count"]),
        "positive_reward_rate": rewards["positive_rate"],
        "zero_reward_count": int(rewards["zero_count"]),
        "zero_reward_rate": rewards["zero_rate"],
        "negative_reward_count": int(rewards["negative_count"]),
        "negative_reward_rate": rewards["negative_rate"],
        "large_loss_count": large_losses,
        "large_loss_rate": large_losses / completed if completed else 0.0,
        "large_loss_threshold": seat_reports[0]["large_loss_threshold"] if seat_reports else None,
        "episodes": completed,
        "per_episode_rewards": all_rewards,
        "per_episode_placements": all_placements,
        "mean_placement": placements["mean"],
        "mean_placement_ci95": placements["ci95"],
        "placement_count": len(all_placements),
        **_clustered_report_fields(seat_reports),
        "truncation_count": truncations,
        "truncation_rate": truncations / completed if completed else 0.0,
        "action_family_counts": dict(sorted(action_counts.items())),
        "action_family_rates": action_family_rates(action_counts),
        "round_outcome_counts": dict(sorted(outcome_counts.items())),
        "round_outcome_rates": outcome_rates(outcome_counts),
        "policy_choice_counts": dict(sorted(choice_source_counts.items())),
        "policy_choice_rates": action_family_rates(choice_source_counts),
        "policy_q_margins": q_margins,
        "policy_q_margin_summary": reward_summary(q_margins),
        "policy_episode_summaries": policy_episode_summaries,
        "policy_episode_outcome_summary": summarize_policy_episode_outcomes(policy_episode_summaries),
        "episode_summaries": episode_summaries,
        "large_loss_episodes": summarize_large_loss_episodes(
            episode_summaries,
            seat_reports[0]["large_loss_threshold"] if seat_reports else _default_large_loss_threshold(normalized_match_mode),
        ),
        "seat_summary": seat_summary,
        "seat_reports": seat_reports,
    }


def evaluate_duplicate_seats(
    model: nn.Module,
    seeds: Sequence[int],
    seats: Iterable[int] = (0, 1, 2, 3),
    bridge_kind: str = "go",
    bridge_library_path: Optional[str] = None,
    device: str = "cpu",
    large_loss_threshold: Optional[float] = None,
    match_mode: str = "classic",
    chongci_starting_score: int = 2000,
    chongci_bust_threshold: int = 0,
    chongci_max_hands: int = 50,
    max_steps_per_episode: Optional[int] = None,
    oracle_observation: bool = False,
    event_history_window: int = 0,
) -> Dict[str, Any]:
    """Evaluate the same seeds with the learning agent rotated through seats."""
    normalized_match_mode = _normalize_match_mode(match_mode)
    # Snapshot the bridge library BEFORE the eval loop: the digest and every
    # bridge dlopen refer to the same immutable copy (see
    # _snapshot_bridge_library), so a concurrent rebuild cannot make the
    # report attest a binary other than the one evaluated.
    bridge_library_path, bridge_lib_sha256, _bridge_snapshot = _snapshot_bridge_library(
        bridge_kind, bridge_library_path
    )
    seat_list = list(seats)
    seat_reports = []
    all_rewards: list[float] = []
    all_placements: list[float] = []
    action_counts: Counter[str] = Counter()
    outcome_counts: Counter[str] = Counter()
    wins = 0
    large_losses = 0
    completed = 0
    truncations = 0
    episode_summaries: list[dict[str, Any]] = []

    try:
        for seat in seat_list:
            report = evaluate_online(
                model=model,
                episodes=len(seeds),
                seeds=list(seeds),
                bridge_kind=bridge_kind,
                bridge_library_path=bridge_library_path,
                device=device,
                learning_seat=seat,
                large_loss_threshold=large_loss_threshold,
                match_mode=normalized_match_mode,
                chongci_starting_score=chongci_starting_score,
                chongci_bust_threshold=chongci_bust_threshold,
                chongci_max_hands=chongci_max_hands,
                max_steps_per_episode=max_steps_per_episode,
                oracle_observation=oracle_observation,
                event_history_window=event_history_window,
            )
            seat_reports.append(report)
            all_rewards.extend(float(reward) for reward in report["per_episode_rewards"])
            all_placements.extend(float(p) for p in report.get("per_episode_placements", []))
            action_counts.update(report["action_family_counts"])
            outcome_counts.update(report.get("round_outcome_counts", {}))
            episode_summaries.extend(report.get("episode_summaries", []))
            wins += int(report["win_count"])
            large_losses += int(report["large_loss_count"])
            completed += int(report["episodes"])
            truncations += int(report.get("truncation_count", 0))

    finally:
        if _bridge_snapshot is not None:
            _bridge_snapshot.cleanup()
    rewards = reward_summary(all_rewards)
    placements = reward_summary(all_placements)
    seat_summary = {
        str(report["seat"]): {
            "episodes": report["episodes"],
            "mean_reward": report["mean_reward"],
            "reward_sum": report["reward_sum"],
            "win_rate": report["win_rate"],
            "positive_reward_rate": report["positive_reward_rate"],
            "negative_reward_rate": report["negative_reward_rate"],
            "large_loss_rate": report["large_loss_rate"],
            "action_family_rates": report["action_family_rates"],
            "round_outcome_rates": report.get("round_outcome_rates", {}),
        }
        for report in seat_reports
    }
    return {
        "match_mode": normalized_match_mode,
        "chongci_config": _chongci_report_config(
            normalized_match_mode,
            chongci_starting_score,
            chongci_bust_threshold,
            chongci_max_hands,
        ),
        "seeds": list(seeds),
        "seats": seat_list,
        "max_steps_per_episode": max_steps_per_episode,
        "oracle_observation": oracle_observation,
        "event_history_window": event_history_window,
        "bridge_lib_sha256": bridge_lib_sha256,
        "avg_reward": round(float(rewards["mean"]), 2),
        "mean_reward": rewards["mean"],
        "mean_reward_sem": rewards["sem"],
        "mean_reward_ci95": rewards["ci95"],
        "reward_sum": rewards["sum"],
        "reward_summary": rewards,
        "win_count": wins,
        "win_rate": wins / completed if completed else 0.0,
        "win_metric_note": (
            "Backward-compatible reward-positive count; for chongci this is final match net-positive rate, "
            "not single-hand win rate."
            if normalized_match_mode == "chongci"
            else "Reward-positive single-round result."
        ),
        "positive_reward_count": int(rewards["positive_count"]),
        "positive_reward_rate": rewards["positive_rate"],
        "zero_reward_count": int(rewards["zero_count"]),
        "zero_reward_rate": rewards["zero_rate"],
        "negative_reward_count": int(rewards["negative_count"]),
        "negative_reward_rate": rewards["negative_rate"],
        "large_loss_count": large_losses,
        "large_loss_rate": large_losses / completed if completed else 0.0,
        "large_loss_threshold": seat_reports[0]["large_loss_threshold"] if seat_reports else None,
        "episodes": completed,
        "per_episode_rewards": all_rewards,
        "per_episode_placements": all_placements,
        "mean_placement": placements["mean"],
        "mean_placement_ci95": placements["ci95"],
        "placement_count": len(all_placements),
        **_clustered_report_fields(seat_reports),
        "truncation_count": truncations,
        "truncation_rate": truncations / completed if completed else 0.0,
        "action_family_counts": dict(sorted(action_counts.items())),
        "action_family_rates": action_family_rates(action_counts),
        "round_outcome_counts": dict(sorted(outcome_counts.items())),
        "round_outcome_rates": outcome_rates(outcome_counts),
        "episode_summaries": episode_summaries,
        "large_loss_episodes": summarize_large_loss_episodes(
            episode_summaries,
            seat_reports[0]["large_loss_threshold"] if seat_reports else _default_large_loss_threshold(normalized_match_mode),
        ),
        "seat_summary": seat_summary,
        "seat_reports": seat_reports,
    }
