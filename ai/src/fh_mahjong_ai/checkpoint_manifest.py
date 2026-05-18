"""Tracked checkpoint manifest helpers."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


DEFAULT_MANIFEST_PATH = Path(__file__).resolve().parents[3] / "checkpoints" / "best-checkpoints.json"
DEFAULT_CHECKPOINT_ENV = "FH_MAHJONG_AI_CHECKPOINT"


@dataclass(frozen=True)
class CheckpointEntry:
    id: str
    method: str
    checkpoint_path: Path
    payload: dict[str, Any]


@dataclass(frozen=True)
class CheckpointManifest:
    path: Path
    payload: dict[str, Any]

    @property
    def current(self) -> CheckpointEntry:
        return _entry_from_payload(self.payload["current_reward_trained_best"])

    @property
    def fallbacks(self) -> tuple[CheckpointEntry, ...]:
        return tuple(_entry_from_payload(item) for item in self.payload.get("fallbacks", []))

    def fallback(self, fallback_id: Optional[str] = None) -> CheckpointEntry:
        fallbacks = self.fallbacks
        if not fallbacks:
            raise ValueError("checkpoint manifest has no fallbacks")
        if fallback_id is None:
            return fallbacks[0]
        for entry in fallbacks:
            if entry.id == fallback_id:
                return entry
        raise KeyError(f"fallback checkpoint {fallback_id!r} is not in {self.path}")


def load_checkpoint_manifest(path: Path = DEFAULT_MANIFEST_PATH) -> CheckpointManifest:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if int(payload.get("schema_version", 0)) != 1:
        raise ValueError(f"unsupported checkpoint manifest schema in {path}")
    return CheckpointManifest(path=path, payload=payload)


def resolve_checkpoint_path(
    manifest: CheckpointManifest,
    checkpoint_id: str = "current",
    checkpoint_override: Optional[Path] = None,
    env_var: str = DEFAULT_CHECKPOINT_ENV,
) -> Path:
    """Resolve a checkpoint path for serving.

    Explicit CLI overrides win, then the environment variable, then the tracked
    manifest entry. This lets local and remote machines use the same manifest
    while keeping large binary checkpoints out of git.
    """
    if checkpoint_override is not None:
        return checkpoint_override
    env_value = os.environ.get(env_var)
    if env_value:
        return Path(env_value)
    if checkpoint_id == "current":
        return manifest.current.checkpoint_path
    if checkpoint_id == "fallback":
        return manifest.fallback().checkpoint_path
    if checkpoint_id == manifest.current.id:
        return manifest.current.checkpoint_path
    for fallback in manifest.fallbacks:
        if checkpoint_id == fallback.id:
            return fallback.checkpoint_path
    raise KeyError(f"checkpoint id {checkpoint_id!r} is not in {manifest.path}")


def _entry_from_payload(payload: dict[str, Any]) -> CheckpointEntry:
    return CheckpointEntry(
        id=str(payload["id"]),
        method=str(payload.get("method", "")),
        checkpoint_path=Path(str(payload["checkpoint_path"])),
        payload=payload,
    )
