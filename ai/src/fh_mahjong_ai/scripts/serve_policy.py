"""Small JSON HTTP server for checkpoint-backed policy inference."""
from __future__ import annotations

import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional

import numpy as np

from fh_mahjong_ai.checkpoint_manifest import DEFAULT_MANIFEST_PATH
from fh_mahjong_ai.config import EnvConfig
from fh_mahjong_ai.serving import CheckpointPolicy, load_policy_from_manifest
from fh_mahjong_ai.types import Observation


class PolicyHolder:
    """Thread-safe holder for the active policy so it can be hot-swapped at
    runtime via POST /reload without restarting the server.

    Readers (/act, /healthz) take the current reference lock-free; reloads are
    serialized and only swap in the new policy after it loads successfully, so a
    bad checkpoint returns an error and leaves the previous model serving.
    """

    def __init__(self, policy: CheckpointPolicy, manifest_path: Path, device: str = "cpu") -> None:
        self._policy = policy
        self._manifest_path = manifest_path
        self._device = device
        self._lock = threading.Lock()

    @property
    def policy(self) -> CheckpointPolicy:
        return self._policy

    def reload(self, checkpoint: Optional[str] = None, checkpoint_id: str = "current") -> CheckpointPolicy:
        with self._lock:
            if checkpoint:
                new_policy = CheckpointPolicy.from_checkpoint(Path(checkpoint), device=self._device)
            else:
                new_policy = load_policy_from_manifest(
                    manifest_path=self._manifest_path,
                    checkpoint_id=checkpoint_id,
                    device=self._device,
                )
            self._policy = new_policy
            return new_policy


class PolicyRequestHandler(BaseHTTPRequestHandler):
    holder: PolicyHolder

    def do_GET(self) -> None:
        if self.path != "/healthz":
            self.send_error(404)
            return
        policy = self.holder.policy
        self._write_json(
            {
                "ok": True,
                "checkpoint": str(policy.checkpoint_path),
                "checkpoint_step": policy.checkpoint_step,
            }
        )

    def do_POST(self) -> None:
        if self.path == "/act":
            self._handle_act()
        elif self.path == "/reload":
            self._handle_reload()
        else:
            self.send_error(404)

    def _handle_act(self) -> None:
        try:
            length = int(self.headers.get("content-length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            observation = observation_from_json(payload)
            action = self.holder.policy.choose(observation)
        except Exception as exc:
            self._write_json({"error": str(exc)}, status=400)
            return
        self._write_json(
            {
                "action_id": action.action_id,
                "value": action.value,
                "checkpoint_path": action.checkpoint_path,
                "checkpoint_step": action.checkpoint_step,
            }
        )

    def _handle_reload(self) -> None:
        try:
            length = int(self.headers.get("content-length", "0"))
            raw = self.rfile.read(length).decode("utf-8") if length else ""
            payload = json.loads(raw) if raw.strip() else {}
            checkpoint = payload.get("checkpoint")
            checkpoint_id = payload.get("checkpoint_id")
            if not checkpoint and not checkpoint_id:
                raise ValueError("provide 'checkpoint' (path) or 'checkpoint_id'")
            policy = self.holder.reload(checkpoint=checkpoint, checkpoint_id=checkpoint_id or "current")
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


def observation_from_json(payload: dict) -> Observation:
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
    return Observation(
        seat=int(payload.get("seat", 0)),
        planes=planes,
        scalars=scalars,
        action_mask=action_mask,
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
    args = parser.parse_args()

    policy = load_policy_from_manifest(
        manifest_path=args.manifest,
        checkpoint_id=args.checkpoint_id,
        checkpoint_override=args.checkpoint,
        device=args.device,
    )
    holder = PolicyHolder(policy, manifest_path=args.manifest, device=args.device)
    handler = type("BoundPolicyRequestHandler", (PolicyRequestHandler,), {"holder": holder})
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Serving {policy.checkpoint_path} on http://{args.host}:{args.port}")
    print("POST /act with visible SeatObservation JSON. Go must still validate the returned action_id.")
    print('POST /reload {"checkpoint": "/path/to/model.pt"} to hot-swap the model without restarting.')
    server.serve_forever()


if __name__ == "__main__":
    main()
