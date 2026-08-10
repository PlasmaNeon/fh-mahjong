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
