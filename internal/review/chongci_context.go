package review

import (
	"google.golang.org/protobuf/proto"

	"github.com/plasma/fh-mahjong/internal/engine"
	pb "github.com/plasma/fh-mahjong/proto"
)

const defaultChongciStartingScore = int32(25000)

// isChongciPaipu detects chongci matches: chongci rounds record real (nonzero)
// starting scores; classic rounds record zeros.
func isChongciPaipu(paipu *engine.Paipu) bool {
	for _, r := range paipu.Rounds {
		for _, s := range r.StartingScores {
			if s != 0 {
				return true
			}
		}
	}
	return false
}

// reviewState clones the replay state and dresses it in the chongci context
// the champion was trained on. Classic matches are presented as the FINAL hand
// of a chongci match with all scores equal (user decision, see spec); chongci
// matches carry their real per-round starting scores. MaxHands for chongci is
// approximated by the number of recorded rounds (the true config cap is not
// stored in the paipu).
func reviewState(state *pb.GameState, paipu *engine.Paipu, roundIdx int) *pb.GameState {
	clone := proto.Clone(state).(*pb.GameState)
	clone.MatchMode = pb.MatchMode_MATCH_MODE_CHONGCI

	chongci := isChongciPaipu(paipu)
	startingScore := defaultChongciStartingScore
	if chongci {
		startingScore = paipu.Rounds[0].StartingScores[0]
	}
	maxHands := uint32(len(paipu.Rounds))
	if chongci {
		// engine.Game's HandNum is 1-based (HandNum:1 == "East 1", see
		// game.go NewGame); roundIdx is the paipu's 0-based round index, so
		// the real hand number is roundIdx+1.
		clone.HandNum = uint32(roundIdx + 1)
	} else {
		clone.HandNum = maxHands // final hand: progress=1, remaining=0
	}
	clone.ChongciConfig = &pb.ChongciConfig{
		MaxHands:      maxHands,
		StartingScore: startingScore,
		BustThreshold: 0,
	}
	for seat, player := range clone.Players {
		if player == nil {
			continue
		}
		if chongci {
			player.Score = paipu.Rounds[roundIdx].StartingScores[seat]
		} else {
			player.Score = startingScore
		}
	}
	return clone
}
