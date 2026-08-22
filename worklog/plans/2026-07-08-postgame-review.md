# Post-Game Review ("复盘") Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** mjai-reviewer-style post-game review: replay a stored paipu decision-by-decision, score every seat's decision against the RL champion's policy distribution, and render the result as an integrated overlay in the replay viewer.

**Architecture:** A new Go package `internal/review` re-drives each paipu round deterministically (WallSeed + recorded actions), captures a 39ch observation + action mask + chosen-action id at every decision point (including implicit "pass" on call windows), and batch-queries a new `/evaluate` endpoint on the Python policy server for masked policy distributions + values. The backend caches the assembled report in a new `match_reviews` table behind `GET/POST /api/v1/matches/:matchId/review`. The frontend replay viewer gains a KillerDucky-style analysis panel (probability bars, tiered severity, mistake navigation, value timeline).

**Tech Stack:** Go 1.25 (gin, GORM), Python/PyTorch (`ai/` package, stdlib HTTP server), React 19 + TypeScript + Vite (vitest).

**Spec:** `worklog/specs/2026-07-08-postgame-review-design.md` — read it before starting any task.

## Global Constraints

- `internal/engine/game.go` must NEVER import `internal/rules/` (review may import both; engine stays ruleset-agnostic).
- `internal/review` must not fork rules or state-transition logic — it drives `engine.Game` and reuses `internal/rl` encoders exactly.
- Hidden-information honesty: only `rl.EncodeObservation` (39ch visible). NEVER the oracle/51ch encoding (`encodeObservation(..., oracle=true)`).
- Tile-face index order everywhere: `man(0-8), pin(9-17), sou(18-26), jihai(27-33), flower(34-41)` (see `internal/rl/action.go tileFaceIndex42`).
- Action catalog constants (from `internal/rl/action.go`): `ActionPass=0, ActionTsumo=1, ActionRon=2, ActionAcceptHaitei=3, ActionRefuseHaitei=4, DiscardBase=5, PonBase=47, KanDirectBase=81, KanClosedBase=115, KanUpgradedBase=149, ChiiBase=183, ActionSpaceSize=204`.
- Tile id 0 is a real tile (first 1s). Never treat 0 as "unset".
- No proto changes in this feature (report is plain JSON).
- Go verification: `go vet ./... && go test ./...`. Python: `uv run --project ai pytest ai/tests/<file> -q` (full: `uv run --project ai pytest`). Frontend: `cd web && npx tsc --noEmit && npx vitest run`.
- Commit trailer on every commit: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Update the `AGENTS.md` of every directory a task touches, in that same task.
- After implementation is complete (separate session workflow): `/adversarial-review-loop` until approve BEFORE opening the PR; wait for GitHub Codex PR review approval; merge with `gh pr merge N --merge` (never squash/rebase).

## File Structure

| File | Responsibility |
|---|---|
| `internal/rl/action.go` (modify) | Export `LegalActions` and `EncodeAction` wrappers for the review driver |
| `internal/review/replay.go` (create) | Paipu → engine replay driver; decision-point extraction |
| `internal/review/context.go` (create) | Chongci-context normalization of the state before observation encoding |
| `internal/review/report.go` (create) | Report JSON types + `BuildReport` |
| `internal/review/client.go` (create) | HTTP policy client for `/evaluate` (chunked batches) |
| `internal/review/AGENTS.md` (create) | Package docs |
| `ai/src/fh_mahjong_ai/serving.py` (modify) | `CheckpointPolicy.evaluate_batch` |
| `ai/src/fh_mahjong_ai/scripts/serve_policy.py` (modify) | `POST /evaluate` handler |
| `ai/tests/test_serving_evaluate.py` (create) | Python tests |
| `internal/storage/db.go` (modify) | `MatchReview` model + AutoMigrate |
| `internal/api/review.go` (create) | `GET/POST /matches/:matchId/review` handlers |
| `internal/api/paipu.go` (modify) | Extract reusable `loadPaipuJSON` helper |
| `internal/api/server.go` (modify) | Route registration |
| `web/src/features/replay/reviewTypes.ts` (create) | Report TS types + fetch helpers |
| `web/src/features/replay/reviewUtils.ts` (create) | Severity tiers, gap, action labels |
| `web/src/features/replay/ReviewPanel.tsx` (create) | Analysis panel UI (bars, summary, value timeline) |
| `web/src/features/replay/Replay.tsx` (modify) | Wire review mode into the viewer |

Dependency order: Task 1 → 2 → 3 → 5; Task 4 independent after 3 defines the wire format; Tasks 6 → 7 need 3's JSON schema. Task 8 last.

---

### Task 1: Paipu replay driver (`internal/review/replay.go`)

Re-drives every round of a paipu through `engine.Game` and returns the chosen catalog-action id at each decision point, failing fast on any divergence. No observations yet (Task 2).

**Files:**
- Modify: `internal/rl/action.go` (add two export wrappers at the end of the file)
- Create: `internal/review/replay.go`
- Create: `internal/review/replay_test.go`
- Create: `internal/review/AGENTS.md`

**Interfaces:**
- Consumes: `engine.Paipu`, `engine.NewGame`, `engine.SeedFromBase64`, `Game.SetWallSeed/SetNextDealer/Start/ProcessPlayerAction/ResolveInterrupts/InterruptQueued`, `rules.FenghuaRuleset`, `bot.NewHeuristicPolicy` (test helper only).
- Produces:
  - `rl.LegalActions(state *pb.GameState, seat uint32) (map[int]*pb.PlayerAction, error)`
  - `rl.EncodeAction(state *pb.GameState, seat uint32, action *pb.PlayerAction) (int, bool)`
  - `review.Decision{Seat uint32; RoundIndex, ActionIndex int; DecisionIndex uint64; ChosenAction int; Observation *pb.SeatObservation}` (Observation stays nil until Task 2)
  - `review.ExtractDecisions(paipu *engine.Paipu) ([]Decision, error)`

**Background you need (read these first):**
- `internal/rl/env.go:326-530` — `advanceToDecision`, `currentActionSeat`, `assertInterruptsReadyToResolve`: this is the canonical decision-loop shape. The driver mirrors it, but instead of a policy choosing, the paipu's recorded action stream dictates the action.
- `internal/engine/paipu.go` — action record vocabulary: `draw, discard, chii, pon, okan, ckan, ukan, flower, tsumo, ron, haitei, haiteiRefuse`. `draw` and `flower` are system events the engine performs itself (`FLOWER_REVEAL` is excluded from the agent action space, and draws are `ExecuteSystemDraw`): the driver only *verifies* them against engine state and advances its cursor.
- `internal/engine/game.go:163-200` — `SetWallSeed` + `SetNextDealer` before `Start()` reproduce dealer, dice, wilds, and deals from the seed.
- `cmd/rlpaipu/main.go` — how to generate a heuristic-played paipu in-process (the test helper copies this shape).

- [ ] **Step 1: Export the rl wrappers**

Append to `internal/rl/action.go`:

```go
// LegalActions exposes the catalog-indexed legal action map so replay/review
// drivers can resolve recorded actions through the same legality map used by
// the RL bridge.
func LegalActions(state *pb.GameState, seat uint32) (map[int]*pb.PlayerAction, error) {
	return legalActionMap(state, seat)
}

// EncodeAction exposes catalog encoding for replay/review drivers.
func EncodeAction(state *pb.GameState, seat uint32, action *pb.PlayerAction) (int, bool) {
	return encodeAction(state, seat, action)
}
```

Run: `go test ./internal/rl/` — Expected: PASS (pure addition).

- [ ] **Step 2: Write the failing round-trip test**

`internal/review/replay_test.go`:

