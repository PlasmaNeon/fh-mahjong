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
import hashlib
import json
import math
import sys
import urllib.error
import urllib.parse
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
# Reuses evaluate.py's chongci step-budget resolution (adversarial round 10,
# Finding 1c): a full chongci match needs far more decisions than a fixed
# small default to have any chance of crossing round boundaries, and this is
# the SAME budget the champion's own online-eval CLI already relies on to
# reach PHASE_MATCH_END instead of truncating mid-match.
from fh_mahjong_ai.scripts.evaluate import resolve_max_steps_per_episode
from fh_mahjong_ai.serving import CheckpointPolicy
from fh_mahjong_ai.types import Observation

# Pre-Finding-1 default for --max-decisions in classic/mock mode; preserved
# so existing --in-process/mock callers (CI, this module's own tests) are
# unaffected by the chongci-aware resolution below.
_LEGACY_DEFAULT_MAX_DECISIONS = 64

# In-process logit tolerance (spec B2c section 3, item 2): "exact logits on
# the same hardware, tight tolerance (1e-4)".
LOGIT_TOLERANCE = 1e-4


class ServingParityError(RuntimeError):
    """Raised on the first parity violation; the message carries the full
    failure dump (seed, decision index, offending state summary) required by
    the hard-gate contract."""


def _finite_nonnegative_float(value: str) -> float:
    """argparse `type=` for --logit-tolerance: rejects NaN/Inf/negative at
    parse time (adversarial round 3, Finding 3). A NaN tolerance would make
    every `logit_diff > tolerance` comparison False (NaN compares false
    against everything), silently disabling the hard gate; Inf has the same
    effect since nothing can ever exceed it. argparse reports a clean usage
    error (exit code 2) rather than letting a bad value reach the episode
    loop."""
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid float value: {value!r}") from exc
    if not math.isfinite(parsed):
        raise argparse.ArgumentTypeError(f"--logit-tolerance must be finite, got {value!r}")
    if parsed < 0.0:
        raise argparse.ArgumentTypeError(f"--logit-tolerance must be >= 0, got {value!r}")
    return parsed


def _assert_finite_logits(logits: np.ndarray, legal: np.ndarray, *, side: str, seed: int, decision_index: int) -> None:
    """Hard-gate guard (Finding 3, adversarial round 3): a NaN or Inf entry in
    either logit vector, over the legal actions actually compared, makes the
    `abs(diff) > tolerance` check silently pass (NaN comparisons are always
    False; Inf - Inf is NaN too). Any non-finite legal-action logit is an
    immediate, explicit failure naming which side produced it, never a value
    that reaches the subtraction."""
    legal_logits = np.asarray(logits, dtype=np.float64)[legal]
    if not np.all(np.isfinite(legal_logits)):
        bad = [int(a) for a, v in zip(legal.tolist(), legal_logits.tolist()) if not math.isfinite(v)]
        raise ServingParityError(
            f"serving parity FAILED seed={seed} decision_index={decision_index}: "
            f"{side} logits contain non-finite values (NaN/Inf) at legal action ids {bad} "
            "— cannot be trusted for a tolerance comparison"
        )


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


def build_act_payload(
    observation: Observation, decision_index: int, event_window: int, return_logits: bool = False,
) -> dict:
    """Build the exact /act JSON payload `HTTPPolicy.chooseRemoteCtx` would
    send for this observation: the compact wire form, tail-windowed to
    `event_window` (the SERVING policy's declared window — the room hands
    each policy the raw, unwindowed event log; each policy applies its own
    contract, per the DecisionContext design). Field names/shapes mirror
    `actRequest` in internal/bot/remote/http_policy.go exactly, plus the
    harness-only `return_logits` field (Finding 3, adversarial round 2) that
    real Go callers never send — `serve_policy.py`'s `/act` handler treats it
    as opt-in and legacy servers simply ignore the unknown field."""
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
    if return_logits:
        payload["return_logits"] = True
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


def _derive_healthz_url(act_endpoint: str) -> str:
    """Map an /act endpoint to its /healthz route: same scheme+host(+port),
    path replaced wholesale. Mirrors `deriveHealthURL` in
    internal/bot/remote/health.go, which the Go server uses to derive the
    same URL from the same /act endpoint."""
    parsed = urllib.parse.urlsplit(act_endpoint)
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "/healthz", "", ""))


