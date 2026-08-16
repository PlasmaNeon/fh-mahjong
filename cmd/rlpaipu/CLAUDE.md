# cmd/rlpaipu/

> Debug CLI that plays a deterministic heuristic round and writes replay-viewer-compatible paipu JSON.

## Overview

Plays one round through `engine.Game` with a `PaipuRecorder` attached, driving every seat with `bot.NewHeuristicPolicy`, then writes the resulting paipu to disk. The point is to produce a real paipu fixture without running a server, a database, or a live match — open it directly in the replay viewer.

## Usage

```bash
go run ./cmd/rlpaipu                       # writes testdata/paipu/rl-seed-1.json
go run ./cmd/rlpaipu -seed 7 -match-id rl-seed-7 -output /tmp/rl-seed-7.json
```

| Flag | Default | Meaning |
|---|---|---|
| `-match-id` | `rl-seed-1` | Match id used by the `/replay/:matchId` route |
| `-seed` | `1` | Deterministic wall seed |
| `-output` | `testdata/paipu/rl-seed-1.json` | Output paipu JSON path |
| `-max-actions` | `512` | Fail rather than loop forever if the round doesn't terminate |

On success it prints the written path plus the `http://localhost:3000/replay/<match-id>` URL to open.

## Key Files

- **main.go**
  - `generateHeuristicPaipu(matchID, seed, maxActions)` — builds the game, attaches the recorder, plays to round end.
  - `playNextHeuristicAction` / `feedTracedAction` — advance one heuristic decision and feed it through the same `ProcessPlayerAction` path the live server uses.
  - `snapshotDecision(game, seat, action)` — records a **paipu v2 `Decisions` supervision trace** alongside the heuristic play, snapshotting legal ids / chosen id the same way `internal/api/room_decisions.go` does, labelled `source: "heuristic"`. This is what makes generated paipu pass `internal/review`'s v2 decision cross-check.
  - `finalScores(state)` — extracts the per-seat final scores for the paipu result.
- **main_test.go** — `TestGeneratedPaipuPassesReview` pins that a freshly generated paipu round-trips clean through `review.ExtractDecisions`.

## Architecture Notes

- Needs no PostgreSQL and no network — it drives the engine in-process.
- The v2 decision trace is not optional decoration: without it, output would fail the review cross-check and the fixture would be useless for exercising the review pipeline.
- Sibling to `cmd/rlsmoke`, which does the opposite job — it verifies paipu provenance against a **live** server rather than generating a fixture offline.
