package bot

import (
	"bytes"
	"log"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/plasma/fh-mahjong/internal/engine"
	pb "github.com/plasma/fh-mahjong/proto"
)

// captureLog redirects the standard logger to a buffer for the duration of
// the test and restores the previous output on cleanup.
func captureLog(t *testing.T) *bytes.Buffer {
	t.Helper()
	var buf bytes.Buffer
	prev := log.Writer()
	log.SetOutput(&buf)
	t.Cleanup(func() { log.SetOutput(prev) })
	return &buf
}

// fixedPolicy is a Policy/ContextPolicy stub that always returns the same
// action, regardless of state.
type fixedPolicy struct {
	action *pb.PlayerAction
}

func (f *fixedPolicy) ChooseAction(state *pb.GameState, seat uint32) *pb.PlayerAction {
	return f.action
}

func (f *fixedPolicy) ChooseActionCtx(ctx *DecisionContext) *pb.PlayerAction {
	return f.action
}

var _ Policy = (*fixedPolicy)(nil)
var _ ContextPolicy = (*fixedPolicy)(nil)

// blockingShadow is a ContextPolicy stub that blocks until release is
// closed, then returns action. It also records the last context it was
// invoked with and how many times it was called, for deep-clone-isolation
// and agreement assertions.
type blockingShadow struct {
	release chan struct{}
	action  *pb.PlayerAction
	err     bool

	mu        sync.Mutex
	lastCtx   *DecisionContext
	callCount int
}

func (b *blockingShadow) ChooseActionCtx(ctx *DecisionContext) *pb.PlayerAction {
	if b.release != nil {
		<-b.release
	}
	b.mu.Lock()
	b.lastCtx = ctx
	b.callCount++
	b.mu.Unlock()
	if b.err {
		panic("simulated shadow policy failure")
	}
	return b.action
}

var _ ContextPolicy = (*blockingShadow)(nil)

func (b *blockingShadow) snapshot() (*DecisionContext, int) {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.lastCtx, b.callCount
}

func newTestState(closedHandID uint32) *pb.GameState {
	return &pb.GameState{
		Players: []*pb.PlayerState{
			{
				ClosedHand: []*pb.Tile{
					{Id: closedHandID, Suit: pb.Suit_SUIT_MAN, Value: 1},
				},
			},
		},
	}
}

func testDiscardAction(tileID uint32) *pb.PlayerAction {
	return &pb.PlayerAction{
		Type: pb.ActionType_ACTION_DISCARD,
		Tile: &pb.Tile{Id: tileID, Suit: pb.Suit_SUIT_MAN, Value: 1},
	}
}

