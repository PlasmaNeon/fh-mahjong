package bot

import (
	"sync/atomic"
	"testing"
	"time"

	pb "github.com/plasma/fh-mahjong/proto"
)

// slowShadow is a ContextPolicy stub whose calls block until delay is
// closed, simulating a shadow policy with a bounded-but-nonzero per-call
// latency (analogous to remote.HTTPPolicy's real HTTP timeout in
// production). calls counts how many times it was actually invoked, so
// tests can assert a discarded backlog never reached the shadow policy at
// all.
type slowShadow struct {
	delay  chan struct{}
	action *pb.PlayerAction
	calls  int32
}

func (s *slowShadow) ChooseActionCtx(ctx *DecisionContext) *pb.PlayerAction {
	atomic.AddInt32(&s.calls, 1)
	<-s.delay
	return s.action
}

// --- adversarial round 24, Finding 2: teardown must discard, not drain -----

// TestShadowPolicyCloseDiscardsBacklogInsteadOfDraining pins the fix: Close
// must not run a full, queued backlog through the shadow policy one by one
// (which could take up to queueSize x the shadow policy's own timeout, far
// exceeding a room's shutdown budget). It must instead let only the
// currently in-flight call finish, then discard everything still queued —
// counting the discarded remainder into Dropped — and return well within a
// small bound regardless of how large or slow the backlog is.
func TestShadowPolicyCloseDiscardsBacklogInsteadOfDraining(t *testing.T) {
	primary := &fixedPolicy{action: testDiscardAction(1)}
	delay := make(chan struct{})
	shadow := &slowShadow{delay: delay, action: testDiscardAction(1)}

	const queueSize = 64
	sp := NewShadowPolicy(primary, shadow, queueSize)

	// The in-flight call finishes on its own after a short, bounded delay
	// (standing in for the shadow policy's own real HTTP timeout) —
	// independent of when Close is invoked below.
	go func() {
		time.Sleep(50 * time.Millisecond)
		close(delay)
	}()

	// Enqueue enough decisions to fill the buffered queue plus one that the
	// worker immediately dequeues and blocks on (the "current in-flight
	// call"). All of these must be either the one in-flight call or part of
	// the discarded backlog — never individually executed one-by-one.
	for i := 0; i < queueSize+1; i++ {
		sp.ChooseActionCtx(&DecisionContext{State: newTestState(1), Seat: 0, DecisionIndex: uint64(i)})
	}
	// Give the worker a moment to actually dequeue job #1 and block inside
	// evaluate() on delay, so the remaining enqueues sit in the backlog
	// rather than also being picked up before Close runs.
	time.Sleep(20 * time.Millisecond)

	closeDone := make(chan struct{})
	start := time.Now()
	go func() {
		sp.Close()
		close(closeDone)
	}()

	select {
	case <-closeDone:
	case <-time.After(3 * time.Second):
		t.Fatal("Close did not return within bound — appears to be draining the full backlog instead of discarding it")
	}
	elapsed := time.Since(start)
	if elapsed >= 2*time.Second {
		t.Fatalf("Close took %v (>= 2s bound); teardown must discard the queued backlog, not execute it", elapsed)
	}

	// workerDone must actually be closed (not just "Close returned because
	// something else unblocked it") — confirms the worker goroutine itself
	// exited rather than leaking.
	select {
	case <-sp.workerDone:
	default:
		t.Fatal("workerDone was not closed after Close returned")
	}

	metrics := sp.Metrics()
	if metrics.Dropped == 0 {
		t.Fatalf("expected the discarded backlog to be counted as Dropped, got 0 (metrics=%+v)", metrics)
	}
	// At most the one in-flight call (plus, in the rare case the worker's
	// stop-check loses the select race once, one extra) should have actually
	// reached the shadow policy — the rest of the backlog must never be
	// executed.
	if calls := atomic.LoadInt32(&shadow.calls); calls > 2 {
		t.Fatalf("expected at most ~1 job to actually reach the shadow policy before discarding kicked in, got %d calls", calls)
	}
}

// TestShadowPolicyIdleCloseUnaffectedByDiscardChange pins that Close on an
// idle (empty-queue) ShadowPolicy is unchanged by the discard-on-teardown
// fix: nothing to discard, Dropped stays 0, and Close still returns quickly.
func TestShadowPolicyIdleCloseUnaffectedByDiscardChange(t *testing.T) {
	primary := &fixedPolicy{action: testDiscardAction(1)}
	shadow := &blockingShadow{action: testDiscardAction(1)}

	sp := NewShadowPolicy(primary, shadow, 4)
	sp.ChooseActionCtx(&DecisionContext{State: newTestState(1), Seat: 0, DecisionIndex: 1})
	waitForDecisions(t, sp, 1)

	closeDone := make(chan struct{})
	go func() {
		sp.Close()
		close(closeDone)
	}()
	select {
	case <-closeDone:
	case <-time.After(2 * time.Second):
		t.Fatal("idle Close did not return promptly")
	}

	metrics := sp.Metrics()
	if metrics.Dropped != 0 {
		t.Fatalf("expected 0 dropped on an idle Close, got %d", metrics.Dropped)
	}
	if metrics.Decisions != 1 {
		t.Fatalf("expected the single enqueued decision to have been evaluated, got %d decisions", metrics.Decisions)
	}
}
