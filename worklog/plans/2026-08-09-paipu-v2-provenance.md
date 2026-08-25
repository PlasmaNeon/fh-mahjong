# Paipu v2 Provenance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a per-decision supervision trace (legal action IDs + source provenance + per-decision checkpoint SHA) and match-level metadata to the paipu, so production matches become usable training data.

**Architecture:** The engine stays provenance-blind: `PaipuDecision`/`Decisions` are plain data in `internal/engine/paipu.go`. Capture happens at the room layer (`internal/api`) — the one choke point where humans (`dispatchClientAction`), bots (`room_bot.go`), and fallbacks all pass — which snapshots `rl.LegalActions` before each `ProcessPlayerAction` and appends after success. Checkpoint SHA travels atomically inside the `/act` response (Python → Go), never via `/healthz`.

**Tech Stack:** Go 1.25 (`internal/engine`, `internal/api`, `internal/bot`, `internal/rl`, `internal/review`), Python (`ai/src/fh_mahjong_ai/scripts/serve_policy.py`).

**Spec:** `worklog/specs/2026-08-09-paipu-v2-provenance-design.md` — read it first.

## Global Constraints

- Branch: `feat/paipu-v2-provenance` (already created off main; spec committed).
- `internal/engine` must NEVER import `internal/rules` or `internal/rl` or `internal/bot`. `internal/api` may import all of them.
- Paipu `version` becomes `2`. v1 paipus (no `decisions` key) must load and replay exactly as before.
- `PaipuRound.Actions` semantics are untouched — no new action kinds, no injected passes.
- Decision rows are appended ONLY after the action was successfully processed; legal IDs are snapshotted BEFORE processing. Failed/illegal attempts are never recorded.
- `source` values: exactly `human | remote | fallback | heuristic`.
- No mutable "last provenance" state anywhere — provenance travels via return values.
- Never break existing tests: run `go test ./...` (repo root) after every Go task, `uv run --project ai pytest -q` after the Python task.
- Commit after every task with the trailer: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Tile id 0 and seat 0 and action id 0 (`ActionPass`) are all VALID values — never use 0 as a sentinel in JSON (use pointers or `omitempty`-safe shapes as specified below; `chosenId`/`legalIds` are always emitted, never omitted).

---

### Task 1: Engine — paipu v2 schema (`PaipuDecision`, header metadata, `RecordDecision`)

**Files:**
- Modify: `internal/engine/paipu.go`
- Test: `internal/engine/paipu_v2_test.go` (create)

**Interfaces:**
- Consumes: nothing new.
- Produces (later tasks rely on these exact names):
  - `type PaipuCheckpoint struct { Name string; Step int64; Sha256 string }`
  - `type PaipuDecision struct { Index int; Seat uint32; ChosenID int; LegalIDs []int; LegalIDsError bool; Source string; FallbackReason string; Checkpoint *PaipuCheckpoint }`
  - `PaipuRound.Decisions []PaipuDecision`
  - `func (r *PaipuRecorder) RecordDecision(d PaipuDecision)` (assigns `Index` itself)
  - `type PaipuMatchMeta struct { Status string; CompletionReason string; Placements *[4]uint; ServerCommit string; MatchMode string; Chongci *PaipuChongciConfig; RulesetVersion string; EventContractVersion uint32; ProtoEnumsRevision int; ActionCatalogVersion int }`
  - `func (r *PaipuRecorder) SetMatchMeta(m PaipuMatchMeta)`
  - `const PaipuVersion = 2`, `const ProtoEnumsRevision = 1`

- [ ] **Step 1: Write the failing test**

```go
package engine

import (
	"encoding/json"
	"testing"
)

func TestPaipuV2DecisionTraceRoundTrip(t *testing.T) {
	r := NewPaipuRecorder("m1", "fenghua")
	r.AddPlayer(0, "p0", 1)
	r.StartRound(1, 0, 0, [2]uint32{1, 2}, "seed", nil, 16, [4]int32{}, [4][]uint32{})
	r.RecordDecision(PaipuDecision{
		Seat: 2, ChosenID: 0, LegalIDs: []int{0, 47}, Source: "human",
	})
	r.RecordDecision(PaipuDecision{
		Seat: 1, ChosenID: 12, LegalIDs: []int{5, 12}, Source: "remote",
		Checkpoint: &PaipuCheckpoint{Name: "ck.pt", Step: 75, Sha256: "abc"},
	})
	r.EndRound(&PaipuRoundResult{Type: "draw", ScoreChanges: []int32{0, 0, 0, 0}})
	r.SetMatchMeta(PaipuMatchMeta{
		Status: "completed", CompletionReason: "match_end",
		Placements: &[4]uint{1, 2, 3, 4}, ServerCommit: "deadbeef",
		MatchMode: "chongci", RulesetVersion: "fenghua-v1",
		EventContractVersion: 1, ProtoEnumsRevision: ProtoEnumsRevision,
		ActionCatalogVersion: 1,
	})
	p := r.Finalize([4]int32{10, 0, 0, -10})

	if p.Version != 2 {
		t.Fatalf("Version = %d, want 2", p.Version)
	}
	blob, err := json.Marshal(p)
	if err != nil {
		t.Fatal(err)
	}
	var back Paipu
	if err := json.Unmarshal(blob, &back); err != nil {
		t.Fatal(err)
	}
	decs := back.Rounds[0].Decisions
	if len(decs) != 2 {
		t.Fatalf("decisions = %d, want 2", len(decs))
	}
	// Index assigned by the recorder, monotonic from 0 per round.
	if decs[0].Index != 0 || decs[1].Index != 1 {
		t.Fatalf("indices = %d,%d, want 0,1", decs[0].Index, decs[1].Index)
	}
	// ChosenID 0 (pass) must survive JSON (no omitempty on chosenId).
	if decs[0].ChosenID != 0 || decs[0].Source != "human" {
		t.Fatalf("row 0 = %+v", decs[0])
	}
	if decs[1].Checkpoint == nil || decs[1].Checkpoint.Sha256 != "abc" {
		t.Fatalf("row 1 checkpoint = %+v", decs[1].Checkpoint)
	}
	if back.Status != "completed" || back.CompletionReason != "match_end" {
		t.Fatalf("meta = %q/%q", back.Status, back.CompletionReason)
	}
	if back.Placements == nil || back.Placements[0] != 1 {
		t.Fatalf("placements = %v", back.Placements)
	}
}

func TestPaipuV1FixtureStillLoads(t *testing.T) {
	// A v1 blob: no decisions key, no meta keys. Must unmarshal cleanly with
	// nil Decisions and zero meta.
	v1 := `{"version":1,"matchId":"old","ruleset":"fenghua","players":[],"rounds":[{"round":1,"prevailingWind":0,"dealer":0,"dice":[1,2],"wallSeed":"s","wildTiles":[],"wangpaiStacks":16,"startingScores":[0,0,0,0],"deals":[[],[],[],[]],"initialFlowers":null,"actions":[{"act":"draw","seat":0,"tile":5}],"result":null}],"finalScores":[0,0,0,0]}`
	var p Paipu
	if err := json.Unmarshal([]byte(v1), &p); err != nil {
		t.Fatal(err)
	}
	if p.Version != 1 || p.Rounds[0].Decisions != nil || p.Status != "" {
		t.Fatalf("v1 decode changed: version=%d decisions=%v status=%q", p.Version, p.Rounds[0].Decisions, p.Status)
	}
}

func TestPaipuSnapshotKeepsInProgressDecisions(t *testing.T) {
	r := NewPaipuRecorder("m1", "fenghua")
	r.StartRound(1, 0, 0, [2]uint32{1, 2}, "seed", nil, 16, [4]int32{}, [4][]uint32{})
	r.RecordDecision(PaipuDecision{Seat: 0, ChosenID: 7, LegalIDs: []int{7}, Source: "heuristic"})
	snap := r.Snapshot([4]int32{})
	if len(snap.Rounds) != 1 || len(snap.Rounds[0].Decisions) != 1 {
		t.Fatalf("snapshot dropped in-progress decisions: %+v", snap.Rounds)
	}
}
```

