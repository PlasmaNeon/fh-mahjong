"""CLI to hot-swap (or inspect) the model served by a running policy server.

This is a thin client over the server's HTTP API — the *server* loads the
checkpoint into the live model, so switching models needs no restart of the
policy server or the Go backend. No torch import here, so it starts instantly.

Examples:
    # Show the currently served model
    uv run --project ai fh-mj-reload-policy --status

    # Switch to a different checkpoint at runtime
    uv run --project ai fh-mj-reload-policy --checkpoint /path/to/model.pt

    # Resolve a checkpoint id from the server's manifest
    uv run --project ai fh-mj-reload-policy --checkpoint-id current
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Optional


def reload_payload(checkpoint: Optional[str], checkpoint_id: Optional[str]) -> dict:
    """Build the /reload request body, requiring exactly one target."""
    payload: dict = {}
    if checkpoint:
        payload["checkpoint"] = checkpoint
    if checkpoint_id:
        payload["checkpoint_id"] = checkpoint_id
    if not payload:
        raise ValueError("provide --checkpoint or --checkpoint-id")
    return payload


def _post_json(url: str, payload: dict, timeout: float) -> dict:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _get_json(url: str, timeout: float) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Hot-swap or inspect the served policy model.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--url", default=None, help="Base URL override (default http://host:port)")
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--checkpoint", help="Path (on the server) to a .pt file to load")
    target.add_argument("--checkpoint-id", help="Checkpoint id resolved from the server manifest")
    target.add_argument("--status", action="store_true", help="Only show the currently served model")
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args(argv)

    base = (args.url or f"http://{args.host}:{args.port}").rstrip("/")

    try:
        if args.status or (not args.checkpoint and not args.checkpoint_id):
            print(json.dumps(_get_json(f"{base}/healthz", args.timeout), indent=2, sort_keys=True))
            return 0

        payload = reload_payload(args.checkpoint, args.checkpoint_id)
        body = _post_json(f"{base}/reload", payload, args.timeout)
        print(json.dumps(body, indent=2, sort_keys=True))
        return 0 if body.get("ok") else 1
    except urllib.error.HTTPError as exc:  # e.g. /reload 400 with a JSON error body
        try:
            print(json.dumps(json.loads(exc.read().decode("utf-8")), indent=2, sort_keys=True))
        except Exception:
            print(f"HTTP {exc.code}: {exc.reason}", file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"could not reach policy server at {base}: {exc.reason}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
