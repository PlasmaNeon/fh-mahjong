package engine

import (
	"encoding/json"
	"strings"
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
	// Raw-bytes guard: a future omitempty on ChosenID would silently drop
	// pass (id 0) rows from the JSON without the struct round-trip below
	// ever noticing (Go would just decode the missing field back to its
	// zero value).
	if !strings.Contains(string(blob), "\"chosenId\":0") {
		t.Fatalf("marshaled paipu missing chosenId:0, got: %s", blob)
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

// TestPaipuRecordDecisionAfterEndRound pins the terminal-decision route: the
// room layer records a decision immediately AFTER the engine accepted it, so a
// round-terminating action (winning tsumo/ron, haitei acceptance, the
// exhaustive-draw discard) is recorded when the engine has already closed the
// round. That row must land on the just-closed round, not be dropped.
func TestPaipuRecordDecisionAfterEndRound(t *testing.T) {
	r := NewPaipuRecorder("m1", "fenghua")
	r.StartRound(1, 0, 0, [2]uint32{1, 2}, "seed", nil, 16, [4]int32{}, [4][]uint32{})
	r.RecordDecision(PaipuDecision{Seat: 0, ChosenID: 7, LegalIDs: []int{7, 9}, Source: "heuristic"})
	r.EndRound(&PaipuRoundResult{Type: "win", ScoreChanges: []int32{0, 0, 0, 0}})

	// The terminal row arrives after the round is closed.
	r.RecordDecision(PaipuDecision{Seat: 2, ChosenID: 200, LegalIDs: []int{200, 0}, Source: "human"})

	p := r.Finalize([4]int32{})
	if len(p.Rounds) != 1 {
		t.Fatalf("rounds = %d, want 1 (post-EndRound row must not open a new round)", len(p.Rounds))
	}
	decs := p.Rounds[0].Decisions
	if len(decs) != 2 {
		t.Fatalf("closed round has %d decisions, want 2 (terminal row was dropped)", len(decs))
	}
	if decs[1].Index != 1 {
		t.Fatalf("terminal row Index = %d, want 1", decs[1].Index)
	}
	if decs[1].Seat != 2 || decs[1].ChosenID != 200 {
		t.Fatalf("terminal row = %+v, want seat 2 / chosen 200", decs[1])
	}

	// A second round's rows still go to the new current round.
	r.StartRound(2, 0, 1, [2]uint32{3, 4}, "seed2", nil, 16, [4]int32{}, [4][]uint32{})
	r.RecordDecision(PaipuDecision{Seat: 1, ChosenID: 3, LegalIDs: []int{3}, Source: "heuristic"})
	if got := len(r.CurrentRound().Decisions); got != 1 {
		t.Fatalf("new round has %d decisions, want 1", got)
	}
	if idx := r.CurrentRound().Decisions[0].Index; idx != 0 {
		t.Fatalf("new round's first row Index = %d, want 0", idx)
	}
	if got := len(p.Rounds[0].Decisions); got != 2 {
		t.Fatalf("closed round grew to %d decisions after a new round started", got)
	}
}

// TestPaipuRecordDecisionWithNoRoundsIsNoOp: before any round exists there is
// nowhere for a row to belong, so RecordDecision stays a no-op.
func TestPaipuRecordDecisionWithNoRoundsIsNoOp(t *testing.T) {
	r := NewPaipuRecorder("m1", "fenghua")
	r.RecordDecision(PaipuDecision{Seat: 0, ChosenID: 7, LegalIDs: []int{7}, Source: "heuristic"})
	p := r.Finalize([4]int32{})
	if len(p.Rounds) != 0 {
		t.Fatalf("rounds = %d, want 0", len(p.Rounds))
	}
	if r.CurrentRound() != nil {
		t.Fatalf("current round = %+v, want nil", r.CurrentRound())
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
