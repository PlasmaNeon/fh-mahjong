package api

import (
	"context"
	"errors"
	"sync/atomic"
	"testing"
	"time"

	"github.com/plasma/fh-mahjong/internal/bot"
	pb "github.com/plasma/fh-mahjong/proto"
)

// newWarmupTestMatchmaker builds a DB-less matchmaker whose RL seats resolve to
// a plain heuristic policy (the warmup gate, not the policy wiring, is what is
// under test here).
func newWarmupTestMatchmaker() *Matchmaker {
	hub := NewHub()
	hub.BindRoom = make(chan RoomBind, 1)
	m := NewMatchmaker(NewInMemoryQueue(), nil, hub)
	m.RLAgentAvailable = func() bool { return true }
	m.SeatPolicyResolver = func(d pb.Difficulty, _ string, _ uint32) (bot.Policy, error) {
		if d == pb.Difficulty_DIFFICULTY_RL {
			return bot.NewHeuristicPolicy(), nil
		}
		return bot.NewPolicy(d)
	}
	return m
}

// configureTable creates a table hosted by user 101 with the given bot
// difficulties in seats 1..3.
func configureTable(t *testing.T, m *Matchmaker, tableID string, difficulties [3]pb.Difficulty) {
	t.Helper()
	if _, err := m.CreatePrivateTable(tableID, 101, "alice"); err != nil {
		t.Fatalf("create: %v", err)
	}
	if _, err := m.MutatePrivateTable(tableID, func(pt *PrivateTable) error {
		for i, d := range difficulties {
			if err := pt.setSeat(uint32(i+1), "bot", d); err != nil {
				return err
			}
		}
		return nil
	}); err != nil {
		t.Fatalf("configure seats: %v", err)
	}
}

// TestStartPrivateTable_WarmsRLEndpointsBeforeAdmission pins the admission
// rule: a table seating the RL agent must warm the policy endpoints before the
// room is created.
func TestStartPrivateTable_WarmsRLEndpointsBeforeAdmission(t *testing.T) {
	m := newWarmupTestMatchmaker()
	var warmCalls int32
	m.WarmRLEndpoints = func(ctx context.Context) error {
		if _, ok := ctx.Deadline(); !ok {
			t.Error("warmup hook should receive a context with the warmup budget as its deadline")
		}
		atomic.AddInt32(&warmCalls, 1)
		return nil
	}

	configureTable(t, m, "t-warm-ok", [3]pb.Difficulty{
		pb.Difficulty_DIFFICULTY_RL,
		pb.Difficulty_DIFFICULTY_HEURISTIC,
		pb.Difficulty_DIFFICULTY_HEURISTIC,
	})

	table, err := m.StartPrivateTable("t-warm-ok", 101)
	if err != nil {
		t.Fatalf("StartPrivateTable: %v", err)
	}
	if table.State != "started" {
		t.Fatalf("table state = %q, want started", table.State)
	}
	if got := atomic.LoadInt32(&warmCalls); got != 1 {
		t.Fatalf("warmup hook called %d time(s), want 1", got)
	}
}

// TestStartPrivateTable_FailsCleanlyWhenWarmupFails pins the "never silently
// play heuristic" rule: a warmup failure aborts the start with an
// ErrRLWarmupFailed-wrapped error and leaves the table configurable (so the
// host can retry).
func TestStartPrivateTable_FailsCleanlyWhenWarmupFails(t *testing.T) {
	m := newWarmupTestMatchmaker()
	warmErr := errors.New("warmup status 503: cold")
	var warmCalls int32
	m.WarmRLEndpoints = func(context.Context) error {
		atomic.AddInt32(&warmCalls, 1)
		return warmErr
	}

	configureTable(t, m, "t-warm-fail", [3]pb.Difficulty{
		pb.Difficulty_DIFFICULTY_RL,
		pb.Difficulty_DIFFICULTY_HEURISTIC,
		pb.Difficulty_DIFFICULTY_HEURISTIC,
	})

	if _, err := m.StartPrivateTable("t-warm-fail", 101); err == nil {
		t.Fatal("expected StartPrivateTable to fail when warmup fails")
	} else {
		if !errors.Is(err, ErrRLWarmupFailed) {
			t.Fatalf("error %v does not wrap ErrRLWarmupFailed", err)
		}
		if !errors.Is(err, warmErr) {
			t.Fatalf("error %v does not preserve the underlying warmup error", err)
		}
	}

	table := m.GetConfiguringPrivateTable("t-warm-fail")
	if table == nil {
		t.Fatal("table should still be configuring after a failed start")
	}
	if table.State != "configuring" {
		t.Fatalf("table state = %q, want configuring (retryable)", table.State)
	}

	// Retryable: once the hook succeeds, the same table starts.
	m.WarmRLEndpoints = func(context.Context) error { return nil }
	if _, err := m.StartPrivateTable("t-warm-fail", 101); err != nil {
		t.Fatalf("retry after warmup recovery: %v", err)
	}
	if got := atomic.LoadInt32(&warmCalls); got != 1 {
		t.Fatalf("failing hook called %d time(s), want 1", got)
	}
}

