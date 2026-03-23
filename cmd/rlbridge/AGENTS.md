# cmd/rlbridge/

> c-shared Go entry point for the Python RL bridge.

## Overview

This package wraps the `rlenv` environment in a narrow protobuf-based C ABI so Python can drive the authoritative Go simulator through `ctypes`. It is intended to be built with `-buildmode=c-shared`.

## Key Files

- **main.go** — Exports the bridge surface:
  - `FHEnvNew`
  - `FHEnvReset`
  - `FHEnvStep`
  - `FHEnvClose`
  - `FHGenerateHeuristicTrajectory`
  - `FHFree`

## Architecture Notes

- Requests and responses are serialized protobuf bytes defined in `proto/game.proto`.
- Environment handles are managed in-process by a global map keyed by `uint64`.
- The handle map is mutex-protected, but callers must still serialize `Reset`/`Step`/`Close` per handle because individual `*rlenv.Env` instances are not internally synchronized.
- `FHFree` must be called by foreign callers for both returned payload buffers and returned error strings.
