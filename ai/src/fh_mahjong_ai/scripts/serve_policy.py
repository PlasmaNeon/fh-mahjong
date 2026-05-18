"""Small JSON HTTP server for checkpoint-backed policy inference."""
from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np

from fh_mahjong_ai.checkpoint_manifest import DEFAULT_MANIFEST_PATH
from fh_mahjong_ai.config import EnvConfig
from fh_mahjong_ai.serving import CheckpointPolicy, load_policy_from_manifest
from fh_mahjong_ai.types import Observation


class PolicyRequestHandler(BaseHTTPRequestHandler):
    policy: CheckpointPolicy

    def do_GET(self) -> None:
        if self.path != "/healthz":
            self.send_error(404)
            return
        self._write_json({"ok": True, "checkpoint": str(self.policy.checkpoint_path)})

    def do_POST(self) -> None:
        if self.path != "/act":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("content-length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            observation = observation_from_json(payload)
            action = self.policy.choose(observation)
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
    handler = type("BoundPolicyRequestHandler", (PolicyRequestHandler,), {"policy": policy})
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Serving {policy.checkpoint_path} on http://{args.host}:{args.port}")
    print("POST /act with visible SeatObservation JSON. Go must still validate the returned action_id.")
    server.serve_forever()


if __name__ == "__main__":
    main()
