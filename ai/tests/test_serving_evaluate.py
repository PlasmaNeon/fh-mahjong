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
from fh_mahjong_ai.scripts.serve_policy import PolicyHolder, PolicyRequestHandler
from fh_mahjong_ai.serving import CheckpointPolicy
from fh_mahjong_ai.storage import save_checkpoint


def _bearer(token: str) -> dict:
    """The `Authorization: Bearer <token>` header POST /evaluate requires
    (adversarial round 19) — mirrors POST /reload's header-based auth."""
    return {"Authorization": f"Bearer {token}"}


def _tiny_policy() -> CheckpointPolicy:
    env = EnvConfig()
    model = PolicyValueNet(env, ModelConfig(residual_blocks=1))
    return CheckpointPolicy(
        model=model, checkpoint_path=Path("test.pt"), checkpoint_step=1, device="cpu",
    )


def _batch(n: int, legal: list[int]):
    env = EnvConfig()
    planes = np.zeros((n, *env.plane_shape), dtype=np.float32)
    scalars = np.zeros((n, env.scalar_features), dtype=np.float32)
    masks = np.zeros((n, env.action_space_size), dtype=np.int8)
    masks[:, legal] = 1
    return planes, scalars, masks


def test_evaluate_batch_masks_and_normalizes():
    policy = _tiny_policy()
    planes, scalars, masks = _batch(3, legal=[0, 5, 12, 40])
    probs, values = policy.evaluate_batch(planes, scalars, masks)
    assert probs.shape == (3, EnvConfig().action_space_size)
    assert values.shape == (3,)
    legal_sum = probs[:, [0, 5, 12, 40]].sum(axis=1)
    np.testing.assert_allclose(legal_sum, 1.0, atol=1e-5)
    illegal = np.delete(probs, [0, 5, 12, 40], axis=1)
    assert float(np.abs(illegal).max()) == 0.0


def test_evaluate_batch_rejects_all_zero_mask_row():
    policy = _tiny_policy()
    planes, scalars, masks = _batch(3, legal=[0, 5, 12])
    masks[1, :] = 0
    try:
        policy.evaluate_batch(planes, scalars, masks)
    except ValueError as exc:
        assert "1" in str(exc)
    else:
        raise AssertionError("expected ValueError for all-zero mask row")


def test_evaluate_batch_deterministic_and_chunked():
    policy = _tiny_policy()
    planes, scalars, masks = _batch(10, legal=[1, 2, 3])
    p1, v1 = policy.evaluate_batch(planes, scalars, masks, chunk_size=4)
    p2, v2 = policy.evaluate_batch(planes, scalars, masks, chunk_size=256)
    np.testing.assert_allclose(p1, p2, atol=1e-6)
    np.testing.assert_allclose(v1, v2, atol=1e-6)


class _EvaluateServer:
    """A ThreadingHTTPServer bound to port 0, serving a tiny policy, for
    exercising the /evaluate HTTP contract end to end."""

    def __init__(self, tmp_path: Path, evaluate_token: str = "eval-token") -> None:
        checkpoint_path = tmp_path / "tiny.pt"
        model = PolicyValueNet(EnvConfig(), ModelConfig(residual_blocks=1))
        save_checkpoint(checkpoint_path, model, step=3)
        policy = CheckpointPolicy.from_checkpoint(checkpoint_path)
        holder = PolicyHolder(policy, manifest_path=tmp_path / "manifest.json", evaluate_token=evaluate_token)
        handler = type("BoundPolicyRequestHandler", (PolicyRequestHandler,), {"holder": holder})
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


def _observation_payload(legal: list[int]) -> dict:
    env = EnvConfig()
    mask = [0] * env.action_space_size
    for action_id in legal:
        mask[action_id] = 1
    return {
        "seat": 0,
        "planes": np.zeros(env.plane_shape, dtype=np.float32).tolist(),
        "scalars": np.zeros(env.scalar_features, dtype=np.float32).tolist(),
        "action_mask": mask,
    }


def test_http_evaluate_endpoint_returns_masked_probs_and_value(tmp_path: Path) -> None:
    server = _EvaluateServer(tmp_path)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
        body = json.dumps({
            "observations": [
                _observation_payload([0, 5, 12]),
                _observation_payload([1, 2, 3]),
            ]
        })
        conn.request("POST", "/evaluate", body=body, headers={"content-type": "application/json", **_bearer("eval-token")})
        response = conn.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        conn.close()
    finally:
        server.close()

    assert response.status == 200
    assert payload["checkpoint_path"].endswith("tiny.pt")
    assert payload["checkpoint_step"] == 3
    # Round 17, Finding 2: /evaluate must publish the checkpoint's sha256
    # from the SAME snapshot used for the batch — internal/review's
    # cross-chunk consistency check needs it to detect a same-path hot
    # reload mixing bytes from two different checkpoints within one review.
    assert isinstance(payload.get("checkpoint_sha256"), str)
    assert len(payload["checkpoint_sha256"]) == 64
    results = payload["results"]
    assert len(results) == 2
    for result, legal in zip(results, ([0, 5, 12], [1, 2, 3])):
        assert len(result["probs"]) == EnvConfig().action_space_size
        legal_sum = sum(result["probs"][i] for i in legal)
        assert abs(legal_sum - 1.0) < 1e-4
        illegal_mass = sum(
            abs(p) for i, p in enumerate(result["probs"]) if i not in legal
        )
        assert illegal_mass == 0.0
        assert isinstance(result["value"], float)