def _sha256_of_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_endpoint_checkpoint_identity(endpoint: str, checkpoint: Path, timeout: float = 5.0) -> None:
    """Hard-gate guard for `--endpoint` mode: before trusting any action-id
    agreement, confirm the running `serve_policy` server is actually serving
    the SAME checkpoint file under test, not a stale or swapped one. GETs
    `/healthz` (deriving its URL from the /act `endpoint`) and, if the
    response reports `checkpoint_sha256` (see serve_policy.py's
    `PolicyHolder.checkpoint_sha256`), compares it against the sha256 of
    `checkpoint`. A mismatch is an immediate `ServingParityError` — parity
    checked against the wrong weights is worse than no check at all. An
    older server whose `/healthz` predates this field omits it entirely;
    that case proceeds (nothing to compare against) but prints a warning so
    a silent identity gap doesn't go unnoticed.
    """
    healthz_url = _derive_healthz_url(endpoint)
    request = urllib.request.Request(healthz_url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except (urllib.error.HTTPError, urllib.error.URLError) as exc:
        raise ServingParityError(
            f"serving parity FAILED: endpoint error: could not reach {healthz_url} to verify "
            f"checkpoint identity: {exc}"
        ) from exc
    body = json.loads(raw)
    reported_sha256 = body.get("checkpoint_sha256")
    if reported_sha256 is None:
        print(
            f"WARNING: {healthz_url} reports no checkpoint_sha256 (older server); "
            "proceeding without endpoint checkpoint-identity verification.",
            file=sys.stderr,
        )
        return
    expected_sha256 = _sha256_of_file(checkpoint)
    if reported_sha256 != expected_sha256:
        raise ServingParityError(
            f"serving parity FAILED: endpoint {endpoint} is serving checkpoint_sha256="
            f"{reported_sha256}, but --checkpoint {checkpoint} hashes to {expected_sha256} — "
            "the server under test is not serving the checkpoint being verified."
        )


def _post_act(
    endpoint: str, payload: dict, timeout: float,
) -> tuple[int, Optional[str], Optional[np.ndarray]]:
    """Real HTTP POST to a running serve_policy `/act` endpoint. Returns
    (action_id, error, logits); error is non-None on ANY failure (HTTP
    status, connection error, or an `{"error": ...}` response body) — the
    hard gate tolerates none of these. `logits` is the response's `logits`
    field (present when the request set `return_logits: true` and the server
    supports it), or None (a legacy server that omits it, or when logits were
    not requested)."""
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        endpoint, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return -1, f"HTTP {exc.code}: {detail}", None
    except urllib.error.URLError as exc:
        return -1, f"connection error: {exc.reason}", None
    data = json.loads(raw)
    if data.get("error"):
        return -1, str(data["error"]), None
    action_id = data.get("action_id")
    if action_id is None:
        return -1, "response missing 'action_id'", None
    logits_field = data.get("logits")
    logits = np.asarray(logits_field, dtype=np.float64) if logits_field is not None else None
    return int(action_id), None, logits


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
    max_decisions: Optional[int] = None,
    http_timeout: float = 5.0,
    logit_tolerance: float = LOGIT_TOLERANCE,
    match_mode: str = "classic",
    allow_non_production: bool = False,
) -> ParityReport:
    """Drive `episodes` seeded bridge episodes (seeds `start_seed ..
    start_seed + episodes - 1`), checking eval-vs-serving action parity on
    every decision. Raises `ServingParityError` on the first violation.
    """
    # Adversarial round 10, Finding 1: --endpoint is the release HARD GATE
    # (spec's promotion runbook step 2). The runbook's own command supplied
    # no --bridge-kind/--match-mode overrides, so it silently ran against
    # this CLI's default mock/classic bridge — a random single-round episode
    # generator that never exercises production-shaped Chongci event
    # streams (round transitions/resets, interrupts, tail truncation). A
    # gate that never drives real event streams can pass while the actual
    # deployed contract (Go's real event encoding, real round boundaries)
    # is broken.
    #
    # This check is deliberately about EPISODE SHAPE, not wire-payload
    # byte-equality: the JSON payload construction in `build_act_payload`
    # (below) is Python-side and stays Python-side either way — Go's own
    # byte-for-byte wire encoding is independently pinned by
    # internal/rl/serving_parity_test.go (layer 1) and internal/bot/remote's
    # wire tests. What THIS gate is responsible for is making sure the
    # bridge driving each decision is the real Go engine playing a real
    # chongci match, not a random mock stepping through a single truncated
    # round.
    if endpoint is not None and not allow_non_production:
        if bridge_kind != "go" or match_mode != "chongci":
            raise ServingParityError(
                "serving parity FAILED: --endpoint is the release HARD GATE and requires "
                f"--bridge-kind go --match-mode chongci (production-shaped Chongci event "
                f"streams with real round transitions), got bridge_kind={bridge_kind!r} "
                f"match_mode={match_mode!r}. Pass --allow-non-production to run --endpoint "
                "against a non-production bridge/match-mode for local experimentation only "
                "— never for the actual promotion gate."
            )

    # Finding 1c: a full chongci match needs far more decisions than a small
    # fixed default to have any realistic chance of crossing a round
    # boundary. An explicit `max_decisions` always wins; when unset, mirror
    # evaluate.py's online-eval default (classic keeps this module's
    # pre-existing 64-decision default, chongci gets the same budget
    # evaluate.py already relies on to reach PHASE_MATCH_END).
    resolved_max_decisions = resolve_max_steps_per_episode(match_mode, max_decisions)
    if resolved_max_decisions is None:
        resolved_max_decisions = _LEGACY_DEFAULT_MAX_DECISIONS
    max_decisions = resolved_max_decisions

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

    # Finding 1 (adversarial round 5): the requested --event-history-window
    # must EXACTLY match the checkpoint's own model_config.event_window
    # before any episode/decision runs. The old code built the bridge with
    # max(requested, model_window) and built payloads from model_window, so a
    # deliberately wrong --event-history-window (e.g. 0 against a window-128
    # model — exactly the backend-misconfiguration a real deployment would
    # hit) silently got "corrected" to the model's window and the gate
    # PASSED, hiding the exact failure it exists to catch. A real serving
    # backend is configured with ONE window; if the CLI value doesn't match
    # the checkpoint, that mismatch itself is the bug under test.
    if int(event_history_window) != model_event_window:
        raise ServingParityError(
            "serving parity FAILED: --event-history-window="
            f"{int(event_history_window)} does not match the checkpoint's "
            f"model_config.event_window={model_event_window}; a real serving "
            "backend must be configured with the checkpoint's own event window "
            "exactly — this is a backend-misconfiguration failure, not "
            "something to silently widen and pass"
        )

    reference_policy = TorchGreedyPolicy(model=model, device=device)

    if endpoint is not None:
        # Before trusting a single action-id agreement, confirm the endpoint
        # is actually serving THIS checkpoint's weights (see
        # verify_endpoint_checkpoint_identity's docstring) — an endpoint
        # quietly serving a different checkpoint would otherwise look like a
        # clean parity pass for the wrong reason.
        verify_endpoint_checkpoint_identity(endpoint, checkpoint, timeout=http_timeout)

    env_config = EnvConfig(
        bridge_kind=bridge_kind,
        bridge_library_path=bridge_library_path,
        learning_seats=(0, 1, 2, 3),
        auto_play_heuristics=False,
        max_steps_per_episode=max_decisions,
        match_mode=match_mode,
        # Validated equal to model_event_window above; use the checkpoint's
        # own window (the only value that can reach this line).
        event_history_window=model_event_window,
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

                if endpoint is not None:
                    # Finding 3 (adversarial round 2): endpoint mode must
                    # check tight logit parity too, not just argmax agreement
                    # — preprocessing drift that happens to preserve argmax
                    # would otherwise pass this "hard gate" silently.
                    act_payload = build_act_payload(
                        observation, decision_index, model_event_window, return_logits=True,
                    )
                    serving_action_id, served_error, serving_logits = _post_act(
                        endpoint, act_payload, timeout=http_timeout
                    )
                    if served_error is not None:
                        # Adversarial round 12, Finding 1(d): a 400 whose body
                        # mentions the logit-export gate means the endpoint
                        # under test was launched WITHOUT --enable-logit-export
                        # — this harness always sends return_logits=true, so
                        # that flag is required on the CANDIDATE service (see
                        # the B2c runbook's step 2 launch command). Point the
                        # operator straight at the fix rather than a bare
                        # "endpoint error".
                        if "logit export" in served_error.lower():
                            raise ServingParityError(
                                _failure_message(
                                    seed, decision_index,
                                    f"endpoint error: {served_error} — the fh-mj-serving-parity "
                                    "--endpoint hard gate always requests return_logits=true; "
                                    "relaunch the CANDIDATE serve_policy instance with "
                                    "--enable-logit-export (never the production instance) and "
                                    "re-run this gate",
                                    observation,
                                )
                            )
                        raise ServingParityError(
                            _failure_message(seed, decision_index, f"endpoint error: {served_error}", observation)
                        )
                    if serving_logits is None:
                        # Hard gate: there is no legacy event server in this
                        # deployment (see the runbook) — an endpoint that
                        # doesn't return logits when asked cannot have its
                        # logit parity verified, and silently skipping the
                        # check is exactly the gap this fix closes.
                        raise ServingParityError(
                            _failure_message(
                                seed, decision_index,
                                "endpoint response has no 'logits' field (requested return_logits=true); "
                                "cannot verify logit parity — this is a hard-gate failure, not a legacy "
                                "server exemption",
                                observation,
                            )
                        )
                    reference_logits = _forward_logits(model, observation, device)
                    legal = np.asarray(observation.legal_actions, dtype=np.int64)
                    _assert_finite_logits(
                        reference_logits, legal, side="reference", seed=seed, decision_index=decision_index,
                    )
                    _assert_finite_logits(
                        serving_logits, legal, side="served", seed=seed, decision_index=decision_index,
                    )
                    logit_diff = float(np.max(np.abs(reference_logits[legal] - serving_logits[legal])))
                    report.max_logit_diff = max(report.max_logit_diff, logit_diff)
                    if logit_diff > logit_tolerance:
                        raise ServingParityError(
                            _failure_message(
                                seed, decision_index,
                                f"endpoint logit max-abs diff {logit_diff:.6g} over legal actions exceeds "
                                f"tolerance {logit_tolerance:.0e}",
                                observation,
                            )
                        )
                else:
                    act_payload = build_act_payload(observation, decision_index, model_event_window)
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
                    legal = np.asarray(observation.legal_actions, dtype=np.int64)
                    _assert_finite_logits(
                        reference_logits, legal, side="reference", seed=seed, decision_index=decision_index,
                    )
                    _assert_finite_logits(
                        serving_logits, legal, side="served", seed=seed, decision_index=decision_index,
                    )
                    logit_diff = float(np.max(np.abs(reference_logits - serving_logits)))
                    report.max_logit_diff = max(report.max_logit_diff, logit_diff)
                    if logit_diff > logit_tolerance:
                        raise ServingParityError(
                            _failure_message(
                                seed, decision_index,
                                f"logit max-abs diff {logit_diff:.6g} exceeds tolerance {logit_tolerance:.0e}",
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


def _print_summary(
    report: ParityReport, *, mode: str, checkpoint: Path, device: str, logit_tolerance: float,
) -> None:
    print(f"fh-mj-serving-parity report ({mode}, device={device})")
    print(f"  checkpoint:        {checkpoint}")
    print(f"  episodes:          {len(report.episodes)}")
    print(f"  decisions checked: {report.decisions_checked}")
    print(f"  agreements:        {report.agreements}")
    print(f"  max logit diff:    {report.max_logit_diff:.3e} (tolerance {logit_tolerance:.0e})")
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
    parser.add_argument(
        "--match-mode", choices=("classic", "chongci"), default="classic",
        help="Simulator match mode driving each seeded episode; --endpoint (the hard gate) "
        "requires 'chongci' (production-shaped event streams with real round transitions) "
        "unless --allow-non-production is also given",
    )
    parser.add_argument(
        "--allow-non-production", action="store_true",
        help="Escape hatch for LOCAL EXPERIMENTATION ONLY: permits --endpoint mode against a "
        "non-'go'/non-'chongci' bridge (e.g. the default mock/classic). Never pass this for the "
        "actual release/promotion gate — it exists to skip the production-shape requirement "
        "while iterating locally, not to relax the real gate.",
    )
    parser.add_argument(
        "--max-decisions", type=int, default=None,
        help="Bridge decision cap per episode. Default: 64 (classic/mock, unchanged) or "
        "evaluate.py's chongci online-eval budget (chongci) — a full chongci match needs far "
        "more decisions than 64 to have any chance of crossing a round boundary",
    )
    parser.add_argument("--http-timeout", type=float, default=5.0, help="Per-request timeout in seconds (--endpoint mode)")
    parser.add_argument(
        "--logit-tolerance", type=_finite_nonnegative_float, default=LOGIT_TOLERANCE,
        help="Max-abs logit difference over legal actions allowed before failing the hard gate "
        "(same-hardware assumption: exact reproducibility is expected on identical CPU/GPU/dtype). "
        "Must be a finite value >= 0 (adversarial round 3, Finding 3): NaN/Inf would silently "
        "disable the gate.",
    )
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
            logit_tolerance=args.logit_tolerance,
            match_mode=args.match_mode,
            allow_non_production=args.allow_non_production,
        )
    except ServingParityError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

    mode = "endpoint" if args.endpoint else "in-process"
    _print_summary(report, mode=mode, checkpoint=args.checkpoint, device=args.device, logit_tolerance=args.logit_tolerance)
    if not report.all_agree:
        print("serving parity FAILED: not every checked decision agreed", file=sys.stderr)
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
