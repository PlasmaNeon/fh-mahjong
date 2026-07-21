"""Spec B2c Task 8: the `fh-mj-serving-parity` hard-gate harness.

Three things are pinned:
(a) in-process action parity end-to-end on a mock-bridge window-8 event
    model passes cleanly;
(b) the harness CAN FAIL — a deliberate perturbation of the serving-side
    feature construction is caught, proving (a) is not a vacuous pass;
(c) endpoint mode against a real `serve_policy` server (spun in-thread on an
    ephemeral port) passes the same way.
"""
from __future__ import annotations

import dataclasses
import http.client
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np
import pytest

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.scripts import serve_policy as serve_policy_module
from fh_mahjong_ai.scripts.serving_parity import (
    ServingParityError,
    run_serving_parity,
    verify_endpoint_checkpoint_identity,
)
from fh_mahjong_ai.serving import CheckpointPolicy
from fh_mahjong_ai.storage import model_config_metadata, save_checkpoint

_SMALL = dict(
    channels=16, residual_blocks=1, plane_feature_dim=32, scalar_hidden_dim=16,
    trunk_hidden_dim=32, value_hidden_dim=16, q_hidden_dim=16,
)
_ENV = EnvConfig()
_WINDOW = 8


def _event_model_config(window: int = _WINDOW) -> ModelConfig:
    return ModelConfig(**dict(_SMALL, event_window=window))


def _save_checkpoint(tmp_path: Path, model_config: ModelConfig, step: int = 1, name: str = "model.pt") -> Path:
    model = PolicyValueNet(_ENV, model_config)
    path = tmp_path / name
    save_checkpoint(path, model, step=step, metadata={"model_config": model_config_metadata(model_config)})
    return path


# --- (a) in-process parity: clean pass ------------------------------------------------


def test_in_process_parity_passes_on_mock_bridge_event_model(tmp_path: Path) -> None:
    checkpoint = _save_checkpoint(tmp_path, _event_model_config())

    report = run_serving_parity(
        checkpoint=checkpoint,
        event_history_window=_WINDOW,
        episodes=3,
        start_seed=1000,
        device="cpu",
        endpoint=None,
        bridge_kind="mock",
        max_decisions=5,
    )

    assert report.all_agree
    assert report.decisions_checked == 3 * 5
    assert report.agreements == report.decisions_checked
    assert report.max_logit_diff <= 1e-4


def test_in_process_parity_passes_on_window_zero_model(tmp_path: Path) -> None:
    """The event-free (window=0) legacy path must also parity-check cleanly —
    this is the runbook's step-1 regression bar (new server image, old
    champion, byte-identical behavior)."""
    checkpoint = _save_checkpoint(tmp_path, ModelConfig(**_SMALL))  # event_window=0

    report = run_serving_parity(
        checkpoint=checkpoint,
        event_history_window=0,
        episodes=2,
        start_seed=2000,
        device="cpu",
        endpoint=None,
        bridge_kind="mock",
        max_decisions=4,
    )

    assert report.all_agree
    assert report.decisions_checked == 2 * 4


# --- (b) the harness can FAIL: injected perturbation is caught -------------------------


