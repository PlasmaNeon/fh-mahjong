"""Spec B2c Task 5: serve_policy event-contract validation, enriched /healthz,
and a validated /reload that never swaps in an incompatible checkpoint."""
from __future__ import annotations

import hashlib
import http.client
import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import numpy as np
import pytest

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.events import EVENT_CONTRACT_V1
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.scripts.serve_policy import (
    PolicyHolder,
    PolicyRequestHandler,
    observation_from_json,
)
from fh_mahjong_ai.serving import CheckpointPolicy
from fh_mahjong_ai.storage import model_config_metadata, save_checkpoint

_SMALL = dict(
    channels=16, residual_blocks=1, plane_feature_dim=32, scalar_hidden_dim=16,
    trunk_hidden_dim=32, value_hidden_dim=16, q_hidden_dim=16,
)
_ENV = EnvConfig()


def _event_model_config(window: int = 8) -> ModelConfig:
    return ModelConfig(**dict(_SMALL, event_window=window))


def _save_checkpoint(tmp_path: Path, model_config: ModelConfig, step: int = 1, name: str = "model.pt") -> Path:
    model = PolicyValueNet(_ENV, model_config)
    path = tmp_path / name
    save_checkpoint(path, model, step=step, metadata={"model_config": model_config_metadata(model_config)})
    return path


def _observation_payload(legal: list[int], **event_fields) -> dict:
    env = EnvConfig()
    mask = [0] * env.action_space_size
    for action_id in legal:
        mask[action_id] = 1
    payload = {
        "seat": 0,
        "planes": np.zeros(env.plane_shape, dtype=np.float32).tolist(),
        "scalars": np.zeros(env.scalar_features, dtype=np.float32).tolist(),
        "action_mask": mask,
    }
    payload.update(event_fields)
    return payload


