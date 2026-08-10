package api

import (
	"testing"

	"github.com/plasma/fh-mahjong/internal/bot"
	"github.com/plasma/fh-mahjong/internal/engine"
	"github.com/plasma/fh-mahjong/internal/rl"
	pb "github.com/plasma/fh-mahjong/proto"
)

// These tests pin the paipu v2 supervision trace captured at the room layer:
// every explicit gameplay decision (human, heuristic, remote, fallback,
// including explicit passes) yields exactly one PaipuDecision row, with the
// legal set + chosen id snapshotted on the PRE-action state.

// roundsWithDecisions returns every recorded round (finished + in progress).
func roundsWithDecisions(room *Room) []engine.PaipuRound {
	return room.Engine.Recorder.Snapshot([4]int32{}).Rounds
}

// allDecisions flattens the decision rows of every recorded round.
func allDecisions(room *Room) []engine.PaipuDecision {
	var out []engine.PaipuDecision
	for _, round := range roundsWithDecisions(room) {
		out = append(out, round.Decisions...)
	}
	return out
}

func containsInt(haystack []int, needle int) bool {
	for _, v := range haystack {
		if v == needle {
			return true
		}
	}
	return false
}

// stepBotRoomUntilRoundEnd drives a bot-only room one automated step at a
// time so the test observes the trace of a single hand.
func stepBotRoomUntilRoundEnd(t *testing.T, room *Room) {
	t.Helper()
	if err := room.Engine.Start(); err != nil {
		t.Fatalf("Engine.Start: %v", err)
	}
	for i := 0; i < 200; i++ {
		if room.Engine.State.Phase == pb.GamePhase_PHASE_ROUND_END ||
			room.Engine.State.Phase == pb.GamePhase_PHASE_MATCH_END {
			return
		}
		room.advanceAutomatedSeatsN(1)
	}
}

func TestDecisionTraceRecordsBotPlay(t *testing.T) {
	room := NewRoom("decision-trace-bots", nil, nil)
	stepBotRoomUntilRoundEnd(t, room)

	rounds := roundsWithDecisions(room)
	total := 0
	for _, round := range rounds {
		for i, d := range round.Decisions {
			total++
			if d.Index != i {
				t.Fatalf("decision %d has Index %d, want %d (indices must be 0..n-1 in order)", i, d.Index, i)
			}
			if d.Source != "heuristic" {
				t.Fatalf("decision %d Source = %q, want \"heuristic\"", i, d.Source)
			}
			if d.LegalIDsError {
				t.Fatalf("decision %d has LegalIDsError set", i)
			}
			if len(d.LegalIDs) == 0 {
				t.Fatalf("decision %d has empty LegalIDs", i)
			}
			if !containsInt(d.LegalIDs, d.ChosenID) {
				t.Fatalf("decision %d ChosenID %d not in LegalIDs %v", i, d.ChosenID, d.LegalIDs)
			}
			if d.Seat >= 4 {
				t.Fatalf("decision %d has out-of-range Seat %d", i, d.Seat)
			}
			if d.Checkpoint != nil {
				t.Fatalf("decision %d unexpectedly carries a checkpoint: %+v", i, d.Checkpoint)
			}
		}
	}
	if total == 0 {
		t.Fatal("expected the bot-only room to record decision rows")
	}
}

// TestDecisionTraceExcludesReady: the READY acks at round end are round-flow
// control, not gameplay decisions — they must never appear in the trace. A
// READY would encode as no catalog action, so it would show up as a
// LegalIDsError/ChosenID -1 row if it were traced.
func TestDecisionTraceExcludesReady(t *testing.T) {
	room := NewRoom("decision-trace-ready", nil, nil)
	stepBotRoomUntilRoundEnd(t, room)
	if room.Engine.State.Phase != pb.GamePhase_PHASE_ROUND_END {
		t.Fatalf("expected the hand to reach round end, phase=%v", room.Engine.State.Phase)
	}
	before := len(allDecisions(room))

	// Drive the round-end READY flow: four READY acks, zero decision rows.
	room.advanceAutomatedSeatsN(1)

	if after := len(allDecisions(room)); after != before {
		t.Fatalf("READY flow added %d decision rows, want 0", after-before)
	}
	for _, d := range allDecisions(room) {
		if d.ChosenID < 0 || d.LegalIDsError {
			t.Fatalf("found a non-gameplay decision row (READY leaked into the trace): %+v", d)
		}
	}
}

