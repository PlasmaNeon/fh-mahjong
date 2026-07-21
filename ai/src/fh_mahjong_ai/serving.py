"""Checkpoint-backed inference helpers for serving Mahjong actions."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import torch

from .action_catalog import action_family
from .bridge import build_bridge
from .checkpoint_manifest import DEFAULT_MANIFEST_PATH, load_checkpoint_manifest, resolve_checkpoint_path
from .config import EnvConfig
from .model import PolicyValueNet, infer_model_config
from .storage import load_checkpoint
from .types import Observation


@dataclass(frozen=True)
class ServedAction:
    action_id: int
    value: float
    checkpoint_path: str
    checkpoint_step: int
    greedy_action_id: int = -1
    sampling_applied: bool = False
    sampled_from_greedy: bool = False
    # Masked logits (the ones argmax was actually taken over), populated only
    # when `choose(..., return_logits=True)` is requested (see
    # serve_policy.py's `return_logits` /act field, added for Finding 3's
    # endpoint-mode logit-parity gate). Illegal-action entries carry
    # `torch.finfo(dtype).min` — a large but FINITE negative value (not
    # -inf), so it round-trips through `json.dumps` without special-casing.
    logits: Optional[np.ndarray] = None


class CheckpointPolicy:
    """PolicyValueNet checkpoint wrapper for visible-observation inference."""

    def __init__(
        self,
        model: PolicyValueNet,
        checkpoint_path: Path,
        checkpoint_step: int,
        device: str = "cpu",
        sample_temperature: float = 0.0,
        sample_top_k: int = 0,
        sample_action_family: str = "all",
        seed: int = 1,
    ) -> None:
        self.model = model
        self.checkpoint_path = checkpoint_path
        self.checkpoint_step = checkpoint_step
        self.device = device
        self.sample_temperature = max(0.0, float(sample_temperature))
        self.sample_top_k = max(0, int(sample_top_k))
        self.sample_action_family = str(sample_action_family or "all")
        self.sample_seed = int(seed)  # kept so holders can rebuild with the same config
        self._rng = np.random.default_rng(seed)
        self.model.eval()

    @classmethod
    def from_checkpoint(
        cls,
        checkpoint_path: Path,
        device: str = "cpu",
        sample_temperature: float = 0.0,
        sample_top_k: int = 0,
        sample_action_family: str = "all",
        seed: int = 1,
    ) -> "CheckpointPolicy":
        # Architecture varies across promoted checkpoints (e.g. residual-block
        # depth, or Spec B2b's event encoder / privileged critic / aux heads);
        # recover it from the saved tensors (plus any checkpoint metadata)
        # instead of assuming defaults.
        payload = torch.load(checkpoint_path, map_location="cpu")
        saved_state = payload["model"]
        metadata = payload.get("metadata")
        model = PolicyValueNet(EnvConfig(), infer_model_config(saved_state, metadata))
        step = load_checkpoint(checkpoint_path, model)
        model.to(device)
        return cls(
            model=model,
            checkpoint_path=checkpoint_path,
            checkpoint_step=step,
            device=device,
            sample_temperature=sample_temperature,
            sample_top_k=sample_top_k,
            sample_action_family=sample_action_family,
            seed=seed,
        )

    @torch.inference_mode()
    def choose(self, observation: Observation, return_logits: bool = False) -> ServedAction:
        legal_actions = observation.legal_actions
        if not legal_actions:
            raise ValueError("observation has no legal actions")

        planes = torch.from_numpy(observation.planes).unsqueeze(0).to(self.device)
        scalars = torch.from_numpy(observation.scalars).unsqueeze(0).to(self.device)
        expected_scalars = self.model.scalar_encoder[0].in_features
        if scalars.shape[1] < expected_scalars:
            scalars = torch.nn.functional.pad(scalars, (0, expected_scalars - scalars.shape[1]))
        elif scalars.shape[1] > expected_scalars:
            raise ValueError(f"expected at most {expected_scalars} scalars, got {scalars.shape[1]}")
        action_mask = torch.from_numpy(observation.action_mask).unsqueeze(0).to(self.device)

        events = event_lengths = None
        if getattr(self.model, "wants_events", False):
            window = self.model.model_config.event_window
            history = np.asarray(
                getattr(observation, "event_history", np.zeros(0, np.uint32)), dtype=np.uint32
            )
            if history.size == 0:
                # Defense-in-depth: serve_policy's own validation is the first
                # line of defense against this, but an event model (window>0)
                # must never silently zero-fill a missing history — that
                # would serve a decision the model was never trained to make.
                # A genuinely early-round history is short, not empty: this
                # codebase's bridges always emit at least a deal/draw event
                # before any decision reaches serving (see test_events.py's
                # test_mock_bridge_emits_wellformed_history), so an empty
                # history here indicates an upstream bug, not a legitimate
                # round start.
                raise ValueError(
                    f"event model (event_window={window}) received an observation with an "
                    "EMPTY event_history; refusing to silently zero-fill it"
                )
            row = np.zeros((1, window), dtype=np.int64)
            n = min(history.size, window)
            row[0, :n] = history[-n:].astype(np.int64)
            events = torch.from_numpy(row).to(self.device)
            event_lengths = torch.tensor([n], dtype=torch.int64, device=self.device)

        logits, value = self.model(planes, scalars, action_mask, events=events, event_lengths=event_lengths)
        greedy_action_id = int(torch.argmax(logits, dim=1).item())
        sampling_actions = self._sampling_actions(legal_actions)
        sampling_applied = self.sample_temperature > 0.0 and bool(sampling_actions)
        if self.sample_temperature > 0.0 and sampling_actions:
            legal_actions = sampling_actions
            candidate_actions = np.asarray(legal_actions, dtype=np.int64)
            legal_logits = logits[0, legal_actions].detach().cpu().numpy().astype(np.float64)
            if self.sample_top_k > 0 and legal_logits.size > self.sample_top_k:
                top_indices = np.argpartition(-legal_logits, self.sample_top_k - 1)[: self.sample_top_k]
                top_indices = top_indices[np.argsort(-legal_logits[top_indices])]
                candidate_actions = candidate_actions[top_indices]
                legal_logits = legal_logits[top_indices]
            scaled = legal_logits / self.sample_temperature
            scaled -= float(np.max(scaled))
            probabilities = np.exp(scaled)
            probabilities /= float(np.sum(probabilities))
            action_id = int(self._rng.choice(candidate_actions, p=probabilities))
        else:
            action_id = greedy_action_id
        if action_id not in legal_actions:
            raise ValueError(f"model selected illegal action_id={action_id}; legal={legal_actions}")
        return ServedAction(
            action_id=action_id,
            value=float(value.item()),
            checkpoint_path=str(self.checkpoint_path),
            checkpoint_step=self.checkpoint_step,
            greedy_action_id=greedy_action_id,
            sampling_applied=sampling_applied,
            sampled_from_greedy=sampling_applied and action_id != greedy_action_id,
            logits=logits[0].detach().cpu().numpy() if return_logits else None,
        )

    @torch.inference_mode()
    def evaluate_batch(
        self,
        planes: np.ndarray,
        scalars: np.ndarray,
        action_masks: np.ndarray,
        chunk_size: int = 256,
        events: Optional[np.ndarray] = None,
        event_lengths: Optional[np.ndarray] = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Masked policy distribution + value for a batch of visible observations.

        Deterministic: no temperature/top-k sampling. Illegal actions get exactly
        zero probability. Used by the post-game review pipeline.

        `events`/`event_lengths` are optional int64/int32 arrays shaped like
        `TorchGreedyPolicy`'s per-row tensors (`[n, model_config.event_window]`
        and `[n]`); omit them for window-0 models. Unlike `choose`, this batch
        entry point has no per-row Observation to validate against, so it does
        not raise on a missing/empty history — callers that batch event-model
        observations are responsible for supplying real histories.
        """
        n = planes.shape[0]
        no_legal_rows = np.flatnonzero(~action_masks.astype(bool).any(axis=1))
        if no_legal_rows.size:
            raise ValueError(f"observation {int(no_legal_rows[0])} has no legal actions")
        all_probs = np.zeros((n, action_masks.shape[1]), dtype=np.float32)
        all_values = np.zeros((n,), dtype=np.float32)
        expected_scalars = self.model.scalar_encoder[0].in_features
        for start in range(0, n, max(1, chunk_size)):
            end = min(n, start + max(1, chunk_size))
            p = torch.from_numpy(planes[start:end]).to(self.device)
            s = torch.from_numpy(scalars[start:end]).to(self.device)
            if s.shape[1] < expected_scalars:
                s = torch.nn.functional.pad(s, (0, expected_scalars - s.shape[1]))
            elif s.shape[1] > expected_scalars:
                raise ValueError(f"expected at most {expected_scalars} scalars, got {s.shape[1]}")
            m = torch.from_numpy(action_masks[start:end]).to(self.device)
            ev = ev_len = None
            if events is not None and event_lengths is not None:
                ev = torch.from_numpy(events[start:end]).to(self.device)
                ev_len = torch.from_numpy(event_lengths[start:end]).to(self.device)
            logits, value = self.model(p, s, m, events=ev, event_lengths=ev_len)
            legal = m.to(dtype=torch.bool)
            masked = logits.masked_fill(~legal, float("-inf"))
            probs = torch.softmax(masked, dim=1)
            probs = probs.masked_fill(~legal, 0.0)  # exact zeros, no -inf softmax residue
            all_probs[start:end] = probs.cpu().numpy().astype(np.float32)
            all_values[start:end] = value.reshape(-1).cpu().numpy().astype(np.float32)
        return all_probs, all_values

    def _sampling_actions(self, legal_actions: list[int]) -> list[int]:
        if self.sample_action_family in {"", "all", "*"}:
            return list(legal_actions)
        if all(action_family(action_id) == self.sample_action_family for action_id in legal_actions):
            return list(legal_actions)
        return []