- [ ] **Step 2: Run to verify it fails**

Run: `go test ./internal/engine/ -run 'TestPaipuV2|TestPaipuV1Fixture|TestPaipuSnapshotKeeps' -v`
Expected: FAIL — `undefined: PaipuDecision`, `undefined: PaipuCheckpoint`, etc.

- [ ] **Step 3: Implement**

In `internal/engine/paipu.go`:

```go
// After PaipuAction (line ~44), add:

// PaipuCheckpoint identifies the exact model that served a remote decision.
// Captured atomically from the same /act response that produced the action.
type PaipuCheckpoint struct {
	Name   string `json:"name"`             // checkpoint file base name
	Step   int64  `json:"step"`             // training step
	Sha256 string `json:"sha256,omitempty"` // empty when the server predates sha reporting
}

// PaipuDecision is one row of the v2 supervision trace: a player decision
// with its full legal-action context and provenance. It is SEPARATE from the
// Actions replay stream (which stays canonical and pass-free); replay
// consumers cross-check the two (internal/review).
type PaipuDecision struct {
	Index int    `json:"index"` // monotonic within the round, assigned by the recorder
	Seat  uint32 `json:"seat"`
	// ChosenID/LegalIDs are catalog action IDs (internal/rl action catalog,
	// pinned by Paipu.ActionCatalogVersion). NEVER omitempty: id 0 is PASS.
	ChosenID int   `json:"chosenId"`
	LegalIDs []int `json:"legalIds"`
	// LegalIDsError marks a row whose legal-set snapshot failed at record
	// time (LegalIDs is then nil). Live play never blocks on snapshot errors.
	LegalIDsError  bool             `json:"legalIdsError,omitempty"`
	Source         string           `json:"source"` // "human" | "remote" | "fallback" | "heuristic"
	FallbackReason string           `json:"fallbackReason,omitempty"`
	Checkpoint     *PaipuCheckpoint `json:"checkpoint,omitempty"` // remote decisions only
}
```

Add `Decisions []PaipuDecision \`json:"decisions,omitempty"\`` to `PaipuRound` (after `Actions`).

```go
// Paipu version + proto-enum provenance constants.
const (
	// PaipuVersion is the schema version written by this recorder.
	// v2 (2026-08-09) added the Decisions supervision trace + match metadata.
	PaipuVersion = 2
	// ProtoEnumsRevision guards the raw proto enum ints embedded in paipu
	// JSON (PaipuTile.Suit). Bump if proto/game.proto ever renumbers an enum
	// a paipu embeds — historical records are only interpretable against the
	// revision they were written with.
	ProtoEnumsRevision = 1
)
```

