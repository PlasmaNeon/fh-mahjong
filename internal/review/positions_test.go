package review

import (
	"math"
	"testing"

	"github.com/plasma/fh-mahjong/internal/engine"
	"github.com/plasma/fh-mahjong/internal/rl"
	pb "github.com/plasma/fh-mahjong/proto"
)

func TestReviewPositionsAndChoiceTruth(t *testing.T) {
	p := generateHeuristicPaipuV2(t, 17, engine.MatchOptions{})
	ds, err := extractDecisions(p, 0, true)
	if err != nil {
		t.Fatal(err)
	}
	for _, d := range ds {
		if d.Branch == nil {
			t.Fatal("missing pre-choice snapshot")
		}
		if d.Branch.State.Phase == pb.GamePhase_PHASE_PLAYER_TURN {
			if d.PositionIndex != d.ActionIndex-1 {
				t.Fatalf("turn position %+v", d)
			}
			if d.ActualTileID != nil {
				found := false
				for _, tile := range d.Branch.State.Players[d.Seat].ClosedHand {
					if int(tile.Id) == *d.ActualTileID {
						found = true
					}
				}
				if !found {
					t.Fatal("actual discard already left the hand")
				}
			}
		} else {
			if d.Branch.State.ActiveDiscard == nil {
				t.Fatal("response missing triggering tile")
			}
			if d.PositionIndex > d.ActionIndex {
				t.Fatal("response anchored in the future")
			}
		}
		if d.ChoiceSource != "recorded" {
			t.Fatalf("valid v2 trace lost provenance: %+v", d)
		}
	}
	// Make a declined response a legal losing bid; the action stream stays
	// unchanged, but the review must compare the bid rather than an invented pass.
	for i := range p.Rounds[0].Decisions {
		row := &p.Rounds[0].Decisions[i]
		if row.ChosenID != rl.ActionPass || len(row.LegalIDs) < 2 {
			continue
		}
		for _, id := range row.LegalIDs {
			if id != rl.ActionPass {
				row.ChosenID = id
				break
			}
		}
		updated, err := ExtractDecisions(p, 0)
		if err != nil {
			t.Fatal(err)
		}
		count := func(rows []Decision, id int) int {
			n := 0
			for _, d := range rows {
				if d.Seat == row.Seat && d.ChosenAction == id && d.ChoiceSource == "recorded" {
					n++
				}
			}
			return n
		}
		if count(updated, row.ChosenID) != count(ds, row.ChosenID)+1 || count(updated, rl.ActionPass) != count(ds, rl.ActionPass)-1 {
			t.Fatal("losing bid was still reported as pass")
		}
		return
	}
	t.Fatal("fixture has no declined response")
}

func TestInvalidEvaluatorProbabilitiesFailClosed(t *testing.T) {
	d := Decision{ChosenAction: 0, Observation: &pb.SeatObservation{ActionMask: []byte{1, 1}}}
	for _, ps := range [][]float32{{0, 0}, {-1, 2}, {float32(math.NaN()), 1}, {float32(math.Inf(1)), 1}} {
		if _, err := buildReportDecision(d, PolicyResult{Probs: ps}); err == nil {
			t.Fatalf("accepted %v", ps)
		}
	}
}
