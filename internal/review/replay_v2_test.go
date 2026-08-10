package review

import (
	"fmt"
	"sort"
	"strings"
	"testing"

	"github.com/plasma/fh-mahjong/internal/bot"
	"github.com/plasma/fh-mahjong/internal/engine"
	"github.com/plasma/fh-mahjong/internal/rl"
	"github.com/plasma/fh-mahjong/internal/rules"
	pb "github.com/plasma/fh-mahjong/proto"
)

// generateHeuristicPaipuV2 is generateHeuristicPaipu plus the v2 supervision
// trace: every explicit decision fed to the engine (including explicit
// passes, excluding READY round-flow control) gets a PaipuDecision row
// snapshotted on the PRE-action state — a faithful mirror of what the room
// layer does in internal/api/room_decisions.go (snapshotDecision +
// recordDecision), which internal/review cannot import (cycle).
func generateHeuristicPaipuV2(t *testing.T, seed uint64, opts engine.MatchOptions) *engine.Paipu {
	t.Helper()
	matchID := fmt.Sprintf("review-v2-test-%d", seed)
	game := engine.NewGame(matchID, &rules.FenghuaRuleset{}, opts)
	game.SetWallSeed(engine.SeedFromUint64(seed))
	game.Recorder = engine.NewPaipuRecorder(matchID, "fenghua")
	for seat := uint32(0); seat < 4; seat++ {
		game.Recorder.AddPlayer(seat, fmt.Sprintf("Bot %d", seat+1), 0)
	}
	if err := game.Start(); err != nil {
		t.Fatalf("start: %v", err)
	}
	driveGameWithHeuristicsTraced(t, game, bot.NewHeuristicPolicy(), seed)
	return game.Recorder.Finalize(finalScores(game))
}

// driveGameWithHeuristicsTraced mirrors driveGameWithHeuristics (same seat
// iteration order, same resolution fallbacks) and additionally records a
// decision row for every action it feeds the engine.
func driveGameWithHeuristicsTraced(t *testing.T, game *engine.Game, policy bot.Policy, seed uint64) {
	t.Helper()
	const maxActions = 20000
	for actionCount := 0; actionCount < maxActions; actionCount++ {
		switch game.State.Phase {
		case pb.GamePhase_PHASE_MATCH_END:
			return
		case pb.GamePhase_PHASE_ROUND_END:
			if game.State.MatchMode != pb.MatchMode_MATCH_MODE_CHONGCI {
				return
			}
			// READY is round-flow control, never a traced decision.
			if err := readyAllPlayersForNextRound(game, seed); err != nil {
				t.Fatalf("ready all players: %v", err)
			}
			continue
		case pb.GamePhase_PHASE_PLAYER_TURN:
			seat := game.State.ActivePlayer
			action := policy.ChooseAction(game.State, seat)
			if action == nil {
				t.Fatalf("heuristic returned nil turn action for seat %d", seat)
			}
			row := snapshotFixtureDecision(game, seat, action)
			if err := game.ProcessPlayerAction(seat, action); err != nil {
				t.Fatalf("process turn action: %v", err)
			}
			game.Recorder.RecordDecision(row)
		case pb.GamePhase_PHASE_WAIT_DISCARDS:
			acted := false
			for seat := uint32(0); seat < uint32(len(game.State.Players)); seat++ {
				if seat == game.State.ActivePlayer {
					continue
				}
				player := game.State.Players[seat]
				if len(player.ValidActions) == 0 || game.InterruptQueued(seat) {
					continue
				}
				action := policy.ChooseAction(game.State, seat)
				if action == nil {
					t.Fatalf("heuristic returned nil interrupt action for seat %d", seat)
				}
				row := snapshotFixtureDecision(game, seat, action)
				if err := game.ProcessPlayerAction(seat, action); err != nil {
					t.Fatalf("process interrupt action: %v", err)
				}
				game.Recorder.RecordDecision(row)
				acted = true
				break
			}
			if !acted {
				game.ResolveInterrupts()
			}
		default:
			t.Fatalf("unsupported phase %v", game.State.Phase)
		}
	}
	t.Fatalf("game did not finish within %d actions", maxActions)
}

// snapshotFixtureDecision is the test-side twin of Room.snapshotDecision:
// legal set + chosen catalog id computed against the PRE-action state.
func snapshotFixtureDecision(game *engine.Game, seat uint32, action *pb.PlayerAction) engine.PaipuDecision {
	row := engine.PaipuDecision{Seat: seat, ChosenID: -1, Source: "heuristic"}
	legal, err := rl.LegalActions(game.State, seat)
	if err != nil {
		row.LegalIDsError = true
	} else {
		ids := make([]int, 0, len(legal))
		for id := range legal {
			ids = append(ids, id)
		}
		sort.Ints(ids)
		row.LegalIDs = ids
	}
	if id, ok := rl.EncodeAction(game.State, seat, action); ok {
		row.ChosenID = id
	} else {
		row.LegalIDsError = true
	}
	return row
}

