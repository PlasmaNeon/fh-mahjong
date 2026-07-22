package remote_test

// FINDING 2 coverage: a shadow-mode candidate policy (bot.ShadowPolicy
// wrapping a remote.HTTPPolicy) must count a dead or contract-rejecting
// candidate endpoint as a shadow error, never as a quiet fallback success —
// otherwise the runbook's zero-shadow-error gate would pass with the
// candidate down. This lives in an external _test package (not `package
// remote`) because bot.ShadowPolicy (internal/bot) can't be imported from
// inside internal/bot/remote without an import cycle (remote already imports
// bot); a black-box integration test importing both packages has no such
// restriction.

import (
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/plasma/fh-mahjong/internal/bot"
	"github.com/plasma/fh-mahjong/internal/bot/remote"
	pb "github.com/plasma/fh-mahjong/proto"
)

// fixedPrimaryPolicy always returns the same action, standing in for the
// live-serving primary/champion policy that ShadowPolicy wraps.
type fixedPrimaryPolicy struct {
	action *pb.PlayerAction
}

func (f *fixedPrimaryPolicy) ChooseAction(_ *pb.GameState, _ uint32) *pb.PlayerAction {
	return f.action
}

func (f *fixedPrimaryPolicy) ChooseActionCtx(_ *bot.DecisionContext) *pb.PlayerAction {
	return f.action
}

var _ bot.Policy = (*fixedPrimaryPolicy)(nil)
var _ bot.ContextPolicy = (*fixedPrimaryPolicy)(nil)

func testShadowState() *pb.GameState {
	return &pb.GameState{
		Phase:        pb.GamePhase_PHASE_PLAYER_TURN,
		ActivePlayer: 0,
		Players: []*pb.PlayerState{
			{Seat: 0}, {Seat: 1}, {Seat: 2}, {Seat: 3},
		},
	}
}

// waitForShadowDecision polls sp.Metrics().Decisions until the worker has
// processed at least one, or fails the test after a short bound (see round
// 24's Close doc for why this can no longer be assumed synchronously after
// enqueueing).
func waitForShadowDecision(t *testing.T, sp *bot.ShadowPolicy) {
	t.Helper()
	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		if sp.Metrics().Decisions >= 1 {
			return
		}
		time.Sleep(time.Millisecond)
	}
	t.Fatalf("timed out waiting for the shadow worker to process a decision, got %d", sp.Metrics().Decisions)
}

func shadowMetricsAfterOneDecision(t *testing.T, shadowHTTPPolicy *remote.HTTPPolicy) bot.ShadowMetrics {
	t.Helper()
	primaryAction := &pb.PlayerAction{Type: pb.ActionType_ACTION_DISCARD}
	primary := &fixedPrimaryPolicy{action: primaryAction}

	sp := bot.NewShadowPolicy(primary, shadowHTTPPolicy, 4)
	defer sp.Close()

	got := sp.ChooseActionCtx(&bot.DecisionContext{State: testShadowState(), Seat: 0, DecisionIndex: 1})
	if got != primaryAction {
		t.Fatalf("expected the primary's action returned unchanged, got %v", got)
	}
	// Round 24: Close no longer guarantees a queued-but-not-yet-started job
	// gets evaluated before the worker exits (mirroring is best-effort
	// telemetry, not something teardown owes the queue — see
	// bot.ShadowPolicy's Close/discardRemaining). Confirm the worker
	// actually reached this decision before tearing down, so the metrics
	// below are deterministic instead of racing worker scheduling.
	waitForShadowDecision(t, sp)
	sp.Close() // idempotent; the decision above is already accounted for
	return sp.Metrics()
}

// An unreachable candidate endpoint, with its fallback disabled
// (remote.WithFallback(nil), as cmd/server must construct the shadow
// candidate), must surface as a shadow error — not a silent
// agreement-miss and not a masked success.
func TestShadowPolicy_UnreachableCandidateCountsAsShadowError(t *testing.T) {
	shadowHTTPPolicy := remote.NewHTTPPolicy(
		"http://127.0.0.1:1/act", // nothing listens here
		remote.WithFallback(nil),
		remote.WithLogger(nil),
	)

	metrics := shadowMetricsAfterOneDecision(t, shadowHTTPPolicy)
	if metrics.ShadowErrors != 1 {
		t.Fatalf("ShadowErrors = %d, want 1 (unreachable candidate must count as a shadow error)", metrics.ShadowErrors)
	}
	if metrics.Agreements != 0 {
		t.Fatalf("Agreements = %d, want 0", metrics.Agreements)
	}
}

// A candidate endpoint that rejects the request (contract mismatch, modeled
// here as an HTTP 400) must likewise count as a shadow error when the
// fallback is disabled.
func TestShadowPolicy_ContractMismatchCandidateCountsAsShadowError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "contract mismatch", http.StatusBadRequest)
	}))
	defer server.Close()

	shadowHTTPPolicy := remote.NewHTTPPolicy(
		server.URL+"/act",
		remote.WithFallback(nil),
		remote.WithLogger(nil),
	)

	metrics := shadowMetricsAfterOneDecision(t, shadowHTTPPolicy)
	if metrics.ShadowErrors != 1 {
		t.Fatalf("ShadowErrors = %d, want 1 (400/contract-mismatch candidate must count as a shadow error)", metrics.ShadowErrors)
	}
	if metrics.Agreements != 0 {
		t.Fatalf("Agreements = %d, want 0", metrics.Agreements)
	}
}
