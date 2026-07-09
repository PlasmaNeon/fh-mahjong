from __future__ import annotations

import http.client
import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import numpy as np

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.scripts.serve_policy import PolicyHolder, PolicyRequestHandler
from fh_mahjong_ai.serving import CheckpointPolicy
from fh_mahjong_ai.storage import save_checkpoint


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

    def __init__(self, tmp_path: Path) -> None:
        checkpoint_path = tmp_path / "tiny.pt"
        model = PolicyValueNet(EnvConfig(), ModelConfig(residual_blocks=1))
        save_checkpoint(checkpoint_path, model, step=3)
        policy = CheckpointPolicy.from_checkpoint(checkpoint_path)
        holder = PolicyHolder(policy, manifest_path=tmp_path / "manifest.json")
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
        conn.request("POST", "/evaluate", body=body, headers={"content-type": "application/json"})
        response = conn.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        conn.close()
    finally:
        server.close()

    assert response.status == 200
    assert payload["checkpoint_path"].endswith("tiny.pt")
    assert payload["checkpoint_step"] == 3
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


def test_http_evaluate_endpoint_rejects_malformed_payload(tmp_path: Path) -> None:
    server = _EvaluateServer(tmp_path)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
        body = json.dumps({"observations": [{"seat": 0, "planes": [], "scalars": [], "action_mask": []}]})
        conn.request("POST", "/evaluate", body=body, headers={"content-type": "application/json"})
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
        conn.request("POST", "/evaluate", body=body, headers={"content-type": "application/json"})
        response = conn.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        conn.close()
    finally:
        server.close()

    assert response.status == 400
    assert "error" in payload
