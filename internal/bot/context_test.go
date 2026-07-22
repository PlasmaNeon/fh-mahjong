package bot

import (
	"testing"

	"github.com/plasma/fh-mahjong/internal/engine"
	pb "github.com/plasma/fh-mahjong/proto"
)

// stubContextPolicy is a ContextPolicy that records the last context it
// received, for assertion by tests.
type stubContextPolicy struct {
	lastCtx *DecisionContext
}

func (s *stubContextPolicy) ChooseActionCtx(ctx *DecisionContext) *pb.PlayerAction {
	s.lastCtx = ctx
	return nil
}

func TestDecisionContextEventsDoNotAliasSource(t *testing.T) {
	source := []engine.PublicEvent{
		{Type: engine.EventDraw, Seat: 0, Face: 1, FromSeat: -1},
		{Type: engine.EventDiscard, Seat: 1, Face: 2, FromSeat: -1},
	}

	snapshot := make([]engine.PublicEvent, len(source))
	copy(snapshot, source)

	ctx := &DecisionContext{
		State:         &pb.GameState{},
		Seat:          0,
		DecisionIndex: 1,
		Events:        snapshot,
	}

	policy := &stubContextPolicy{}
	policy.ChooseActionCtx(ctx)

	// Mutate the source after building the context; the context's copy must
	// be unaffected.
	source[0].Face = 99
	source[0].Type = engine.EventKanUpgrade

	if policy.lastCtx.Events[0].Face == 99 {
		t.Fatalf("DecisionContext.Events aliases the source slice: got Face=%d after source mutation", policy.lastCtx.Events[0].Face)
	}
	if policy.lastCtx.Events[0].Type == engine.EventKanUpgrade {
		t.Fatalf("DecisionContext.Events aliases the source slice: got Type=%v after source mutation", policy.lastCtx.Events[0].Type)
	}
	if policy.lastCtx.Events[0].Face != 1 || policy.lastCtx.Events[0].Type != engine.EventDraw {
		t.Fatalf("unexpected context event snapshot: %+v", policy.lastCtx.Events[0])
	}
}