func TestShadowPolicyReturnsPrimaryActionEvenWhenShadowBlocks(t *testing.T) {
	primaryAction := testDiscardAction(1)
	primary := &fixedPolicy{action: primaryAction}
	shadow := &blockingShadow{release: make(chan struct{})} // never released during this test

	sp := NewShadowPolicy(primary, shadow, 4)
	defer func() {
		close(shadow.release)
		sp.Close()
	}()

	ctx := &DecisionContext{State: newTestState(1), Seat: 0, DecisionIndex: 1}

	done := make(chan *pb.PlayerAction, 1)
	go func() {
		done <- sp.ChooseActionCtx(ctx)
	}()

	select {
	case got := <-done:
		if got != primaryAction {
			t.Fatalf("expected primary action returned unchanged, got %v", got)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("ChooseActionCtx blocked on shadow policy instead of returning the primary's action synchronously")
	}
}

func TestShadowPolicyReturnsPrimaryActionEvenWhenShadowErrors(t *testing.T) {
	primaryAction := testDiscardAction(1)
	primary := &fixedPolicy{action: primaryAction}
	shadow := &blockingShadow{err: true}

	sp := NewShadowPolicy(primary, shadow, 4)
	defer sp.Close()

	ctx := &DecisionContext{State: newTestState(1), Seat: 0, DecisionIndex: 1}
	got := sp.ChooseActionCtx(ctx)
	if got != primaryAction {
		t.Fatalf("expected primary action returned, got %v", got)
	}

	sp.Close()
	metrics := sp.Metrics()
	if metrics.ShadowErrors != 1 {
		t.Fatalf("expected 1 shadow error recorded, got %d", metrics.ShadowErrors)
	}
}

func TestShadowPolicyDeepClonesStateAndEvents(t *testing.T) {
	primary := &fixedPolicy{action: testDiscardAction(1)}
	shadow := &blockingShadow{release: make(chan struct{}), action: testDiscardAction(1)}

	sp := NewShadowPolicy(primary, shadow, 4)

	state := newTestState(1)
	events := []engine.PublicEvent{
		{Type: engine.EventDraw, Seat: 0, Face: 1, FromSeat: -1},
	}
	ctx := &DecisionContext{State: state, Seat: 0, DecisionIndex: 1, Events: events}

	sp.ChooseActionCtx(ctx)

	// Mutate the live state and events after the call returns, then release
	// the shadow so it runs and captures whatever it sees.
	state.Players[0].ClosedHand[0].Id = 999
	events[0].Face = 42
	events[0].Type = engine.EventKanUpgrade

	close(shadow.release)
	sp.Close()

	seen, calls := shadow.snapshot()
	if calls != 1 {
		t.Fatalf("expected shadow to be invoked exactly once, got %d", calls)
	}
	if seen == nil || seen.State == nil || len(seen.State.Players) == 0 || len(seen.State.Players[0].ClosedHand) == 0 {
		t.Fatalf("shadow did not receive a usable state snapshot: %+v", seen)
	}
	if got := seen.State.Players[0].ClosedHand[0].Id; got != 1 {
		t.Fatalf("shadow saw mutated state: ClosedHand[0].Id = %d, want pre-mutation value 1", got)
	}
	if len(seen.Events) != 1 {
		t.Fatalf("expected 1 event in shadow snapshot, got %d", len(seen.Events))
	}
	if seen.Events[0].Face != 1 || seen.Events[0].Type != engine.EventDraw {
		t.Fatalf("shadow saw mutated events: %+v, want pre-mutation Face=1 Type=EventDraw", seen.Events[0])
	}
}

func TestShadowPolicyDroppedUnderFullQueue(t *testing.T) {
	primary := &fixedPolicy{action: testDiscardAction(1)}
	shadow := &blockingShadow{release: make(chan struct{})}

	// queueSize 1: the worker picks up the first job and blocks inside
	// shadow.ChooseActionCtx (release is never closed until the end), so the
	// queue's buffer slot is immediately free again for job 2 but occupied
	// while the worker holds job 1 - use enough decisions to guarantee an
	// overrun regardless of scheduling.
	sp := NewShadowPolicy(primary, shadow, 1)

	ctx := func(i uint64) *DecisionContext {
		return &DecisionContext{State: newTestState(1), Seat: 0, DecisionIndex: i}
	}

	// First call is picked up by the worker and blocks there.
	sp.ChooseActionCtx(ctx(1))
	// Give the worker a moment to dequeue job 1 so the channel buffer (size
	// 1) is free, then fill it and overflow it.
	time.Sleep(20 * time.Millisecond)
	sp.ChooseActionCtx(ctx(2)) // fills the buffer
	sp.ChooseActionCtx(ctx(3)) // must be dropped: buffer full, worker busy

	close(shadow.release)
	sp.Close()

	metrics := sp.Metrics()
	if metrics.Dropped == 0 {
		t.Fatalf("expected at least 1 dropped decision under a full queue, got 0 (metrics=%+v)", metrics)
	}
}

func TestShadowPolicyCloseTerminatesCleanlyAndIsIdempotent(t *testing.T) {
	primary := &fixedPolicy{action: testDiscardAction(1)}
	shadow := &blockingShadow{action: testDiscardAction(1)}

	sp := NewShadowPolicy(primary, shadow, 4)
	sp.ChooseActionCtx(&DecisionContext{State: newTestState(1), Seat: 0, DecisionIndex: 1})

	done := make(chan struct{})
	go func() {
		sp.Close()
		close(done)
	}()

	select {
	case <-done:
	case <-time.After(2 * time.Second):
		t.Fatal("Close did not terminate")
	}

	// Idempotent: a second Close must not panic or hang.
	closedAgain := make(chan struct{})
	go func() {
		sp.Close()
		close(closedAgain)
	}()
	select {
	case <-closedAgain:
	case <-time.After(2 * time.Second):
		t.Fatal("second Close call hung")
	}
}

func TestShadowPolicyAgreementCounting(t *testing.T) {
	primaryAction := testDiscardAction(1)
	primary := &fixedPolicy{action: primaryAction}

	t.Run("agrees", func(t *testing.T) {
		shadow := &blockingShadow{action: testDiscardAction(1)} // same tile id -> proto.Equal true
		sp := NewShadowPolicy(primary, shadow, 4)
		sp.ChooseActionCtx(&DecisionContext{State: newTestState(1), Seat: 0, DecisionIndex: 1})
		sp.Close()

		metrics := sp.Metrics()
		if metrics.Agreements != 1 {
			t.Fatalf("expected 1 agreement, got %d (metrics=%+v)", metrics.Agreements, metrics)
		}
		if metrics.Decisions != 1 {
			t.Fatalf("expected 1 decision recorded, got %d", metrics.Decisions)
		}
	})

	t.Run("disagrees", func(t *testing.T) {
		shadow := &blockingShadow{action: testDiscardAction(2)} // different tile id
		sp := NewShadowPolicy(primary, shadow, 4)
		sp.ChooseActionCtx(&DecisionContext{State: newTestState(1), Seat: 0, DecisionIndex: 1})
		sp.Close()

		metrics := sp.Metrics()
		if metrics.Agreements != 0 {
			t.Fatalf("expected 0 agreements, got %d", metrics.Agreements)
		}
		if metrics.Decisions != 1 {
			t.Fatalf("expected 1 decision recorded, got %d", metrics.Decisions)
		}
	})
}

func TestShadowPolicyLegacyChooseActionSkipsMirroring(t *testing.T) {
	primaryAction := testDiscardAction(1)
	primary := &fixedPolicy{action: primaryAction}
	shadow := &blockingShadow{action: testDiscardAction(1)}

	sp := NewShadowPolicy(primary, shadow, 4)
	defer sp.Close()

	got := sp.ChooseAction(newTestState(1), 0)
	if got != primaryAction {
		t.Fatalf("expected primary action, got %v", got)
	}

	// Give any (incorrect) async mirroring a chance to happen, then verify
	// nothing was enqueued/recorded.
	time.Sleep(20 * time.Millisecond)
	metrics := sp.Metrics()
	if metrics.Decisions != 0 {
		t.Fatalf("legacy ChooseAction must not mirror to the shadow policy, got %d decisions", metrics.Decisions)
	}
}

// TestShadowPolicyConcurrentChooseActionDuringClose is a regression test for
// the goroutine-leak/panic fix: a room tearing down calls Close while other
// goroutines may still be mid-decision (e.g. a straggling dispatch racing
// shutdown). Concurrent ChooseActionCtx callers must never panic (send on a
// closed channel) and must keep getting the primary's action even after
// Close has fully finished. Run with -race to catch the send/close data
// race this guards against.
func TestShadowPolicyConcurrentChooseActionDuringClose(t *testing.T) {
	primaryAction := testDiscardAction(1)
	primary := &fixedPolicy{action: primaryAction}
	shadow := &blockingShadow{action: testDiscardAction(1)}

	sp := NewShadowPolicy(primary, shadow, 4)

	const goroutines = 50
	var wg sync.WaitGroup
	wg.Add(goroutines)
	start := make(chan struct{})
	for i := 0; i < goroutines; i++ {
		i := i
		go func() {
			defer wg.Done()
			<-start
			for j := 0; j < 20; j++ {
				got := sp.ChooseActionCtx(&DecisionContext{
					State:         newTestState(1),
					Seat:          0,
					DecisionIndex: uint64(i*20 + j),
				})
				if got != primaryAction {
					t.Errorf("expected primary action from concurrent ChooseActionCtx, got %v", got)
				}
			}
		}()
	}

	close(start)
	// Close concurrently with the callers above — this is the race the fix
	// targets: enqueueShadow's send racing Close's channel close.
	sp.Close()
	wg.Wait()

	// Calling after Close has fully returned must still work and must not
	// attempt to mirror (the queue is closed; enqueueShadow must see closed
	// and skip rather than panic).
	got := sp.ChooseActionCtx(&DecisionContext{State: newTestState(1), Seat: 0, DecisionIndex: 9999})
	if got != primaryAction {
		t.Fatalf("expected primary action after Close, got %v", got)
	}
}

// --- adversarial round 3, Finding 2: auditable per-decision telemetry -------------------

// TestShadowPolicyPerDecisionLogIncludesLabelAndBothActionIDs pins the
// per-decision log line's shape: it must carry the caller-supplied label
// (so concurrent rooms/seats are distinguishable in shared server logs),
// the decision index, and BOTH the primary's and the shadow's action so a
// disagreement can be diagnosed without re-running anything.
func TestShadowPolicyPerDecisionLogIncludesLabelAndBothActionIDs(t *testing.T) {
	buf := captureLog(t)

	primaryAction := testDiscardAction(1)
	primary := &fixedPolicy{action: primaryAction}
	shadow := &blockingShadow{action: testDiscardAction(2)} // deliberately disagrees

	sp := NewShadowPolicyWithLabel(primary, shadow, 4, "room=abc123 seat=2")
	sp.ChooseActionCtx(&DecisionContext{State: newTestState(1), Seat: 2, DecisionIndex: 7})
	sp.Close()

	out := buf.String()
	if !strings.Contains(out, "room=abc123 seat=2") {
		t.Fatalf("expected log to contain the label, got: %s", out)
	}
	if !strings.Contains(out, "decision_index=7") {
		t.Fatalf("expected log to contain decision_index=7, got: %s", out)
	}
	if !strings.Contains(out, "tile=1") {
		t.Fatalf("expected log to contain the primary action's tile id (1), got: %s", out)
	}
	if !strings.Contains(out, "tile=2") {
		t.Fatalf("expected log to contain the shadow action's tile id (2), got: %s", out)
	}
	if !strings.Contains(out, "agree=false") {
		t.Fatalf("expected log to report agree=false for a disagreement, got: %s", out)
	}
}

// TestShadowPolicyPerDecisionLogOnNilShadowActionNamesConcreteReason pins the
// "not just a bare nil" half of the fix: when the shadow returns nil (the
// only failure signal ChooseActionCtx exposes, e.g. remote failure with
// fallback disabled), the log line must carry a concrete, human-readable
// reason rather than silently saying only error=true.
func TestShadowPolicyPerDecisionLogOnNilShadowActionNamesConcreteReason(t *testing.T) {
	buf := captureLog(t)

	primary := &fixedPolicy{action: testDiscardAction(1)}
	shadow := &blockingShadow{action: nil} // returns nil, no panic

	sp := NewShadowPolicyWithLabel(primary, shadow, 4, "room=xyz seat=0")
	sp.ChooseActionCtx(&DecisionContext{State: newTestState(1), Seat: 0, DecisionIndex: 3})
	sp.Close()

	out := buf.String()
	if !strings.Contains(out, "error=true") {
		t.Fatalf("expected error=true in the log line, got: %s", out)
	}
	if !strings.Contains(strings.ToLower(out), "nil action") && !strings.Contains(strings.ToLower(out), "fallback") {
		t.Fatalf("expected a concrete reason naming the nil-action/fallback situation, got: %s", out)
	}
}

// TestShadowPolicyCloseEmitsSummaryLineOnce pins that Close() logs exactly
// one final per-wrapper summary line (label, decision/error/dropped/
// agreement counts, p95 latency), and that summary is not duplicated by a
// second (idempotent) Close call.
func TestShadowPolicyCloseEmitsSummaryLineOnce(t *testing.T) {
	buf := captureLog(t)

	primary := &fixedPolicy{action: testDiscardAction(1)}
	shadow := &blockingShadow{action: testDiscardAction(1)}

	sp := NewShadowPolicyWithLabel(primary, shadow, 4, "room=summary-test seat=1")
	sp.ChooseActionCtx(&DecisionContext{State: newTestState(1), Seat: 1, DecisionIndex: 1})
	sp.Close()
	sp.Close() // idempotent: must not emit a second summary line

	out := buf.String()
	count := strings.Count(out, "shadow summary")
	if count != 1 {
		t.Fatalf("expected exactly 1 shadow summary line, got %d: %s", count, out)
	}
	if !strings.Contains(out, "room=summary-test seat=1") {
		t.Fatalf("expected summary line to contain the label, got: %s", out)
	}
	if !strings.Contains(out, "decisions=1") {
		t.Fatalf("expected summary line to report decisions=1, got: %s", out)
	}
}
