from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Iterator, Optional

import numpy as np
import torch

from .data import compute_steps_to_done
from .types import Observation, Transition

SHARDED_TRANSITIONS_MANIFEST = "manifest.json"
SHARDED_TRANSITIONS_SCHEMA_VERSION = 1


class ShardedTransitionWriter:
    """Incrementally write transition arrays to NumPy shards."""

    def __init__(
        self,
        directory: Path,
        shard_size: int = 50_000,
        compressed: bool = False,
        overwrite: bool = True,
    ) -> None:
        self.directory = directory
        self.shard_size = max(1, int(shard_size))
        self.compressed = compressed
        self.shards: list[dict[str, object]] = []
        self.total = 0
        self._current: list[Transition] = []
        self._closed = False

        self.directory.mkdir(parents=True, exist_ok=True)
        if overwrite:
            for path in self.directory.glob("transitions-*.npz"):
                path.unlink()
            manifest_path = self.directory / SHARDED_TRANSITIONS_MANIFEST
            if manifest_path.exists():
                manifest_path.unlink()

    def write_many(self, transitions: Iterable[Transition]) -> None:
        if self._closed:
            raise RuntimeError("cannot write to a closed ShardedTransitionWriter")
        for transition in transitions:
            self._current.append(transition)
            if len(self._current) >= self.shard_size:
                self._flush_current()

    def close(self) -> dict[str, object]:
        if self._closed:
            return self.manifest()
        if self._current:
            self._flush_current()
        manifest = self.manifest()
        (self.directory / SHARDED_TRANSITIONS_MANIFEST).write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        self._closed = True
        return manifest

    def manifest(self) -> dict[str, object]:
        return {
            "schema_version": SHARDED_TRANSITIONS_SCHEMA_VERSION,
            "format": "npz_shards",
            "compressed": self.compressed,
            "shard_size": self.shard_size,
            "transitions": self.total,
            "shards": self.shards,
        }

    def _flush_current(self) -> None:
        self.total += _write_transition_shard(
            self.directory,
            self._current,
            len(self.shards),
            self.compressed,
            self.shards,
        )
        self._current = []

    def __enter__(self) -> "ShardedTransitionWriter":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def save_checkpoint(path: Path, model: torch.nn.Module, optimizer: Optional[torch.optim.Optimizer] = None, step: int = 0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"model": model.state_dict(), "step": step}
    if optimizer is not None:
        payload["optimizer"] = optimizer.state_dict()
    torch.save(payload, path)


def load_checkpoint(path: Path, model: torch.nn.Module, optimizer: Optional[torch.optim.Optimizer] = None) -> int:
    payload = torch.load(path, map_location="cpu")
    checkpoint_state = _adapt_checkpoint_state(payload["model"], model.state_dict())
    missing, unexpected = model.load_state_dict(checkpoint_state, strict=False)
    compatible_optional_prefixes = ("q_head.", "large_loss_head.", "action_risk_probability_head.", "action_risk_severity_head.")
    missing_bad = [key for key in missing if not key.startswith(compatible_optional_prefixes)]
    unexpected_bad = [key for key in unexpected if not key.startswith(compatible_optional_prefixes)]
    if missing_bad or unexpected_bad:
        raise RuntimeError(
            "checkpoint is incompatible with model state: "
            f"missing={missing_bad}, unexpected={unexpected_bad}"
        )
    if optimizer is not None and "optimizer" in payload:
        optimizer.load_state_dict(payload["optimizer"])
    return int(payload.get("step", 0))


def load_compatible_checkpoint(path: Path, model: torch.nn.Module) -> tuple[int, dict[str, object]]:
    """Load only same-name, same-shape tensors from a checkpoint.

    This is intended for explicit architecture ablations, for example adding
    residual blocks while reusing the existing stem, early blocks, and heads.
    Normal serving/evaluation should use `load_checkpoint`.
    """
    payload = torch.load(path, map_location="cpu")
    target_state = model.state_dict()
    checkpoint_state = _adapt_checkpoint_state(payload["model"], target_state)
    compatible = {
        key: value
        for key, value in checkpoint_state.items()
        if key in target_state and value.shape == target_state[key].shape
    }
    skipped = sorted(
        key
        for key, value in checkpoint_state.items()
        if key not in target_state or value.shape != target_state[key].shape
    )
    missing = sorted(key for key in target_state if key not in compatible)
    merged = dict(target_state)
    merged.update(compatible)
    model.load_state_dict(merged)
    return int(payload.get("step", 0)), {
        "loaded_keys": len(compatible),
        "missing_keys": missing,
        "skipped_keys": skipped,
    }


