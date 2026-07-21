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

import http.client
import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import numpy as np
import pytest

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.scripts import serve_policy as serve_policy_module
from fh_mahjong_ai.scripts.serving_parity import ServingParityError, run_serving_parity
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
    # Endpoint mode never computes local logits (no logits over the wire).
    assert report.max_logit_diff == 0.0


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
