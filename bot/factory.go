package bot

import (
	"fmt"

	pb "github.com/plasma/fh-mahjong/proto"
)

// NewPolicy returns the bot Policy implementation for the given difficulty.
// Returns an error for DIFFICULTY_UNSPECIFIED or unknown values so callers
// (e.g. the REST seat handler) can surface a 400 instead of silently
// installing a wrong policy.
func NewPolicy(d pb.Difficulty) (Policy, error) {
	switch d {
	case pb.Difficulty_DIFFICULTY_HEURISTIC:
		return NewHeuristicPolicy(), nil
	default:
		return nil, fmt.Errorf("bot: unsupported difficulty %v", d)
	}
}