// firstMultiOptionRow returns a mutable pointer to the first trace row whose
// legal set has more than one option (so it can be corrupted meaningfully).
func firstMultiOptionRow(t *testing.T, paipu *engine.Paipu) *engine.PaipuDecision {
	t.Helper()
	for roundIdx := range paipu.Rounds {
		for i := range paipu.Rounds[roundIdx].Decisions {
			row := &paipu.Rounds[roundIdx].Decisions[i]
			if !row.LegalIDsError && len(row.LegalIDs) > 1 {
				return row
			}
		}
	}
	t.Fatal("fixture has no multi-option decision row to corrupt")
	return nil
}

func totalDecisionRows(paipu *engine.Paipu) int {
	total := 0
	for roundIdx := range paipu.Rounds {
		total += len(paipu.Rounds[roundIdx].Decisions)
	}
	return total
}

func stripDecisions(paipu *engine.Paipu) {
	for roundIdx := range paipu.Rounds {
		paipu.Rounds[roundIdx].Decisions = nil
	}
}

func TestReplayV2CrossCheckPasses(t *testing.T) {
	paipu := generateHeuristicPaipuV2(t, 7, engine.MatchOptions{})
	if totalDecisionRows(paipu) == 0 {
		t.Fatal("fixture recorded no v2 decision rows")
	}
	decisions, err := ExtractDecisions(paipu, 0)
	if err != nil {
		t.Fatalf("ExtractDecisions on well-formed v2 paipu: %v", err)
	}
	if len(decisions) == 0 {
		t.Fatal("expected at least one reviewable decision")
	}
}

// TestReplayV2CrossCheckAlignsReorderedWindows pins the alignment rule. In
// every one of these games some interrupt window has a lower seat declining
// (or losing) a call before a higher seat's winning call: the trace records
// them in response order, the replayer reconstructs the winning call first.
// A naive "next row must be this seat's" cursor false-fails on all of them,
// so these seeds must keep replaying clean.
func TestReplayV2CrossCheckAlignsReorderedWindows(t *testing.T) {
	for _, seed := range []uint64{11, 17, 28, 34} {
		paipu := generateHeuristicPaipuV2(t, seed, engine.MatchOptions{})
		if _, err := ExtractDecisions(paipu, 0); err != nil {
			t.Errorf("classic seed %d: %v", seed, err)
		}
	}
	for _, seed := range []uint64{2, 3} {
		paipu := generateHeuristicPaipuV2(t, seed, engine.MatchOptions{
			Mode: pb.MatchMode_MATCH_MODE_CHONGCI,
			ChongciConfig: &pb.ChongciConfig{
				StartingScore: 25000,
				BustThreshold: 0,
				MaxHands:      4,
			},
		})
		if _, err := ExtractDecisions(paipu, 0); err != nil {
			t.Errorf("chongci seed %d: %v", seed, err)
		}
	}
}

func TestReplayV2CrossCheckCatchesUnmatchedRow(t *testing.T) {
	paipu := generateHeuristicPaipuV2(t, 7, engine.MatchOptions{})
	round := &paipu.Rounds[0]
	// A row nothing in the reconstruction can account for: a fabricated
	// interrupt decision spliced in near the front of the trace.
	fabricated := engine.PaipuDecision{
		Seat:     3,
		ChosenID: rl.ActionTsumo,
		LegalIDs: []int{rl.ActionPass, rl.ActionTsumo},
		Source:   "human",
	}
	round.Decisions = append(round.Decisions[:1],
		append([]engine.PaipuDecision{fabricated}, round.Decisions[1:]...)...)
	for i := range round.Decisions {
		round.Decisions[i].Index = i
	}

	_, err := ExtractDecisions(paipu, 0)
	if err == nil {
		t.Fatal("expected an error for a fabricated decision row, got nil")
	}
	if !strings.Contains(err.Error(), "decision cross-check failed") {
		t.Fatalf("error %q does not name the cross-check failure", err)
	}
}

func TestReplayV2CrossCheckCatchesTamperedChosenID(t *testing.T) {
	paipu := generateHeuristicPaipuV2(t, 7, engine.MatchOptions{})
	row := firstMultiOptionRow(t, paipu)
	// Pick a catalog id that is definitely NOT in the legal set.
	inLegal := make(map[int]bool, len(row.LegalIDs))
	for _, id := range row.LegalIDs {
		inLegal[id] = true
	}
	tampered := -1
	for id := 0; id < rl.ActionSpaceSize; id++ {
		if !inLegal[id] {
			tampered = id
			break
		}
	}
	if tampered < 0 {
		t.Fatal("every catalog id is legal for this row; cannot tamper")
	}
	row.ChosenID = tampered

	_, err := ExtractDecisions(paipu, 0)
	if err == nil {
		t.Fatal("expected an error for a tampered chosen id, got nil")
	}
	if !strings.Contains(err.Error(), "decision cross-check failed") {
		t.Fatalf("error %q does not name the cross-check failure", err)
	}
}

