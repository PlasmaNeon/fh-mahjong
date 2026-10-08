# cmd/rlbridge/

> c-shared library that lets Python drive the Go simulator through `ctypes`.

Build: `go build -buildmode=c-shared -o build/libfh_mahjong_bridge.dylib ./cmd/rlbridge` (`.so`
on Linux). Requests and responses are serialized protobuf bytes from `proto/game.proto`.

## Exports (main.go)

| Export | Wraps |
|---|---|
| `FHEnvNew`, `FHEnvReset`, `FHEnvStep`, `FHEnvClose` | one `rl.Env` |
| `FHEnvEvaluateBranches` | same-state candidate-action rollouts |
| `FHEnvRouteProbe` | read-only route shanten for one seat |
| `FHEnvPoolNew`, `FHEnvPoolStep`, `FHEnvPoolClose` | `rl.EnvPool`; `New` returns handle 0 for an event window > 512 or `lookahead_version` > 1 |
| `FHSearchPoolNew`, `FHSearchPoolStep`, `FHSearchPoolRoot`, `FHSearchPoolClose` | `rl.SearchPool` built from a live env handle; `root_seat` is passed only when set; `Root` returns every clone's root observation |
| `FHGenerateHeuristicTrajectory` | heuristic dataset export |
| `FHFree` | frees every returned payload and error string |

## Notes

- Each handle family has its own mutex-protected registry keyed by `uint64`, but a single
  `rl.Env` is not synchronized: serialize `Reset`/`Step`/`Close` per handle.
- Foreign callers must call `FHFree` on every returned buffer and error string.
- Rebuilding the library changes its sha256 even with identical sources (Go stamps the VCS
  revision); evaluation reports pin that sha, and `fh-mj-compare` refuses mismatched builds.
