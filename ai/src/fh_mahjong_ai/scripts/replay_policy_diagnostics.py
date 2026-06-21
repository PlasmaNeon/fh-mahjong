"""Compare checkpoints on existing replay states before live evaluation."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import torch

from fh_mahjong_ai.action_catalog import action_family
from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.scripts.model_config_args import add_model_config_args, model_config_from_args, model_config_params
from fh_mahjong_ai.storage import SHARDED_TRANSITIONS_SCHEMA_VERSION, load_checkpoint, read_transition_arrays

REPLAY_KEYS = (
    "planes",
    "scalars",
    "action_mask",
    "action_ids",
    "seats",
    "terminal_rewards",
    "policy_source_ids",
)


def _summary(values: np.ndarray) -> dict[str, float]:
    if values.size == 0:
        return {"count": 0, "mean": 0.0, "sum": 0.0, "std": 0.0, "min": 0.0, "max": 0.0}
    return {
        "count": int(values.size),
        "mean": float(np.mean(values)),
        "sum": float(np.sum(values)),
        "std": float(np.std(values)),
        "min": float(np.min(values)),
        "max": float(np.max(values)),
    }


def _rate(numerator: int, denominator: int) -> float:
    return float(numerator / denominator) if denominator else 0.0


def _counter_rates(counter: Counter[str], total: int) -> dict[str, float]:
    return {key: _rate(value, total) for key, value in sorted(counter.items())}


def _count_by_family(action_ids: np.ndarray) -> Counter[str]:
    return Counter(action_family(int(action_id)) for action_id in action_ids.tolist())


def _load_policy(checkpoint: Path, model_config: ModelConfig, device: str) -> tuple[PolicyValueNet, int]:
    model = PolicyValueNet(EnvConfig(), model_config)
    step = load_checkpoint(checkpoint, model)
    model.to(device)
    model.eval()
    return model, step


def _predict_actions(
    model: PolicyValueNet,
    arrays: dict[str, np.ndarray],
    batch_size: int,
    device: str,
) -> np.ndarray:
    predictions: list[np.ndarray] = []
    total = int(arrays["action_ids"].shape[0])
    with torch.inference_mode():
        for start in range(0, total, max(1, int(batch_size))):
            stop = min(start + max(1, int(batch_size)), total)
            planes = torch.from_numpy(np.asarray(arrays["planes"][start:stop], dtype=np.float32)).to(device)
            scalars = torch.from_numpy(np.asarray(arrays["scalars"][start:stop], dtype=np.float32)).to(device)
            mask = torch.from_numpy(np.asarray(arrays["action_mask"][start:stop], dtype=np.int8)).to(device)
            logits, _ = model(planes, scalars, mask)
            predictions.append(torch.argmax(logits, dim=1).cpu().numpy().astype(np.int64))
    if not predictions:
        return np.zeros(0, dtype=np.int64)
    return np.concatenate(predictions, axis=0)


def _family_pair_counts(left_actions: np.ndarray, right_actions: np.ndarray) -> Counter[str]:
    pairs: Counter[str] = Counter()
    for left, right in zip(left_actions.tolist(), right_actions.tolist()):
        pairs[f"{action_family(int(left))}->{action_family(int(right))}"] += 1
    return pairs


def _policy_source_summary(values: np.ndarray, mask: np.ndarray) -> dict[str, dict[str, float | int]]:
    summary: dict[str, dict[str, float | int]] = {}
    for source_id in sorted(np.unique(values).astype(np.int64).tolist()):
        source_mask = values == source_id
        total = int(source_mask.sum())
        changed = int(np.logical_and(source_mask, mask).sum())
        summary[str(int(source_id))] = {
            "total": total,
            "divergence_count": changed,
            "divergence_rate": _rate(changed, total),
        }
    return summary


def build_replay_policy_diagnostics(
    data_path: Path,
    anchor_checkpoint: Path,
    candidate_checkpoint: Path,
    model_config: ModelConfig | None = None,
    batch_size: int = 4096,
    device: str = "cpu",
    large_loss_threshold: float = -1.0,
    max_transitions: int | None = None,
) -> dict[str, Any]:
    effective_model_config = model_config or ModelConfig()
    arrays = read_transition_arrays(data_path, keys=REPLAY_KEYS, limit=max_transitions)
    anchor_model, anchor_step = _load_policy(anchor_checkpoint, effective_model_config, device)
    candidate_model, candidate_step = _load_policy(candidate_checkpoint, effective_model_config, device)

    replay_actions = np.asarray(arrays["action_ids"], dtype=np.int64)
    seats = np.asarray(arrays["seats"], dtype=np.int64)
    terminal_rewards = np.asarray(arrays["terminal_rewards"], dtype=np.float32)
    row_indices = np.arange(replay_actions.shape[0], dtype=np.int64)
    acting_returns = terminal_rewards[row_indices, seats]
    anchor_actions = _predict_actions(anchor_model, arrays, batch_size=batch_size, device=device)
    candidate_actions = _predict_actions(candidate_model, arrays, batch_size=batch_size, device=device)

    total = int(replay_actions.shape[0])
    anchor_replay_match = anchor_actions == replay_actions
    candidate_replay_match = candidate_actions == replay_actions
    candidate_anchor_match = candidate_actions == anchor_actions
    divergence_mask = ~candidate_anchor_match
    large_loss_mask = acting_returns <= float(large_loss_threshold)
    positive_mask = acting_returns > 0.0

    divergence_returns = acting_returns[divergence_mask]
    agreement_returns = acting_returns[~divergence_mask]
    source_ids = np.asarray(arrays["policy_source_ids"], dtype=np.int64)
    family_pair_counts = _family_pair_counts(anchor_actions[divergence_mask], candidate_actions[divergence_mask])

    divergence_by_replay_family: dict[str, dict[str, float | int]] = {}
    for family in sorted(set(action_family(int(action_id)) for action_id in replay_actions.tolist())):
        family_mask = np.asarray([action_family(int(action_id)) == family for action_id in replay_actions], dtype=np.bool_)
        family_total = int(family_mask.sum())
        family_divergence = int(np.logical_and(family_mask, divergence_mask).sum())
        divergence_by_replay_family[family] = {
            "total": family_total,
            "divergence_count": family_divergence,
            "divergence_rate": _rate(family_divergence, family_total),
        }

    return {
        "schema_version": 1,
        "data": str(data_path),
        "anchor_checkpoint": str(anchor_checkpoint),
        "anchor_checkpoint_step": int(anchor_step),
        "candidate_checkpoint": str(candidate_checkpoint),
        "candidate_checkpoint_step": int(candidate_step),
        "device": device,
        "batch_size": int(batch_size),
        "max_transitions": int(max_transitions) if max_transitions is not None else None,
        "large_loss_threshold": float(large_loss_threshold),
        "model_config": model_config_params(effective_model_config),
        "total_transitions": total,
        "replay_action_family_counts": dict(sorted(_count_by_family(replay_actions).items())),
        "anchor_action_family_counts": dict(sorted(_count_by_family(anchor_actions).items())),
        "candidate_action_family_counts": dict(sorted(_count_by_family(candidate_actions).items())),
        "anchor_vs_replay": {
            "agreement_count": int(anchor_replay_match.sum()),
            "agreement_rate": _rate(int(anchor_replay_match.sum()), total),
        },
        "candidate_vs_replay": {
            "agreement_count": int(candidate_replay_match.sum()),
            "agreement_rate": _rate(int(candidate_replay_match.sum()), total),
        },
        "candidate_vs_anchor": {
            "agreement_count": int(candidate_anchor_match.sum()),
            "agreement_rate": _rate(int(candidate_anchor_match.sum()), total),
            "divergence_count": int(divergence_mask.sum()),
            "divergence_rate": _rate(int(divergence_mask.sum()), total),
            "divergence_family_pair_counts": dict(sorted(family_pair_counts.items())),
            "divergence_family_pair_rates": _counter_rates(family_pair_counts, int(divergence_mask.sum())),
            "divergence_by_replay_action_family": divergence_by_replay_family,
            "divergence_by_policy_source_id": _policy_source_summary(source_ids, divergence_mask),
        },
        "returns": {
            "all": _summary(acting_returns),
            "anchor_candidate_agree": _summary(agreement_returns),
            "anchor_candidate_diverge": _summary(divergence_returns),
            "positive_rate": _rate(int(positive_mask.sum()), total),
            "large_loss_rate": _rate(int(large_loss_mask.sum()), total),
            "large_loss_divergence_count": int(np.logical_and(large_loss_mask, divergence_mask).sum()),
            "large_loss_divergence_rate": _rate(int(np.logical_and(large_loss_mask, divergence_mask).sum()), int(large_loss_mask.sum())),
        },
    }


def build_anchor_preservation_divergence_arrays(
    data_path: Path,
    anchor_checkpoint: Path,
    candidate_checkpoint: Path,
    model_config: ModelConfig | None = None,
    batch_size: int = 4096,
    device: str = "cpu",
    large_loss_threshold: float = -1.0,
    max_transitions: int | None = None,
    family_pair: str | None = None,
    large_loss_only: bool = False,
    pairwise_reward_gap: float = 0.05,
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    """Build pairwise rows where a rejected candidate diverges from the anchor.

    These labels are anchor-preservation labels, not exact branch counterfactual
    rewards. Use them to prevent known harmful candidate drift before promoting
    another broad replay update.
    """
    effective_model_config = model_config or ModelConfig()
    arrays = read_transition_arrays(data_path, keys=REPLAY_KEYS, limit=max_transitions)
    anchor_model, anchor_step = _load_policy(anchor_checkpoint, effective_model_config, device)
    candidate_model, candidate_step = _load_policy(candidate_checkpoint, effective_model_config, device)

    replay_actions = np.asarray(arrays["action_ids"], dtype=np.int64)
    seats = np.asarray(arrays["seats"], dtype=np.int64)
    terminal_rewards = np.asarray(arrays["terminal_rewards"], dtype=np.float32)
    row_indices = np.arange(replay_actions.shape[0], dtype=np.int64)
    acting_returns = terminal_rewards[row_indices, seats]
    anchor_actions = _predict_actions(anchor_model, arrays, batch_size=batch_size, device=device)
    candidate_actions = _predict_actions(candidate_model, arrays, batch_size=batch_size, device=device)
    divergence_mask = anchor_actions != candidate_actions
    if family_pair is not None:
        requested_pair = str(family_pair)
        pair_mask = np.asarray(
            [
                f"{action_family(int(anchor))}->{action_family(int(candidate))}" == requested_pair
                for anchor, candidate in zip(anchor_actions.tolist(), candidate_actions.tolist())
            ],
            dtype=np.bool_,
        )
        divergence_mask = np.logical_and(divergence_mask, pair_mask)
    if large_loss_only:
        divergence_mask = np.logical_and(divergence_mask, acting_returns <= float(large_loss_threshold))

    selected = np.flatnonzero(divergence_mask).astype(np.int64)
    if selected.size == 0:
        raise ValueError("no anchor/candidate divergence rows matched the requested filters")

    output_arrays = {
        "seats": seats[selected].astype(np.int16, copy=False),
        "planes": np.asarray(arrays["planes"][selected], dtype=np.float32),
        "scalars": np.asarray(arrays["scalars"][selected], dtype=np.float32),
        "action_mask": np.asarray(arrays["action_mask"][selected], dtype=np.int8),
        "action_ids": candidate_actions[selected].astype(np.int64, copy=False),
        "episode_index": selected.astype(np.int64, copy=False),
        "terminal_rewards": terminal_rewards[selected].astype(np.float32, copy=False),
        "sample_weights": np.ones(selected.size, dtype=np.float32),
        "pairwise_preferred_action_ids": anchor_actions[selected].astype(np.int64, copy=False),
        "pairwise_avoided_action_ids": candidate_actions[selected].astype(np.int64, copy=False),
        "pairwise_weights": np.ones(selected.size, dtype=np.float32),
        "pairwise_reward_delta_targets": np.full(selected.size, float(pairwise_reward_gap), dtype=np.float32),
        "replay_action_ids": replay_actions[selected].astype(np.int64, copy=False),
        "replay_row_indices": selected.astype(np.int64, copy=False),
        "replay_acting_returns": acting_returns[selected].astype(np.float32, copy=False),
        "policy_source_ids": np.asarray(arrays["policy_source_ids"][selected], dtype=np.int16),
    }
    metadata: dict[str, Any] = {
        "label_type": "anchor_preservation_divergence",
        "warning": (
            "preferred/avoided actions come from anchor-vs-candidate replay divergence, "
            "not exact same-state branch reward evaluation"
        ),
        "data": str(data_path),
        "anchor_checkpoint": str(anchor_checkpoint),
        "anchor_checkpoint_step": int(anchor_step),
        "candidate_checkpoint": str(candidate_checkpoint),
        "candidate_checkpoint_step": int(candidate_step),
        "max_transitions": int(max_transitions) if max_transitions is not None else None,
        "large_loss_threshold": float(large_loss_threshold),
        "large_loss_only": bool(large_loss_only),
        "family_pair_filter": family_pair,
        "pairwise_reward_gap": float(pairwise_reward_gap),
        "rows": int(selected.size),
        "return_summary": _summary(acting_returns[selected]),
        "family_pair_counts": dict(sorted(_family_pair_counts(anchor_actions[selected], candidate_actions[selected]).items())),
        "replay_action_family_counts": dict(sorted(_count_by_family(replay_actions[selected]).items())),
        "policy_source_counts": {str(key): int(value) for key, value in sorted(Counter(output_arrays["policy_source_ids"].tolist()).items())},
    }
    return output_arrays, metadata


def write_divergence_shard(output_dir: Path, arrays: dict[str, np.ndarray], metadata: dict[str, Any]) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    for path in output_dir.glob("transitions-*.npz"):
        path.unlink()
    shard_name = "transitions-00000.npz"
    np.savez(output_dir / shard_name, **arrays)
    manifest = {
        "schema_version": SHARDED_TRANSITIONS_SCHEMA_VERSION,
        "format": "npz_shards",
        "compressed": False,
        "shard_size": int(arrays["action_ids"].shape[0]),
        "transitions": int(arrays["action_ids"].shape[0]),
        "shards": [{"path": shard_name, "transitions": int(arrays["action_ids"].shape[0])}],
        "counterfactual": metadata,
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare anchor and candidate checkpoint choices on replay states")
    parser.add_argument("--data", type=Path, required=True, help="JSONL or sharded NumPy transition dataset")
    parser.add_argument("--anchor-checkpoint", type=Path, required=True)
    parser.add_argument("--candidate-checkpoint", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=4096)
    parser.add_argument("--device", type=str, default="cpu")
    parser.add_argument("--large-loss-threshold", type=float, default=-1.0)
    parser.add_argument("--max-transitions", type=int, default=None)
    parser.add_argument("--report-output", type=Path, default=None)
    parser.add_argument("--divergence-output-dir", type=Path, default=None)
    parser.add_argument(
        "--divergence-family-pair",
        type=str,
        default=None,
        help="Optional anchor->candidate action-family pair filter, e.g. discard->discard.",
    )
    parser.add_argument("--divergence-large-loss-only", action="store_true")
    parser.add_argument(
        "--divergence-pairwise-reward-gap",
        type=float,
        default=0.05,
        help="Conservative synthetic gap for anchor-preservation pairwise labels.",
    )
    add_model_config_args(parser)
    args = parser.parse_args()
    model_config = model_config_from_args(args)

    report = build_replay_policy_diagnostics(
        data_path=args.data,
        anchor_checkpoint=args.anchor_checkpoint,
        candidate_checkpoint=args.candidate_checkpoint,
        model_config=model_config,
        batch_size=args.batch_size,
        device=args.device,
        large_loss_threshold=args.large_loss_threshold,
        max_transitions=args.max_transitions,
    )
    if args.divergence_output_dir is not None:
        arrays, metadata = build_anchor_preservation_divergence_arrays(
            data_path=args.data,
            anchor_checkpoint=args.anchor_checkpoint,
            candidate_checkpoint=args.candidate_checkpoint,
            model_config=model_config,
            batch_size=args.batch_size,
            device=args.device,
            large_loss_threshold=args.large_loss_threshold,
            max_transitions=args.max_transitions,
            family_pair=args.divergence_family_pair,
            large_loss_only=args.divergence_large_loss_only,
            pairwise_reward_gap=args.divergence_pairwise_reward_gap,
        )
        manifest = write_divergence_shard(args.divergence_output_dir, arrays, metadata)
        report["divergence_output"] = {
            "path": str(args.divergence_output_dir),
            "rows": int(arrays["action_ids"].shape[0]),
            "manifest": manifest,
        }
    payload = json.dumps(report, indent=2, sort_keys=True)
    if args.report_output is not None:
        args.report_output.parent.mkdir(parents=True, exist_ok=True)
        args.report_output.write_text(payload + "\n", encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