Extend the `Paipu` struct (all new fields AFTER `FinalScores`, all `omitempty` except none needed — they're header-level):

```go
type Paipu struct {
	Version     int           `json:"version"`
	MatchID     string        `json:"matchId"`
	Ruleset     string        `json:"ruleset"`
	Players     []PaipuPlayer `json:"players"`
	Rounds      []PaipuRound  `json:"rounds"`
	FinalScores [4]int32      `json:"finalScores"`

	// v2 match metadata (empty/nil in v1 records — readers treat absence as
	// unknown). Set once at persist time via SetMatchMeta.
	Status               string              `json:"status,omitempty"`           // "completed" | "aborted"
	CompletionReason     string              `json:"completionReason,omitempty"` // "match_end" | "drained" | "abandoned"
	Placements           *[4]uint            `json:"placements,omitempty"`       // competition ranking, ties share best
	ServerCommit         string              `json:"serverCommit,omitempty"`
	MatchMode            string              `json:"matchMode,omitempty"` // "classic" | "chongci"
	Chongci              *PaipuChongciConfig `json:"chongci,omitempty"`
	RulesetVersion       string              `json:"rulesetVersion,omitempty"`
	EventContractVersion uint32              `json:"eventContractVersion,omitempty"`
	ProtoEnumsRevision   int                 `json:"protoEnumsRevision,omitempty"`
	ActionCatalogVersion int                 `json:"actionCatalogVersion,omitempty"`
}

// PaipuChongciConfig mirrors the pb.ChongciConfig the match ran under.
type PaipuChongciConfig struct {
	StartingScore int32  `json:"startingScore"`
	BustThreshold int32  `json:"bustThreshold"`
	MaxHands      uint32 `json:"maxHands"`
}

// PaipuMatchMeta carries the v2 header fields set at persist time.
type PaipuMatchMeta struct {
	Status               string
	CompletionReason     string
	Placements           *[4]uint
	ServerCommit         string
	MatchMode            string
	Chongci              *PaipuChongciConfig
	RulesetVersion       string
	EventContractVersion uint32
	ProtoEnumsRevision   int
	ActionCatalogVersion int
}
```

Change `NewPaipuRecorder` to write `Version: PaipuVersion`. Add:

```go
// RecordDecision appends a supervision-trace row to the current round,
// assigning its monotonic per-round index. No-op between rounds (mirrors
// record()); callers snapshot legal IDs BEFORE processing the action and
// call this only AFTER the action succeeded.
func (r *PaipuRecorder) RecordDecision(d PaipuDecision) {
	if r.currentRound == nil {
		return
	}
	d.Index = len(r.currentRound.Decisions)
	r.currentRound.Decisions = append(r.currentRound.Decisions, d)
}

// SetMatchMeta stamps the v2 match-level header fields. Called at persist
// time (idempotent — persistMatch may run more than once for snapshots).
func (r *PaipuRecorder) SetMatchMeta(m PaipuMatchMeta) {
	p := &r.paipu
	p.Status = m.Status
	p.CompletionReason = m.CompletionReason
	p.Placements = m.Placements
	p.ServerCommit = m.ServerCommit
	p.MatchMode = m.MatchMode
	p.Chongci = m.Chongci
	p.RulesetVersion = m.RulesetVersion
	p.EventContractVersion = m.EventContractVersion
	p.ProtoEnumsRevision = m.ProtoEnumsRevision
	p.ActionCatalogVersion = m.ActionCatalogVersion
}
```

**Snapshot fix (critical):** `Snapshot` (line ~309) copies `*r.currentRound` by value — the `Decisions` slice header is shared exactly like `Actions`, which the existing comment already covers ("Call from the goroutine that owns the recorder"). No code change needed, but extend that comment to mention Decisions.

- [ ] **Step 4: Run to verify it passes**

Run: `go test ./internal/engine/ -v -run 'TestPaipu'`
Expected: PASS (all, including pre-existing paipu tests — `NewPaipuRecorder` now stamps version 2; if an existing test asserts `Version == 1`, update that assertion to `PaipuVersion` — that is the ONLY acceptable existing-test change).

- [ ] **Step 5: Full package + commit**

Run: `go test ./... 2>&1 | tail -20` — all packages pass. Note: `internal/api` tests may compare marshalled paipu JSON; if any fail on the new version stamp, fix the fixture expectation, never the schema.

```bash
git add internal/engine/paipu.go internal/engine/paipu_v2_test.go
git commit -m "feat(engine): paipu v2 schema — Decisions supervision trace + match metadata

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: `internal/rl` — pinned action-catalog version + drift golden test

**Files:**
- Modify: `internal/rl/action.go`
- Test: `internal/rl/action_catalog_test.go` (create)

**Interfaces:**
- Produces: `rl.ActionCatalogVersion` (const int = 1). Later tasks stamp it into the paipu header.

- [ ] **Step 1: Write the failing test**

```go
package rl

import "testing"

// TestActionCatalogPinned freezes every constant of the action-ID catalog.
// Paipu v2 stores raw catalog IDs (chosenId/legalIds) pinned to
// ActionCatalogVersion; ANY change to these values silently re-labels
// historical decisions. If this test fails you MUST bump
// ActionCatalogVersion and add a translation note — never just update the
// expected numbers.
func TestActionCatalogPinned(t *testing.T) {
	if ActionCatalogVersion != 1 {
		t.Fatalf("ActionCatalogVersion = %d; version bumps require a migration note", ActionCatalogVersion)
	}
	pins := map[string][2]int{
		"ActionPass":         {ActionPass, 0},
		"ActionTsumo":        {ActionTsumo, 1},
		"ActionRon":          {ActionRon, 2},
		"ActionAcceptHaitei": {ActionAcceptHaitei, 3},
		"ActionRefuseHaitei": {ActionRefuseHaitei, 4},
		"DiscardBase":        {DiscardBase, 5},
		"DiscardCount":       {DiscardCount, 42},
		"PonBase":            {PonBase, 47},
		"PonCount":           {PonCount, 34},
		"KanDirectBase":      {KanDirectBase, 81},
		"KanClosedBase":      {KanClosedBase, 115},
		"KanUpgradedBase":    {KanUpgradedBase, 149},
		"ChiiBase":           {ChiiBase, 183},
		"ChiiCount":          {ChiiCount, 21},
		"ActionSpaceSize":    {ActionSpaceSize, 204},
	}
	for name, v := range pins {
		if v[0] != v[1] {
			t.Errorf("%s = %d, pinned %d (catalog drift without version bump)", name, v[0], v[1])
		}
	}
}
```

- [ ] **Step 2: Run to verify it fails**

Run: `go test ./internal/rl/ -run TestActionCatalogPinned -v`
Expected: FAIL — `undefined: ActionCatalogVersion`.

- [ ] **Step 3: Implement**

In `internal/rl/action.go`, directly above the existing `const ( ActionPass = 0 ...` block:

```go
// ActionCatalogVersion pins the action-ID ↔ meaning mapping below. Paipu v2
// records raw catalog IDs (PaipuDecision.ChosenID/LegalIDs) stamped with
// this version; bump it on ANY change to the constants below or to
// EncodeAction/DecodeActionID semantics, and record the old→new translation
// in docs. Guarded by TestActionCatalogPinned.
const ActionCatalogVersion = 1
```

- [ ] **Step 4: Run to verify it passes**

Run: `go test ./internal/rl/ -run TestActionCatalogPinned -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add internal/rl/action.go internal/rl/action_catalog_test.go
git commit -m "feat(rl): pin action catalog version 1 with drift golden test

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: `internal/bot` + `internal/bot/remote` — provenance-carrying decisions

**Files:**
- Modify: `internal/bot/context.go` (add `DecisionProvenance`, `ProvenanceContextPolicy`)
- Modify: `internal/bot/remote/http_policy.go` (thread provenance through `chooseRemoteCtx`/`doAct`; decode `checkpoint_sha256`)
- Modify: `internal/bot/shadow.go` (forward primary's provenance)
- Test: `internal/bot/remote/http_policy_provenance_test.go` (create), extend `internal/bot/shadow_test.go`

**Interfaces:**
- Consumes: nothing from Tasks 1-2.
- Produces (Task 5 relies on these exact shapes):

```go
// internal/bot/context.go
type DecisionProvenance struct {
	Source         string // "remote" | "fallback" | "heuristic"
	FallbackReason string // set only when Source == "fallback"
	CheckpointName string // set only when Source == "remote"
	CheckpointStep int64
	CheckpointSha  string // may be empty (legacy server)
}

// ProvenanceContextPolicy is the additive capability: same decision flow as
// ChooseActionCtx but the provenance of THIS decision travels back with the
// action (never via mutable policy state).
type ProvenanceContextPolicy interface {
	ContextPolicy
	ChooseActionCtxProv(ctx *DecisionContext) (*pb.PlayerAction, DecisionProvenance)
}
```

- [ ] **Step 1: Write the failing tests**

`internal/bot/remote/http_policy_provenance_test.go`. Follow the existing test-server pattern in `internal/bot/remote/http_policy_test.go` (an `httptest.Server` returning a canned `/act` JSON body over a legal game state built by that file's helpers — reuse its state-builder helper; read that file first and copy its setup verbatim). Three cases:

```go
// Case 1: remote success → Source "remote", checkpoint name/step/sha from the
// /act body. Server returns:
//   {"action_id": <legal id>, "checkpoint_path": "/models/ck.pt",
//    "checkpoint_step": 75, "checkpoint_sha256": "ff00"}
// Assert: action non-nil; prov.Source == "remote";
// prov.CheckpointName == "ck.pt" (base name only — reuse checkpointIdentity's
// path.Base convention, NOT the full path); prov.CheckpointStep == 75;
// prov.CheckpointSha == "ff00".

// Case 2: server 500 → fallback fires. Assert: action non-nil (heuristic),
// prov.Source == "fallback", prov.FallbackReason == FallbackReasonStatus,
// prov.CheckpointName == "".

// Case 3: sha absent from body (legacy server) → prov.Source == "remote",
// prov.CheckpointSha == "".
```

Shadow test (extend `internal/bot/shadow_test.go`): wrap a stub primary implementing `bot.ProvenanceContextPolicy` (returns a fixed action + `DecisionProvenance{Source: "remote", CheckpointSha: "aa"}`) in `NewShadowPolicy(primary, shadowStub, 1)`; call `ChooseActionCtxProv` on the ShadowPolicy; assert the returned provenance equals the primary's exactly, and the returned action is the primary's. Also: a primary that is a plain `Policy` (no provenance) → ShadowPolicy's `ChooseActionCtxProv` returns `DecisionProvenance{Source: "heuristic"}`.

- [ ] **Step 2: Run to verify they fail**

Run: `go test ./internal/bot/... -run 'Provenance' -v`
Expected: FAIL — `undefined: bot.DecisionProvenance` / method not found.

- [ ] **Step 3: Implement**

1. `internal/bot/context.go`: add the two types shown in **Interfaces** verbatim (with doc comments).
2. `internal/bot/remote/http_policy.go`:
   - `actResponse` gains `CheckpointSha256 string \`json:"checkpoint_sha256,omitempty"\``.
   - Add a small internal type and thread it through:

```go
// remoteProvenance carries the serving checkpoint of ONE /act decision back
// up the call chain (never stored on the policy — a hot reload between two
// decisions must not cross-attribute).
type remoteProvenance struct {
	name string
	step int64
	sha  string
}
```

   - Change `doAct` to return `(*pb.PlayerAction, remoteProvenance, error)`: populate from `response.CheckpointPath` (via `path.Base` — same convention as `checkpointIdentity`), `response.CheckpointStep`, `response.CheckpointSha256` at the SAME point the existing `recordObservedPolicyID` call happens (line ~349, i.e. only after action validation). Keep `recordObservedPolicyID` as-is (aggregate label compat).
   - Change `chooseRemote` and `chooseRemoteCtx` to return `(*pb.PlayerAction, remoteProvenance, error)` (pass-through).
   - Add the capability method, and refactor `ChooseActionCtx` to delegate so the fallback/counter logic exists exactly once:

```go
// ChooseActionCtxProv implements bot.ProvenanceContextPolicy: identical
// decision flow to ChooseActionCtx, with this decision's provenance
// returned alongside the action.
func (p *HTTPPolicy) ChooseActionCtxProv(decisionCtx *bot.DecisionContext) (*pb.PlayerAction, bot.DecisionProvenance) {
	// (body: current ChooseActionCtx logic; on remote success return
	//  DecisionProvenance{Source: "remote", CheckpointName: prov.name,
	//  CheckpointStep: prov.step, CheckpointSha: prov.sha};
	//  on fallback return DecisionProvenance{Source: "fallback",
	//  FallbackReason: reason} with the heuristic's action;
	//  when p.fallback == nil and remote failed, return (nil, that same
	//  fallback provenance) — caller treats nil action as today.)
}

func (p *HTTPPolicy) ChooseActionCtx(decisionCtx *bot.DecisionContext) *pb.PlayerAction {
	action, _ := p.ChooseActionCtxProv(decisionCtx)
	return action
}
```

   - `ChooseAction` (legacy, non-ctx path): update its internal calls for the new `chooseRemote` signature, discard the provenance. Add `var _ bot.ProvenanceContextPolicy = (*HTTPPolicy)(nil)`.
3. `internal/bot/shadow.go`: add

```go
var _ ProvenanceContextPolicy = (*ShadowPolicy)(nil)

// ChooseActionCtxProv forwards to the primary's provenance-capable path when
// it has one (remote.HTTPPolicy), still mirroring the decision to the shadow
// exactly like ChooseActionCtx. A non-provenance primary is by construction
// a local policy: label it "heuristic".
func (s *ShadowPolicy) ChooseActionCtxProv(ctx *DecisionContext) (*pb.PlayerAction, DecisionProvenance) {
	// (body mirrors ChooseActionCtx at line ~206: call primary — via
	//  ProvenanceContextPolicy if implemented, else ContextPolicy/Policy —
	//  then s.enqueueShadow(ctx, primaryAction) exactly as ChooseActionCtx
	//  does, then return.)
}
```

   Read `ChooseActionCtx` (shadow.go:206) first and keep the enqueue behavior identical — the shadow mirror must fire for provenance calls too.

- [ ] **Step 4: Run to verify green**

Run: `go test ./internal/bot/... -v 2>&1 | tail -15` → PASS, including all pre-existing shadow/http_policy tests (the refactor must not change `ChooseActionCtx` observable behavior).

- [ ] **Step 5: Commit**

```bash
git add internal/bot/context.go internal/bot/remote/http_policy.go internal/bot/shadow.go internal/bot/remote/http_policy_provenance_test.go internal/bot/shadow_test.go
git commit -m "feat(bot): provenance-carrying decisions — per-/act checkpoint sha, fallback reason via return values

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Python — `checkpoint_sha256` in the `/act` response

**Files:**
- Modify: `ai/src/fh_mahjong_ai/scripts/serve_policy.py` (the `/act` response dict, line ~522-526)
- Test: extend the existing serve_policy tests (find them: `grep -rn "action_id" ai/tests | head`)

**Interfaces:**
- Consumes: the handler-scoped `snapshot` (`_PolicySnapshot`) already captured once per request (line ~583) — `snapshot.checkpoint_sha256` is the attested hash of the exact bytes serving this request.
- Produces: `/act` JSON gains `"checkpoint_sha256": <hex str>`. Go already decodes it (Task 3).

- [ ] **Step 1: Write the failing test**

Locate the existing `/act` handler test (the one asserting `checkpoint_path`/`checkpoint_step` in the response — `grep -rn "checkpoint_step" ai/tests/`). Add, in the same style:

```python
def test_act_response_includes_checkpoint_sha256(<same fixtures as the neighboring /act test>):
    # POST a valid /act request exactly as the neighboring test does.
    payload = <response json>
    assert payload["checkpoint_sha256"] == <the server's snapshot sha —
        the fixture knows the checkpoint file; compute hashlib.sha256 of its
        bytes, or reuse the fixture's existing expected-sha helper if one exists>
    assert payload["checkpoint_sha256"] == <same value as GET /healthz reports>
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run --project ai pytest ai/tests -k "checkpoint_sha256 and act" -q`
Expected: FAIL — KeyError `checkpoint_sha256`.

- [ ] **Step 3: Implement**

In the `/act` response construction (line ~522), add one line, sourcing from the request-scoped snapshot (NOT a re-read of global state — the atomicity point of the ratified design):

```python
"checkpoint_sha256": snapshot.checkpoint_sha256,
```

Verify by reading the handler that `action.checkpoint_path`/`action.checkpoint_step` and `snapshot` come from the same snapshot capture (the comment at line ~583 says exactly this); if `action` is produced from `snapshot.policy` the pairing is already atomic.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run --project ai pytest ai/tests -q 2>&1 | tail -5` → all pass.

Also check the parity tool tolerates the new field: `grep -n "checkpoint_sha256\|json" ai/src/fh_mahjong_ai/scripts/serving_smoke.py | head` and the `fh-mj-serving-parity` source — they parse named keys, so an additive key is inert; confirm no strict-schema validation rejects unknown keys (if one does, allowlist the field).

- [ ] **Step 5: Commit**

```bash
git add ai/src/fh_mahjong_ai/scripts/serve_policy.py ai/tests/<modified test file>
git commit -m "feat(serving): /act response carries checkpoint_sha256 atomically

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Room layer — capture the decision trace

**Files:**
- Create: `internal/api/room_decisions.go`
- Modify: `internal/api/room.go` (`dispatchClientAction`), `internal/api/room_bot.go` (both decision sites)
- Test: `internal/api/room_decisions_test.go` (create)

**Interfaces:**
- Consumes: `engine.PaipuDecision`/`PaipuCheckpoint`/`RecordDecision` (Task 1); `bot.ProvenanceContextPolicy`/`DecisionProvenance` (Task 3); `rl.LegalActions(state, seat) (map[int]*pb.PlayerAction, error)` and `rl.EncodeAction(state, seat, action) (int, bool)` (existing, `internal/rl/action.go:317,322`).
- Produces: every successfully processed gameplay action lands one `PaipuDecision` row. Task 6/7 consume the recorded shape.

**Capture rules (from the spec — implement exactly):**
- Record: discard, all claims (chii/pon/kans), tsumo/ron, haitei accept/refuse, flower reveal, and PASS (`ACTION_PASS`).
- Exclude: `ACTION_READY` (round-end flow control, not a game decision), automatic draws/auto-flower (never reach these call sites), and interrupt seats resolved by `Engine.ResolveInterrupts()` timeout (no explicit action → no decision was made).
- Legal set + chosen ID are computed on the PRE-action state; the row is recorded only after `ProcessPlayerAction` returns nil.
- Legal-set or encode failure must never block play: record with `LegalIDs: nil, LegalIDsError: true` (and `ChosenID: -1` if `EncodeAction` returned ok=false) and log once.

- [ ] **Step 1: Write the failing test**

`internal/api/room_decisions_test.go`. Build a `Room` the way existing room tests do (read `internal/api/room_test.go` / the bot-tick tests for the constructor + engine setup helpers; use `botActionDelay: 0`, a nil DB, and `engine.NewGame` with a `PaipuRecorder` attached). Drive a deterministic opening:

```go
// TestDecisionTraceRecordsBotPlay: room with 4 automated heuristic seats,
// advanceAutomatedSeats() until PHASE_ROUND_END or 200 iterations.
// Assert on recorder.CurrentRound()/Snapshot():
//   - len(Decisions) > 0
//   - every row: Source == "heuristic"; LegalIDs non-empty (no LegalIDsError);
//     ChosenID ∈ LegalIDs
//   - indices are 0..n-1 in order
//   - no row has Seat >= 4; no row with the engine's ACTION_READY phase
// TestDecisionTraceRecordsHumanAction: seat 0 "human" (bind a fake client the
// way existing tests do), submit its legal discard via dispatchClientAction;
// assert the recorded row has Source == "human" and the discard's catalog id.
// TestDecisionTraceRecordsExplicitPass: drive to a WAIT_DISCARDS state where
// an automated seat has ValidActions (reuse/adapt the existing interrupt-path
// test fixture in room_bot / engine tests); after the bot pass, assert a row
// with ChosenID == 0 (rl.ActionPass), Source "heuristic", LegalIDs containing
// both 0 and the claim id.
// TestDecisionTraceRemoteProvenance: SeatPolicies[seat] = a stub implementing
// bot.ProvenanceContextPolicy returning a legal action +
// DecisionProvenance{Source:"remote", CheckpointName:"ck.pt",
// CheckpointStep: 9, CheckpointSha:"aa"}; after one bot step assert the row
// carries Checkpoint{Name:"ck.pt",Step:9,Sha256:"aa"}.
// TestDecisionTraceFallbackReason: stub returns provenance
// {Source:"fallback", FallbackReason:"status"}; assert row's
// FallbackReason == "status" and Checkpoint == nil.
```

Write these as real Go — copy the exact room/engine construction from the nearest existing test and keep each test focused on the assertions above.

- [ ] **Step 2: Run to verify they fail**

Run: `go test ./internal/api/ -run TestDecisionTrace -v`
Expected: FAIL — no `Decisions` rows recorded (helpers don't exist yet).

- [ ] **Step 3: Implement `internal/api/room_decisions.go`**

```go
package api

import (
	"log"

	"github.com/plasma/fh-mahjong/internal/bot"
	"github.com/plasma/fh-mahjong/internal/engine"
	"github.com/plasma/fh-mahjong/internal/rl"
	pb "github.com/plasma/fh-mahjong/proto"
)

// This file captures the paipu v2 supervision trace (spec:
// worklog/specs/2026-08-09-paipu-v2-provenance-design.md §2-3).
// The room layer is the single choke point where every explicit decision
// passes AND provenance is known; the engine stays provenance-blind.

// decisionSnapshot holds the pre-action context of one decision: the legal
// catalog IDs and the chosen action's catalog id, both computed against the
// PRE-action state (encoding after mutation would be wrong).
type decisionSnapshot struct {
	legalIDs  []int
	chosenID  int
	snapErr   bool // legal-set enumeration failed (never blocks play)
}

// snapshotDecision computes the legal-set + chosen-id context for seat's
// pending action. Call BEFORE Engine.ProcessPlayerAction.
func (r *Room) snapshotDecision(seat uint32, action *pb.PlayerAction) decisionSnapshot {
	snap := decisionSnapshot{chosenID: -1}
	legal, err := rl.LegalActions(r.Engine.State, seat)
	if err != nil {
		log.Printf("paipu decision snapshot: legal-set enumeration failed for seat %d in room %s: %v", seat, r.ID, err)
		snap.snapErr = true
	} else {
		snap.legalIDs = make([]int, 0, len(legal))
		for id := range legal {
			snap.legalIDs = append(snap.legalIDs, id)
		}
		sort.Ints(snap.legalIDs)
	}
	if id, ok := rl.EncodeAction(r.Engine.State, seat, action); ok {
		snap.chosenID = id
	} else {
		log.Printf("paipu decision snapshot: EncodeAction failed for seat %d action %v in room %s", seat, action.Type, r.ID)
		snap.snapErr = true
	}
	return snap
}

// recordDecision appends the supervision-trace row for a decision that has
// just been SUCCESSFULLY processed. prov describes who produced the action.
func (r *Room) recordDecision(seat uint32, snap decisionSnapshot, prov bot.DecisionProvenance) {
	if r.Engine.Recorder == nil {
		return
	}
	d := engine.PaipuDecision{
		Seat:           seat,
		ChosenID:       snap.chosenID,
		LegalIDs:       snap.legalIDs,
		LegalIDsError:  snap.snapErr,
		Source:         prov.Source,
		FallbackReason: prov.FallbackReason,
	}
	if prov.Source == "remote" {
		d.Checkpoint = &engine.PaipuCheckpoint{
			Name:   prov.CheckpointName,
			Step:   prov.CheckpointStep,
			Sha256: prov.CheckpointSha,
		}
	}
	r.Engine.Recorder.RecordDecision(d)
}

// humanProvenance / heuristicProvenance are the fixed labels for
// non-remote decision sources.
func humanProvenance() bot.DecisionProvenance     { return bot.DecisionProvenance{Source: "human"} }
func heuristicProvenance() bot.DecisionProvenance { return bot.DecisionProvenance{Source: "heuristic"} }
```

(add the `sort` import.)

**Wire `dispatchClientAction`** (`room.go:637`): before the `ProcessPlayerAction` call at line 655 insert:

```go
	var snap decisionSnapshot
	traced := clientAction.Action.Type != pb.ActionType_ACTION_READY
	if traced && r.Engine.Recorder != nil {
		snap = r.snapshotDecision(originSeat, clientAction.Action)
	}
```

and after the successful-processing point (immediately after the `err != nil { ... return }` block):

```go
	if traced && r.Engine.Recorder != nil {
		r.recordDecision(originSeat, snap, humanProvenance())
	}
```

**Wire `room_bot.go`** — both decision sites. Replace the policy-invocation pattern at lines 42-60 (PLAYER_TURN) and 73-92 (WAIT_DISCARDS) so that provenance-capable policies are asked via the capability:

```go
			policy := r.policyForSeat(seat)
			var action *pb.PlayerAction
			prov := heuristicProvenance()
			if provPolicy, ok := policy.(bot.ProvenanceContextPolicy); ok {
				action, prov = provPolicy.ChooseActionCtxProv(r.buildDecisionContext(seat))
			} else if ctxPolicy, ok := policy.(bot.ContextPolicy); ok {
				action = ctxPolicy.ChooseActionCtx(r.buildDecisionContext(seat))
			} else {
				action = policy.ChooseAction(r.Engine.State, seat)
			}
```

(`prov` is a plain `bot.DecisionProvenance` value, so the two-value assignment works directly.)

Then, per site:
- PLAYER_TURN: `snap := r.snapshotDecision(seat, action)` before `ProcessPlayerAction` (line 56); after success (before `r.automatedDecisions[seat]++`): `r.recordDecision(seat, snap, prov)`.
- WAIT_DISCARDS: same around line 86. The default-pass at line 81 (`action = &pb.PlayerAction{Type: pb.ActionType_ACTION_PASS}`) is still the policy's decision — record it with `prov` as computed. The error-recovery forced pass at line 89 (`_ = r.Engine.ProcessPlayerAction(seat, &pb.PlayerAction{Type: ACTION_PASS})`): snapshot+record it too (it is a successfully processed pass), with `prov` unchanged BUT `snap` recomputed for the pass action; only record if that forced pass's `ProcessPlayerAction` returned nil (change `_ =` to capture the error).
- ROUND_END READY block (line 109-127): NOT traced — leave untouched.

- [ ] **Step 4: Run to verify green**

Run: `go test ./internal/api/ -v -run TestDecisionTrace 2>&1 | tail -15` → PASS.
Then the whole tree: `go test ./... 2>&1 | tail -10` → PASS (RL env drives rooms through `internal/rl/env.go` — its games now also record decision rows when a recorder is attached; confirm no test asserts an exact paipu JSON that now differs, fix fixtures if so).

- [ ] **Step 5: Commit**

```bash
git add internal/api/room_decisions.go internal/api/room.go internal/api/room_bot.go internal/api/room_decisions_test.go
git commit -m "feat(api): record paipu v2 decision trace at the room choke point

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Match metadata at persist time + server build stamp

**Files:**
- Create: `internal/api/buildinfo.go`
- Modify: `internal/api/room.go` (`persistMatch`, `persistMatchPlayers`), `internal/api/matchmaker.go` (drain reason), `cmd/server/main.go` (ldflags var pass-through), `Dockerfile` (build arg)
- Test: `internal/api/room_meta_test.go` (create)

**Interfaces:**
- Consumes: `engine.PaipuMatchMeta`/`SetMatchMeta`/`PaipuChongciConfig` (Task 1), `rl.ActionCatalogVersion` (Task 2), `rl.EventContractV1` (existing).
- Produces: every persisted paipu carries the v2 header; `api.ServerCommit` variable settable via `-ldflags "-X github.com/plasma/fh-mahjong/internal/api.ServerCommit=<sha>"`.

- [ ] **Step 1: Write the failing test**

```go
// internal/api/room_meta_test.go
// TestPersistMatchStampsV2Meta: build a room (nil DB + PaipuStore capture
// func — the persistMatch in-memory path at room.go:414 hands the JSON to
// r.PaipuStore), with a chongci engine (MatchOptions{Mode: CHONGCI, default
// config}), drive one full bot hand to ROUND_END, then set State.Phase =
// PHASE_MATCH_END and call persistMatch(). Unmarshal the captured JSON into
// engine.Paipu and assert:
//   Status == "completed", CompletionReason == "match_end",
//   Placements != nil (competition ranking of finalScores),
//   MatchMode == "chongci", Chongci != nil with the engine's config values,
//   RulesetVersion == "fenghua-v1", EventContractVersion == rl.EventContractV1,
//   ActionCatalogVersion == rl.ActionCatalogVersion,
//   ProtoEnumsRevision == engine.ProtoEnumsRevision,
//   ServerCommit == "unknown" (test binary has no ldflags).
// TestPersistMatchAbortReason: same room but leave Phase mid-hand; call
// r.markDrained() then persistMatch(); assert Status == "aborted",
// CompletionReason == "drained". Without markDrained: "abandoned".
```

- [ ] **Step 2: Run to verify it fails**

Run: `go test ./internal/api/ -run TestPersistMatch -v` → FAIL (fields absent / helpers missing).

- [ ] **Step 3: Implement**

`internal/api/buildinfo.go`:

```go
package api

// ServerCommit is stamped at build time via
//   go build -ldflags "-X github.com/plasma/fh-mahjong/internal/api.ServerCommit=$(git rev-parse --short HEAD)"
// and recorded into every paipu (v2 provenance). "unknown" means the binary
// was built without the stamp (local `go run`, tests).
var ServerCommit = "unknown"
```

`internal/api/room.go`:
- Add field `drained bool` to the `Room` struct and `func (r *Room) markDrained() { r.drained = true }`; call `markDrained()` from the drain path — find it: `grep -n "DrainActiveRooms" internal/api/matchmaker.go` (line ~237) and follow to where each room's shutdown/persist is triggered; set the flag before persistence.
- In `persistMatch` (line ~365), before the `r.Engine.Recorder.Snapshot(finalScores)` call, compute and stamp the meta:

```go
	if r.Engine.Recorder != nil {
		r.reconcileRLPolicyIDs()
		status := "completed"
		reason := "match_end"
		if r.Engine.State.Phase != pb.GamePhase_PHASE_MATCH_END {
			status = "aborted"
			if r.drained {
				reason = "drained"
			} else {
				reason = "abandoned"
			}
		}
		placements := placementsFromScores(finalScores)
		meta := engine.PaipuMatchMeta{
			Status:               status,
			CompletionReason:     reason,
			Placements:           &placements,
			ServerCommit:         ServerCommit,
			MatchMode:            matchModeLabel(r.Engine.State.MatchMode),
			Chongci:              paipuChongciConfig(r.Engine.State.ChongciConfig),
			RulesetVersion:       "fenghua-v1",
			EventContractVersion: rl.EventContractV1,
			ProtoEnumsRevision:   engine.ProtoEnumsRevision,
			ActionCatalogVersion: rl.ActionCatalogVersion,
		}
		r.Engine.Recorder.SetMatchMeta(meta)
		paipu = r.Engine.Recorder.Snapshot(finalScores)
		...
	}
```

  (Check the actual field names on `pb.GameState` for match mode + chongci config — `grep -n "MatchMode\|ChongciConfig" proto/game.pb.go | head` — and write `matchModeLabel` ("classic"/"chongci") + `paipuChongciConfig` (nil-safe pb→Paipu mapping) as small helpers in room_decisions.go or room.go.)
- The existing `status` computation at line 392 must be UNIFIED with this one (single source): compute status/reason once, use for both the meta and the DB row.
- **DRY the placement rule**: extract the per-seat competition-ranking loop in `persistMatchPlayers` (lines 483-488) into `func placementsFromScores(finalScores [4]int32) [4]uint` and use it in both places (a seat-index-preserving array; `persistMatchPlayers` indexes it by `p.Seat`).

`cmd/server/main.go` + `Dockerfile`: no Go change needed in main (the var lives in `internal/api`). In the backend `Dockerfile`, locate the `go build` line (`grep -n "go build" Dockerfile`) and add:

```dockerfile
ARG GIT_COMMIT=unknown
RUN go build -ldflags "-X github.com/plasma/fh-mahjong/internal/api.ServerCommit=${GIT_COMMIT}" -o /server ./cmd/server
```

(match the existing build line's flags/output path exactly; only add the `-ldflags`. Zeabur builds without the arg → "unknown"; that is acceptable for now and noted in the AGENTS.md update, Task 8.)

- [ ] **Step 4: Run to verify green**

Run: `go test ./internal/api/ -run TestPersistMatch -v` → PASS; then `go test ./... 2>&1 | tail -5` → PASS. Also `go vet ./...`.

- [ ] **Step 5: Commit**

```bash
git add internal/api/buildinfo.go internal/api/room.go internal/api/matchmaker.go internal/api/room_meta_test.go Dockerfile
git commit -m "feat(api): stamp paipu v2 match metadata + server commit at persist time

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: v2 replay cross-check in `internal/review`

**Files:**
- Modify: `internal/review/replay.go`
- Test: `internal/review/replay_v2_test.go` (create)

**Interfaces:**
- Consumes: `engine.PaipuDecision` rows (Task 1); the replay driver's existing reconstruction loop (read `internal/review/replay.go` FIRST — it re-runs the engine over the paipu; `rl.LegalActions` is already called at lines ~212/272/292/457 and implicit passes are inferred at lines ~288-305).
- Produces: replaying a v2 paipu additionally verifies the decision trace; any mismatch returns a loud error naming round, decision index, and the mismatch kind.

**Cross-check rules (spec §8):**
- For each round, walk `Decisions` alongside the reconstruction. At each reconstructed decision point for seat S, the next unconsumed `Decisions` row for the corresponding decision must satisfy: (a) `row.ChosenID` is legal in the reconstructed legal set; (b) `row.LegalIDs` (when `LegalIDsError` is false) equals the reconstructed legal ID set exactly (sorted compare).
- Rows with `LegalIDsError: true`: check only (a).
- v1 paipus (`Decisions == nil`): skip the cross-check entirely — behavior byte-identical to today.
- On mismatch: `fmt.Errorf("paipu v2 decision cross-check failed: round %d decision %d seat %d: %s", ...)` — propagate, never warn-and-continue.
- IMPORTANT alignment note: the trace contains rows for decisions that do NOT appear in the Actions stream (explicit passes). The reconstruction already infers pass points (lines ~288-305) — attach the cross-check where the replayer processes each explicit action AND each inferred pass, consuming trace rows in order and matching on seat. Timeout-resolved seats have NO trace row (spec: not decisions) — the cross-check must tolerate reconstructed pass-points that have no matching trace row for v2 paipus ONLY when the row's seat doesn't match; do not consume a row for them. Simplest robust rule: maintain a cursor into `Decisions`; at each reconstructed decision point where the next row's `(seat)` matches, verify + consume; otherwise skip the point (it was an untraced auto-resolution). At round end, error if unconsumed rows remain.

- [ ] **Step 1: Write the failing test**

```go
// internal/review/replay_v2_test.go
// Build a real match the same way review's existing tests build one (find
// the fixture helper: grep -n "func Test" internal/review/replay_test.go |
// head — reuse its game-driving helper), but attach a PaipuRecorder AND
// record decision rows by driving through internal/api's room bot loop is
// NOT available here (import cycle) — instead craft the paipu:
//   1. Drive a scripted engine game exactly as the existing replay tests do,
//      recording the paipu.
//   2. For each explicit action in the recorded rounds, append the matching
//      correct PaipuDecision row (compute legal set + chosen id with
//      rl.LegalActions/rl.EncodeAction while re-driving a parallel engine —
//      mirror of what Task 5 does at the room layer).
// TestReplayV2CrossCheckPasses: replay succeeds on the well-formed v2 paipu.
// TestReplayV2CrossCheckCatchesTamperedChosenID: corrupt one row's ChosenID
// to an id NOT in its legal set → replay returns error containing
// "decision cross-check failed".
// TestReplayV2CrossCheckCatchesWrongLegalSet: corrupt one row's LegalIDs
// (drop an element) → same loud error.
// TestReplayV1Unchanged: strip Decisions (nil) → replay succeeds exactly as
// before (reuse an existing v1 fixture test as the template).
```

- [ ] **Step 2: Run to verify it fails**

Run: `go test ./internal/review/ -run TestReplayV2 -v` → FAIL (no cross-check exists; tampered fixtures replay without error).

- [ ] **Step 3: Implement**

In `internal/review/replay.go`, add the cursor-based cross-check exactly per the rules above, invoked wherever the reconstruction processes a decision point (explicit action or inferred pass). Keep it in a dedicated helper (`func (r *replayer) crossCheckDecision(seat uint32, legal map[int]*pb.PlayerAction, chosen *pb.PlayerAction) error` or the closest fit to the file's existing structure — READ the file first and follow its naming). Round-end: verify cursor consumed all rows.

- [ ] **Step 4: Run to verify green**

Run: `go test ./internal/review/ -v 2>&1 | tail -10` → PASS (new + all existing).

- [ ] **Step 5: Commit**

```bash
git add internal/review/replay.go internal/review/replay_v2_test.go
git commit -m "feat(review): fail-loud v2 decision-trace cross-check during replay

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: Docs, gates, and finish

**Files:**
- Modify: `internal/engine/AGENTS.md`, `internal/api/AGENTS.md`, `internal/bot/AGENTS.md`, `internal/review/AGENTS.md`, `ai/AGENTS.md` (whichever of these exist and describe the touched behavior — check each)
- Modify: `worklog/specs/2026-08-09-paipu-v2-provenance-design.md` (mark shipped status if desired — optional)

- [ ] **Step 1: AGENTS.md updates**

For each touched package's AGENTS.md, add/refresh the paipu-v2 facts: the Decisions trace shape + capture rules (api), the schema + version constants (engine), the provenance capability + atomic-sha rule (bot), the cross-check (review), the `/act` sha field (ai). Also record the **trusted-read-path rule** (spec §9) in `internal/api/AGENTS.md`: training extraction must read `matches.paipu_json` only — never the `handleUploadPaipu` in-memory/`paipu_records` chain.

- [ ] **Step 2: Full gates**

```bash
go vet ./... && go test ./... 2>&1 | tail -5
uv run --project ai pytest -q 2>&1 | tail -3
cd web && npx tsc --noEmit 2>&1 | tail -3 && cd ..   # only if any web file was touched (should be none)
```

All green.

- [ ] **Step 3: Commit docs**

```bash
git add -A
git commit -m "docs: AGENTS.md updates for paipu v2 provenance

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

- [ ] **Step 4: Final review + PR**

Run the repo's review gate on the whole branch diff vs main (per current project practice), fix findings, then:

```bash
git push -u origin feat/paipu-v2-provenance
gh pr create --title "feat: paipu v2 — per-decision provenance + supervision trace" --body "<summary: spec link, ratified design points, test evidence>

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
gh pr merge <N> --merge
```

(Merge only after CI is green. `--merge`, never squash/rebase.)

---

## Post-merge (NOT part of this plan's tasks — tracked separately)

Deploy backend + policy services, then run the production smoke from the spec's Rollout gate section (one RL-seat match → fetch paipu → verify pass rows, legal sets, remote sha, status). Only then does the Champion Promotion shadow phase resume.
