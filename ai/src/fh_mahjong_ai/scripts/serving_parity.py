"""Spec B2c Task 8: `fh-mj-serving-parity` — the HARD-GATE eval-vs-serving action
parity harness.

For every seeded bridge decision state this drives two independent code
paths against the SAME checkpoint weights and demands they agree:

- the "reference"/eval path: `TorchGreedyPolicy.choose()` fed the raw bridge
  `Observation` directly (no wire round-trip);
- the "serving" path: the /act-shaped JSON payload `HTTPPolicy` would send
  (see `internal/bot/remote/http_policy.go`'s `actRequest` — compact
  `event_history`/`event_count`/`event_window`/`contract_version` fields,
  tail-windowed from the bridge observation's raw event history), decoded
  the same way `serve_policy.py`'s `/act` handler does
  (`observation_from_json`), then fed to `CheckpointPolicy.choose()`
  in-process OR POSTed as a real HTTP request to a running `serve_policy`
  server (`--endpoint`).

Any action-id disagreement, illegal action, HTTP error, or (in-process only)
excessive logit drift is an IMMEDIATE failure that dumps the offending seed,
decision index, and state summary — this is a hard gate, not a smoke test.
Exit 0 only when every decision checked agreed.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import torch

from fh_mahjong_ai.bridge import build_bridge
from fh_mahjong_ai.config import EnvConfig
from fh_mahjong_ai.events import EVENT_CONTRACT_V1
from fh_mahjong_ai.policies import TorchGreedyPolicy
from fh_mahjong_ai.scripts import serve_policy as serve_policy_module
from fh_mahjong_ai.serving import CheckpointPolicy
from fh_mahjong_ai.types import Observation

# In-process logit tolerance (spec B2c section 3, item 2): "exact logits on
# the same hardware, tight tolerance (1e-4)".
LOGIT_TOLERANCE = 1e-4


class ServingParityError(RuntimeError):
    """Raised on the first parity violation; the message carries the full
    failure dump (seed, decision index, offending state summary) required by
    the hard-gate contract."""


@dataclass
class EpisodeSummary:
    seed: int
    decisions: int
    agreements: int


@dataclass
class ParityReport:
    decisions_checked: int = 0
    agreements: int = 0
    max_logit_diff: float = 0.0
    episodes: list[EpisodeSummary] = field(default_factory=list)

    @property
    def all_agree(self) -> bool:
        # Deliberately vacuity-proof: zero decisions checked is NOT a pass.
        return self.decisions_checked > 0 and self.agreements == self.decisions_checked


def build_act_payload(observation: Observation, decision_index: int, event_window: int) -> dict:
    """Build the exact /act JSON payload `HTTPPolicy.chooseRemoteCtx` would
    send for this observation: the compact wire form, tail-windowed to
    `event_window` (the SERVING policy's declared window — the room hands
    each policy the raw, unwindowed event log; each policy applies its own
    contract, per the DecisionContext design). Field names/shapes mirror
    `actRequest` in internal/bot/remote/http_policy.go exactly."""
    history = np.asarray(observation.event_history, dtype=np.uint32)
    windowed_count = min(history.size, event_window) if event_window > 0 else 0
    windowed = history[-windowed_count:].tolist() if windowed_count else []
    payload: dict = {
        "seat": int(observation.seat),
        "planes": np.asarray(observation.planes, dtype=np.float32).reshape(-1).tolist(),
        "scalars": np.asarray(observation.scalars, dtype=np.float32).reshape(-1).tolist(),
        "action_mask": [int(value) for value in np.asarray(observation.action_mask).reshape(-1).tolist()],
        "event_count": windowed_count,
        "event_window": int(event_window),
        "contract_version": EVENT_CONTRACT_V1,
        "metadata": {
            "decision_index": int(decision_index),
            "phase": "",
            "active_player": int(observation.seat),
        },
    }
    # Go's `EventHistory []uint32 \`json:"event_history,omitempty"\`` drops an
    # empty slice entirely rather than sending `[]`; mirror that so the
    # decode path (`observation_from_json`'s "missing history + count==0 is
    # valid" branch) is exercised identically to the real wire form.
    if windowed:
        payload["event_history"] = windowed
    return payload


def _forward_logits(model: torch.nn.Module, observation: Observation, device: str) -> np.ndarray:
    """Direct model forward pass for `observation`, replicating the tensor
    construction `CheckpointPolicy.choose`/`TorchGreedyPolicy.choose` do
    (tail-windowed, zero-padded event rows). Used ONLY for the in-process
    logit-tolerance check; action-id agreement (the actual hard gate) comes
    from calling the real `.choose()` entry points, not this helper."""
    planes = torch.from_numpy(np.asarray(observation.planes, dtype=np.float32)).unsqueeze(0).to(device)
    scalars = torch.from_numpy(np.asarray(observation.scalars, dtype=np.float32)).unsqueeze(0).to(device)
    action_mask = torch.from_numpy(np.asarray(observation.action_mask, dtype=np.int8)).unsqueeze(0).to(device)
    events = event_lengths = None
    if getattr(model, "wants_events", False):
        window = model.model_config.event_window
        history = np.asarray(observation.event_history, dtype=np.uint32)
        row = np.zeros((1, window), dtype=np.int64)
        n = min(history.size, window)
        if n:
            row[0, :n] = history[-n:].astype(np.int64)
        events = torch.from_numpy(row).to(device)
        event_lengths = torch.tensor([n], dtype=torch.int64, device=device)
    with torch.inference_mode():
        logits, _ = model(planes, scalars, action_mask, events=events, event_lengths=event_lengths)
    return logits.detach().cpu().numpy()[0]


def _post_act(endpoint: str, payload: dict, timeout: float) -> tuple[int, Optional[str]]:
    """Real HTTP POST to a running serve_policy `/act` endpoint. Returns
    (action_id, error); error is non-None on ANY failure (HTTP status,
    connection error, or an `{"error": ...}` response body) — the hard gate
    tolerates none of these."""
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        endpoint, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return -1, f"HTTP {exc.code}: {detail}"
    except urllib.error.URLError as exc:
        return -1, f"connection error: {exc.reason}"
    data = json.loads(raw)
    if data.get("error"):
        return -1, str(data["error"])
    action_id = data.get("action_id")
    if action_id is None:
        return -1, "response missing 'action_id'"
    return int(action_id), None


def _failure_message(seed: int, decision_index: int, reason: str, observation: Observation) -> str:
    return (
        f"serving parity FAILED seed={seed} decision_index={decision_index}: {reason}\n"
        f"  seat={observation.seat} legal_actions={observation.legal_actions} "
        f"event_history_len={int(np.asarray(observation.event_history).size)}"
    )


def run_serving_parity(
    checkpoint: Path,
    event_history_window: int,
    episodes: int,
    start_seed: int,
    device: str = "cpu",
    endpoint: Optional[str] = None,
    bridge_kind: str = "mock",
    bridge_library_path: Optional[Path] = None,
    max_decisions: int = 64,
    http_timeout: float = 5.0,
) -> ParityReport:
    """Drive `episodes` seeded bridge episodes (seeds `start_seed ..
    start_seed + episodes - 1`), checking eval-vs-serving action parity on
    every decision. Raises `ServingParityError` on the first violation.
    """
    # One model load, shared by both the reference (TorchGreedyPolicy) and,
    # in --in-process mode, the serving (CheckpointPolicy) path: this isolates
    # feature-construction/wire-round-trip drift from weight drift, which is
    # exactly the residual risk the spec's hard gate targets. In --endpoint
    # mode the model is still loaded locally to build the reference policy;
    # the serving action instead comes from a REAL HTTP call to the endpoint
    # under test, so the endpoint's own weights are independently verified by
    # the eventual action-id comparison.
    served_reference = CheckpointPolicy.from_checkpoint(checkpoint, device=device)
    model = served_reference.model
    model_event_window = model.model_config.event_window
    reference_policy = TorchGreedyPolicy(model=model, device=device)

    env_config = EnvConfig(
        bridge_kind=bridge_kind,
        bridge_library_path=bridge_library_path,
        learning_seats=(0, 1, 2, 3),
        auto_play_heuristics=False,
        max_steps_per_episode=max_decisions,
        event_history_window=max(int(event_history_window), model_event_window),
    )
    bridge = build_bridge(env_config)
    report = ParityReport()
    try:
        for offset in range(max(0, int(episodes))):
            seed = start_seed + offset
            observation = bridge.reset(seed=seed)
            reset_result = bridge.last_reset_result
            if reset_result is not None and (reset_result.terminated or reset_result.truncated):
                report.episodes.append(EpisodeSummary(seed=seed, decisions=0, agreements=0))
                continue

            decisions = 0
            agreements = 0
            decision_index = 0
            while True:
                reference_action = reference_policy.choose(observation)
                act_payload = build_act_payload(observation, decision_index, model_event_window)

                if endpoint is not None:
                    serving_action_id, served_error = _post_act(endpoint, act_payload, timeout=http_timeout)
                    if served_error is not None:
                        raise ServingParityError(
                            _failure_message(seed, decision_index, f"endpoint error: {served_error}", observation)
                        )
                else:
                    served_observation = serve_policy_module.observation_from_json(act_payload, model_event_window)
                    try:
                        served = served_reference.choose(served_observation)
                    except Exception as exc:  # noqa: BLE001 - any raise here is a hard-gate failure, not a bug
                        raise ServingParityError(
                            _failure_message(seed, decision_index, f"serving choose() raised: {exc}", observation)
                        ) from exc
                    serving_action_id = served.greedy_action_id

                    reference_logits = _forward_logits(model, observation, device)
                    serving_logits = _forward_logits(model, served_observation, device)
                    logit_diff = float(np.max(np.abs(reference_logits - serving_logits)))
                    report.max_logit_diff = max(report.max_logit_diff, logit_diff)
                    if logit_diff > LOGIT_TOLERANCE:
                        raise ServingParityError(
                            _failure_message(
                                seed, decision_index,
                                f"logit max-abs diff {logit_diff:.6g} exceeds tolerance {LOGIT_TOLERANCE:.0e}",
                                observation,
                            )
                        )

                if serving_action_id not in observation.legal_actions:
                    raise ServingParityError(
                        _failure_message(
                            seed, decision_index,
                            f"serving action_id={serving_action_id} is illegal; legal={observation.legal_actions}",
                            observation,
                        )
                    )
                if serving_action_id != reference_action.action_id:
                    raise ServingParityError(
                        _failure_message(
                            seed, decision_index,
                            f"action mismatch: serving={serving_action_id} reference={reference_action.action_id}",
                            observation,
                        )
                    )

                decisions += 1
                agreements += 1
                report.decisions_checked += 1
                report.agreements += 1

                decision_index += 1
                result = bridge.step(reference_action.action_id)
                if result.terminated or result.truncated:
                    break
                observation = result.observation

            report.episodes.append(EpisodeSummary(seed=seed, decisions=decisions, agreements=agreements))
    finally:
        bridge.close()

    return report


def _print_summary(report: ParityReport, *, mode: str, checkpoint: Path, device: str) -> None:
    print(f"fh-mj-serving-parity report ({mode}, device={device})")
    print(f"  checkpoint:        {checkpoint}")
    print(f"  episodes:          {len(report.episodes)}")
    print(f"  decisions checked: {report.decisions_checked}")
    print(f"  agreements:        {report.agreements}")
    if mode == "in-process":
        print(f"  max logit diff:    {report.max_logit_diff:.3e} (tolerance {LOGIT_TOLERANCE:.0e})")
    print("  per-episode:")
    for episode in report.episodes:
        print(
            f"    seed={episode.seed:>10} decisions={episode.decisions:>4} agreements={episode.agreements:>4}"
        )
    print(f"  result: {'PASS' if report.all_agree else 'FAIL'}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Hard-gate eval-vs-serving action parity harness (Spec B2c). "
        "Exit 0 only on 100% action-id parity across every decision checked."
    )
    parser.add_argument("--checkpoint", type=Path, required=True, help="Path to the .pt checkpoint under test")
    parser.add_argument(
        "--event-history-window", type=int, required=True,
        help="Bridge event-history window (rows); use the checkpoint's own event_window for an "
        "event model, or 0 for a window-0 (event-free) checkpoint",
    )
    parser.add_argument("--episodes", type=int, required=True, help="Number of seeded bridge episodes")
    parser.add_argument("--start-seed", type=int, required=True, help="First episode seed (seeds start_seed..start_seed+episodes-1)")
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--in-process", action="store_true",
        help="Fast mode: CheckpointPolicy fed the /act-shaped payload directly, no HTTP server needed",
    )
    mode_group.add_argument(
        "--endpoint", type=str, default=None,
        help="Hard-gate mode: real HTTP POSTs to this running serve_policy /act URL",
    )
    parser.add_argument("--device", type=str, default="cpu", choices=("cpu", "cuda"))
    parser.add_argument("--bridge-kind", choices=("mock", "go"), default="mock", help="Bridge implementation to seed decision states from")
    parser.add_argument("--bridge-lib", type=Path, default=None, help="Path to c-shared library (--bridge-kind go)")
    parser.add_argument("--max-decisions", type=int, default=64, help="Bridge decision cap per episode")
    parser.add_argument("--http-timeout", type=float, default=5.0, help="Per-request timeout in seconds (--endpoint mode)")
    args = parser.parse_args()

    try:
        report = run_serving_parity(
            checkpoint=args.checkpoint,
            event_history_window=args.event_history_window,
            episodes=args.episodes,
            start_seed=args.start_seed,
            device=args.device,
            endpoint=args.endpoint,
            bridge_kind=args.bridge_kind,
            bridge_library_path=args.bridge_lib,
            max_decisions=args.max_decisions,
            http_timeout=args.http_timeout,
        )
    except ServingParityError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

    mode = "endpoint" if args.endpoint else "in-process"
    _print_summary(report, mode=mode, checkpoint=args.checkpoint, device=args.device)
    if not report.all_agree:
        print("serving parity FAILED: not every checked decision agreed", file=sys.stderr)
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