// TestStartPrivateTable_SkipsWarmupWithoutRLSeats pins that non-RL tables never
// touch the policy service: they must neither pay the warmup latency nor be
// blocked by a policy-service outage.
func TestStartPrivateTable_SkipsWarmupWithoutRLSeats(t *testing.T) {
	m := newWarmupTestMatchmaker()
	var warmCalls int32
	m.WarmRLEndpoints = func(context.Context) error {
		atomic.AddInt32(&warmCalls, 1)
		return errors.New("policy service is down")
	}

	configureTable(t, m, "t-no-rl", [3]pb.Difficulty{
		pb.Difficulty_DIFFICULTY_HEURISTIC,
		pb.Difficulty_DIFFICULTY_HEURISTIC,
		pb.Difficulty_DIFFICULTY_HEURISTIC,
	})

	if _, err := m.StartPrivateTable("t-no-rl", 101); err != nil {
		t.Fatalf("StartPrivateTable without RL seats: %v", err)
	}
	if got := atomic.LoadInt32(&warmCalls); got != 0 {
		t.Fatalf("warmup hook called %d time(s) for a table with no RL seat, want 0", got)
	}
}

// TestStartPrivateTable_WarmupDoesNotHoldTableLock pins the lock discipline:
// the (seconds-long) warm runs with table.mu RELEASED, so a concurrent
// table.mu operation — here SnapshotProto, the same lock every join/seat/state
// handler takes — completes while the warm is still in flight. Holding the
// lock across the warm would freeze the whole table for the 25s budget and
// serialize repeated Start clicks into sequential waits.
func TestStartPrivateTable_WarmupDoesNotHoldTableLock(t *testing.T) {
	m := newWarmupTestMatchmaker()
	warming := make(chan struct{}) // closed once the warm hook is running
	release := make(chan struct{}) // closed to let the warm finish
	m.WarmRLEndpoints = func(ctx context.Context) error {
		close(warming)
		select {
		case <-release:
			return nil
		case <-ctx.Done():
			return ctx.Err()
		}
	}

	configureTable(t, m, "t-warm-lock", [3]pb.Difficulty{
		pb.Difficulty_DIFFICULTY_RL,
		pb.Difficulty_DIFFICULTY_HEURISTIC,
		pb.Difficulty_DIFFICULTY_HEURISTIC,
	})
	table := m.GetConfiguringPrivateTable("t-warm-lock")
	if table == nil {
		t.Fatal("table should be configuring")
	}

	startErr := make(chan error, 1)
	go func() { _, err := m.StartPrivateTable("t-warm-lock", 101); startErr <- err }()

	<-warming // the warm is in flight; the lock must NOT be held

	snapshotted := make(chan *pb.PrivateTableState, 1)
	go func() { snapshotted <- table.SnapshotProto() }()
	select {
	case snap := <-snapshotted:
		if snap.State != "configuring" {
			t.Errorf("snapshot during warmup: state = %q, want configuring", snap.State)
		}
	case <-time.After(2 * time.Second):
		close(release)
		t.Fatal("SnapshotProto blocked while a warmup was in flight: table.mu is held across the warm")
	}

	close(release)
	if err := <-startErr; err != nil {
		t.Fatalf("StartPrivateTable: %v", err)
	}
}

// TestStartPrivateTable_RevalidatesAfterWarmup pins the other half of the
// lock-free warm: because the lock is released, the table can be reconfigured
// mid-warm — and a start must then be refused rather than proceeding on a
// configuration that was never validated (or warmed) for.
func TestStartPrivateTable_RevalidatesAfterWarmup(t *testing.T) {
	m := newWarmupTestMatchmaker()
	warming := make(chan struct{})
	release := make(chan struct{})
	m.WarmRLEndpoints = func(ctx context.Context) error {
		close(warming)
		<-release
		return nil
	}

	configureTable(t, m, "t-warm-revalidate", [3]pb.Difficulty{
		pb.Difficulty_DIFFICULTY_RL,
		pb.Difficulty_DIFFICULTY_HEURISTIC,
		pb.Difficulty_DIFFICULTY_HEURISTIC,
	})

	startErr := make(chan error, 1)
	go func() { _, err := m.StartPrivateTable("t-warm-revalidate", 101); startErr <- err }()

	<-warming
	// Swap a seat while the warm is in flight (the host clicking around in
	// another tab). This is only reachable BECAUSE the lock is released.
	if _, err := m.MutatePrivateTable("t-warm-revalidate", func(pt *PrivateTable) error {
		return pt.setSeat(2, "bot", pb.Difficulty_DIFFICULTY_RL)
	}); err != nil {
		t.Fatalf("reconfigure during warmup: %v", err)
	}
	close(release)

	err := <-startErr
	if !errors.Is(err, ErrPrivateTableChangedDuringStart) {
		t.Fatalf("err = %v, want ErrPrivateTableChangedDuringStart", err)
	}
	table := m.GetConfiguringPrivateTable("t-warm-revalidate")
	if table == nil || table.SnapshotProto().State != "configuring" {
		t.Fatal("table should still be configuring (retryable) after a mid-start reconfiguration")
	}
	// Retryable against the new configuration (re-warmed, this time without
	// the blocking stub).
	m.WarmRLEndpoints = func(context.Context) error { return nil }
	if _, err := m.StartPrivateTable("t-warm-revalidate", 101); err != nil {
		t.Fatalf("retry after reconfiguration: %v", err)
	}
}

// TestStartPrivateTable_NoWarmupHookIsANoOp keeps the default (hook unset,
// e.g. every existing test/server without warmup wiring) working unchanged.
func TestStartPrivateTable_NoWarmupHookIsANoOp(t *testing.T) {
	m := newWarmupTestMatchmaker()
	configureTable(t, m, "t-no-hook", [3]pb.Difficulty{
		pb.Difficulty_DIFFICULTY_RL,
		pb.Difficulty_DIFFICULTY_HEURISTIC,
		pb.Difficulty_DIFFICULTY_HEURISTIC,
	})
	if _, err := m.StartPrivateTable("t-no-hook", 101); err != nil {
		t.Fatalf("StartPrivateTable with no warmup hook: %v", err)
	}
}