func TestDecisionTraceRecordsHumanAction(t *testing.T) {
	room := NewRoom("decision-trace-human", nil, nil)
	human := &Client{UserID: 7, Username: "human", Send: make(chan []byte, 256)}
	room.Seats[0] = human
	room.SeatOwners[0] = 7
	if err := room.Engine.Start(); err != nil {
		t.Fatalf("Engine.Start: %v", err)
	}

	// Let the bots play up to seat 0's turn, passing on seat 0's behalf if
	// the human is offered an interrupt along the way.
	reached := false
	for i := 0; i < 200 && !reached; i++ {
		room.advanceAutomatedSeats()
		st := room.Engine.State
		switch {
		case st.Phase == pb.GamePhase_PHASE_PLAYER_TURN && st.ActivePlayer == 0:
			reached = true
		case st.Phase == pb.GamePhase_PHASE_WAIT_DISCARDS && len(st.Players[0].ValidActions) > 0:
			room.dispatchClientAction(ClientAction{
				Client: human,
				Action: &pb.PlayerAction{Type: pb.ActionType_ACTION_PASS},
			})
		case st.Phase == pb.GamePhase_PHASE_ROUND_END:
			room.dispatchClientAction(ClientAction{
				Client: human,
				Action: &pb.PlayerAction{Type: pb.ActionType_ACTION_READY},
			})
		}
	}
	if !reached {
		t.Fatalf("never reached the human seat's turn, phase=%v active=%d",
			room.Engine.State.Phase, room.Engine.State.ActivePlayer)
	}

	legal, err := rl.LegalActions(room.Engine.State, 0)
	if err != nil {
		t.Fatalf("rl.LegalActions: %v", err)
	}
	var discardID = -1
	var discard *pb.PlayerAction
	for id, action := range legal {
		if action.Type == pb.ActionType_ACTION_DISCARD {
			if discardID == -1 || id < discardID {
				discardID, discard = id, action
			}
		}
	}
	if discard == nil {
		t.Fatalf("no legal discard for the human seat, legal=%v", legal)
	}

	before := len(allDecisions(room))
	room.dispatchClientAction(ClientAction{Client: human, Action: discard})

	rows := allDecisions(room)
	if len(rows) <= before {
		t.Fatal("human discard did not record a decision row")
	}
	row := rows[before]
	if row.Seat != 0 {
		t.Fatalf("Seat = %d, want 0", row.Seat)
	}
	if row.Source != "human" {
		t.Fatalf("Source = %q, want \"human\"", row.Source)
	}
	if row.ChosenID != discardID {
		t.Fatalf("ChosenID = %d, want %d (the discard's catalog id)", row.ChosenID, discardID)
	}
	if !containsInt(row.LegalIDs, discardID) {
		t.Fatalf("LegalIDs %v does not contain the chosen discard %d", row.LegalIDs, discardID)
	}
}

// TestDecisionTraceRecordsExplicitPass: passes on a claim window are real
// decisions and must be traced (the canonical Actions stream stays pass-free).
func TestDecisionTraceRecordsExplicitPass(t *testing.T) {
	room := NewRoom("decision-trace-pass", nil, nil)
	if err := room.Engine.Start(); err != nil {
		t.Fatalf("Engine.Start: %v", err)
	}

	found := false
	for i := 0; i < 4000 && !found; i++ {
		room.advanceAutomatedSeatsN(1)
		for _, d := range allDecisions(room) {
			if d.ChosenID == rl.ActionPass {
				if d.Source != "heuristic" {
					t.Fatalf("pass row Source = %q, want \"heuristic\"", d.Source)
				}
				if !containsInt(d.LegalIDs, rl.ActionPass) {
					t.Fatalf("pass row LegalIDs %v missing ActionPass", d.LegalIDs)
				}
				if len(d.LegalIDs) < 2 {
					t.Fatalf("pass row LegalIDs %v should also contain the declined claim", d.LegalIDs)
				}
				found = true
				break
			}
		}
	}
	if !found {
		t.Fatal("expected at least one explicit PASS decision row")
	}
}

// provStubPolicy returns a fixed provenance alongside a heuristic action.
type provStubPolicy struct {
	delegate bot.Policy
	prov     bot.DecisionProvenance
}

func (p *provStubPolicy) ChooseAction(state *pb.GameState, seat uint32) *pb.PlayerAction {
	return p.delegate.ChooseAction(state, seat)
}

func (p *provStubPolicy) ChooseActionCtx(ctx *bot.DecisionContext) *pb.PlayerAction {
	return p.delegate.ChooseAction(ctx.State, ctx.Seat)
}

func (p *provStubPolicy) ChooseActionCtxProv(ctx *bot.DecisionContext) (*pb.PlayerAction, bot.DecisionProvenance) {
	return p.delegate.ChooseAction(ctx.State, ctx.Seat), p.prov
}

func firstDecisionWithProvPolicy(t *testing.T, name string, prov bot.DecisionProvenance) engine.PaipuDecision {
	t.Helper()
	policy := &provStubPolicy{delegate: bot.NewHeuristicPolicy(), prov: prov}
	room := NewRoom(name, nil, nil, WithBotPolicy(policy))
	if err := room.Engine.Start(); err != nil {
		t.Fatalf("Engine.Start: %v", err)
	}
	room.advanceAutomatedSeatsN(1)
	rows := allDecisions(room)
	if len(rows) == 0 {
		t.Fatal("expected a decision row after one automated step")
	}
	return rows[0]
}

func TestDecisionTraceRemoteProvenance(t *testing.T) {
	row := firstDecisionWithProvPolicy(t, "decision-trace-remote", bot.DecisionProvenance{
		Source:         "remote",
		CheckpointName: "ck.pt",
		CheckpointStep: 9,
		CheckpointSha:  "aa",
	})
	if row.Source != "remote" {
		t.Fatalf("Source = %q, want \"remote\"", row.Source)
	}
	if row.Checkpoint == nil {
		t.Fatal("remote decision row must carry a checkpoint")
	}
	if *row.Checkpoint != (engine.PaipuCheckpoint{Name: "ck.pt", Step: 9, Sha256: "aa"}) {
		t.Fatalf("Checkpoint = %+v, want {ck.pt 9 aa}", *row.Checkpoint)
	}
}

func TestDecisionTraceFallbackReason(t *testing.T) {
	row := firstDecisionWithProvPolicy(t, "decision-trace-fallback", bot.DecisionProvenance{
		Source:         "fallback",
		FallbackReason: "status",
	})
	if row.Source != "fallback" {
		t.Fatalf("Source = %q, want \"fallback\"", row.Source)
	}
	if row.FallbackReason != "status" {
		t.Fatalf("FallbackReason = %q, want \"status\"", row.FallbackReason)
	}
	if row.Checkpoint != nil {
		t.Fatalf("fallback row must not carry a checkpoint, got %+v", row.Checkpoint)
	}
}
