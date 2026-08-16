# cmd/rlbridge/

> c-shared Go entry point for the Python RL bridge.

## Overview

This package wraps the `rl` environment in a narrow protobuf-based C ABI so Python can drive the authoritative Go simulator through `ctypes`. It is intended to be built with `-buildmode=c-shared`.

## Key Files

- **main.go** — Exports the bridge surface:
  - `FHEnvNew`
  - `FHEnvReset`
  - `FHEnvStep`
  - `FHEnvEvaluateBranches`
  - `FHEnvClose`
  - `FHEnvPoolNew` / `FHEnvPoolStep` / `FHEnvPoolClose` — batched env-pool exports (own handle registry, same FHBytesResult conventions): one FFI round-trip steps/resets many envs and returns all pending observations as flat buffers inside `EnvPoolStepResponse`.
  - `FHSearchPoolNew` / `FHSearchPoolStep` / `FHSearchPoolClose` — test-time search exports (own handle registry, same conventions as the env-pool trio). `FHSearchPoolNew` takes a live env handle plus a `SearchPoolNewRequest` (clones/seed/max_rollout_decisions/determinizations, and the proto3-`optional` `root_seat` — passed through to `rl.NewSearchPool`'s variadic root only when present, so an absent field falls back to `currentActionSeat()`) and wraps `rl.NewSearchPool`; `FHSearchPoolStep` reuses `EnvPoolStepRequest`/`EnvPoolStepResponse` and wraps `(*rl.SearchPool).Step`.
  - `FHGenerateHeuristicTrajectory`
  - `FHFree`

## Architecture Notes

- Requests and responses are serialized protobuf bytes defined in `proto/game.proto`.
- Environment handles are managed in-process by a global map keyed by `uint64`.
- The handle map is mutex-protected, but callers must still serialize `Reset`/`Step`/`Close` per handle because individual `*rl.Env` instances are not internally synchronized.
- `FHFree` must be called by foreign callers for both returned payload buffers and returned error strings.