```go
package review

import (
	"fmt"
	"testing"

	"github.com/plasma/fh-mahjong/internal/bot"
	"github.com/plasma/fh-mahjong/internal/engine"
	"github.com/plasma/fh-mahjong/internal/rl"
	"github.com/plasma/fh-mahjong/internal/rules"
	pb "github.com/plasma/fh-mahjong/proto"
)

// generateHeuristicPaipu plays a full deterministic game with the shared
// heuristic bot and records it, mirroring cmd/rlpaipu. opts selects
// classic (engine.MatchOptions{}) or chongci mode.
func generateHeuristicPaipu(t *testing.T, seed uint64, opts engine.MatchOptions) *engine.Paipu {
	t.Helper()
	game := engine.NewGame(fmt.Sprintf("review-test-%d", seed), &rules.FenghuaRuleset{}, opts)
	game.SetWallSeed(engine.SeedFromUint64(seed))
	game.Recorder = engine.NewPaipuRecorder(fmt.Sprintf("review-test-%d", seed), "fenghua")
	for seat := uint32(0); seat < 4; seat++ {
		game.Recorder.AddPlayer(seat, fmt.Sprintf("Bot %d", seat+1), 0)
	}
	if err := game.Start(); err != nil {
		t.Fatalf("start: %v", err)
	}
	policy := bot.NewHeuristicPolicy()
	// Drive to completion exactly like cmd/rlpaipu/main.go does (copy its
	// loop, including WAIT_DISCARDS resolution and — for chongci — the
	// ROUND_END ready-ack flow with a derived per-hand wall seed).
	driveGameWithHeuristics(t, game, policy)
	// Finalize returns the recorded paipu.
	return game.Recorder.Finalize(finalScores(game))
}

func TestExtractDecisionsClassicRoundTrip(t *testing.T) {
	paipu := generateHeuristicPaipu(t, 7, engine.MatchOptions{})
	decisions, err := ExtractDecisions(paipu)
	if err != nil {
		t.Fatalf("ExtractDecisions: %v", err)
	}
	if len(decisions) == 0 {
		t.Fatal("expected at least one decision")
	}
	seatSeen := map[uint32]bool{}
	passSeen := false
	for i, d := range decisions {
		if d.RoundIndex < 0 || d.RoundIndex >= len(paipu.Rounds) {
			t.Fatalf("decision %d: bad round index %d", i, d.RoundIndex)
		}
		if d.ActionIndex < 0 || d.ActionIndex >= len(paipu.Rounds[d.RoundIndex].Actions) {
			t.Fatalf("decision %d: bad action index %d", i, d.ActionIndex)
		}
		if d.ChosenAction < 0 || d.ChosenAction >= rl.ActionSpaceSize {
			t.Fatalf("decision %d: chosen action %d out of catalog", i, d.ChosenAction)
		}
		seatSeen[d.Seat] = true
		if d.ChosenAction == rl.ActionPass {
			passSeen = true
		}
	}
	if len(seatSeen) != 4 {
		t.Fatalf("expected decisions for all 4 seats, got %v", seatSeen)
	}
	// A full heuristic game virtually always has at least one declined call
	// window; if this seed has none, pick another seed rather than delete
	// the assertion.
	if !passSeen {
		t.Fatal("expected at least one implicit pass decision")
	}
}

func TestExtractDecisionsChongciMultiRound(t *testing.T) {
	paipu := generateHeuristicPaipu(t, 11, engine.MatchOptions{
		Mode: pb.MatchMode_MATCH_MODE_CHONGCI,
		// Copy a small valid ChongciConfig from internal/rl/env_test.go /
		// engine tests (e.g. MaxHands: 4, StartingScore: 25000).
	})
	if len(paipu.Rounds) < 2 {
		t.Fatalf("want a multi-round paipu for this test, got %d rounds", len(paipu.Rounds))
	}
	if _, err := ExtractDecisions(paipu); err != nil {
		t.Fatalf("ExtractDecisions: %v", err)
	}
}

func TestExtractDecisionsDivergenceAborts(t *testing.T) {
	paipu := generateHeuristicPaipu(t, 7, engine.MatchOptions{})
	// Corrupt one dealt tile: replay must abort, never emit a wrong review.
	paipu.Rounds[0].Deals[0][0] = (paipu.Rounds[0].Deals[0][0] + 4) % 144
	if _, err := ExtractDecisions(paipu); err == nil {
		t.Fatal("expected divergence error, got nil")
	}
}
```

Also write `driveGameWithHeuristics` and `finalScores` helpers in the test file (copy the loop body from `cmd/rlpaipu/main.go`; for chongci add the ready-ack flow modeled on `internal/rl/env.go readyAllPlayersForNextRound`, calling `game.SetWallSeed(engine.SeedFromUint64(seed*1000+uint64(handNum)))` before the final ready so each hand is seeded — the recorder stores whatever seed the engine used, which is all the replayer needs).

- [ ] **Step 3: Run test to verify it fails**

Run: `go test ./internal/review/ -run TestExtractDecisions -v`
Expected: FAIL — package does not exist / `ExtractDecisions` undefined.

- [ ] **Step 4: Implement the replay driver**

`internal/review/replay.go`. Structure:

```go
// Package review reconstructs decision points from recorded paipu and scores
// them against a served policy. It drives engine.Game and reuses internal/rl
// encoders; it must not fork rules or state-transition logic.
package review

import (
	"fmt"

	"github.com/plasma/fh-mahjong/internal/engine"
	"github.com/plasma/fh-mahjong/internal/rl"
	"github.com/plasma/fh-mahjong/internal/rules"
	pb "github.com/plasma/fh-mahjong/proto"
)

// Decision is one reviewable decision reconstructed from a paipu.
type Decision struct {
	Seat          uint32
	RoundIndex    int    // index into paipu.Rounds
	ActionIndex   int    // paipu action index this decision anchors to (see below)
	DecisionIndex uint64 // monotone counter across the whole match
	ChosenAction  int    // 204-catalog id actually taken (rl.ActionPass for silent windows)
	Observation   *pb.SeatObservation
}

// ExtractDecisions replays every round of the paipu deterministically and
// returns each seat's decisions in chronological order. Any divergence
// between the paipu and the engine aborts with an error.
func ExtractDecisions(paipu *engine.Paipu) ([]Decision, error) {
	if paipu == nil || len(paipu.Rounds) == 0 {
		return nil, fmt.Errorf("paipu has no rounds")
	}
	var decisions []Decision
	var decisionIndex uint64
	for roundIdx := range paipu.Rounds {
		roundDecisions, next, err := replayRound(paipu, roundIdx, decisionIndex)
		if err != nil {
			return nil, fmt.Errorf("round %d: %w", roundIdx, err)
		}
		decisions = append(decisions, roundDecisions...)
		decisionIndex = next
	}
	return decisions, nil
}
```

`replayRound` mechanics (each round is replayed in a fresh classic-mode game — per-round independence is what makes chongci paipu replayable without knowing the original ChongciConfig):

```go
func replayRound(paipu *engine.Paipu, roundIdx int, decisionIndex uint64) ([]Decision, uint64, error) {
	round := &paipu.Rounds[roundIdx]
	seed, err := engine.SeedFromBase64(round.WallSeed)
	if err != nil {
		return nil, decisionIndex, fmt.Errorf("wall seed: %w", err)
	}
	game := engine.NewGame(paipu.MatchID, &rules.FenghuaRuleset{}, engine.MatchOptions{})
	game.SetWallSeed(seed)
	game.SetNextDealer(round.Dealer)
	if err := game.Start(); err != nil {
		return nil, decisionIndex, err
	}
	if err := verifyRoundSetup(game.State, round); err != nil {
		return nil, decisionIndex, err
	}
	r := &roundReplayer{game: game, round: round, roundIdx: roundIdx, decisionIndex: decisionIndex}
	if err := r.run(); err != nil {
		return nil, decisionIndex, err
	}
	return r.decisions, r.decisionIndex, nil
}
```

`verifyRoundSetup` compares `game.State` deals/wilds against `round.Deals` and `round.WildTiles` — every dealt tile id must match exactly; on mismatch return an error naming seat and slot.

The `roundReplayer.run()` loop mirrors `rl.Env.advanceToDecision` (`internal/rl/env.go:326`):

