"""Small JSON HTTP server for checkpoint-backed policy inference."""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import math
import os
import threading
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional

import numpy as np

from fh_mahjong_ai.checkpoint_manifest import DEFAULT_MANIFEST_PATH
from fh_mahjong_ai.config import EnvConfig
from fh_mahjong_ai.events import EVENT_CONTRACT_V1
from fh_mahjong_ai.serving import (
    CheckpointPolicy,
    load_checkpoint_policy_with_hash,
    load_policy_from_manifest_with_hash,
)
from fh_mahjong_ai.types import Observation

# Caps a single /evaluate request. The Go review client (internal/review/client.go)
# chunks its calls at 256 observations, well under this limit.
MAX_EVALUATE_BATCH = 1024


@dataclass(frozen=True)
class _PolicySnapshot:
    """An immutable (policy, checkpoint_sha256) pair. /act and /healthz both
    read a single snapshot reference, so they can never observe a policy
    paired with the wrong checkpoint's hash — see PolicyHolder's docstring."""

    policy: CheckpointPolicy
    checkpoint_sha256: str


class PolicyHolder:
    """Thread-safe holder for the active policy so it can be hot-swapped at
    runtime via POST /reload without restarting the server.

    Readers (/act, /healthz) take the current snapshot lock-free; reloads are
    serialized and build a COMPLETE new snapshot (load policy, validate the
    event window, compute the new checkpoint's sha256) entirely before
    swapping it in. The swap is a single attribute assignment (atomic under
    the GIL), so any failure along the way — including the checkpoint file
    vanishing or being replaced between load and hashing — leaves the
    previous snapshot (policy AND hash together) fully intact and serving.
    """

    def __init__(
        self,
        policy: CheckpointPolicy,
        manifest_path: Path,
        device: str = "cpu",
        checkpoint_sha256: Optional[str] = None,
        logit_export_token: Optional[str] = None,
    ) -> None:
        """`checkpoint_sha256`, when given, MUST be the hash of the exact
        bytes `policy` was deserialized from (see
        `serving.load_checkpoint_policy_with_hash` /
        `load_policy_from_manifest_with_hash`) — the production startup path
        (`main()`) always passes it, so the policy and its attested hash come
        from a single read of the checkpoint file, never two independent
        opens (adversarial round 5, Finding 2). When omitted (test/back-compat
        convenience callers that already hold a constructed `policy` and have
        no bytes to hash), this falls back to re-hashing `policy.checkpoint_path`
        from disk, which does not have that guarantee.

        `logit_export_token` gates whether ANY caller's `return_logits: true`
        on /act is honored (adversarial round 12, Finding 1; adversarial round
        13, Finding 1): the full masked logit vector is a material model-
        extraction surface on a publicly deployed endpoint, so `return_logits`
        requires a shared-secret token, not just a process-wide on/off switch
        — a bare boolean flag would let ANY network caller harvest logits the
        instant it was set. When `logit_export_token` is None (the default,
        and production's posture), `return_logits` is refused unconditionally.
        When set, a request is honored ONLY when it carries a matching
        `logit_export_token` field, compared with `hmac.compare_digest` (never
        `==`, which leaks timing information about how many leading bytes
        matched). Only the candidate/parity serving instance used for
        `fh-mj-serving-parity --endpoint` sets this; production never does."""
        self._manifest_path = manifest_path
        self._device = device
        self._lock = threading.Lock()
        self.logit_export_token = logit_export_token
        resolved_sha256 = (
            checkpoint_sha256 if checkpoint_sha256 is not None else self._sha256_of(policy.checkpoint_path)
        )
        self._snapshot = _PolicySnapshot(policy=policy, checkpoint_sha256=resolved_sha256)

    @property
    def policy(self) -> CheckpointPolicy:
        return self._snapshot.policy

    @property
    def checkpoint_sha256(self) -> str:
        return self._snapshot.checkpoint_sha256

    @property
    def snapshot(self) -> _PolicySnapshot:
        """The current (policy, checkpoint_sha256) pair as a single
        attribute read. Handlers that need MULTIPLE fields describing "the
        currently-serving checkpoint" (e.g. /healthz: path, step, sha256,
        model_config, event_window all in one response) MUST capture this
        once at the start of the request and derive every field from that
        one local reference — never read `.policy` and `.checkpoint_sha256`
        (or call `.snapshot` more than once) across the same request. A
        concurrent `reload()` swaps `self._snapshot` to a new
        `_PolicySnapshot` in a single attribute assignment (atomic under the
        GIL) between any two separate reads, which would otherwise produce a
        response mixing one snapshot's path/step/config with another
        snapshot's sha256 (adversarial round 6, Finding 2)."""
        return self._snapshot

    @staticmethod
    def _sha256_of(path: Path) -> str:
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def reload(
        self,
        checkpoint: Optional[str] = None,
        checkpoint_id: str = "current",
        expected_event_window: Optional[int] = None,
    ) -> CheckpointPolicy:
        with self._lock:
            # Carry the current sampling config into the new policy: a hot-swap
            # must not silently change serving behavior — whatever sampling was
            # explicitly configured at launch (production default: none = greedy)
            # is preserved across reloads.
            # Deliberate: the sampler RNG RESTARTS from the base seed on reload
            # (config is preserved, generator state is not) — reloads are rare
            # promotion events and real-play trajectories diverge immediately,
            # so transferring generator state would add complexity for no
            # observable benefit.
            current = self._snapshot.policy
            # Read the checkpoint bytes ONCE and derive both the loaded policy
            # AND its sha256 from that same buffer (adversarial round 5,
            # Finding 2): the old flow loaded the model from `checkpoint_path`
            # and then separately re-opened the same path to hash it, so an
            # atomic file replacement landing in between could make the
            # reported hash attest bytes different from the ones actually
            # deserialized. `load_checkpoint_policy_with_hash` /
            # `load_policy_from_manifest_with_hash` read the path exactly once.
            if checkpoint:
                new_policy, new_sha256 = load_checkpoint_policy_with_hash(
                    Path(checkpoint),
                    device=self._device,
                    sample_temperature=current.sample_temperature,
                    sample_top_k=current.sample_top_k,
                    sample_action_family=current.sample_action_family,
                    seed=current.sample_seed,
                )
            else:
                new_policy, new_sha256 = load_policy_from_manifest_with_hash(
                    manifest_path=self._manifest_path,
                    checkpoint_id=checkpoint_id,
                    device=self._device,
                    sample_temperature=current.sample_temperature,
                    sample_top_k=current.sample_top_k,
                    sample_action_family=current.sample_action_family,
                    sample_seed=current.sample_seed,
                )
            # Validate the NEW policy fully BEFORE swapping the reference: an
            # event-window mismatch against the currently-serving policy is a
            # contract break (the model's event encoder expects a fixed-width
            # history) and must never silently take over serving. Callers that
            # deliberately promote to a different window pass
            # expected_event_window to override the check explicitly.
            required_window = (
                expected_event_window
                if expected_event_window is not None
                else current.model.model_config.event_window
            )
            new_window = new_policy.model.model_config.event_window
            if new_window != required_window:
                raise ValueError(
                    f"reload checkpoint event_window={new_window} does not match the "
                    f"required window {required_window} (current policy's window unless "
                    "overridden by 'expected_event_window'); refusing to swap"
                )
            # `new_sha256` above was computed from the SAME bytes `new_policy`
            # was deserialized from — no second open of the checkpoint path.
            # Single reference assignment — atomic under the GIL — is the
            # only mutation of shared state; either both the new policy and
            # its hash become visible together, or (on any earlier exception)
            # neither does.
            self._snapshot = _PolicySnapshot(policy=new_policy, checkpoint_sha256=new_sha256)
            return new_policy