func TestReplayV2CrossCheckCatchesWrongLegalSet(t *testing.T) {
	paipu := generateHeuristicPaipuV2(t, 7, engine.MatchOptions{})
	row := firstMultiOptionRow(t, paipu)
	// Drop a legal id that is not the chosen one, so only rule (b) trips.
	dropped := make([]int, 0, len(row.LegalIDs))
	removed := false
	for _, id := range row.LegalIDs {
		if !removed && id != row.ChosenID {
			removed = true
			continue
		}
		dropped = append(dropped, id)
	}
	if !removed {
		t.Fatal("could not drop a non-chosen legal id from the row")
	}
	row.LegalIDs = dropped

	_, err := ExtractDecisions(paipu, 0)
	if err == nil {
		t.Fatal("expected an error for a corrupted legal set, got nil")
	}
	if !strings.Contains(err.Error(), "decision cross-check failed") {
		t.Fatalf("error %q does not name the cross-check failure", err)
	}
}

// TestReplayV2WholesaleDeletedTraceFailsLoudly pins the Version-gated skip:
// unlike TestReplayV1Unchanged's genuinely-legacy (Version 1) fixtures, this
// paipu keeps its real Version (2, stamped by NewPaipuRecorder) but has one
// round's entire Decisions array deleted outright. Reconstruction still
// finds real decision points in that round, so the empty trace must fail
// loudly instead of silently passing like a true v1 record would.
func TestReplayV2WholesaleDeletedTraceFailsLoudly(t *testing.T) {
	paipu := generateHeuristicPaipuV2(t, 7, engine.MatchOptions{})
	deleted := false
	for i := range paipu.Rounds {
		if len(paipu.Rounds[i].Decisions) > 0 {
			paipu.Rounds[i].Decisions = nil
			deleted = true
			break
		}
	}
	if !deleted {
		t.Fatal("fixture has no round with decision rows to delete")
	}

	_, err := ExtractDecisions(paipu, 0)
	if err == nil {
		t.Fatal("expected an error for a wholesale-deleted v2 decision trace, got nil")
	}
	if !strings.Contains(err.Error(), "decision cross-check failed") {
		t.Fatalf("error %q does not name the cross-check failure", err)
	}
}

// TestReplayV2CrossCheckCatchesRetargetedChosenID pins check (a)'s upgrade
// from "legal" to "identical" on explicit paths: unlike
// TestReplayV2CrossCheckCatchesTamperedChosenID (which tampers to an
// ILLEGAL id), this retargets the row to a DIFFERENT id that is still legal
// in the same reconstructed set. Before the fix this passed (legality-only);
// an explicit turn/interrupt row must now match the fed action exactly.
func TestReplayV2CrossCheckCatchesRetargetedChosenID(t *testing.T) {
	paipu := generateHeuristicPaipuV2(t, 7, engine.MatchOptions{})
	row := firstMultiOptionRow(t, paipu)
	alt := -1
	for _, id := range row.LegalIDs {
		if id != row.ChosenID {
			alt = id
			break
		}
	}
	if alt < 0 {
		t.Fatal("row has no alternate legal id to retarget to")
	}
	row.ChosenID = alt

	_, err := ExtractDecisions(paipu, 0)
	if err == nil {
		t.Fatal("expected an error for a retargeted-but-still-legal chosen id on an explicit path, got nil")
	}
	if !strings.Contains(err.Error(), "decision cross-check failed") {
		t.Fatalf("error %q does not name the cross-check failure", err)
	}
}

func TestReplayV1Unchanged(t *testing.T) {
	// A v2 paipu with its trace stripped must replay exactly like the v1
	// paipu the same seed produces without any trace at all. Both fixtures
	// come from NewPaipuRecorder, which always stamps the current schema
	// version (2) — genuinely old records on disk carry a literal Version:1,
	// so both are force-set to 1 here to actually exercise the Version<2
	// skip path (crossCheckDecision/verifyTraceConsumed), not just the
	// row-count coincidence of a paipu that happens to carry zero rows.
	v2 := generateHeuristicPaipuV2(t, 7, engine.MatchOptions{})
	stripDecisions(v2)
	v2.Version = 1
	stripped, err := ExtractDecisions(v2, 0)
	if err != nil {
		t.Fatalf("ExtractDecisions on trace-stripped paipu: %v", err)
	}

	v1 := generateHeuristicPaipu(t, 7, engine.MatchOptions{})
	if totalDecisionRows(v1) != 0 {
		t.Fatal("v1 fixture unexpectedly carries decision rows")
	}
	baseline, err := ExtractDecisions(v1, 0)
	if err != nil {
		t.Fatalf("ExtractDecisions on v1 paipu: %v", err)
	}
	if len(stripped) != len(baseline) {
		t.Fatalf("stripped-v2 decision count %d != v1 decision count %d", len(stripped), len(baseline))
	}
	for i := range baseline {
		if stripped[i].Seat != baseline[i].Seat ||
			stripped[i].RoundIndex != baseline[i].RoundIndex ||
			stripped[i].ActionIndex != baseline[i].ActionIndex ||
			stripped[i].DecisionIndex != baseline[i].DecisionIndex ||
			stripped[i].ChosenAction != baseline[i].ChosenAction {
			t.Fatalf("decision %d diverges: stripped-v2 %+v vs v1 %+v", i,
				stripped[i], baseline[i])
		}
	}
}
