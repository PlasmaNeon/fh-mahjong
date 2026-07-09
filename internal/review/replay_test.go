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
	driveGameWithHeuristics(t, game, policy, seed)
	// Finalize returns the recorded paipu.
	return game.Recorder.Finalize(finalScores(game))
}

// driveGameWithHeuristics plays the game to completion using the heuristic
// policy for every seat, mirroring cmd/rlpaipu/main.go's loop. For chongci
// matches it also acks ROUND_END with a derived per-hand wall seed, mirroring
// internal/rl/env.go readyAllPlayersForNextRound.
func driveGameWithHeuristics(t *testing.T, game *engine.Game, policy bot.Policy, seed uint64) {
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
			if err := readyAllPlayersForNextRound(game, seed); err != nil {
				t.Fatalf("ready all players: %v", err)
			}
			continue
		case pb.GamePhase_PHASE_PLAYER_TURN:
			actSeat := game.State.ActivePlayer
			action := policy.ChooseAction(game.State, actSeat)
			if action == nil {
				t.Fatalf("heuristic returned nil turn action for seat %d", actSeat)
			}
			if err := game.ProcessPlayerAction(actSeat, action); err != nil {
				t.Fatalf("process turn action: %v", err)
			}
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
				if err := game.ProcessPlayerAction(seat, action); err != nil {
					t.Fatalf("process interrupt action: %v", err)
				}
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

// readyAllPlayersForNextRound acks every seat's ROUND_END ready state,
// deriving a fresh wall seed for the next hand before the final ack —
// mirroring internal/rl/env.go readyAllPlayersForNextRound so multi-round
// chongci paipu are reproducible from the seeds the recorder captures.
func readyAllPlayersForNextRound(game *engine.Game, baseSeed uint64) error {
	for seat := uint32(0); seat < 4; seat++ {
		if game.State.Phase != pb.GamePhase_PHASE_ROUND_END {
			return nil
		}
		if len(game.State.PlayerReady) > int(seat) && game.State.PlayerReady[seat] {
			continue
		}
		if isFinalReadyBeforeNextRound(game, seat) {
			nextHand := uint64(game.State.HandNum) + 1
			game.SetWallSeed(engine.SeedFromUint64(baseSeed*1000 + nextHand))
		}
		if err := game.ProcessPlayerAction(seat, &pb.PlayerAction{Type: pb.ActionType_ACTION_READY}); err != nil {
			return err
		}
	}
	return nil
}

func isFinalReadyBeforeNextRound(game *engine.Game, seat uint32) bool {
	if game == nil || game.State == nil {
		return false
	}
	if game.State.MatchMode != pb.MatchMode_MATCH_MODE_CHONGCI {
		return false
	}
	for other := uint32(0); other < 4; other++ {
		if other == seat {
			continue
		}
		if len(game.State.PlayerReady) <= int(other) || !game.State.PlayerReady[other] {
			return false
		}
	}
	return true
}

func finalScores(game *engine.Game) [4]int32 {
	var scores [4]int32
	if game == nil || game.State == nil {
		return scores
	}
	for seat := 0; seat < len(scores) && seat < len(game.State.Players); seat++ {
		scores[seat] = game.State.Players[seat].Score
	}
	return scores
}

// actMatchesCatalogFamily reports whether a paipu action verb and a catalog
// action id belong to the same action family — the anchor-correctness link
// between a Decision and the paipu record it claims to represent.
func actMatchesCatalogFamily(act string, id int) bool {
	switch act {
	case "discard":
		return id >= rl.DiscardBase && id < rl.DiscardBase+rl.DiscardCount
	case "pon":
		return id >= rl.PonBase && id < rl.PonBase+rl.PonCount
	case "okan":
		return id >= rl.KanDirectBase && id < rl.KanDirectBase+rl.KanModeCount
	case "ckan":
		return id >= rl.KanClosedBase && id < rl.KanClosedBase+rl.KanModeCount
	case "ukan":
		return id >= rl.KanUpgradedBase && id < rl.KanUpgradedBase+rl.KanModeCount
	case "chii":
		return id >= rl.ChiiBase && id < rl.ChiiBase+rl.ChiiCount
	case "tsumo":
		return id == rl.ActionTsumo
	case "ron":
		return id == rl.ActionRon
	case "haitei":
		return id == rl.ActionAcceptHaitei
	case "haiteiRefuse":
		return id == rl.ActionRefuseHaitei
	default:
		return false
	}
}

// assertDecisionAnchors bounds-checks every decision and verifies its anchor
// points at the RIGHT paipu record: pass decisions must anchor to the
// triggering "discard" record; non-pass decisions must anchor to a record
// made by the same seat whose Act maps to the same catalog family as the
// chosen action id.
func assertDecisionAnchors(t *testing.T, paipu *engine.Paipu, decisions []Decision) {
	t.Helper()
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
		anchored := paipu.Rounds[d.RoundIndex].Actions[d.ActionIndex]
		if d.ChosenAction == rl.ActionPass {
			if anchored.Act != "discard" {
				t.Fatalf("decision %d: pass decision anchored to %q record, want the triggering \"discard\"", i, anchored.Act)
			}
			continue
		}
		if anchored.Seat != d.Seat {
			t.Fatalf("decision %d: seat %d's decision anchored to seat %d's %q record", i, d.Seat, anchored.Seat, anchored.Act)
		}
		if !actMatchesCatalogFamily(anchored.Act, d.ChosenAction) {
			t.Fatalf("decision %d: chosen action %d is not in the catalog family of anchored %q record", i, d.ChosenAction, anchored.Act)
		}
	}
}