1. **`PHASE_ROUND_END`** → verify the cursor consumed all paipu actions (trailing unconsumed actions = divergence error) → done.
2. **System records at the cursor**: while the next paipu action is `draw` or `flower`, verify it against engine state (for `draw`: the recorded tile id must equal the tile the engine just dispensed to that seat — check `game.State.Players[seat].DrawnTileId` / hand contents; consult how `RecordDraw` is invoked in `internal/engine/game.go` to pick the exact field) and advance the cursor. Mismatch = divergence error.
3. **`PHASE_PLAYER_TURN`** (active seat has `ValidActions`): the next non-system paipu action must belong to that seat. Resolve it to a catalog id with `paipuActionID` (below), record a `Decision` if the seat had >1 legal action (`len(legalMap) > 1`), then `game.ProcessPlayerAction(seat, act)` where `act` is the matched legal action, and advance the cursor.
4. **`PHASE_WAIT_DISCARDS`**: peek the next non-system paipu action. For every seat with pending `ValidActions` and `!game.InterruptQueued(seat)` (same scan as `env.currentActionSeat`): if the peeked action is that seat's interrupt response (`chii`/`pon`/`okan`/`ron` whose `From` matches the current discarder), feed it (and record the decision anchored to the *peeked action's own index*, consuming the cursor); otherwise feed pass (`rl.ActionPass` decoded via `rl.DecodeActionID`) and record a pass decision anchored to the *triggering discard's* action index. When no seat is pending, `game.ResolveInterrupts()` (mirror `assertInterruptsReadyToResolve` first) and continue.
5. Anything else → error with a state summary (copy the spirit of `env.decisionStateSummary`).

`paipuActionID` maps a paipu record to a catalog id, then resolves the concrete engine action through `rl.LegalActions`:

```go
// paipuActionID maps a recorded paipu action to its 204-catalog id and the
// concrete legal pb.PlayerAction to feed the engine.
func (r *roundReplayer) paipuActionID(seat uint32, pa *engine.PaipuAction) (int, *pb.PlayerAction, error) {
	legal, err := rl.LegalActions(r.game.State, seat)
	if err != nil {
		return 0, nil, err
	}
	var id int
	switch pa.Act {
	case "discard":
		id = rl.DiscardBase + faceIndex42FromTileID(uint32(*pa.Tile))
	case "pon":
		id = rl.PonBase + faceIndex34FromTileID(calledTileID(pa))
	case "okan":
		id = rl.KanDirectBase + faceIndex34FromTileID(calledTileID(pa))
	case "ckan":
		id = rl.KanClosedBase + faceIndex34FromTileID(pa.Tiles[0])
	case "ukan":
		id = rl.KanUpgradedBase + faceIndex34FromTileID(uint32(*pa.Tile))
	case "chii":
		// ChiiCount=21 = 3 suits x 7 sequence starts. Recover the id by
		// scanning the legal map for the ACTION_CHII entry whose tiles match
		// the recorded meld faces — do NOT re-derive chiiSequenceIndex here.
		id = matchChiiID(legal, pa)
	case "tsumo":
		id = rl.ActionTsumo
	case "ron":
		id = rl.ActionRon
	case "haitei":
		id = rl.ActionAcceptHaitei
	case "haiteiRefuse":
		id = rl.ActionRefuseHaitei
	default:
		return 0, nil, fmt.Errorf("unmappable paipu act %q", pa.Act)
	}
	act, ok := legal[id]
	if !ok {
		return 0, nil, fmt.Errorf("recorded %s action (id %d) is not legal for seat %d", pa.Act, id, seat)
	}
	return id, act, nil
}
```

`faceIndex42FromTileID` / `faceIndex34FromTileID` convert a tile id (0-143) to the face index via `engine.TileFromId` + the same suit ordering as `tileFaceIndex42` (man 0-8, pin 9-17, sou 18-26, jihai 27-33, flower 34-41 — note paipu tile-id layout is SOU-first, the FACE order is MAN-first; do not confuse them). `calledTileID` for pon/okan: the called tile is the discarder's tile — the meld face equals the face of any tile in `pa.Tiles`, so use `pa.Tiles[0]`.

**Exact-tile fidelity:** after matching a discard's catalog id, if the legal action's tile id differs from the recorded tile id (two copies of the same face in hand), clone the action (`tiles.CloneAction` from `internal/tiles` — check its exact name in that package) and substitute the recorded tile, verifying the player actually holds that id. Later meld/discard-pile ids must match the paipu exactly.

Record decisions only when `len(legal) > 1` (a forced single-legal-action state is not a decision). Interrupt windows always have ≥2 (pass + the call), so every window with an offer is reviewable.

- [ ] **Step 5: Run tests until green**

Run: `go test ./internal/review/ -v`
Expected: PASS (all three tests). Iterate on driver details (draw verification field, flower handling, chongci ready flow in the helper) until the round-trip is exact. If the engine turns out to auto-execute something the paipu also records (or vice versa), fix the *driver's* cursor handling — never patch the engine.

- [ ] **Step 6: Write `internal/review/AGENTS.md`**

