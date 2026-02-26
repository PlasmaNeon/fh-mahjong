package core

import (
	pb "github.com/plasma/fh-mahjong/proto"
)

// The RuleEngine defines the strict interface every ruleset plugin must follow.
// By abstracting the rules, the core state machine (game.go) operates independently
// of how hands are evaluated, allowing easy switching between Hometown rules, Riichi, etc.
type RuleEngine interface {
	// Name returns the identifier for this ruleset plugin.
	Name() string

	// GetInitialWall returns a shuffled slice of tiles based on the ruleset's deck composition.
	// For instance, standard Mahjong has 136 tiles, some rules exclude bamboos, etc.
	GetInitialWall() []*pb.Tile

	// EvaluateHand checks if a player's hand is a winning hand (Agari)
	// and returns the score, yaku, and a boolean indicating success.
	EvaluateHand(hand []*pb.Tile, openMelds []*pb.Meld, winTile *pb.Tile, state *pb.GameState, playerSeat uint32, isTsumo bool) (score int32, canWin bool)

	// GetValidActions returns all legal actions an active player can take during their turn (e.g., Discard, Tsumo, Riichi, Kan).
	GetValidActions(state *pb.GameState, playerSeat uint32) []pb.ActionType

	// GetValidInterrupts returns all legal actions non-active players can take when a tile is discarded (e.g., Ron, Pong, Chi, Kan).
	GetValidInterrupts(state *pb.GameState, discardedTile *pb.Tile, playerSeat uint32) []pb.ActionType

	// ResolveInterruptPriority determines which action succeeds when multiple players try to claim the same discarded tile.
	// (e.g., Ron > Pong/Kong > Chi). Returns the seat number of the winner.
	ResolveInterruptPriority(actions map[uint32]*pb.PlayerAction) (winnerSeat uint32, action *pb.PlayerAction)
}