class PolicyRequestHandler(BaseHTTPRequestHandler):
    holder: PolicyHolder

    def do_GET(self) -> None:
        if self.path != "/healthz":
            self.send_error(404)
            return
        # Captured ONCE: every field below describes THIS snapshot, so a
        # concurrent /reload landing mid-request can never make this response
        # mix one checkpoint's path/step/config with another's sha256 (see
        # PolicyHolder.snapshot's docstring; adversarial round 6, Finding 2).
        snapshot = self.holder.snapshot
        policy = snapshot.policy
        model_config = policy.model.model_config
        self._write_json(
            {
                "ok": True,
                "checkpoint": str(policy.checkpoint_path),
                "checkpoint_step": policy.checkpoint_step,
                "checkpoint_sha256": snapshot.checkpoint_sha256,
                "sample_temperature": policy.sample_temperature,
                "sample_top_k": policy.sample_top_k,
                "sample_action_family": policy.sample_action_family,
                "sample_seed": policy.sample_seed,
                "model_config": asdict(model_config),
                "event_window": model_config.event_window,
                "contract_version": EVENT_CONTRACT_V1,
            }
        )

    def do_POST(self) -> None:
        if self.path == "/act":
            self._handle_act()
        elif self.path == "/evaluate":
            self._handle_evaluate()
        elif self.path == "/reload":
            self._handle_reload()
        else:
            self.send_error(404)

    def _handle_act(self) -> None:
        try:
            length = int(self.headers.get("content-length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            return_logits = bool(payload.get("return_logits", False))
            # Adversarial round 12, Finding 1 / round 13, Finding 1: an
            # unauthenticated caller must never be able to pull the full
            # masked logit vector off a publicly deployed /act endpoint —
            # that is a material model-extraction surface, and a process-wide
            # boolean flag would let ANY caller harvest it the instant the
            # flag was on. Require a shared-secret token instead: with no
            # token configured, return_logits is refused outright (400); with
            # a token configured, the request must carry a matching
            # 'logit_export_token' field (constant-time compare) or it is
            # rejected (400) with no logits in the response either way. Fail
            # loudly rather than silently ignoring the request, so the parity
            # harness's hard gate (which relies on --logit-export-token being
            # set on the CANDIDATE service) fails clearly instead of
            # comparing nothing.
            if return_logits:
                configured_token = self.holder.logit_export_token
                if not configured_token:
                    raise ValueError(
                        "logit export disabled on this server; launch serve_policy with "
                        "--logit-export-token TOKEN (or FH_MJ_LOGIT_EXPORT_TOKEN) to allow "
                        "return_logits (candidate/parity service only — never enable this "
                        "on the production endpoint)"
                    )
                request_token = payload.get("logit_export_token")
                if not isinstance(request_token, str) or not hmac.compare_digest(
                    configured_token, request_token
                ):
                    raise ValueError(
                        "logit export token missing or does not match this server's "
                        "--logit-export-token; refusing return_logits"
                    )
            policy = self.holder.policy
            observation = observation_from_json(payload, policy.model.model_config.event_window)
            # `observation_from_json` is the ONLY thing that produced `observation`
            # above, and for an event model (event_window > 0) it never returns
            # successfully with an empty `event_history` unless the wire payload's
            # own `event_count` field explicitly said 0 (a documented legitimate
            # early-round case) — a missing/inconsistent count raises there first.
            # So by the time control reaches this line, any empty history is
            # already explicitly validated, not silently missing; it is safe (and
            # required, per Finding 2) to tell `choose()` to trust it rather than
            # apply its defense-in-depth raise, which exists for callers that
            # build an `Observation` directly without going through this decode.
            action = policy.choose(observation, return_logits=return_logits, allow_empty_event_history=True)
        except Exception as exc:
            self._write_json({"error": str(exc)}, status=400)
            return
        response: dict = {
            "action_id": action.action_id,
            "value": action.value,
            "checkpoint_path": action.checkpoint_path,
            "checkpoint_step": action.checkpoint_step,
        }
        if return_logits and action.logits is not None:
            # These are the MASKED logits argmax was actually taken over
            # (see PolicyValueNet.forward): illegal-action entries carry
            # `torch.finfo(dtype).min`, a large but finite negative value, so
            # this list round-trips through JSON without any -inf sentinel
            # substitution being necessary. Used by fh-mj-serving-parity's
            # --endpoint logit-tolerance gate (Finding 3, adversarial round 2).
            # `action.logits` can be None even when `return_logits` was
            # requested (defense-in-depth against a policy implementation
            # that ignores the flag) — the field is simply omitted, and the
            # parity harness's hard-gate check for a missing 'logits' field
            # is exactly what catches that.
            response["logits"] = [float(value) for value in action.logits.tolist()]
        self._write_json(response)

    def _handle_evaluate(self) -> None:
        try:
            length = int(self.headers.get("content-length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            observations = payload["observations"]
            if len(observations) > MAX_EVALUATE_BATCH:
                raise ValueError(
                    f"batch of {len(observations)} observations exceeds max of {MAX_EVALUATE_BATCH}"
                )
            policy = self.holder.policy
            model_event_window = policy.model.model_config.event_window
            parsed = [observation_from_json(item, model_event_window) for item in observations]
            planes = np.stack([obs.planes for obs in parsed]) if parsed else np.zeros(
                (0, *EnvConfig().plane_shape), dtype=np.float32
            )
            scalars = np.stack([obs.scalars for obs in parsed]) if parsed else np.zeros(
                (0, EnvConfig().scalar_features), dtype=np.float32
            )
            action_masks = np.stack([obs.action_mask for obs in parsed]) if parsed else np.zeros(
                (0, EnvConfig().action_space_size), dtype=np.int8
            )
            events = event_lengths = None
            if model_event_window > 0:
                # `observation_from_json` already validated event_history/event_count/
                # event_window/contract_version for every row above; here we only
                # thread the validated compact histories into the fixed-width rows
                # `evaluate_batch` expects. An observation with event_count == 0 (a
                # legitimate early-round state) becomes a length-0 row rather than
                # being rejected: unlike `choose`, `evaluate_batch` has no per-row
                # Observation to raise against, so this asymmetry with the /act path
                # (which refuses empty histories) is deliberate, per Task 4's
                # evaluate_batch contract.
                n = len(parsed)
                events = np.zeros((n, model_event_window), dtype=np.int64)
                event_lengths = np.zeros((n,), dtype=np.int64)
                for i, obs in enumerate(parsed):
                    history = obs.event_history
                    count = min(history.size, model_event_window)
                    if count:
                        events[i, :count] = history[-count:].astype(np.int64)
                    event_lengths[i] = count
            probs, values = policy.evaluate_batch(
                planes, scalars, action_masks, events=events, event_lengths=event_lengths
            )
        except Exception as exc:
            self._write_json({"error": str(exc)}, status=400)
            return
        self._write_json(
            {
                "results": [
                    {"probs": probs[i].tolist(), "value": float(values[i])}
                    for i in range(len(parsed))
                ],
                "checkpoint_path": str(policy.checkpoint_path),
                "checkpoint_step": policy.checkpoint_step,
            }
        )

    def _handle_reload(self) -> None:
        try:
            length = int(self.headers.get("content-length", "0"))
            raw = self.rfile.read(length).decode("utf-8") if length else ""
            payload = json.loads(raw) if raw.strip() else {}
            checkpoint = payload.get("checkpoint")
            checkpoint_id = payload.get("checkpoint_id")
            expected_event_window = payload.get("expected_event_window")
            if not checkpoint and not checkpoint_id:
                raise ValueError("provide 'checkpoint' (path) or 'checkpoint_id'")
            policy = self.holder.reload(
                checkpoint=checkpoint,
                checkpoint_id=checkpoint_id or "current",
                expected_event_window=expected_event_window,
            )
        except Exception as exc:
            self._write_json({"error": str(exc)}, status=400)
            return
        self._write_json(
            {
                "ok": True,
                "checkpoint_path": str(policy.checkpoint_path),
                "checkpoint_step": policy.checkpoint_step,
            }
        )

    def log_message(self, format: str, *args: object) -> None:
        return None

    def _write_json(self, payload: dict, status: int = 200) -> None:
        encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


# The four wire fields that make up the compact event contract. Presence of
# ANY of these on a payload is what triggers validation against a window-0
# model (adversarial round 12, Finding 2) — see `observation_from_json`.
_EVENT_CONTRACT_FIELDS = ("event_count", "event_window", "contract_version", "event_history")


def _decode_and_validate_event_history(payload: dict, model_event_window: int) -> np.ndarray:
    """Validate and decode the compact event-contract fields against
    `model_event_window`, shared by both the "event model" branch and the
    "window-0 model that was sent contract fields anyway" branch of
    `observation_from_json` — the checks are IDENTICAL either way (adversarial
    round 12, Finding 2: validation must be symmetric in model_event_window,
    including 0)."""
    if "event_count" not in payload or "event_window" not in payload or "contract_version" not in payload:
        raise ValueError(
            "event-contract fields are partially present: 'event_count', 'event_window', and "
            "'contract_version' must ALL be present together (or all absent for a true legacy "
            f"caller) on every /act and /evaluate observation — got payload keys {sorted(k for k in payload if k in _EVENT_CONTRACT_FIELDS)}"
        )
    event_count = payload["event_count"]
    event_window = payload["event_window"]
    contract_version = payload["contract_version"]
    raw_history = payload.get("event_history")
    if raw_history is None:
        raw_history = []
    if len(raw_history) != event_count:
        raise ValueError(
            f"event_history length {len(raw_history)} does not match event_count {event_count}"
        )
    if event_count > event_window:
        raise ValueError(f"event_count {event_count} exceeds event_window {event_window}")
    if event_window != model_event_window:
        raise ValueError(
            f"event_window {event_window} does not match the serving model's "
            f"event_window {model_event_window}"
        )
    if contract_version != EVENT_CONTRACT_V1:
        raise ValueError(
            f"unsupported contract_version {contract_version!r}; expected {EVENT_CONTRACT_V1}"
        )
    return np.asarray(raw_history, dtype=np.uint32)


def observation_from_json(payload: dict, model_event_window: int) -> Observation:
    """Decode a Go /act or /evaluate request body into an `Observation`.

    `model_event_window` is the SERVING model's `ModelConfig.event_window`
    (0 for the event-free champion). When it is > 0, all three scalar event
    fields (`event_count`/`event_window`/`contract_version`) are REQUIRED (Go
    always sends them, per the compact /act contract in internal/rl's
    HTTPPolicy); `event_history` may be omitted only when `event_count == 0`
    (Go's `omitempty` drops the empty array) and is then treated as `[]`.

    When `model_event_window == 0`, a request that omits ALL FOUR event
    fields entirely is a true legacy caller (pre-B2c Go, or old test
    payloads) and is accepted with an empty event history, unchanged from
    before the event contract existed. But if the payload sends ANY of the
    four fields — e.g. a caller still configured for an event model
    (event_window=128, or a stale contract_version) that got rolled back
    (skewed) onto a window-0 checkpoint without noticing — validation is
    symmetric with the event-model branch above: contract_version must match
    EVENT_CONTRACT_V1, event_window must equal model_event_window (0, here),
    and event_count/event_history length must be consistent. This closes a
    silent-acceptance gap (adversarial round 12, Finding 2) where rollback
    skew against a window-0 model produced fake remote successes instead of
    a loud rejection. The Go legacy path always sends the three scalars as
    0/0/1 against a window-0 model, which satisfies this validation exactly
    (event_window 0 == 0, contract_version 1 matches) and keeps passing.
    """
    env_config = EnvConfig()
    planes = np.asarray(payload["planes"], dtype=np.float32).reshape(env_config.plane_shape)
    scalars = np.asarray(payload["scalars"], dtype=np.float32)
    action_mask = np.asarray(payload["action_mask"], dtype=np.int8)
    if scalars.ndim != 1:
        raise ValueError(f"expected one-dimensional scalars, got shape {scalars.shape}")
    if scalars.shape[0] < env_config.scalar_features:
        scalars = np.pad(scalars, (0, env_config.scalar_features - scalars.shape[0]))
    if scalars.shape != (env_config.scalar_features,):
        raise ValueError(f"expected {env_config.scalar_features} scalars, got shape {scalars.shape}")
    if action_mask.shape != (env_config.action_space_size,):
        raise ValueError(f"expected action mask of length {env_config.action_space_size}, got shape {action_mask.shape}")

    event_history = np.zeros(0, dtype=np.uint32)
    if model_event_window > 0:
        event_history = _decode_and_validate_event_history(payload, model_event_window)
    elif any(key in payload for key in _EVENT_CONTRACT_FIELDS):
        event_history = _decode_and_validate_event_history(payload, model_event_window)
    # else: model_event_window == 0 and NO event-contract field is present at
    # all — a true legacy caller; event_history stays empty, byte-identical
    # to pre-event-contract behavior.

    return Observation(
        seat=int(payload.get("seat", 0)),
        planes=planes,
        scalars=scalars,
        action_mask=action_mask,
        event_history=event_history,
        metadata=dict(payload.get("metadata", {})),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve checkpoint policy decisions over JSON HTTP")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--checkpoint-id", type=str, default="current")
    parser.add_argument("--checkpoint", type=Path, default=None, help="Override manifest checkpoint path")
    parser.add_argument("--device", type=str, default="cpu")
    parser.add_argument("--host", type=str, default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--sample-temperature", type=float, default=0.0,
                        help="softmax temperature for served actions; 0 = greedy. Swept 2026-07: "
                             "T<=0.7 with top-k 3 + discard-only costs nothing vs greedy; T=1.0 "
                             "degrades tail risk")
    parser.add_argument("--sample-top-k", type=int, default=0,
                        help="restrict sampling to the top-k legal actions (0 = no cap)")
    parser.add_argument("--sample-action-family", type=str, default="all",
                        help="only sample when every legal action is in this family (e.g. 'discard')")
    parser.add_argument("--sample-seed", type=int, default=1)
    parser.add_argument(
        "--logit-export-token", type=str, default=os.environ.get("FH_MJ_LOGIT_EXPORT_TOKEN"),
        help="Shared-secret token required for /act callers to request 'return_logits: true' and "
        "receive the full masked logit vector (adversarial round 12, Finding 1; adversarial round "
        "13, Finding 1: a bare on/off flag would let ANY network caller harvest logits once set, "
        "so this must be a token the caller has to present). Unset (default): return_logits is "
        "refused unconditionally with HTTP 400, never a silent no-op. Set: a request must carry a "
        "matching 'logit_export_token' field (constant-time compare) or it gets HTTP 400 with no "
        "logits in the body. Set ONLY on the candidate/parity serving instance used for "
        "fh-mj-serving-parity --endpoint (see the B2c runbook) — never in production. Can also be "
        "set via FH_MJ_LOGIT_EXPORT_TOKEN; the CLI flag takes precedence when both are given.",
    )
    args = parser.parse_args()

    # Fail loudly on misconfigured sampling: a typo here would otherwise start
    # a server that silently serves greedy (or clamps values) in production.
    if not math.isfinite(args.sample_temperature) or args.sample_temperature < 0.0:
        parser.error("--sample-temperature must be a finite value >= 0")
    if args.sample_top_k < 0:
        parser.error("--sample-top-k must be >= 0")
    if args.sample_temperature == 0.0 and (args.sample_top_k > 0 or args.sample_action_family != "all"):
        parser.error("--sample-top-k / --sample-action-family have no effect without --sample-temperature > 0")
    if args.sample_temperature > 0.0:
        from fh_mahjong_ai.action_catalog import action_family as _action_family
        known_families = {"all", "", "*"} | {
            _action_family(a) for a in range(EnvConfig().action_space_size)
        }
        if args.sample_action_family not in known_families:
            parser.error(f"--sample-action-family {args.sample_action_family!r} is not a known "
                         f"action family (choose from {sorted(known_families - {'', '*'})})")

    # Single-read construction at startup (adversarial round 5, Finding 2):
    # the policy and its attested checkpoint_sha256 must come from the same
    # buffer, not a load followed by an independent re-open for hashing.
    policy, checkpoint_sha256 = load_policy_from_manifest_with_hash(
        manifest_path=args.manifest,
        checkpoint_id=args.checkpoint_id,
        checkpoint_override=args.checkpoint,
        device=args.device,
        sample_temperature=args.sample_temperature,
        sample_top_k=args.sample_top_k,
        sample_action_family=args.sample_action_family,
        sample_seed=args.sample_seed,
    )
    holder = PolicyHolder(
        policy,
        manifest_path=args.manifest,
        device=args.device,
        checkpoint_sha256=checkpoint_sha256,
        logit_export_token=args.logit_export_token,
    )
    handler = type("BoundPolicyRequestHandler", (PolicyRequestHandler,), {"holder": holder})
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Serving {policy.checkpoint_path} on http://{args.host}:{args.port}")
    print("POST /act with visible SeatObservation JSON. Go must still validate the returned action_id.")
    print('POST /reload {"checkpoint": "/path/to/model.pt"} to hot-swap the model without restarting.')
    print(
        "Logit export (return_logits): "
        f"{'ENABLED (token required)' if args.logit_export_token else 'disabled'}"
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
