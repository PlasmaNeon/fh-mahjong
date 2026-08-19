package rl

import (
	"github.com/plasma/fh-mahjong/internal/engine"
	pb "github.com/plasma/fh-mahjong/proto"
)

// IsFinalReadyBeforeNextRound reports whether seat is the last of the four to
// send READY at a Chongci round end — the moment the next hand's wall seed must
// be set, before the engine deals it.
//
// Non-Chongci matches never re-seed between hands, so this is always false for
// them.
func IsFinalReadyBeforeNextRound(game *engine.Game, seat uint32) bool {
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

// ReadyAllPlayersForNextRound sends READY for every seat that has not yet sent
// it, re-seeding the wall just before the final one so the next hand is
// deterministic.
//
// nextHandSeed maps the upcoming hand number to its wall seed. It is a
// parameter rather than a fixed rule because the callers genuinely differ: the
// RL env uses deriveHandSeed (splitmix), while the review fixtures were
// generated with baseSeed*1000+handNum and must keep reproducing byte-identical
// paipu. Passing nil skips re-seeding entirely.
func ReadyAllPlayersForNextRound(game *engine.Game, nextHandSeed func(handNum uint64) uint64) error {
	for seat := uint32(0); seat < 4; seat++ {
		if game.State.Phase != pb.GamePhase_PHASE_ROUND_END {
			return nil
		}
		if len(game.State.PlayerReady) > int(seat) && game.State.PlayerReady[seat] {
			continue
		}
		if nextHandSeed != nil && IsFinalReadyBeforeNextRound(game, seat) {
			nextHand := uint64(game.State.HandNum) + 1
			game.SetWallSeed(engine.SeedFromUint64(nextHandSeed(nextHand)))
		}
		if err := game.ProcessPlayerAction(seat, &pb.PlayerAction{Type: pb.ActionType_ACTION_READY}); err != nil {
			return err
		}
	}
	return nil
}

// FinalScores reads the four seat scores out of a game state, zero-valued when
// the state or its players are absent.
func FinalScores(state *pb.GameState) [4]int32 {
	var scores [4]int32
	if state == nil {
		return scores
	}
	for _, player := range state.Players {
		if player == nil || player.Seat > 3 {
			continue
		}
		scores[player.Seat] = player.Score
	}
	return scores
}
