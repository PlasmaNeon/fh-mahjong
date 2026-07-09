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
		ChongciConfig: &pb.ChongciConfig{
			StartingScore: 25000,
			BustThreshold: 0,
			MaxHands:      4,
		},
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