// assertCallRecordsHaveDecisions verifies pass-completeness from the paipu
// side: every recorded interrupt call (chii/pon/okan/ron) opened a window
// with at least two legal actions (pass + the call), so the winning seat's
// decision must exist anchored at exactly that record's index. A driver
// regression that stops recording interrupt-window decisions would fail here.
func assertCallRecordsHaveDecisions(t *testing.T, paipu *engine.Paipu, decisions []Decision) {
	t.Helper()
	decisionAt := make(map[[2]int]Decision, len(decisions))
	for _, d := range decisions {
		decisionAt[[2]int{d.RoundIndex, d.ActionIndex}] = d
	}
	callRecords := 0
	for roundIdx := range paipu.Rounds {
		for actionIdx, pa := range paipu.Rounds[roundIdx].Actions {
			switch pa.Act {
			case "chii", "pon", "okan", "ron":
			default:
				continue
			}
			callRecords++
			d, ok := decisionAt[[2]int{roundIdx, actionIdx}]
			if !ok {
				t.Fatalf("round %d action %d: %s call record has no anchored decision", roundIdx, actionIdx, pa.Act)
			}
			if d.Seat != pa.Seat || d.ChosenAction == rl.ActionPass {
				t.Fatalf("round %d action %d: %s call record anchored to wrong decision %+v", roundIdx, actionIdx, pa.Act, d)
			}
		}
	}
	if callRecords == 0 {
		t.Fatal("expected at least one interrupt call record in the paipu; pick another seed rather than delete the assertion")
	}
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
	assertDecisionAnchors(t, paipu, decisions)
	assertCallRecordsHaveDecisions(t, paipu, decisions)
	seatSeen := map[uint32]bool{}
	passCount := 0
	for _, d := range decisions {
		seatSeen[d.Seat] = true
		if d.ChosenAction == rl.ActionPass {
			passCount++
		}
	}
	if len(seatSeen) != 4 {
		t.Fatalf("expected decisions for all 4 seats, got %v", seatSeen)
	}
	// A full heuristic game virtually always has at least one declined call
	// window; if this seed has none, pick another seed rather than delete
	// the assertion.
	if passCount == 0 {
		t.Fatal("expected at least one implicit pass decision")
	}
	// Golden pass-decision count for this fixed seed. The paipu format never
	// records a declined interrupt, so a regression that silently drops
	// recordDecision for a subset of passing seats in a multi-seat window
	// would otherwise pass every per-decision check above. The game is fully
	// deterministic (fixed wall seed + deterministic heuristic policy), so
	// this count only changes if the driver's decision recording — or,
	// legitimately, the heuristic policy / rules engine — changes. If a
	// deliberate upstream change moves it, re-derive the count and update it.
	const wantPassDecisions = 7
	if passCount != wantPassDecisions {
		t.Fatalf("pass-decision count = %d, want %d (decision-dropping regression guard; see comment)", passCount, wantPassDecisions)
	}
}

func TestExtractDecisionsChongciMultiRound(t *testing.T) {
	paipu := generateHeuristicPaipu(t, 11, engine.MatchOptions{
		Mode: pb.MatchMode_MATCH_MODE_CHONGCI,
		ChongciConfig: &pb.ChongciConfig{
			StartingScore: 25000,
			BustThreshold: 0,
			MaxHands:      4,
		},
	})
	if len(paipu.Rounds) < 2 {
		t.Fatalf("want a multi-round paipu for this test, got %d rounds", len(paipu.Rounds))
	}
	decisions, err := ExtractDecisions(paipu)
	if err != nil {
		t.Fatalf("ExtractDecisions: %v", err)
	}
	assertDecisionAnchors(t, paipu, decisions)
}

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
		ChongciConfig: &pb.ChongciConfig{
			StartingScore: 25000,
			BustThreshold: 0,
			MaxHands:      4,
		},
	})
	decisions, err := ExtractDecisions(paipu)
	if err != nil {
		t.Fatalf("ExtractDecisions: %v", err)
	}
	// Find a decision in a round whose StartingScores are no longer equal
	// (after the first hand with a payout) and assert score scalars differ
	// across seats — i.e. real chongci context is carried through.
	unequalRound := -1
	for i, r := range paipu.Rounds {
		s := r.StartingScores
		if s[0] != s[1] || s[0] != s[2] || s[0] != s[3] {
			unequalRound = i
			break
		}
	}
	if unequalRound < 0 {
		t.Fatal("expected at least one round with unequal starting scores; pick another seed rather than delete the assertion")
	}
	var fromSeats []Decision
	seatsSeen := map[uint32]bool{}
	for _, d := range decisions {
		if d.RoundIndex != unequalRound {
			continue
		}
		if seatsSeen[d.Seat] {
			continue
		}
		seatsSeen[d.Seat] = true
		fromSeats = append(fromSeats, d)
		if len(fromSeats) == 2 {
			break
		}
	}
	if len(fromSeats) < 2 {
		t.Fatalf("expected decisions from at least 2 different seats in round %d, got %d", unequalRound, len(fromSeats))
	}
	a, b := fromSeats[0], fromSeats[1]
	if a.Observation.Scalars[50] == b.Observation.Scalars[50] {
		t.Fatalf("expected scalar[50] (own score) to differ across seats %d and %d in round %d with unequal starting scores, both got %f",
			a.Seat, b.Seat, unequalRound, a.Observation.Scalars[50])
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