Document: package purpose (paipu → decisions → champion critique), the decision-anchor semantics (turn decisions anchor to the acted paipu index; pass decisions anchor to the triggering discard's index), the per-round fresh-classic-game replay strategy and why (chongci config not recorded in paipu), the divergence-abort policy, and the rl exports it depends on.

- [ ] **Step 7: Full test suite + commit**

Run: `go vet ./... && go test ./...`
Expected: PASS.

```bash
git add internal/rl/action.go internal/review/
git commit -m "feat(review): paipu replay driver extracting per-decision catalog actions

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Decision observations with Chongci-context normalization

Attach the 39ch observation to every `Decision`, encoding classic rounds as "Chongci final hand, all scores equal" and chongci rounds with their real per-round context.

**Files:**
- Create: `internal/review/context.go`
- Modify: `internal/review/replay.go` (fill `Decision.Observation` at capture time)
- Modify: `internal/review/replay_test.go` (extend)
- Modify: `internal/review/AGENTS.md`

**Interfaces:**
- Consumes: `rl.EncodeObservation(state, seat, decisionIndex) (*pb.SeatObservation, error)`; `Decision` from Task 1; `proto.Clone`.
- Produces: `reviewState(state *pb.GameState, paipu *engine.Paipu, roundIdx int) *pb.GameState` (unexported); `Decision.Observation` populated for every decision.

**Background:** `internal/rl/observation.go:208-251` (`setMatchContextScalars`) reads `state.MatchMode`, `state.HandNum`, `state.ChongciConfig{MaxHands, StartingScore, BustThreshold}`, and `state.Players[i].Score`. The replay game runs in classic mode with all scores 0, so the encode-time clone must be dressed up.

- [ ] **Step 1: Write the failing tests**

Append to `replay_test.go`:

```go
func TestObservationsChongciContextClassic(t *testing.T) {
	paipu := generateHeuristicPaipu(t, 7, engine.MatchOptions{})
	decisions, err := ExtractDecisions(paipu)
	if err != nil {
		t.Fatalf("ExtractDecisions: %v", err)
	}
	for i, d := range decisions {
		obs := d.Observation
		if obs == nil {
			t.Fatalf("decision %d: nil observation", i)
		}
		if int(obs.PlaneChannels) != rl.ObservationPlaneChannels {
			t.Fatalf("decision %d: expected %d channels (visible obs, never oracle), got %d",
				i, rl.ObservationPlaneChannels, obs.PlaneChannels)
		}
		// Classic paipu → chongci-final-hand-equal-scores context:
		// scalar 42 = chongci flag, 43 = hand progress (1 = final), 44 = remaining (0).
		if obs.Scalars[42] != 1 {
			t.Fatalf("decision %d: chongci flag scalar not set", i)
		}
		if obs.Scalars[43] != 1 || obs.Scalars[44] != 0 {
			t.Fatalf("decision %d: expected final-hand context, got progress=%f remaining=%f",
				i, obs.Scalars[43], obs.Scalars[44])
		}
		// Equal scores → self rank strength 1.0 (all tied at rank 1) and zero gaps.
		if obs.Scalars[45] != 1 || obs.Scalars[46] != 0 {
			t.Fatalf("decision %d: expected equal-scores context, got rank=%f leaderGap=%f",
				i, obs.Scalars[45], obs.Scalars[46])
		}
		// Chosen action must be legal in the observation's own mask.
		if obs.ActionMask[d.ChosenAction] != 1 {
			t.Fatalf("decision %d: chosen action %d illegal in mask", i, d.ChosenAction)
		}
	}
}

func TestObservationsChongciRealScores(t *testing.T) {
	paipu := generateHeuristicPaipu(t, 11, engine.MatchOptions{
		Mode: pb.MatchMode_MATCH_MODE_CHONGCI,
		// Same small ChongciConfig as TestExtractDecisionsChongciMultiRound.
	})
	decisions, err := ExtractDecisions(paipu)
	if err != nil {
		t.Fatalf("ExtractDecisions: %v", err)
	}
	// Find a decision in a round whose StartingScores are no longer equal
	// (after the first hand with a payout) and assert score scalars differ
	// across seats — i.e. real chongci context is carried through.
	// (Assert scalars[50] of two seats' decisions in that round differ.)
}
```

(Write the second test's body concretely: locate the first round with unequal `StartingScores`, pick two decisions from different seats in it, compare `obs.Scalars[50]`.)

- [ ] **Step 2: Run to verify failure**

Run: `go test ./internal/review/ -run TestObservations -v`
Expected: FAIL — nil observation.

- [ ] **Step 3: Implement `context.go`**

```go
package review

import (
	"google.golang.org/protobuf/proto"

	"github.com/plasma/fh-mahjong/internal/engine"
	pb "github.com/plasma/fh-mahjong/proto"
)

const defaultChongciStartingScore = int32(25000)

// isChongciPaipu detects chongci matches: chongci rounds record real (nonzero)
// starting scores; classic rounds record zeros.
func isChongciPaipu(paipu *engine.Paipu) bool {
	for _, r := range paipu.Rounds {
		for _, s := range r.StartingScores {
			if s != 0 {
				return true
			}
		}
	}
	return false
}

// reviewState clones the replay state and dresses it in the chongci context
// the champion was trained on. Classic matches are presented as the FINAL hand
// of a chongci match with all scores equal (user decision, see spec); chongci
// matches carry their real per-round starting scores. MaxHands for chongci is
// approximated by the number of recorded rounds (the true config cap is not
// stored in the paipu).
func reviewState(state *pb.GameState, paipu *engine.Paipu, roundIdx int) *pb.GameState {
	clone := proto.Clone(state).(*pb.GameState)
	clone.MatchMode = pb.MatchMode_MATCH_MODE_CHONGCI

	chongci := isChongciPaipu(paipu)
	startingScore := defaultChongciStartingScore
	if chongci {
		startingScore = paipu.Rounds[0].StartingScores[0]
	}
	maxHands := uint32(len(paipu.Rounds))
	if chongci {
		clone.HandNum = uint32(roundIdx)
	} else {
		clone.HandNum = maxHands // final hand: progress=1, remaining=0
	}
	clone.ChongciConfig = &pb.ChongciConfig{
		MaxHands:      maxHands,
		StartingScore: startingScore,
	}
	for seat, player := range clone.Players {
		if player == nil {
			continue
		}
		if chongci {
			player.Score = paipu.Rounds[roundIdx].StartingScores[seat]
		} else {
			player.Score = startingScore
		}
	}
	return clone
}
```

(Verify the actual `pb.ChongciConfig` field names against `proto/game.pb.go` — include `BustThreshold: 0` explicitly if the encoder reads it. Verify `state.HandNum` semantics against how `setMatchContextScalars` consumes it; if `scalars[43]==1` requires `HandNum==maxHands`, the classic branch above is right.)

In `replay.go`, at every decision capture:

```go
obs, err := rl.EncodeObservation(reviewState(r.game.State, r.paipu, r.roundIdx), seat, r.decisionIndex)
if err != nil {
	return fmt.Errorf("encode observation: %w", err)
}
```

(Thread `paipu` into `roundReplayer` for this.) The mask inside `obs` is computed from the dressed clone — scores/mode do not change legality, but assert in the test (already written) that `ChosenAction` is legal in it.

- [ ] **Step 4: Run tests**

Run: `go test ./internal/review/ -v`
Expected: PASS. If scalar assertions fail, re-read `setMatchContextScalars` and fix `reviewState` (not the test thresholds — the scalar semantics are fixed by training).

- [ ] **Step 5: Update AGENTS.md + commit**

Document the context-normalization rule and the MaxHands approximation in `internal/review/AGENTS.md`.

```bash
git add internal/review/
git commit -m "feat(review): encode decision observations with chongci-context normalization

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Report builder + HTTP policy client

Assemble the `ReviewReport` JSON by batch-querying the policy server's `/evaluate` endpoint.

**Files:**
- Create: `internal/review/report.go`
- Create: `internal/review/client.go`
- Create: `internal/review/report_test.go`
- Modify: `internal/review/AGENTS.md`

**Interfaces:**
- Consumes: `ExtractDecisions`, `Decision` (Tasks 1-2).
- Produces (this JSON schema is the frontend contract — Tasks 6/7 depend on the exact field names):

```go
type Report struct {
	SchemaVersion  int              `json:"schemaVersion"` // 1
	MatchID        string           `json:"matchId"`
	Ruleset        string           `json:"ruleset"`
	CheckpointPath string           `json:"checkpointPath"`
	CheckpointStep int              `json:"checkpointStep"`
	GeneratedAt    time.Time        `json:"generatedAt"`
	Decisions      []ReportDecision `json:"decisions"`
	Seats          []SeatSummary    `json:"seats"` // exactly 4
}

type ReportDecision struct {
	Seat        uint32       `json:"seat"`
	Round       int          `json:"round"`
	ActionIndex int          `json:"actionIndex"`
	ChosenID    int          `json:"chosenActionId"`
	ChosenProb  float32      `json:"chosenProb"`
	Value       float32      `json:"value"`
	Actions     []ActionProb `json:"actions"` // legal actions, sorted by prob desc
}

type ActionProb struct {
	ActionID int     `json:"actionId"`
	Prob     float32 `json:"prob"`
}

type SeatSummary struct {
	Seat           uint32   `json:"seat"`
	Decisions      int      `json:"decisions"`
	MeanChosenProb float32  `json:"meanChosenProb"`
	TopGaps        []GapRef `json:"topGaps"` // 5 largest prob gaps
}

type GapRef struct {
	Decision int     `json:"decision"` // index into Report.Decisions
	Gap      float32 `json:"gap"`      // top-action prob minus chosen-action prob
}
```

- `type PolicyClient interface { Evaluate(obs []*pb.SeatObservation) ([]PolicyResult, CheckpointInfo, error) }`
- `type PolicyResult struct { Probs []float32; Value float32 }` (Probs has length 204, dense)
- `type CheckpointInfo struct { Path string; Step int }`
- `func NewHTTPPolicyClient(baseURL string) *HTTPPolicyClient` — implements PolicyClient, POSTs `{baseURL}/evaluate` in chunks of 256 observations
- `func BuildReport(paipu *engine.Paipu, client PolicyClient) (*Report, error)`

**Wire format** (must match Task 4's server exactly; it extends the existing `/act` format from `internal/bot/remote/http_policy.go:246`):

```json
POST /evaluate
{"observations": [{"seat": 0, "planes": [...], "scalars": [...], "action_mask": [0,1,...]}]}

200 → {"results": [{"probs": [204 floats], "value": 0.12}],
       "checkpoint_path": "...", "checkpoint_step": 275}
400/500 → {"error": "..."}
```

- [ ] **Step 1: Write the failing test**

`internal/review/report_test.go`: build a report against an `httptest.Server` stub.

```go
func TestBuildReportAgainstStubServer(t *testing.T) {
	paipu := generateHeuristicPaipu(t, 7, engine.MatchOptions{})

	var gotBatches [][]map[string]any
	stub := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/evaluate" {
			http.NotFound(w, r)
			return
		}
		var req struct {
			Observations []map[string]any `json:"observations"`
		}
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			t.Errorf("decode: %v", err)
		}
		gotBatches = append(gotBatches, req.Observations)
		results := make([]map[string]any, len(req.Observations))
		for i, o := range req.Observations {
			mask := o["action_mask"].([]any)
			probs := make([]float64, len(mask))
			legal := 0
			for _, m := range mask {
				if m.(float64) == 1 {
					legal++
				}
			}
			for j, m := range mask {
				if m.(float64) == 1 {
					probs[j] = 1.0 / float64(legal) // uniform over legal
				}
			}
			results[i] = map[string]any{"probs": probs, "value": 0.25}
		}
		json.NewEncoder(w).Encode(map[string]any{
			"results": results, "checkpoint_path": "stub.pt", "checkpoint_step": 42,
		})
	}))
	defer stub.Close()

	report, err := BuildReport(paipu, NewHTTPPolicyClient(stub.URL))
	if err != nil {
		t.Fatalf("BuildReport: %v", err)
	}
	if report.SchemaVersion != 1 || report.CheckpointPath != "stub.pt" || report.CheckpointStep != 42 {
		t.Fatalf("bad header: %+v", report)
	}
	if len(report.Seats) != 4 {
		t.Fatalf("expected 4 seat summaries, got %d", len(report.Seats))
	}
	for i, d := range report.Decisions {
		if len(d.Actions) == 0 {
			t.Fatalf("decision %d: no legal actions", i)
		}
		var sum float32
		for j, a := range d.Actions {
			sum += a.Prob
			if j > 0 && d.Actions[j-1].Prob < a.Prob {
				t.Fatalf("decision %d: actions not sorted desc", i)
			}
		}
		if sum < 0.99 || sum > 1.01 {
			t.Fatalf("decision %d: legal probs sum %f", i, sum)
		}
		// Uniform stub → chosen prob == 1/len(actions).
		want := 1.0 / float32(len(d.Actions))
		if diff := d.ChosenProb - want; diff < -1e-4 || diff > 1e-4 {
			t.Fatalf("decision %d: chosen prob %f want %f", i, d.ChosenProb, want)
		}
	}
	for _, s := range report.Seats {
		if s.Decisions > 5 && len(s.TopGaps) != 5 {
			t.Fatalf("seat %d: expected 5 top gaps, got %d", s.Seat, len(s.TopGaps))
		}
	}
}

func TestBuildReportServerErrorReturnsNoPartialReport(t *testing.T) {
	paipu := generateHeuristicPaipu(t, 7, engine.MatchOptions{})
	stub := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, `{"error":"boom"}`, http.StatusInternalServerError)
	}))
	defer stub.Close()
	if _, err := BuildReport(paipu, NewHTTPPolicyClient(stub.URL)); err == nil {
		t.Fatal("expected error")
	}
}

func TestHTTPClientChunksBatches(t *testing.T) {
	// Call Evaluate directly with 600 synthetic observations (empty planes ok);
	// stub counts requests; expect ceil(600/256)=3 requests preserving order.
}
```

(Write the chunking test body concretely: synthesize `*pb.SeatObservation`s with tiny slices and distinct seats, echo seat-dependent values from the stub, assert order.)

- [ ] **Step 2: Run to verify failure**

Run: `go test ./internal/review/ -run TestBuildReport -v`
Expected: FAIL — `BuildReport` undefined.

- [ ] **Step 3: Implement client.go and report.go**

`client.go`: marshal each observation as `{"seat": obs.Seat, "planes": obs.Planes, "scalars": obs.Scalars, "action_mask": maskInts}` (mask bytes → ints, mirroring `internal/bot/remote/http_policy.go`). Chunk at 256, `http.Client{Timeout: 120 * time.Second}`, non-200 or `error` field → wrapped error. All chunks must report the same `checkpoint_path`/`checkpoint_step`; a mismatch (hot-swap mid-review) is an error — no mixed-champion reports.

`report.go` `BuildReport`:
1. `ExtractDecisions(paipu)`.
2. `client.Evaluate(observations)`.
3. Per decision: filter `Probs` by the observation's mask → `Actions` (sorted desc), renormalize over legal ids (server already masks; renormalizing is a no-op guard), `ChosenProb` = prob of `ChosenAction`, `Value` from result.
4. Seat summaries: count, mean chosen prob, top-5 gaps (`Actions[0].Prob - ChosenProb`) with decision indices.
5. Header fields from paipu + `CheckpointInfo` + `time.Now().UTC()`.

- [ ] **Step 4: Run tests**

Run: `go test ./internal/review/ -v`
Expected: PASS.

- [ ] **Step 5: Update AGENTS.md + commit**

```bash
git add internal/review/
git commit -m "feat(review): report builder with chunked /evaluate policy client

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Python policy server `/evaluate` endpoint

Batch masked-distribution inference on the existing serve_policy HTTP server.

**Files:**
- Modify: `ai/src/fh_mahjong_ai/serving.py` (add `CheckpointPolicy.evaluate_batch`)
- Modify: `ai/src/fh_mahjong_ai/scripts/serve_policy.py` (add `POST /evaluate`)
- Create: `ai/tests/test_serving_evaluate.py`

**Interfaces:**
- Consumes: `PolicyValueNet` forward `(planes, scalars, action_mask) -> (logits, value)` (verify mask semantics in `ai/src/fh_mahjong_ai/model.py` — logits are expected to be mask-adjusted; if masking happens outside the model, apply `logits[mask == 0] = -inf` before softmax here).
- Produces:
  - `CheckpointPolicy.evaluate_batch(planes: np.ndarray, scalars: np.ndarray, action_masks: np.ndarray, chunk_size: int = 256) -> tuple[np.ndarray, np.ndarray]` returning `(probs [N,204] float32, values [N] float32)`; probs are softmax over legal actions only, exactly 0 on illegal ones.
  - HTTP `POST /evaluate` with the wire format defined in Task 3.

- [ ] **Step 1: Write the failing tests**

`ai/tests/test_serving_evaluate.py` (follow the existing test style — look at how other `ai/tests/test_*.py` construct a small `PolicyValueNet`; there is likely a helper/pattern in `test_bridge.py` or a serving test):

```python
import numpy as np
import torch

from fh_mahjong_ai.config import EnvConfig
from fh_mahjong_ai.model import PolicyValueNet, ModelConfig  # verify actual config type name
from fh_mahjong_ai.serving import CheckpointPolicy


def _tiny_policy() -> CheckpointPolicy:
    env = EnvConfig()
    model = PolicyValueNet(env, ModelConfig(residual_blocks=1))  # match real ctor signature
    return CheckpointPolicy(
        model=model, checkpoint_path="test.pt", checkpoint_step=1, device="cpu",
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
```

Plus an HTTP handler test: import the handler module, build the payload dict, and exercise the `/evaluate` path via `http.client` against a `ThreadingHTTPServer` bound to port 0 with a `_tiny_policy()` holder (mirror any existing serve_policy test; if none exists, this pattern is ~25 lines). Assert response keys `results[i].probs`, `results[i].value`, `checkpoint_path`, `checkpoint_step`, and that a malformed payload returns 400 with `error`.

- [ ] **Step 2: Run to verify failure**

Run: `uv run --project ai pytest ai/tests/test_serving_evaluate.py -q`
Expected: FAIL — `evaluate_batch` missing.

- [ ] **Step 3: Implement `evaluate_batch`**

In `serving.py`, on `CheckpointPolicy`:

```python
@torch.inference_mode()
def evaluate_batch(
    self,
    planes: np.ndarray,
    scalars: np.ndarray,
    action_masks: np.ndarray,
    chunk_size: int = 256,
) -> tuple[np.ndarray, np.ndarray]:
    """Masked policy distribution + value for a batch of visible observations.

    Deterministic: no temperature/top-k sampling. Illegal actions get exactly
    zero probability. Used by the post-game review pipeline.
    """
    n = planes.shape[0]
    all_probs = np.zeros((n, action_masks.shape[1]), dtype=np.float32)
    all_values = np.zeros((n,), dtype=np.float32)
    expected_scalars = self.model.scalar_encoder[0].in_features
    for start in range(0, n, max(1, chunk_size)):
        end = min(n, start + max(1, chunk_size))
        p = torch.from_numpy(planes[start:end]).to(self.device)
        s = torch.from_numpy(scalars[start:end]).to(self.device)
        if s.shape[1] < expected_scalars:
            s = torch.nn.functional.pad(s, (0, expected_scalars - s.shape[1]))
        elif s.shape[1] > expected_scalars:
            raise ValueError(f"expected at most {expected_scalars} scalars, got {s.shape[1]}")
        m = torch.from_numpy(action_masks[start:end]).to(self.device)
        logits, value = self.model(p, s, m)
        legal = m.to(dtype=torch.bool)
        masked = logits.masked_fill(~legal, float("-inf"))
        probs = torch.softmax(masked, dim=1)
        probs = probs.masked_fill(~legal, 0.0)  # exact zeros, no -inf softmax residue
        all_probs[start:end] = probs.cpu().numpy().astype(np.float32)
        all_values[start:end] = value.reshape(-1).cpu().numpy().astype(np.float32)
    return all_probs, all_values
```

In `serve_policy.py`: route `POST /evaluate` in `do_POST`; the handler parses `payload["observations"]` (each element through the existing `observation_from_json`), stacks planes/scalars/masks with `np.stack`, calls `holder.policy.evaluate_batch`, and writes `{"results": [{"probs": [...], "value": v}, ...], "checkpoint_path": ..., "checkpoint_step": ...}`. Any exception → 400 `{"error": str(exc)}` (same pattern as `_handle_act`). Cap request batches: reject `len(observations) > 1024` with a clear error.

- [ ] **Step 4: Run tests**

Run: `uv run --project ai pytest ai/tests/test_serving_evaluate.py -q`
Expected: PASS. Then `uv run --project ai pytest -q` — Expected: PASS (no regressions).

- [ ] **Step 5: Update `ai/` AGENTS.md + commit**

Update the AGENTS.md covering `ai/src/fh_mahjong_ai/` (and its scripts dir if separate) with the `/evaluate` endpoint contract.

```bash
git add ai/
git commit -m "feat(ai): batch /evaluate endpoint serving masked policy distributions

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Storage model + backend review API

`match_reviews` cache table and `GET/POST /api/v1/matches/:matchId/review`.

**Files:**
- Modify: `internal/storage/db.go` (add `MatchReview`, register in `AutoMigrate`)
- Modify: `internal/api/paipu.go` (extract `loadPaipuJSON` helper from `handleGetPaipu`)
- Create: `internal/api/review.go`
- Create: `internal/api/review_test.go`
- Modify: `internal/api/server.go` (routes)
- Modify: `internal/storage/AGENTS.md`, `internal/api/AGENTS.md`

**Interfaces:**
- Consumes: `review.BuildReport`, `review.NewHTTPPolicyClient`, `storage.Match/PaipuRecord`, gin `Server` patterns from `internal/api`.
- Produces:
  - `storage.MatchReview{ID uint; MatchID string; CheckpointID string; ReportJSON string; CreatedAt time.Time}` with unique index on `(match_id, checkpoint_id)`
  - `GET /api/v1/matches/:matchId/review` → 200 cached report JSON | 404
  - `POST /api/v1/matches/:matchId/review` → 200 report (built or cached) | 503 `{"error":"reviewer unavailable"}` (no `POLICY_SERVER_URL`) | 502 (policy server failed) | 404 (no paipu) | 422 (unreviewable paipu)
  - `(*Server) loadPaipuJSON(matchID string) (string, bool)` — the existing paipu source chain (in-memory → PaipuRecord → Match.PaipuJSON → fixtures) reused by both handlers

**Model:**

```go
// MatchReview caches one champion's review report for a match. A new champion
// (different CheckpointID) re-reviews without destroying the old report.
type MatchReview struct {
	ID           uint      `gorm:"primaryKey" json:"-"`
	MatchID      string    `gorm:"size:255;not null;uniqueIndex:idx_match_reviews_match_ckpt,priority:1;index" json:"matchId"`
	CheckpointID string    `gorm:"size:512;not null;uniqueIndex:idx_match_reviews_match_ckpt,priority:2" json:"checkpointId"`
	ReportJSON   string    `gorm:"type:text;not null" json:"-"`
	CreatedAt    time.Time `json:"createdAt"`
}
```

(`MatchID` is `size:255` not `uuid` because replay ids also cover per-round `matchID-handNum` PaipuRecord keys and dev fixtures.) Add `&MatchReview{}` to the `db.AutoMigrate(...)` list in `AutoMigrate`.

**Handler flow (`internal/api/review.go`):**

```go
func (s *Server) handleGetReview(c *gin.Context)  // cache lookup only
func (s *Server) handlePostReview(c *gin.Context) // build-or-cached
```

`handlePostReview`:
1. `policyURL := os.Getenv("POLICY_SERVER_URL")`; empty → 503 `{"error": "reviewer unavailable"}`.
2. `paipuJSON, ok := s.loadPaipuJSON(matchID)`; !ok → 404.
3. `json.Unmarshal` into `engine.Paipu`; error → 422 `{"error": "unreviewable paipu: ..."}`.
4. If DB present: look up `MatchReview` rows for the match; if one exists whose `CheckpointID` matches the *serving* checkpoint — you don't know it before calling — so instead: return the newest cached row immediately UNLESS `c.Query("force") == "1"`. (Simple, honest cache: newest report wins; `?force=1` rebuilds against the current champion.)
5. Build: `review.BuildReport(paipu, review.NewHTTPPolicyClient(policyURL))`; error → 502 with detail. Distinguish 422 for `ExtractDecisions` divergence errors — have `BuildReport` wrap extraction failures in a sentinel (`errors.Is(err, review.ErrUnreviewable)`; add `var ErrUnreviewable = errors.New("unreviewable paipu")` to `report.go` and wrap).
6. Cache: if DB present, upsert on `(MatchID, CheckpointID=report.CheckpointPath)` (`clauses.OnConflict{DoNothing}` or delete+insert — match existing GORM usage in the codebase). DB absent (dev): skip caching, still return the report.
7. Respond 200 with the report JSON.

`handleGetReview`: DB nil → 404; else newest `MatchReview` by `created_at` for the match → 200 raw `ReportJSON` (`c.Data` with `application/json`) or 404.

Routes in `server.go` next to the replay routes (same public visibility as `/replays/:matchId` per spec):

```go
v1.GET("/matches/:matchId/review", s.handleGetReview)
v1.POST("/matches/:matchId/review", s.handlePostReview)
```

- [ ] **Step 1: Write the failing tests**

`internal/api/review_test.go`, following `auth_test.go`'s sqlite pattern (`gorm.Open(sqlite.Open(":memory:"))` + `storage.AutoMigrate`) and `private_tables_test.go`'s server construction:

1. `TestPostReviewNoPolicyServer` — unset `POLICY_SERVER_URL` (use `t.Setenv("POLICY_SERVER_URL", "")`), POST → 503.
2. `TestPostReviewBuildsAndCaches` — generate a heuristic paipu (reuse the Task 1 helper by exporting a tiny test-support generator OR store a golden fixture: simplest is to run `go run ./cmd/rlpaipu -seed 7 -match-id review-fixture -output testdata/paipu/review-fixture.json` once in this task and commit the fixture; the server's fixture loader then serves it with no DB rows needed). Start the Task 3 stub policy server via `httptest`, `t.Setenv("POLICY_SERVER_URL", stub.URL)`, seed the match: `server.StorePaipu("review-fixture", fixtureJSON)`. POST → 200 with `schemaVersion:1`; assert a `MatchReview` row exists; POST again → 200 and stub request count unchanged (cache hit); GET → 200 same body.
3. `TestPostReviewPolicyServerDown` — `t.Setenv("POLICY_SERVER_URL", "http://127.0.0.1:1")`, POST → 502.
4. `TestGetReviewMissing` — GET unknown match → 404.
5. `TestPostReviewBadPaipu` — `server.StorePaipu("bad", "{\"rounds\":[]}")`, POST → 422.

- [ ] **Step 2: Run to verify failure**

Run: `go test ./internal/api/ -run TestPostReview -v`
Expected: FAIL — route not registered (404s).

- [ ] **Step 3: Implement**

- Extract `loadPaipuJSON` from `handleGetPaipu` (pure refactor: the existing handler becomes a thin wrapper; keep behavior identical — in-memory store, PaipuRecord, Match.PaipuJSON with UUID guard, fixtures).
- Add the model + AutoMigrate registration.
- Implement handlers + routes as specified above.
- Commit the `testdata/paipu/review-fixture.json` golden fixture.

- [ ] **Step 4: Run tests**

Run: `go vet ./... && go test ./...`
Expected: PASS, including untouched api/storage suites.

- [ ] **Step 5: Update AGENTS.md files + commit**

`internal/api/AGENTS.md`: review endpoints, status-code contract, `POLICY_SERVER_URL`. `internal/storage/AGENTS.md`: `MatchReview` and the newest-wins/`?force=1` cache policy.

```bash
git add internal/api/ internal/storage/ testdata/paipu/review-fixture.json
git commit -m "feat(api): match review endpoints with match_reviews cache

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Frontend review types + severity/label utils

Pure-logic layer with vitest coverage; no UI yet.

**Files:**
- Create: `web/src/features/replay/reviewTypes.ts`
- Create: `web/src/features/replay/reviewUtils.ts`
- Create: `web/src/features/replay/reviewUtils.test.ts`

**Interfaces:**
- Consumes: Task 3's report JSON schema (field names must match exactly); `getApiUrl` from `web/src/config`.
- Produces:

```ts
// reviewTypes.ts
export interface ActionProb { actionId: number; prob: number }
export interface ReportDecision {
  seat: number; round: number; actionIndex: number
  chosenActionId: number; chosenProb: number; value: number
  actions: ActionProb[]
}
export interface GapRef { decision: number; gap: number }
export interface SeatSummary { seat: number; decisions: number; meanChosenProb: number; topGaps: GapRef[] }
export interface ReviewReport {
  schemaVersion: number; matchId: string; ruleset: string
  checkpointPath: string; checkpointStep: number; generatedAt: string
  decisions: ReportDecision[]; seats: SeatSummary[]
}
export async function fetchReview(matchId: string): Promise<ReviewReport | null>   // GET, null on 404
export async function generateReview(matchId: string): Promise<ReviewReport>       // POST, throws {status, message}
```

```ts
// reviewUtils.ts
export type Severity = 'ok' | 'disagreement' | 'mistake'
export const SEVERITY_THRESHOLDS = { disagreement: 0.3, mistake: 0.6, topNExempt: 3, topNMinProb: 0.05 }
export function decisionGap(d: ReportDecision): number       // top prob - chosen prob (>= 0)
export function decisionSeverity(d: ReportDecision): Severity
export function actionLabel(actionId: number): { en: string; zh: string }
export function decisionKey(round: number, actionIndex: number): string  // `${round}:${actionIndex}`
```

**Action catalog for `actionLabel`** (mirror `internal/rl/action.go` — keep this comment in the file):
ids 0-4 = pass/tsumo/ron/accept-haitei/refuse-haitei; 5-46 discard by face (man 1-9, pin 1-9, sou 1-9, jihai 1-7, flower 1-8); 47-80 pon by face (34 faces, no flowers); 81-114 open kan; 115-148 closed kan; 149-182 upgraded kan; 183-203 chii (3 suits × sequence starts 1-7, order man/pin/sou). Face labels: `1m…9m, 1p…9p, 1s…9s`, jihai `东南西北中发白` order must match the engine's jihai value order 1-7 — copy the value→name mapping used by the existing tile rendering in `web/src/utils/tileUtils.ts` rather than guessing. English: `E S W N` + dragon names. Examples: `actionLabel(5) → {en: 'Discard 1m', zh: '打 1万'}`, `actionLabel(0) → {en: 'Pass', zh: '过'}`, `actionLabel(183) → {en: 'Chii 1-2-3m', zh: '吃 1-2-3万'}`.

- [ ] **Step 1: Write failing tests**

`reviewUtils.test.ts` (vitest):

```ts
import { describe, expect, it } from 'vitest'
import { actionLabel, decisionGap, decisionSeverity } from './reviewUtils'
import type { ReportDecision } from './reviewTypes'

function dec(actions: [number, number][], chosen: number): ReportDecision {
  return {
    seat: 0, round: 0, actionIndex: 3,
    chosenActionId: chosen,
    chosenProb: actions.find(([id]) => id === chosen)?.[1] ?? 0,
    value: 0,
    actions: actions.map(([actionId, prob]) => ({ actionId, prob })),
  }
}

describe('decisionSeverity', () => {
  it('flags a large gap as mistake', () => {
    expect(decisionSeverity(dec([[5, 0.8], [6, 0.15], [7, 0.04], [8, 0.01]], 8))).toBe('mistake')
  })
  it('flags a medium gap as disagreement', () => {
    // Chosen is rank 4 (outside the top-3 exemption) with gap 0.42.
    expect(decisionSeverity(dec([[5, 0.5], [6, 0.3], [7, 0.12], [8, 0.08]], 8))).toBe('disagreement')
  })
  it('never flags a chosen action in top-3 with >=5%', () => {
    // gap 0.75 would be "mistake", but chosen is rank 2 with 20%.
    expect(decisionSeverity(dec([[5, 0.75], [6, 0.2], [7, 0.05]], 6))).toBe('ok')
  })
  it('small gaps are ok', () => {
    expect(decisionSeverity(dec([[5, 0.4], [6, 0.35], [7, 0.25]], 7))).toBe('ok')
  })
})

describe('decisionGap', () => {
  it('is top prob minus chosen prob', () => {
    expect(decisionGap(dec([[5, 0.6], [6, 0.4]], 6))).toBeCloseTo(0.2)
  })
})

describe('actionLabel', () => {
  it('labels catalog boundaries', () => {
    expect(actionLabel(0).en).toBe('Pass')
    expect(actionLabel(5).en).toBe('Discard 1m')
    expect(actionLabel(46).en).toContain('Discard') // last flower discard
    expect(actionLabel(47).en).toContain('Pon 1m')
    expect(actionLabel(183).en).toContain('Chii')
    expect(actionLabel(203).en).toContain('Chii')
  })
})
```

- [ ] **Step 2: Run to verify failure**

Run: `cd web && npx vitest run src/features/replay/reviewUtils.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

```ts
// reviewUtils.ts (core logic)
export function decisionGap(d: ReportDecision): number {
  const top = d.actions[0]?.prob ?? 0 // report actions are sorted desc
  return Math.max(0, top - d.chosenProb)
}

export function decisionSeverity(d: ReportDecision): Severity {
  const rank = d.actions.findIndex(a => a.actionId === d.chosenActionId)
  if (rank >= 0 && rank < SEVERITY_THRESHOLDS.topNExempt && d.chosenProb >= SEVERITY_THRESHOLDS.topNMinProb) {
    return 'ok'
  }
  const gap = decisionGap(d)
  if (gap >= SEVERITY_THRESHOLDS.mistake) return 'mistake'
  if (gap >= SEVERITY_THRESHOLDS.disagreement) return 'disagreement'
  return 'ok'
}
```

`fetchReview`/`generateReview` use `getApiUrl('/api/v1/matches/${matchId}/review')`, GET returning `null` on 404, POST throwing `{status, message}` (surface the server's `error` field).

- [ ] **Step 4: Run tests + typecheck**

Run: `cd web && npx tsc --noEmit && npx vitest run`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/features/replay/reviewTypes.ts web/src/features/replay/reviewUtils.ts web/src/features/replay/reviewUtils.test.ts
git commit -m "feat(web): review report types, severity tiers, and action labels

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: Replay viewer review mode (ReviewPanel + wiring)

The KillerDucky-style integrated overlay.

**Files:**
- Create: `web/src/features/replay/ReviewPanel.tsx`
- Modify: `web/src/features/replay/Replay.tsx`
- Create: `web/src/features/replay/ReviewPanel.test.tsx` (light render test)
- Update: the AGENTS.md covering `web/src/features/replay/` (create if the directory has none — check `web/src/` AGENTS layout)

**Interfaces:**
- Consumes: `ReviewReport`, `fetchReview`, `generateReview`, `decisionSeverity`, `decisionGap`, `actionLabel`, `decisionKey` (Task 6); `ReplayEngine` position (`engine.currentRoundIndex`, `state.actionIndex`) and `jumpToRound` from `replayEngine.ts` (add a `jumpToAction(roundIdx, actionIndex)` method to `ReplayEngine` if stepping-to-index doesn't exist — check `replayEngine.ts` first; it already supports `jumpToRound` + `stepForward`, so `jumpToAction` = jumpToRound + stepForward loop).
- Produces: `<ReviewPanel report={report} viewSeat={n} position={{round, actionIndex}} onJump={(round, actionIndex) => void} lang={'en'|'zh'} />`

**Behavior (all per spec §Component 4):**
1. **Data load:** on mount, `fetchReview(matchId)`. If `null`, show a "Request review / 请求复盘" button → `generateReview`; render progress state; on 503 show "Reviewer unavailable — no policy server configured / 复盘服务未配置" (neutral copy).
2. **Decision index:** `useMemo` building `Map<string, ReportDecision[]>` keyed by `decisionKey(round, actionIndex)` (multiple seats can anchor to one discard index — a call window).
3. **Analysis panel (always-on when review exists):** at the viewer's current position, look up decisions at the current key for the panel's selected seat (default: `viewSeat`, i.e. the perspective selector already in Replay.tsx). Render a horizontal bar chart: one row per legal action (top 8 by prob, plus the chosen action if outside top 8), label via `actionLabel` + percentage, bar width = prob. Chosen action row highlighted with its severity color (ok = neutral/green, disagreement = yellow `#f59e0b`, mistake = red `#ef4444`). Wording: "Champion prefers 5m (72%) / 冠军模型倾向 打5万 (72%)" — never "wrong".
4. **Mistake summary strip:** per selected seat — counts by severity + the seat's `topGaps` as clickable entries ("R2 · Discard 9s · gap 0.71") that call `onJump(round, actionIndex)`.
5. **Value timeline:** inline SVG sparkline of `value` over the selected seat's decisions in decision order; a marker at the current decision; clicking a point jumps to it.
6. **Placement note:** persistent small caption: "The champion optimizes final placement (Chongci) and is strong but not an oracle / 冠军模型以冲刺名次为目标，仅供参考".
7. **Threshold tunability:** a small settings row with two sliders bound to local state overriding `SEVERITY_THRESHOLDS` (pass overrides into `decisionSeverity` — extend its signature with an optional thresholds arg in Task 6's file if needed; keep the default export constant).
8. **Wiring in Replay.tsx:** render `<ReviewPanel/>` as a third column (or collapsible section of the existing control panel — match the existing 280px panel pattern; a second stacked section inside the control panel is least invasive). Mark flagged decisions of the selected seat on the round progress bar as colored ticks (absolutely-positioned dots over the existing progress div).
9. Bilingual: follow the `/calc` page's existing language-toggle pattern (check `web/src/features/calc/` for how it stores the language; reuse the same mechanism/state source).

- [ ] **Step 1: Light failing render test**

`ReviewPanel.test.tsx`: render `ReviewPanel` with a fixture report (two decisions, one mistake), position at the mistake, assert the severity badge text and a bar row for the champion's top action appear (use `@testing-library/react` if present in `web/package.json` — check; if not present, test the pure helper `selectPanelDecisions(report, seat, key)` extracted into `reviewUtils.ts` instead and skip DOM testing).

- [ ] **Step 2: Run to verify failure, then implement**

Run: `cd web && npx vitest run src/features/replay/`
Implement `ReviewPanel.tsx` (inline styles matching Replay.tsx's existing style objects — dark palette `rgba(17,24,39,0.95)`, emerald accents) and the Replay.tsx wiring per the behavior list.

- [ ] **Step 3: Verify**

Run: `cd web && npx tsc --noEmit && npx vitest run`
Expected: PASS.

Manual smoke (documented for the executor, run it): backend `go run cmd/server/main.go` with `POLICY_SERVER_URL` pointed at a running `uv run --project ai python ai/src/fh_mahjong_ai/scripts/serve_policy.py --checkpoint <path>` (or the Task 3 stub for UI-only iteration), open `http://localhost:3000/replay/review-fixture`, click "Request review", step through decisions and confirm: bars render at every decision of the selected seat, severity colors and ticks appear, jump-to-mistake works, value sparkline tracks. Kill old processes on ports 8080/3000 first.

- [ ] **Step 4: Commit**

```bash
git add web/src/features/replay/
git commit -m "feat(web): integrated review overlay in replay viewer

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: Docs, AGENTS.md sweep, full verification

**Files:**
- Modify: `internal/AGENTS.md` (add `review` to the package map)
- Verify/complete: AGENTS.md updates from Tasks 1-7 (`internal/review`, `internal/api`, `internal/storage`, `ai/...`, `web/...` replay dir)
- Modify: root `AGENTS.md` if it lists API endpoints or feature surfaces (check first)

- [ ] **Step 1: AGENTS.md sweep**

Confirm every touched directory's AGENTS.md reflects the final state; add `internal/review` to `internal/AGENTS.md`'s package map with one line: "paipu → decision reconstruction → champion policy critique (post-game review); drives engine.Game, reuses rl encoders, never oracle obs."

- [ ] **Step 2: Full verification**

Run all three suites and record output:

```bash
go vet ./... && go test ./...
uv run --project ai pytest -q
cd web && npx tsc --noEmit && npx vitest run
```

Expected: all PASS. Fix anything that fails before committing.

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "docs: AGENTS.md updates for post-game review feature

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

**After Task 8** (workflow, separate steps — not part of this plan's code): `/adversarial-review-loop` until approve → open PR → wait for GitHub Codex review approval → `gh pr merge N --merge`.

---

## Self-Review Notes (already applied)

- Spec coverage: replay driver + pass decisions + divergence aborts (Task 1), hidden-info + mode normalization (Task 2, asserted in tests), report schema + 5 top gaps + checkpoint stamping (Task 3), `/evaluate` determinism/masking/chunking (Task 4), endpoints/status codes/cache table/TEXT column (Task 5), tiered severity + top-3 exemption + neutral bilingual wording + value timeline + jump navigation + tunable thresholds (Tasks 6-7), AGENTS.md (each task + Task 8). Non-goals untouched: no EV rollouts, no ONNX, no auto-review, no proto changes.
- Known approximations (documented in code/AGENTS by tasks): chongci `MaxHands` ≈ recorded round count; classic-mode detection via all-zero `StartingScores`; cache policy is newest-report-wins with `?force=1` rebuild (spec's "(match_id, checkpoint_id) unique" is kept for storage; the lookup shortcut avoids a pre-flight checkpoint query).
- Deliberate contract risks called out to implementers: `pb.ChongciConfig` field names, `PolicyValueNet` ctor/mask semantics, `RecordDraw` verification field, `tiles` clone helper names — each task says exactly where to verify.