def test_harness_catches_a_skewed_serving_side_plane(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Proves the harness is not vacuous: monkeypatch the serving-side
    feature construction (`observation_from_json`, the function serve_policy's
    /act handler uses to decode the wire payload) to skew one plane value, and
    assert the parity harness reports a failure instead of silently passing."""
    checkpoint = _save_checkpoint(tmp_path, _event_model_config())

    real_observation_from_json = serve_policy_module.observation_from_json

    def _skewed_observation_from_json(payload, model_event_window):
        observation = real_observation_from_json(payload, model_event_window)
        observation.planes[0, 0, 0] += 50.0  # deliberate skew, large enough to flip the argmax
        return observation

    monkeypatch.setattr(serve_policy_module, "observation_from_json", _skewed_observation_from_json)

    with pytest.raises(ServingParityError) as excinfo:
        run_serving_parity(
            checkpoint=checkpoint,
            event_history_window=_WINDOW,
            episodes=2,
            start_seed=3000,
            device="cpu",
            endpoint=None,
            bridge_kind="mock",
            max_decisions=5,
        )

    assert "seed=3000" in str(excinfo.value) or "mismatch" in str(excinfo.value) or "diff" in str(excinfo.value)


def test_harness_catches_corrupted_event_history(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A second, independent perturbation: corrupt the payload's event history
    before it reaches the serving decode path, so the served observation's
    events differ from the reference's raw bridge events."""
    checkpoint = _save_checkpoint(tmp_path, _event_model_config())

    real_observation_from_json = serve_policy_module.observation_from_json

    def _corrupted_observation_from_json(payload, model_event_window):
        corrupted = dict(payload)
        if corrupted.get("event_count", 0) > 0:
            corrupted["event_history"] = [(v + 1) % 4096 for v in corrupted["event_history"]]
        return real_observation_from_json(corrupted, model_event_window)

    monkeypatch.setattr(serve_policy_module, "observation_from_json", _corrupted_observation_from_json)

    with pytest.raises(ServingParityError):
        run_serving_parity(
            checkpoint=checkpoint,
            event_history_window=_WINDOW,
            episodes=3,
            start_seed=4000,
            device="cpu",
            endpoint=None,
            bridge_kind="mock",
            max_decisions=5,
        )


# --- (c) endpoint mode against a real in-thread serve_policy server --------------------


class _Server:
    def __init__(self, checkpoint_path: Path, manifest_path: Path) -> None:
        from fh_mahjong_ai.serving import CheckpointPolicy

        policy = CheckpointPolicy.from_checkpoint(checkpoint_path)
        self.holder = serve_policy_module.PolicyHolder(policy, manifest_path=manifest_path)
        handler = type(
            "BoundPolicyRequestHandler", (serve_policy_module.PolicyRequestHandler,), {"holder": self.holder}
        )
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def port(self) -> int:
        return self.server.server_address[1]

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


def test_endpoint_mode_parity_passes_against_real_server(tmp_path: Path) -> None:
    checkpoint = _save_checkpoint(tmp_path, _event_model_config())
    server = _Server(checkpoint, tmp_path / "manifest.json")
    try:
        report = run_serving_parity(
            checkpoint=checkpoint,
            event_history_window=_WINDOW,
            episodes=2,
            start_seed=5000,
            device="cpu",
            endpoint=f"http://127.0.0.1:{server.port}/act",
            bridge_kind="mock",
            max_decisions=5,
        )
    finally:
        server.close()

    assert report.all_agree
    assert report.decisions_checked == 2 * 5
    # Finding 3 (adversarial round 2): endpoint mode now requests logits
    # (return_logits=true) and checks them against the tolerance too, not
    # just argmax agreement — same weights served over HTTP should reproduce
    # bit-for-bit (well within tolerance).
    assert report.max_logit_diff <= 1e-4


# FINDING 3 (adversarial round 2): endpoint mode previously checked ONLY
# argmax agreement, so preprocessing drift that happens to preserve argmax
# would pass the "hard gate" silently. This drifts the SERVING side's
# reported logits (via return_logits) while leaving the actual served
# action_id (computed from the true, undrifted logits) untouched — proving
# the endpoint-mode logit-tolerance check independently catches drift that
# argmax comparison alone would miss.
def test_endpoint_mode_catches_logit_drift_with_same_argmax(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkpoint = _save_checkpoint(tmp_path, _event_model_config())
    server = _Server(checkpoint, tmp_path / "manifest.json")
    original_choose = CheckpointPolicy.choose

    def _drifted_choose(self, observation, return_logits: bool = False):
        action = original_choose(self, observation, return_logits=return_logits)
        if return_logits and action.logits is not None:
            drifted = action.logits.copy()
            legal = observation.legal_actions
            target = next((a for a in legal if a != action.greedy_action_id), legal[0])
            # Large enough to blow through the 1e-4 tolerance; the reported
            # action_id (computed by `original_choose` before this drift is
            # applied) is completely unaffected.
            drifted[target] += 5.0
            action = dataclasses.replace(action, logits=drifted)
        return action

    monkeypatch.setattr(CheckpointPolicy, "choose", _drifted_choose)
    try:
        with pytest.raises(ServingParityError, match="logit"):
            run_serving_parity(
                checkpoint=checkpoint,
                event_history_window=_WINDOW,
                episodes=2,
                start_seed=8000,
                device="cpu",
                endpoint=f"http://127.0.0.1:{server.port}/act",
                bridge_kind="mock",
                max_decisions=5,
            )
    finally:
        server.close()


# FINDING 3 (adversarial round 3): a NaN in either logit vector makes every
# NaN comparison false, so `logit_diff > logit_tolerance` is False and the
# gate silently PASSES even though the served logits are garbage. This drifts
# the SERVING side's reported logit for a NON-argmax legal action to NaN
# (the reported action_id, computed from the true undrifted logits, is
# unaffected) and asserts the harness still fails the gate.
def test_endpoint_mode_catches_nan_logits_even_with_matching_argmax(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkpoint = _save_checkpoint(tmp_path, _event_model_config())
    server = _Server(checkpoint, tmp_path / "manifest.json")
    original_choose = CheckpointPolicy.choose

    def _nan_choose(self, observation, return_logits: bool = False):
        action = original_choose(self, observation, return_logits=return_logits)
        if return_logits and action.logits is not None:
            drifted = action.logits.copy()
            legal = observation.legal_actions
            target = next((a for a in legal if a != action.greedy_action_id), legal[0])
            drifted[target] = float("nan")
            action = dataclasses.replace(action, logits=drifted)
        return action

    monkeypatch.setattr(CheckpointPolicy, "choose", _nan_choose)
    try:
        with pytest.raises(ServingParityError, match="(?i)nan|non-finite|finite"):
            run_serving_parity(
                checkpoint=checkpoint,
                event_history_window=_WINDOW,
                episodes=2,
                start_seed=8500,
                device="cpu",
                endpoint=f"http://127.0.0.1:{server.port}/act",
                bridge_kind="mock",
                max_decisions=5,
            )
    finally:
        server.close()


def test_endpoint_mode_fails_when_server_omits_logits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A "legacy" server that ignores return_logits and never includes the
    field is a hard-gate failure, not a silently-skipped check — there is no
    legacy event server in this deployment (per the runbook)."""
    checkpoint = _save_checkpoint(tmp_path, _event_model_config())
    server = _Server(checkpoint, tmp_path / "manifest.json")
    original_choose = CheckpointPolicy.choose

    def _no_logits_choose(self, observation, return_logits: bool = False):
        # Simulate a legacy server: never populate logits even when asked.
        return original_choose(self, observation, return_logits=False)

    monkeypatch.setattr(CheckpointPolicy, "choose", _no_logits_choose)
    try:
        with pytest.raises(ServingParityError, match="logits"):
            run_serving_parity(
                checkpoint=checkpoint,
                event_history_window=_WINDOW,
                episodes=1,
                start_seed=9000,
                device="cpu",
                endpoint=f"http://127.0.0.1:{server.port}/act",
                bridge_kind="mock",
                max_decisions=5,
            )
    finally:
        server.close()


def test_endpoint_mode_reports_failure_on_connection_error(tmp_path: Path) -> None:
    checkpoint = _save_checkpoint(tmp_path, _event_model_config())

    with pytest.raises(ServingParityError, match="endpoint error"):
        run_serving_parity(
            checkpoint=checkpoint,
            event_history_window=_WINDOW,
            episodes=1,
            start_seed=6000,
            device="cpu",
            endpoint="http://127.0.0.1:1/act",  # nothing listens here
            bridge_kind="mock",
            max_decisions=3,
            http_timeout=1.0,
        )


# --- --event-history-window must match the checkpoint exactly (finding 1, round 5) -----


def test_run_serving_parity_fails_fast_on_event_history_window_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The old code built the bridge with max(requested, model_window) and
    built payloads from model_window, so `--event-history-window 0` against a
    window-8 model silently got "corrected" and PASSED — hiding exactly the
    backend-misconfiguration failure a real deployment would hit. The fix
    requires the two to match EXACTLY, checked before any bridge/episode is
    built (asserted here by making `build_bridge` blow up if it's ever
    reached)."""
    checkpoint = _save_checkpoint(tmp_path, _event_model_config())  # event_window=8

    def _must_not_be_called(*args, **kwargs):
        raise AssertionError("build_bridge must not run when the event-history window mismatches")

    monkeypatch.setattr("fh_mahjong_ai.scripts.serving_parity.build_bridge", _must_not_be_called)

    with pytest.raises(ServingParityError, match=r"--event-history-window=0.*event_window=8"):
        run_serving_parity(
            checkpoint=checkpoint,
            event_history_window=0,
            episodes=2,
            start_seed=1,
            device="cpu",
            endpoint=None,
            bridge_kind="mock",
            max_decisions=5,
        )


def test_run_serving_parity_passes_bridge_construction_when_window_matches(tmp_path: Path) -> None:
    """Sanity companion to the mismatch test: the matching value must still
    work end-to-end (already pinned by
    test_in_process_parity_passes_on_mock_bridge_event_model, repeated here
    tightly scoped to the window-equality gate itself)."""
    checkpoint = _save_checkpoint(tmp_path, _event_model_config())  # event_window=8

    report = run_serving_parity(
        checkpoint=checkpoint,
        event_history_window=8,
        episodes=1,
        start_seed=1,
        device="cpu",
        endpoint=None,
        bridge_kind="mock",
        max_decisions=3,
    )

    assert report.all_agree
    assert report.decisions_checked == 3


# --- endpoint checkpoint-identity verification (finding 4) -----------------------------


def test_verify_endpoint_checkpoint_identity_passes_on_matching_sha256(tmp_path: Path) -> None:
    checkpoint = _save_checkpoint(tmp_path, _event_model_config())
    server = _Server(checkpoint, tmp_path / "manifest.json")
    try:
        # Must not raise: the endpoint is serving exactly this checkpoint file.
        verify_endpoint_checkpoint_identity(f"http://127.0.0.1:{server.port}/act", checkpoint)
    finally:
        server.close()


def test_verify_endpoint_checkpoint_identity_fails_on_mismatched_sha256(tmp_path: Path) -> None:
    served_checkpoint = _save_checkpoint(tmp_path, _event_model_config(), name="served.pt")
    # A different checkpoint file (different bytes on disk) than the one the
    # server actually loaded — the sha256 the server reports must not match it.
    other_checkpoint = _save_checkpoint(tmp_path, _event_model_config(), step=2, name="other.pt")
    server = _Server(served_checkpoint, tmp_path / "manifest.json")
    try:
        with pytest.raises(ServingParityError, match="checkpoint_sha256"):
            verify_endpoint_checkpoint_identity(f"http://127.0.0.1:{server.port}/act", other_checkpoint)
    finally:
        server.close()


def test_run_serving_parity_fails_fast_on_checkpoint_mismatch_before_any_decisions(tmp_path: Path) -> None:
    # The identity check must run BEFORE the episode loop: a mismatch should
    # never let a single decision be checked (and falsely reported as parity
    # agreement against the wrong weights).
    served_checkpoint = _save_checkpoint(tmp_path, _event_model_config(), name="served.pt")
    other_checkpoint = _save_checkpoint(tmp_path, _event_model_config(), step=2, name="other.pt")
    server = _Server(served_checkpoint, tmp_path / "manifest.json")
    try:
        with pytest.raises(ServingParityError, match="checkpoint_sha256"):
            run_serving_parity(
                checkpoint=other_checkpoint,
                event_history_window=_WINDOW,
                episodes=2,
                start_seed=7000,
                device="cpu",
                endpoint=f"http://127.0.0.1:{server.port}/act",
                bridge_kind="mock",
                max_decisions=5,
            )
    finally:
        server.close()


class _NoShaHealthzServer:
    """A bare HTTP server whose /healthz omits checkpoint_sha256 entirely —
    the pre-checkpoint-identity contract an older serve_policy build would
    speak. Used to pin the "absent field -> proceed with a warning" half of
    verify_endpoint_checkpoint_identity's contract."""

    def __init__(self) -> None:
        body = json.dumps({"ok": True, "event_window": 0, "contract_version": 1}).encode("utf-8")

        class _Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - stdlib method name
                if self.path != "/healthz":
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args: object) -> None:  # silence test output
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def port(self) -> int:
        return self.server.server_address[1]

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


def test_verify_endpoint_checkpoint_identity_proceeds_with_warning_when_field_absent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    checkpoint = _save_checkpoint(tmp_path, _event_model_config())
    server = _NoShaHealthzServer()
    try:
        # Must not raise: an older server reporting no checkpoint_sha256 has
        # nothing to compare against, so this proceeds rather than failing.
        verify_endpoint_checkpoint_identity(f"http://127.0.0.1:{server.port}/act", checkpoint)
    finally:
        server.close()
    assert "WARNING" in capsys.readouterr().err


# --- --logit-tolerance CLI validation (finding 3, adversarial round 3) -----------------


def _run_main_with_argv(monkeypatch: pytest.MonkeyPatch, argv: list[str]) -> int:
    from fh_mahjong_ai.scripts import serving_parity as serving_parity_module

    monkeypatch.setattr("sys.argv", ["fh-mj-serving-parity", *argv])
    with pytest.raises(SystemExit) as excinfo:
        serving_parity_module.main()
    return int(excinfo.value.code)


def _base_argv(tmp_path: Path, logit_tolerance: str) -> list[str]:
    return [
        "--checkpoint", str(tmp_path / "doesnotmatter.pt"),
        "--event-history-window", "0",
        "--episodes", "1",
        "--start-seed", "1",
        "--in-process",
        "--logit-tolerance", logit_tolerance,
    ]


def test_logit_tolerance_nan_rejected_at_cli_parse(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    code = _run_main_with_argv(monkeypatch, _base_argv(tmp_path, "nan"))
    assert code == 2


def test_logit_tolerance_inf_rejected_at_cli_parse(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    code = _run_main_with_argv(monkeypatch, _base_argv(tmp_path, "inf"))
    assert code == 2


def test_logit_tolerance_negative_rejected_at_cli_parse(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    code = _run_main_with_argv(monkeypatch, _base_argv(tmp_path, "-1.0"))
    assert code == 2


def test_logit_tolerance_normal_value_accepted_at_cli_parse(tmp_path: Path) -> None:
    from fh_mahjong_ai.scripts.serving_parity import _finite_nonnegative_float

    assert _finite_nonnegative_float("1e-4") == pytest.approx(1e-4)
    assert _finite_nonnegative_float("0") == 0.0


# --- payload shape sanity ---------------------------------------------------------------


def test_build_act_payload_matches_go_actrequest_field_names(tmp_path: Path) -> None:
    from fh_mahjong_ai.bridge import build_bridge
    from fh_mahjong_ai.scripts.serving_parity import build_act_payload

    env_config = EnvConfig(bridge_kind="mock", event_history_window=_WINDOW)
    bridge = build_bridge(env_config)
    try:
        observation = bridge.reset(seed=1)
    finally:
        bridge.close()

    payload = build_act_payload(observation, decision_index=0, event_window=_WINDOW)

    assert set(payload) >= {
        "seat", "planes", "scalars", "action_mask", "event_count", "event_window",
        "contract_version", "metadata",
    }
    assert payload["event_window"] == _WINDOW
    assert payload["event_count"] == len(payload.get("event_history", []))
    assert payload["event_count"] <= _WINDOW
