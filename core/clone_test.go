package core_test

import (
	"testing"

	"github.com/plasma/fh-mahjong/core"
	pb "github.com/plasma/fh-mahjong/proto"
	"github.com/plasma/fh-mahjong/internal/rules"
	"google.golang.org/protobuf/proto"
)

func TestCloneForBranchIsolatedFromOriginal(t *testing.T) {
	g := core.NewGame("clone-original", &rules.HometownRuleset{}, core.MatchOptions{})
	g.SetWallSeed(core.SeedFromUint64(97))
	if err := g.Start(); err != nil {
		t.Fatalf("start failed: %v", err)
	}

	cloned := g.CloneForBranch()
	if cloned == nil {
		t.Fatalf("expected clone")
	}
	if !proto.Equal(g.State, cloned.State) {
		t.Fatalf("cloned protobuf state does not match original")
	}

	seat := cloned.State.ActivePlayer
	discard := proto.Clone(cloned.State.Players[seat].ClosedHand[0]).(*pb.Tile)
	if err := cloned.ProcessPlayerAction(seat, &pb.PlayerAction{
		Type: pb.ActionType_ACTION_DISCARD,
		Tile: discard,
	}); err != nil {
		t.Fatalf("clone discard failed: %v", err)
	}

	if g.State.Phase != pb.GamePhase_PHASE_PLAYER_TURN {
		t.Fatalf("original phase changed after clone action: %v", g.State.Phase)
	}
	if len(g.State.Players[seat].Discards) != 0 {
		t.Fatalf("original gained clone discard: %v", g.State.Players[seat].Discards)
	}
	if cloned.State.Phase == g.State.Phase && len(cloned.State.Players[seat].Discards) == 0 {
		t.Fatalf("clone did not advance independently")
	}
}