class _Server:
    """A ThreadingHTTPServer bound to port 0, serving a real PolicyHolder, for
    exercising the /act, /healthz, and /reload HTTP contract end to end."""

    def __init__(self, checkpoint_path: Path, manifest_path: Path) -> None:
        policy = CheckpointPolicy.from_checkpoint(checkpoint_path)
        self.holder = PolicyHolder(policy, manifest_path=manifest_path)
        handler = type("BoundPolicyRequestHandler", (PolicyRequestHandler,), {"holder": self.holder})
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def port(self) -> int:
        return self.server.server_address[1]

    def request(self, method: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        body = json.dumps(payload) if payload is not None else None
        headers = {"content-type": "application/json"} if body is not None else {}
        conn.request(method, path, body=body, headers=headers)
        response = conn.getresponse()
        data = json.loads(response.read().decode("utf-8"))
        status = response.status
        conn.close()
        return status, data

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


# --- observation_from_json unit tests -----------------------------------------------------


def test_observation_from_json_window_zero_ignores_event_fields() -> None:
    payload = _observation_payload(
        [0, 1, 2], event_history="not even a list", event_count=-999,
        event_window="garbage", contract_version=None,
    )

    observation = observation_from_json(payload, model_event_window=0)

    assert observation.event_history.size == 0


def test_observation_from_json_accepts_valid_short_history() -> None:
    payload = _observation_payload(
        [0, 1, 2], event_history=[1, 2, 3], event_count=3, event_window=8,
        contract_version=EVENT_CONTRACT_V1,
    )

    observation = observation_from_json(payload, model_event_window=8)

    assert observation.event_history.tolist() == [1, 2, 3]


def test_observation_from_json_accepts_zero_count_early_round() -> None:
    payload = _observation_payload(
        [0, 1, 2], event_history=[], event_count=0, event_window=8,
        contract_version=EVENT_CONTRACT_V1,
    )

    observation = observation_from_json(payload, model_event_window=8)

    assert observation.event_history.size == 0


def test_observation_from_json_missing_event_history_with_zero_count_is_valid() -> None:
    payload = _observation_payload([0, 1, 2], event_count=0, event_window=8, contract_version=EVENT_CONTRACT_V1)
    assert "event_history" not in payload

    observation = observation_from_json(payload, model_event_window=8)

    assert observation.event_history.size == 0


def test_observation_from_json_missing_required_fields_raises() -> None:
    payload = _observation_payload([0, 1, 2])

    with pytest.raises(ValueError):
        observation_from_json(payload, model_event_window=8)


def test_observation_from_json_history_length_mismatch_raises() -> None:
    payload = _observation_payload(
        [0, 1, 2], event_history=[1, 2], event_count=3, event_window=8,
        contract_version=EVENT_CONTRACT_V1,
    )

    with pytest.raises(ValueError, match="event_history"):
        observation_from_json(payload, model_event_window=8)


def test_observation_from_json_count_exceeds_window_raises() -> None:
    payload = _observation_payload(
        [0, 1, 2], event_history=list(range(9)), event_count=9, event_window=8,
        contract_version=EVENT_CONTRACT_V1,
    )

    with pytest.raises(ValueError, match="event_count"):
        observation_from_json(payload, model_event_window=8)


def test_observation_from_json_window_mismatch_raises() -> None:
    payload = _observation_payload(
        [0, 1, 2], event_history=[1, 2, 3], event_count=3, event_window=16,
        contract_version=EVENT_CONTRACT_V1,
    )

    with pytest.raises(ValueError, match="event_window"):
        observation_from_json(payload, model_event_window=8)


def test_observation_from_json_contract_version_mismatch_raises() -> None:
    payload = _observation_payload(
        [0, 1, 2], event_history=[1, 2, 3], event_count=3, event_window=8,
        contract_version=EVENT_CONTRACT_V1 + 1,
    )

    with pytest.raises(ValueError, match="contract_version"):
        observation_from_json(payload, model_event_window=8)


# --- HTTP /act contract ---------------------------------------------------------------


def test_http_act_accepts_valid_short_event_history(tmp_path: Path) -> None:
    checkpoint = _save_checkpoint(tmp_path, _event_model_config(window=8))
    server = _Server(checkpoint, tmp_path / "manifest.json")
    try:
        status, data = server.request(
            "POST", "/act",
            _observation_payload(
                [0, 1, 2], event_history=[1, 2, 3], event_count=3, event_window=8,
                contract_version=EVENT_CONTRACT_V1,
            ),
        )
    finally:
        server.close()

    assert status == 200, data
    assert data["action_id"] in (0, 1, 2)


def test_http_act_window_zero_model_ignores_garbage_event_fields(tmp_path: Path) -> None:
    checkpoint = _save_checkpoint(tmp_path, ModelConfig(**_SMALL))  # event_window=0
    server = _Server(checkpoint, tmp_path / "manifest.json")
    try:
        status, data = server.request(
            "POST", "/act",
            _observation_payload(
                [0, 1, 2], event_history="garbage", event_count=-999,
                event_window="garbage", contract_version=None,
            ),
        )
    finally:
        server.close()

    assert status == 200, data
    assert data["action_id"] in (0, 1, 2)


@pytest.mark.parametrize(
    "event_fields,expected_snippet",
    [
        (dict(event_history=[1, 2], event_count=3, event_window=8, contract_version=EVENT_CONTRACT_V1), "event_history"),
        (dict(event_history=list(range(9)), event_count=9, event_window=8, contract_version=EVENT_CONTRACT_V1), "event_count"),
        (dict(event_history=[1, 2, 3], event_count=3, event_window=16, contract_version=EVENT_CONTRACT_V1), "event_window"),
        (dict(event_history=[1, 2, 3], event_count=3, event_window=8, contract_version=EVENT_CONTRACT_V1 + 1), "contract_version"),
    ],
)
def test_http_act_rejects_each_invalid_event_condition(tmp_path: Path, event_fields: dict, expected_snippet: str) -> None:
    checkpoint = _save_checkpoint(tmp_path, _event_model_config(window=8))
    server = _Server(checkpoint, tmp_path / "manifest.json")
    try:
        status, data = server.request("POST", "/act", _observation_payload([0, 1, 2], **event_fields))
    finally:
        server.close()

    assert status == 400
    assert expected_snippet in data["error"]


# --- HTTP /evaluate contract ------------------------------------------------------------


def test_http_evaluate_threads_event_history_into_evaluate_batch(tmp_path: Path) -> None:
    """/evaluate must feed each observation's validated event_history into
    evaluate_batch, not silently score against a zero history. We pin this by
    comparing the HTTP response against a direct evaluate_batch call with the
    same histories threaded (must match) and against the same call with
    events=None (must NOT match — guards against the fields being dropped)."""
    model_config = _event_model_config(window=8)
    checkpoint = _save_checkpoint(tmp_path, model_config)
    server = _Server(checkpoint, tmp_path / "manifest.json")
    try:
        obs_a = _observation_payload(
            [0, 1, 2], event_history=[1, 2, 3], event_count=3, event_window=8,
            contract_version=EVENT_CONTRACT_V1,
        )
        obs_b = _observation_payload(
            [0, 1, 2], event_history=[4, 5, 6, 7], event_count=4, event_window=8,
            contract_version=EVENT_CONTRACT_V1,
        )
        status, data = server.request("POST", "/evaluate", {"observations": [obs_a, obs_b]})
    finally:
        server.close()

    assert status == 200, data
    results = data["results"]
    assert len(results) == 2

    policy = CheckpointPolicy.from_checkpoint(checkpoint)
    env = EnvConfig()
    planes = np.zeros((2, *env.plane_shape), dtype=np.float32)
    scalars = np.zeros((2, env.scalar_features), dtype=np.float32)
    mask = np.zeros((2, env.action_space_size), dtype=np.int8)
    mask[:, [0, 1, 2]] = 1
    events = np.zeros((2, 8), dtype=np.int64)
    events[0, :3] = [1, 2, 3]
    events[1, :4] = [4, 5, 6, 7]
    event_lengths = np.array([3, 4], dtype=np.int64)

    _, expected_values = policy.evaluate_batch(planes, scalars, mask, events=events, event_lengths=event_lengths)
    _, zero_history_values = policy.evaluate_batch(planes, scalars, mask, events=None, event_lengths=None)

    for i in range(2):
        assert results[i]["value"] == pytest.approx(float(expected_values[i]), abs=1e-5)
    # Guard against a tautological pass: the events=None baseline must actually
    # differ, otherwise this test wouldn't catch events being dropped.
    assert not (
        results[0]["value"] == pytest.approx(float(zero_history_values[0]), abs=1e-5)
        and results[1]["value"] == pytest.approx(float(zero_history_values[1]), abs=1e-5)
    )


def test_http_evaluate_window_zero_model_ignores_event_fields(tmp_path: Path) -> None:
    checkpoint = _save_checkpoint(tmp_path, ModelConfig(**_SMALL))  # event_window=0
    server = _Server(checkpoint, tmp_path / "manifest.json")
    try:
        status, data = server.request(
            "POST", "/evaluate",
            {"observations": [_observation_payload([0, 1, 2], event_history="garbage", event_count=-999)]},
        )
    finally:
        server.close()

    assert status == 200, data
    assert len(data["results"]) == 1


def test_http_evaluate_accepts_zero_count_event_row(tmp_path: Path) -> None:
    checkpoint = _save_checkpoint(tmp_path, _event_model_config(window=8))
    server = _Server(checkpoint, tmp_path / "manifest.json")
    try:
        status, data = server.request(
            "POST", "/evaluate",
            {
                "observations": [
                    _observation_payload(
                        [0, 1, 2], event_count=0, event_window=8, contract_version=EVENT_CONTRACT_V1,
                    )
                ]
            },
        )
    finally:
        server.close()

    assert status == 200, data
    assert len(data["results"]) == 1


# --- /healthz --------------------------------------------------------------------------


def test_healthz_carries_sha256_window_and_contract_version(tmp_path: Path) -> None:
    checkpoint = _save_checkpoint(tmp_path, _event_model_config(window=8))
    server = _Server(checkpoint, tmp_path / "manifest.json")
    try:
        status, data = server.request("GET", "/healthz")
    finally:
        server.close()

    assert status == 200
    expected_sha = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    assert data["checkpoint_sha256"] == expected_sha
    assert data["event_window"] == 8
    assert data["contract_version"] == EVENT_CONTRACT_V1
    assert data["model_config"]["event_window"] == 8
    # Existing fields must still be present.
    assert data["ok"] is True
    assert data["checkpoint_step"] == 1


# --- /reload validation ------------------------------------------------------------------


def test_policy_holder_reload_rejects_incompatible_event_window(tmp_path: Path) -> None:
    old = _save_checkpoint(tmp_path, _event_model_config(window=8), step=1, name="old.pt")
    new = _save_checkpoint(tmp_path, _event_model_config(window=16), step=2, name="new.pt")
    holder = PolicyHolder(CheckpointPolicy.from_checkpoint(old), manifest_path=tmp_path / "manifest.json")

    with pytest.raises(ValueError):
        holder.reload(checkpoint=str(new))

    assert holder.policy.checkpoint_step == 1
    assert holder.policy.checkpoint_path == old


def test_policy_holder_reload_allows_override_via_expected_event_window(tmp_path: Path) -> None:
    old = _save_checkpoint(tmp_path, _event_model_config(window=8), step=1, name="old.pt")
    new = _save_checkpoint(tmp_path, _event_model_config(window=16), step=2, name="new.pt")
    holder = PolicyHolder(CheckpointPolicy.from_checkpoint(old), manifest_path=tmp_path / "manifest.json")

    holder.reload(checkpoint=str(new), expected_event_window=16)

    assert holder.policy.checkpoint_step == 2
    assert holder.policy.checkpoint_path == new


def test_http_reload_incompatible_window_leaves_old_policy_serving(tmp_path: Path) -> None:
    old = _save_checkpoint(tmp_path, _event_model_config(window=8), step=1, name="old.pt")
    new = _save_checkpoint(tmp_path, _event_model_config(window=16), step=2, name="new.pt")
    server = _Server(old, tmp_path / "manifest.json")
    try:
        reload_status, reload_data = server.request("POST", "/reload", {"checkpoint": str(new)})
        act_status, act_data = server.request(
            "POST", "/act",
            _observation_payload(
                [0, 1, 2], event_history=[1, 2, 3], event_count=3, event_window=8,
                contract_version=EVENT_CONTRACT_V1,
            ),
        )
    finally:
        server.close()

    assert reload_status == 400
    assert "error" in reload_data
    assert act_status == 200, act_data
    assert act_data["checkpoint_step"] == 1


def test_policy_holder_reload_failure_after_load_leaves_policy_and_hash_consistent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Adversarial round 3, Finding 1: if computing the new checkpoint's
    sha256 fails AFTER the new policy has already been loaded (e.g. the
    checkpoint file was deleted/replaced on disk between load and hashing),
    the reload must fail WITHOUT having swapped in the new policy — /act and
    /healthz must both keep observing the OLD policy and the OLD hash
    together, never a new policy paired with a stale hash or vice versa."""
    old = _save_checkpoint(tmp_path, _event_model_config(window=8), step=1, name="old.pt")
    new = _save_checkpoint(tmp_path, _event_model_config(window=8), step=2, name="new.pt")
    holder = PolicyHolder(CheckpointPolicy.from_checkpoint(old), manifest_path=tmp_path / "manifest.json")
    old_policy = holder.policy
    old_sha256 = holder.checkpoint_sha256

    calls = {"n": 0}

    def flaky_sha256_of(path: Path) -> str:
        # The holder's constructor already computed the OLD checkpoint's hash
        # with the real implementation before this monkeypatch was installed;
        # any call reaching this stub is reload()'s hash of the NEW
        # checkpoint, which must fail.
        calls["n"] += 1
        raise OSError("checkpoint file vanished after load")

    monkeypatch.setattr(PolicyHolder, "_sha256_of", staticmethod(flaky_sha256_of))

    with pytest.raises(OSError):
        holder.reload(checkpoint=str(new))

    assert holder.policy is old_policy
    assert holder.policy.checkpoint_step == 1
    assert holder.checkpoint_sha256 == old_sha256


def test_policy_holder_reload_success_updates_policy_and_hash_together(tmp_path: Path) -> None:
    old = _save_checkpoint(tmp_path, _event_model_config(window=8), step=1, name="old.pt")
    new = _save_checkpoint(tmp_path, _event_model_config(window=8), step=2, name="new.pt")
    holder = PolicyHolder(CheckpointPolicy.from_checkpoint(old), manifest_path=tmp_path / "manifest.json")

    holder.reload(checkpoint=str(new))

    assert holder.policy.checkpoint_step == 2
    assert holder.policy.checkpoint_path == new
    assert holder.checkpoint_sha256 == hashlib.sha256(new.read_bytes()).hexdigest()