def test_http_evaluate_endpoint_sha256_matches_healthz(tmp_path: Path) -> None:
    # Round 17, Finding 2: /evaluate's checkpoint_sha256 must agree with
    # /healthz's — both are derived from the SAME PolicyHolder snapshot, so a
    # caller stitching together chunks from one review can trust the sha as
    # the checkpoint's true identity, not just its (possibly reused) path.
    server = _EvaluateServer(tmp_path)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
        conn.request("GET", "/healthz")
        healthz = json.loads(conn.getresponse().read().decode("utf-8"))

        body = json.dumps({"observations": [_observation_payload([0, 5, 12])]})
        conn.request("POST", "/evaluate", body=body, headers={"content-type": "application/json", **_bearer("eval-token")})
        evaluate = json.loads(conn.getresponse().read().decode("utf-8"))
        conn.close()
    finally:
        server.close()

    assert healthz["checkpoint_sha256"] == evaluate["checkpoint_sha256"]


def test_http_evaluate_endpoint_rejects_malformed_payload(tmp_path: Path) -> None:
    server = _EvaluateServer(tmp_path)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
        body = json.dumps({"observations": [{"seat": 0, "planes": [], "scalars": [], "action_mask": []}]})
        conn.request("POST", "/evaluate", body=body, headers={"content-type": "application/json", **_bearer("eval-token")})
        response = conn.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        conn.close()
    finally:
        server.close()

    assert response.status == 400
    assert "error" in payload


def test_http_evaluate_endpoint_rejects_all_zero_mask(tmp_path: Path) -> None:
    server = _EvaluateServer(tmp_path)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
        body = json.dumps({
            "observations": [
                _observation_payload([0, 5, 12]),
                _observation_payload([]),
            ]
        })
        conn.request("POST", "/evaluate", body=body, headers={"content-type": "application/json", **_bearer("eval-token")})
        response = conn.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        conn.close()
    finally:
        server.close()

    assert response.status == 400
    assert "error" in payload


def test_http_evaluate_endpoint_rejects_oversized_batch(tmp_path: Path) -> None:
    server = _EvaluateServer(tmp_path)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
        body = json.dumps({"observations": [_observation_payload([0]) for _ in range(1025)]})
        conn.request("POST", "/evaluate", body=body, headers={"content-type": "application/json", **_bearer("eval-token")})
        response = conn.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        conn.close()
    finally:
        server.close()

    assert response.status == 400
    assert "error" in payload


# --- adversarial round 19: /evaluate is disabled without a configured token -------------


def test_http_evaluate_endpoint_disabled_without_configured_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No evaluate_token configured at all: /evaluate must refuse with 403
    WITHOUT ever invoking evaluate_batch, even with a well-formed request."""
    server = _EvaluateServer(tmp_path, evaluate_token=None)

    def _tripwire(*args: object, **kwargs: object) -> None:
        raise AssertionError("evaluate_batch must not be invoked when /evaluate is disabled")

    monkeypatch.setattr(CheckpointPolicy, "evaluate_batch", _tripwire)

    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
        body = json.dumps({"observations": [_observation_payload([0, 5, 12])]})
        conn.request("POST", "/evaluate", body=body, headers={"content-type": "application/json"})
        response = conn.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        conn.close()
    finally:
        server.close()

    assert response.status == 403
    assert "error" in payload


def test_http_evaluate_endpoint_missing_bearer_token_rejected(tmp_path: Path) -> None:
    server = _EvaluateServer(tmp_path, evaluate_token="eval-token")
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
        body = json.dumps({"observations": [_observation_payload([0, 5, 12])]})
        conn.request("POST", "/evaluate", body=body, headers={"content-type": "application/json"})
        response = conn.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        conn.close()
    finally:
        server.close()

    assert response.status == 403
    assert "error" in payload


def test_http_evaluate_endpoint_wrong_bearer_token_rejected(tmp_path: Path) -> None:
    server = _EvaluateServer(tmp_path, evaluate_token="eval-token")
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
        body = json.dumps({"observations": [_observation_payload([0, 5, 12])]})
        conn.request(
            "POST", "/evaluate", body=body,
            headers={"content-type": "application/json", **_bearer("wrong-token")},
        )
        response = conn.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        conn.close()
    finally:
        server.close()

    assert response.status == 403
    assert "error" in payload