def load_policy_from_manifest(
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
    checkpoint_id: str = "current",
    checkpoint_override: Optional[Path] = None,
    device: str = "cpu",
    sample_temperature: float = 0.0,
    sample_top_k: int = 0,
    sample_action_family: str = "all",
    sample_seed: int = 1,
) -> CheckpointPolicy:
    manifest = load_checkpoint_manifest(manifest_path)
    checkpoint_path = resolve_checkpoint_path(
        manifest=manifest,
        checkpoint_id=checkpoint_id,
        checkpoint_override=checkpoint_override,
    )
    return CheckpointPolicy.from_checkpoint(
        checkpoint_path,
        device=device,
        sample_temperature=sample_temperature,
        sample_top_k=sample_top_k,
        sample_action_family=sample_action_family,
        seed=sample_seed,
    )


def run_bridge_serving_smoke(
    policy: CheckpointPolicy,
    episodes: int = 4,
    start_seed: int = 1,
    bridge_kind: str = "mock",
    bridge_library_path: Optional[Path] = None,
    max_decisions: int = 512,
) -> dict[str, int]:
    """Step a served policy through a bridge so Go/mock legality validates actions."""
    completed = 0
    decisions = 0
    # Thread the served model's event window into the bridge config: an event
    # model (model_config.event_window > 0) requires a non-empty event
    # history on every decision (CheckpointPolicy.choose fails closed
    # otherwise, see the EMPTY event_history guard above), so the bridge must
    # be told to actually populate one. Leaving this at the EnvConfig default
    # (0) made this smoke unable to exercise any event checkpoint at all.
    config = EnvConfig(
        bridge_kind=bridge_kind,
        bridge_library_path=bridge_library_path,
        learning_seats=(0, 1, 2, 3),
        auto_play_heuristics=False,
        max_steps_per_episode=max_decisions,
        event_history_window=int(policy.model.model_config.event_window),
    )
    bridge = build_bridge(config)
    try:
        for offset in range(max(0, int(episodes))):
            observation = bridge.reset(seed=start_seed + offset)
            reset_result = bridge.last_reset_result
            if reset_result is not None and (reset_result.terminated or reset_result.truncated):
                completed += 1
                continue
            while True:
                action = policy.choose(observation)
                decisions += 1
                result = bridge.step(action.action_id)
                if result.terminated or result.truncated:
                    completed += 1
                    break
                observation = result.observation
    finally:
        bridge.close()
    return {"episodes": completed, "decisions": decisions}
