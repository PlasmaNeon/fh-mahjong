package api

import (
	"errors"
	"net/http"
	"sync/atomic"
	"testing"

	"github.com/plasma/fh-mahjong/internal/bot"
	pb "github.com/plasma/fh-mahjong/proto"
)

// countingCloseablePolicy is a bot.Policy that also implements
// closeableBotPolicy, tracking how many times it was constructed (via the
// shared constructorCalls counter) and closed.
type countingCloseablePolicy struct {
	closed *int32
}

func (countingCloseablePolicy) ChooseAction(_ *pb.GameState, _ uint32) *pb.PlayerAction {
	return nil
}

func (p countingCloseablePolicy) Close() {
	atomic.AddInt32(p.closed, 1)
}

// TestValidateSeatDifficulty_DoesNotConstructPolicy pins the adversarial
// round-4 Finding 1(a) fix: seat-difficulty VALIDATION (used by
// handlePrivateTableSeat before a seat is actually assigned) must not invoke
// the SeatPolicyResolver at all. Previously, validation called
// resolveSeatPolicy purely to check the difficulty was acceptable and threw
// away the result — with shadow mode configured, cmd/server's resolver
// constructs a bot.ShadowPolicy whose worker goroutine starts immediately, so
// a host repeating the seat request would leak one goroutine per call. This
// resolver counts constructor calls; assigning an RL seat (available) must
// leave the counter at 0.
func TestValidateSeatDifficulty_DoesNotConstructPolicy(t *testing.T) {
	var constructorCalls int32
	server := newPrivateTableTestServer()
	server.Matchmaker.RLAgentAvailable = func() bool { return true }
	server.Matchmaker.SeatPolicyResolver = func(d pb.Difficulty, _ string, _ uint32) (bot.Policy, error) {
		atomic.AddInt32(&constructorCalls, 1)
		if d == pb.Difficulty_DIFFICULTY_RL {
			return bot.NewHeuristicPolicy(), nil
		}
		return bot.NewPolicy(d)
	}

	hostToken := privateTableAuthToken(t, 101, "alice")
	doPrivateTableRequest(t, server, http.MethodPost, "/api/v1/rooms/rl-validate/join", hostToken, map[string]any{})

	recorder, _ := doPrivateTableRequest(t, server, http.MethodPost, "/api/v1/rooms/rl-validate/seat", hostToken, map[string]any{
		"seat":       1,
		"kind":       "bot",
		"difficulty": int(pb.Difficulty_DIFFICULTY_RL),
	})
	if recorder.Code != http.StatusOK {
		t.Fatalf("expected 200 assigning RL seat, got %d: %s", recorder.Code, recorder.Body.String())
	}
	if got := atomic.LoadInt32(&constructorCalls); got != 0 {
		t.Fatalf("seat validation must not construct a policy, but SeatPolicyResolver was called %d time(s)", got)
	}
}

// TestStartPrivateTable_ClosesEarlierSeatPoliciesOnLaterSeatFailure pins
// Finding 1(b): when a later seat's resolution fails inside StartPrivateTable,
// every closeable policy already constructed for an earlier seat must be
// closed before the error is returned — otherwise a ShadowPolicy's worker
// goroutine (and queue) leaks for good, since no Room is ever created to own
// it.
func TestStartPrivateTable_ClosesEarlierSeatPoliciesOnLaterSeatFailure(t *testing.T) {
	var closedCount int32
	hub := NewHub()
	hub.BindRoom = make(chan RoomBind, 1)
	m := NewMatchmaker(NewInMemoryQueue(), nil, hub)

	m.SeatPolicyResolver = func(d pb.Difficulty, _ string, seat uint32) (bot.Policy, error) {
		if seat == 2 {
			return nil, errors.New("boom: seat 2 resolution failed")
		}
		return countingCloseablePolicy{closed: &closedCount}, nil
	}

	if _, err := m.CreatePrivateTable("t-leak", 101, "alice"); err != nil {
		t.Fatalf("create: %v", err)
	}
	if _, err := m.MutatePrivateTable("t-leak", func(pt *PrivateTable) error {
		if err := pt.setSeat(1, "bot", pb.Difficulty_DIFFICULTY_HEURISTIC); err != nil {
			return err
		}
		if err := pt.setSeat(2, "bot", pb.Difficulty_DIFFICULTY_HEURISTIC); err != nil {
			return err
		}
		return pt.setSeat(3, "bot", pb.Difficulty_DIFFICULTY_HEURISTIC)
	}); err != nil {
		t.Fatalf("configure seats: %v", err)
	}

	if _, err := m.StartPrivateTable("t-leak", 101); err == nil {
		t.Fatal("expected StartPrivateTable to fail when seat 2 resolution errors")
	}

	// Seat 1's policy was constructed before seat 2 failed; it must have been
	// closed rather than leaked.
	if got := atomic.LoadInt32(&closedCount); got != 1 {
		t.Fatalf("expected 1 earlier-seat policy closed after later-seat failure, got %d", got)
	}
}
