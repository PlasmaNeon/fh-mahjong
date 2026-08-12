package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/plasma/fh-mahjong/internal/engine"
)

func paipuServer(t *testing.T, p *engine.Paipu) *httptest.Server {
	t.Helper()
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !strings.HasPrefix(r.URL.Path, "/api/v1/replays/") {
			http.NotFound(w, r)
			return
		}
		json.NewEncoder(w).Encode(p)
	}))
}

func gatePassingPaipu() *engine.Paipu {
	ckpt := &engine.PaipuCheckpoint{Name: "champ.pt", Sha256: "377d99bc7e5d"}
	return &engine.Paipu{
		Version: engine.PaipuVersion,
		MatchID: "m1",
		Status:  "completed",
		Rounds: []engine.PaipuRound{{
			Round: 1,
			Decisions: []engine.PaipuDecision{
				{Index: 0, Seat: 0, ChosenID: 7, LegalIDs: []int{0, 7}, Source: "human"},
				{Index: 1, Seat: 1, ChosenID: 3, LegalIDs: []int{0, 3}, Source: "remote", Checkpoint: ckpt},
				{Index: 2, Seat: 2, ChosenID: 0, LegalIDs: []int{0, 4}, Source: "remote", Checkpoint: ckpt},
			},
		}},
	}
}

func TestVerifyPaipuPassesOnCompleteV2Trace(t *testing.T) {
	srv := paipuServer(t, gatePassingPaipu())
	defer srv.Close()
	report, err := verifyPaipu(srv.Client(), srv.URL, "m1")
	if err != nil {
		t.Fatalf("verifyPaipu: %v", err)
	}
	for _, want := range []string{"decisions=3", "remote=2", "pass=1", "377d99bc7e5d"} {
		if !strings.Contains(report, want) {
			t.Fatalf("report %q missing %q", report, want)
		}
	}
}

func TestVerifyPaipuFailsEachGate(t *testing.T) {
	cases := []struct {
		name    string
		mutate  func(p *engine.Paipu)
		wantErr string
	}{
		{"v1 schema", func(p *engine.Paipu) { p.Version = 1 }, "version"},
		{"aborted match", func(p *engine.Paipu) { p.Status = "aborted" }, "status"},
		{"no decisions", func(p *engine.Paipu) { p.Rounds[0].Decisions = nil }, "no decision rows"},
		{"remote sha missing", func(p *engine.Paipu) {
			p.Rounds[0].Decisions[1].Checkpoint = nil
		}, "lack a checkpoint sha256"},
		{"no pass rows", func(p *engine.Paipu) {
			p.Rounds[0].Decisions[2].ChosenID = 4
		}, "no explicit pass rows"},
		{"chosen not legal", func(p *engine.Paipu) {
			p.Rounds[0].Decisions[0].ChosenID = 99
		}, "not in legalIds"},
		{"legal snapshot error", func(p *engine.Paipu) {
			p.Rounds[0].Decisions[0].LegalIDsError = true
			p.Rounds[0].Decisions[0].LegalIDs = nil
		}, "legalIdsError"},
		{"no human rows", func(p *engine.Paipu) {
			p.Rounds[0].Decisions[0].Source = "heuristic"
		}, "no human decision rows"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			p := gatePassingPaipu()
			tc.mutate(p)
			srv := paipuServer(t, p)
			defer srv.Close()
			if _, err := verifyPaipu(srv.Client(), srv.URL, "m1"); err == nil || !strings.Contains(err.Error(), tc.wantErr) {
				t.Fatalf("want error containing %q, got %v", tc.wantErr, err)
			}
		})
	}
}