def _adapt_checkpoint_state(
    checkpoint_state: dict[str, torch.Tensor],
    model_state: dict[str, torch.Tensor],
) -> dict[str, torch.Tensor]:
    adapted = dict(checkpoint_state)
    key = "scalar_encoder.0.weight"
    if key not in adapted or key not in model_state:
        return adapted

    source = adapted[key]
    target = model_state[key]
    if source.shape == target.shape or source.ndim != 2 or target.ndim != 2:
        return adapted

    migrated = target.clone()
    rows = min(source.shape[0], target.shape[0])
    cols = min(source.shape[1], target.shape[1])
    migrated[:rows, :cols] = source[:rows, :cols]
    if target.shape[1] > source.shape[1]:
        migrated[:, source.shape[1] :] = 0
    adapted[key] = migrated
    return adapted


def write_transitions_jsonl(path: Path, transitions: Iterable[Transition], append: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    with path.open(mode, encoding="utf-8") as handle:
        for transition in transitions:
            handle.write(json.dumps(_transition_to_dict(transition)) + "\n")


def read_transitions_jsonl(path: Path) -> list[Transition]:
    return list(iter_transitions_jsonl(path))


def iter_transitions_jsonl(path: Path) -> Iterable[Transition]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            yield _transition_from_dict(json.loads(line))


def read_transitions(path: Path) -> list[Transition]:
    """Read transitions from JSONL or a sharded NumPy dataset directory."""
    if path.is_dir():
        return read_transitions_npz_shards(path)
    if path.name == SHARDED_TRANSITIONS_MANIFEST:
        return read_transitions_npz_shards(path.parent)
    return read_transitions_jsonl(path)


def is_sharded_transition_dataset(path: Path) -> bool:
    return path.is_dir() or path.name == SHARDED_TRANSITIONS_MANIFEST


def read_transition_arrays(
    path: Path,
    keys: Optional[Iterable[str]] = None,
    optional_keys: Optional[Iterable[str]] = None,
    limit: Optional[int] = None,
) -> dict[str, np.ndarray]:
    """Read transitions as contiguous arrays for array-backed replay buffers."""
    if is_sharded_transition_dataset(path):
        directory = path.parent if path.name == SHARDED_TRANSITIONS_MANIFEST else path
        return _read_npz_transition_arrays(directory, keys=keys, optional_keys=optional_keys, limit=limit)
    arrays = _transitions_to_arrays(read_transitions_jsonl(path))
    if limit is not None:
        arrays = {key: value[: max(0, int(limit))] for key, value in arrays.items()}
    if keys is None and optional_keys is None:
        return arrays
    selected = set(keys or arrays.keys())
    selected.update(optional_keys or ())
    return {key: value for key, value in arrays.items() if key in selected}


def iter_observation_action_batches(path: Path, batch_size: int) -> Iterator[dict[str, np.ndarray]]:
    """Yield observation/action arrays for offline policy evaluation."""
    effective_batch_size = max(1, int(batch_size))
    if path.is_dir() or path.name == SHARDED_TRANSITIONS_MANIFEST:
        directory = path.parent if path.name == SHARDED_TRANSITIONS_MANIFEST else path
        yield from _iter_npz_observation_action_batches(directory, effective_batch_size)
    else:
        yield from _iter_jsonl_observation_action_batches(path, effective_batch_size)


def write_transitions_npz_shards(
    directory: Path,
    transitions: Iterable[Transition],
    shard_size: int = 50_000,
    compressed: bool = False,
) -> dict[str, object]:
    """Write transitions to a directory of array shards plus a manifest."""
    writer = ShardedTransitionWriter(directory, shard_size=shard_size, compressed=compressed)
    writer.write_many(transitions)
    return writer.close()


def read_transitions_npz_shards(directory: Path) -> list[Transition]:
    manifest_path = directory / SHARDED_TRANSITIONS_MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if int(manifest.get("schema_version", 0)) != SHARDED_TRANSITIONS_SCHEMA_VERSION:
        raise ValueError(f"unsupported sharded transition schema in {manifest_path}")

    transitions: list[Transition] = []
    for shard in manifest.get("shards", []):
        shard_path = directory / str(shard["path"])
        transitions.extend(_read_transition_shard(shard_path))
    return transitions


def _iter_npz_observation_action_batches(directory: Path, batch_size: int) -> Iterator[dict[str, np.ndarray]]:
    manifest_path = directory / SHARDED_TRANSITIONS_MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if int(manifest.get("schema_version", 0)) != SHARDED_TRANSITIONS_SCHEMA_VERSION:
        raise ValueError(f"unsupported sharded transition schema in {manifest_path}")

    for shard in manifest.get("shards", []):
        shard_path = directory / str(shard["path"])
        with np.load(shard_path, allow_pickle=False) as arrays:
            total = int(arrays["action_ids"].shape[0])
            for start in range(0, total, batch_size):
                stop = min(start + batch_size, total)
                yield {
                    "planes": np.asarray(arrays["planes"][start:stop], dtype=np.float32),
                    "scalars": np.asarray(arrays["scalars"][start:stop], dtype=np.float32),
                    "action_mask": np.asarray(arrays["action_mask"][start:stop], dtype=np.int8),
                    "action_ids": np.asarray(arrays["action_ids"][start:stop], dtype=np.int64),
                }


def _read_npz_transition_arrays(
    directory: Path,
    keys: Optional[Iterable[str]] = None,
    optional_keys: Optional[Iterable[str]] = None,
    limit: Optional[int] = None,
) -> dict[str, np.ndarray]:
    manifest_path = directory / SHARDED_TRANSITIONS_MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if int(manifest.get("schema_version", 0)) != SHARDED_TRANSITIONS_SCHEMA_VERSION:
        raise ValueError(f"unsupported sharded transition schema in {manifest_path}")

    shards = list(manifest.get("shards", []))
    total = int(manifest.get("transitions", 0))
    if limit is not None:
        total = min(total, max(0, int(limit)))
    if total == 0:
        raise ValueError(f"empty sharded transition dataset at {directory}")

    first_path = directory / str(shards[0]["path"])
    with np.load(first_path, allow_pickle=False) as first:
        selected_keys = list(first.files if keys is None else keys)
        optional = [key for key in (optional_keys or ()) if key in first.files and key not in selected_keys]
        selected_keys.extend(optional)
        missing = sorted(set(keys or []) - set(first.files))
        if missing:
            raise KeyError(f"sharded transition dataset is missing arrays: {', '.join(missing)}")
        arrays = {
            key: np.empty((total,) + first[key].shape[1:], dtype=first[key].dtype)
            for key in selected_keys
        }

    offset = 0
    for shard in shards:
        shard_path = directory / str(shard["path"])
        with np.load(shard_path, allow_pickle=False) as loaded:
            count = min(int(loaded["action_ids"].shape[0]), total - offset)
            if count <= 0:
                break
            for key, target in arrays.items():
                target[offset : offset + count] = loaded[key][:count]
            offset += count
            if offset >= total:
                break
    return arrays


def _iter_jsonl_observation_action_batches(path: Path, batch_size: int) -> Iterator[dict[str, np.ndarray]]:
    planes: list[np.ndarray] = []
    scalars: list[np.ndarray] = []
    masks: list[np.ndarray] = []
    action_ids: list[int] = []

    def emit() -> dict[str, np.ndarray]:
        return {
            "planes": np.stack(planes).astype(np.float32),
            "scalars": np.stack(scalars).astype(np.float32),
            "action_mask": np.stack(masks).astype(np.int8),
            "action_ids": np.asarray(action_ids, dtype=np.int64),
        }

    for transition in iter_transitions_jsonl(path):
        planes.append(transition.observation.planes)
        scalars.append(transition.observation.scalars)
        masks.append(transition.observation.action_mask)
        action_ids.append(transition.action_id)
        if len(action_ids) >= batch_size:
            yield emit()
            planes.clear()
            scalars.clear()
            masks.clear()
            action_ids.clear()
    if action_ids:
        yield emit()


def _write_transition_shard(
    directory: Path,
    transitions: list[Transition],
    index: int,
    compressed: bool,
    shards: list[dict[str, object]],
) -> int:
    shard_name = f"transitions-{index:05d}.npz"
    shard_path = directory / shard_name
    payload = _transitions_to_arrays(transitions)
    writer = np.savez_compressed if compressed else np.savez
    writer(shard_path, **payload)
    shards.append({"path": shard_name, "transitions": len(transitions)})
    return len(transitions)


def _transitions_to_arrays(transitions: list[Transition]) -> dict[str, np.ndarray]:
    def terminal_rewards_for(transition: Transition) -> np.ndarray:
        terminal_rewards = transition.info.get("terminal_rewards")
        if terminal_rewards is None:
            return np.asarray(transition.rewards, dtype=np.float32)
        return np.asarray(terminal_rewards, dtype=np.float32)

    def terminal_outcome_for(transition: Transition) -> dict[str, object]:
        outcome = transition.info.get("terminal_outcome") or transition.info.get("round_outcome")
        return outcome if isinstance(outcome, dict) else {}

    outcomes = [terminal_outcome_for(t) for t in transitions]
    episode_indices = np.asarray(
        [int(t.info.get("episode_index", 0)) for t in transitions],
        dtype=np.int64,
    )
    dones = np.asarray([t.terminated or t.truncated for t in transitions], dtype=np.bool_)
    steps_to_done = np.asarray(
        [
            int(t.info["steps_to_done"])
            if "steps_to_done" in t.info
            else int(value)
            for t, value in zip(transitions, compute_steps_to_done(episode_indices, dones))
        ],
        dtype=np.int32,
    )

    return {
        "seats": np.asarray([t.observation.seat for t in transitions], dtype=np.int16),
        "planes": np.stack([t.observation.planes for t in transitions]).astype(np.float32),
        "scalars": np.stack([t.observation.scalars for t in transitions]).astype(np.float32),
        "action_mask": np.stack([t.observation.action_mask for t in transitions]).astype(np.int8),
        "action_ids": np.asarray([t.action_id for t in transitions], dtype=np.int64),
        "decision_indices": np.asarray(
            [int(t.observation.metadata.get("decision_index", -1)) for t in transitions],
            dtype=np.int64,
        ),
        "rewards": np.stack([t.rewards for t in transitions]).astype(np.float32),
        "next_seats": np.asarray([t.next_observation.seat for t in transitions], dtype=np.int16),
        "next_planes": np.stack([t.next_observation.planes for t in transitions]).astype(np.float32),
        "next_scalars": np.stack([t.next_observation.scalars for t in transitions]).astype(np.float32),
        "next_action_mask": np.stack([t.next_observation.action_mask for t in transitions]).astype(np.int8),
        "terminated": np.asarray([t.terminated for t in transitions], dtype=np.bool_),
        "truncated": np.asarray([t.truncated for t in transitions], dtype=np.bool_),
        "episode_index": episode_indices,
        "steps_to_done": steps_to_done,
        "policy_source_ids": np.asarray([int(t.info.get("policy_source_id", -1)) for t in transitions], dtype=np.int16),
        "policy_values": np.asarray([float(t.info.get("policy_value", np.nan)) for t in transitions], dtype=np.float32),
        "sample_weights": np.asarray([float(t.info.get("sample_weight", 1.0)) for t in transitions], dtype=np.float32),
        "terminal_rewards": np.stack([terminal_rewards_for(t) for t in transitions]).astype(np.float32),
        "terminal_is_draw": np.asarray([bool(o.get("is_draw", False)) for o in outcomes], dtype=np.bool_),
        "terminal_winner_seat": np.asarray([int(o.get("winner_seat", -1)) for o in outcomes], dtype=np.int16),
        "terminal_win_type": np.asarray([int(o.get("win_type", 0)) for o in outcomes], dtype=np.int16),
        "terminal_discarder_seat": np.asarray([int(o.get("discarder_seat", -1)) for o in outcomes], dtype=np.int16),
        "terminal_total_score": np.asarray([int(o.get("total_score", 0)) for o in outcomes], dtype=np.int32),
    }


def _read_transition_shard(path: Path) -> list[Transition]:
    with np.load(path, allow_pickle=False) as arrays:
        total = int(arrays["action_ids"].shape[0])
        transitions: list[Transition] = []
        for index in range(total):
            observation = Observation(
                seat=int(arrays["seats"][index]),
                planes=np.asarray(arrays["planes"][index], dtype=np.float32),
                scalars=np.asarray(arrays["scalars"][index], dtype=np.float32),
                    action_mask=np.asarray(arrays["action_mask"][index], dtype=np.int8),
                    metadata={
                        "decision_index": int(arrays["decision_indices"][index])
                        if "decision_indices" in arrays.files
                        else 0,
                    },
            )
            next_observation = Observation(
                seat=int(arrays["next_seats"][index]),
                planes=np.asarray(arrays["next_planes"][index], dtype=np.float32),
                scalars=np.asarray(arrays["next_scalars"][index], dtype=np.float32),
                action_mask=np.asarray(arrays["next_action_mask"][index], dtype=np.int8),
            )
            transitions.append(
                Transition(
                    observation=observation,
                    action_id=int(arrays["action_ids"][index]),
                    rewards=np.asarray(arrays["rewards"][index], dtype=np.float32),
                    next_observation=next_observation,
                    terminated=bool(arrays["terminated"][index]),
                    truncated=bool(arrays["truncated"][index]),
                    info={
                        "episode_index": int(arrays["episode_index"][index]),
                        "steps_to_done": int(arrays["steps_to_done"][index]) if "steps_to_done" in arrays.files else 0,
                        "terminal_rewards": np.asarray(arrays["terminal_rewards"][index], dtype=np.float32),
                        "sample_weight": float(arrays["sample_weights"][index]) if "sample_weights" in arrays.files else 1.0,
                        **_policy_source_info(arrays, index),
                        **_terminal_outcome_info(arrays, index),
                    },
                )
            )
    return transitions


def _policy_source_info(arrays: np.lib.npyio.NpzFile, index: int) -> dict[str, object]:
    info: dict[str, object] = {}
    if "policy_source_ids" in arrays.files:
        info["policy_source_id"] = int(arrays["policy_source_ids"][index])
    if "policy_values" in arrays.files:
        value = float(arrays["policy_values"][index])
        if not np.isnan(value):
            info["policy_value"] = value
    return info


def _terminal_outcome_info(arrays: np.lib.npyio.NpzFile, index: int) -> dict[str, object]:
    required = {
        "terminal_is_draw",
        "terminal_winner_seat",
        "terminal_win_type",
        "terminal_discarder_seat",
        "terminal_total_score",
    }
    if not required.issubset(set(arrays.files)):
        return {}

    is_draw = bool(arrays["terminal_is_draw"][index])
    winner_seat = int(arrays["terminal_winner_seat"][index])
    win_type = int(arrays["terminal_win_type"][index])
    discarder_seat = int(arrays["terminal_discarder_seat"][index])
    total_score = int(arrays["terminal_total_score"][index])
    if not is_draw and winner_seat < 0 and win_type == 0:
        return {}

    return {
        "terminal_outcome": {
            "is_draw": is_draw,
            "winner_seat": winner_seat,
            "win_type": win_type,
            "discarder_seat": discarder_seat,
            "total_score": total_score,
            "payouts": [],
        }
    }


def _transition_to_dict(transition: Transition) -> dict[str, object]:
    return {
        "observation": _observation_to_dict(transition.observation),
        "action_id": transition.action_id,
        "rewards": transition.rewards.tolist(),
        "next_observation": _observation_to_dict(transition.next_observation),
        "terminated": transition.terminated,
        "truncated": transition.truncated,
        "info": _sanitize_info(transition.info),
    }


def _sanitize_info(info: dict) -> dict:
    """Convert any numpy arrays in an info dict to plain Python lists."""
    result = {}
    for key, value in info.items():
        result[key] = value.tolist() if isinstance(value, np.ndarray) else value
    return result


def _transition_from_dict(payload: dict[str, object]) -> Transition:
    from .types import Transition

    return Transition(
        observation=_observation_from_dict(payload["observation"]),
        action_id=int(payload["action_id"]),
        rewards=np.asarray(payload["rewards"], dtype=np.float32),
        next_observation=_observation_from_dict(payload["next_observation"]),
        terminated=bool(payload["terminated"]),
        truncated=bool(payload.get("truncated", False)),
        info=dict(payload.get("info", {})),
    )


def _observation_to_dict(observation: Observation) -> dict[str, object]:
    return {
        "seat": observation.seat,
        "planes": observation.planes.tolist(),
        "scalars": observation.scalars.tolist(),
        "action_mask": observation.action_mask.tolist(),
        "metadata": observation.metadata,
    }


def _observation_from_dict(payload: dict[str, object]) -> Observation:
    return Observation(
        seat=int(payload["seat"]),
        planes=np.asarray(payload["planes"], dtype=np.float32),
        scalars=np.asarray(payload["scalars"], dtype=np.float32),
        action_mask=np.asarray(payload["action_mask"], dtype=np.int8),
        metadata=dict(payload.get("metadata", {})),
    )
