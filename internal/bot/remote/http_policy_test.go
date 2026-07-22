package remote

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/plasma/fh-mahjong/internal/bot"
	"github.com/plasma/fh-mahjong/internal/engine"
	"github.com/plasma/fh-mahjong/internal/rl"
	"github.com/plasma/fh-mahjong/internal/tiles"
	pb "github.com/plasma/fh-mahjong/proto"
)

func TestHTTPPolicyUsesRemoteLegalAction(t *testing.T) {
	state := testDiscardState()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || r.URL.Path != "/act" {
			t.Fatalf("unexpected request %s %s", r.Method, r.URL.Path)
		}
		var request actRequest
		if err := json.NewDecoder(r.Body).Decode(&request); err != nil {
			t.Fatalf("decode request: %v", err)
		}
		if len(request.ActionMask) != 204 {
			t.Fatalf("expected JSON action mask array, got length %d", len(request.ActionMask))
		}
		if request.ActionMask[5] != 1 {
			t.Fatalf("expected discard 1m action to be legal")
		}
		_ = json.NewEncoder(w).Encode(actResponse{ActionID: 5})
	}))
	defer server.Close()

	policy := NewHTTPPolicy(server.URL+"/act", WithLogger(nil))
	action := policy.ChooseAction(state, 0)

	if action == nil || action.Type != pb.ActionType_ACTION_DISCARD || action.Tile == nil {
		t.Fatalf("expected remote discard action, got %+v", action)
	}
	if action.Tile.Suit != pb.Suit_SUIT_MAN || action.Tile.Value != 1 {
		t.Fatalf("expected remote action to discard 1m, got %+v", action.Tile)
	}
	assertStats(t, policy.Stats(), 1, 1, 0, "")
}

func TestHTTPPolicyFallsBackOnServiceError(t *testing.T) {
	state := testDiscardState()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "unavailable", http.StatusServiceUnavailable)
	}))
	defer server.Close()

	var logs []string
	policy := NewHTTPPolicy(server.URL+"/act", WithLogger(func(format string, args ...any) {
		logs = append(logs, fmt.Sprintf(format, args...))
	}))
	action := policy.ChooseAction(state, 0)

	assertFallbackDiscard(t, action)
	assertStats(t, policy.Stats(), 1, 0, 1, FallbackReasonStatus)
	if len(logs) != 1 {
		t.Fatalf("expected one fallback log, got %d", len(logs))
	}
}

func TestHTTPPolicyFallsBackOnIllegalActionID(t *testing.T) {
	state := testDiscardState()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(actResponse{ActionID: 0})
	}))
	defer server.Close()

	policy := NewHTTPPolicy(server.URL+"/act", WithLogger(nil))
	action := policy.ChooseAction(state, 0)

	assertFallbackDiscard(t, action)
	assertStats(t, policy.Stats(), 1, 0, 1, FallbackReasonIllegalAction)
}

func TestHTTPPolicyRecordsNoFallback(t *testing.T) {
	policy := NewHTTPPolicy("", WithFallback(nil), WithLogger(nil))
	action := policy.ChooseAction(testDiscardState(), 0)

	if action != nil {
		t.Fatalf("expected nil action without fallback, got %+v", action)
	}
	stats := policy.Stats()
	if stats.RemoteCalls != 1 || stats.RemoteSuccesses != 0 || stats.Fallbacks != 1 || stats.NoFallback != 1 {
		t.Fatalf("unexpected stats: %+v", stats)
	}
	if got := stats.FallbackReasons[FallbackReasonConfig]; got != 1 {
		t.Fatalf("expected config fallback count 1, got %d", got)
	}
}

func TestHTTPPolicyLogsPeriodicStats(t *testing.T) {
	state := testDiscardState()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(actResponse{ActionID: 5})
	}))
	defer server.Close()

	var logs []string
	policy := NewHTTPPolicy(
		server.URL+"/act",
		WithLogger(func(format string, args ...any) {
			logs = append(logs, fmt.Sprintf(format, args...))
		}),
		WithStatsLogEvery(1),
	)

	action := policy.ChooseAction(state, 0)

	if action == nil {
		t.Fatal("expected remote action")
	}
	if len(logs) != 1 || !strings.Contains(logs[0], "remote policy stats") {
		t.Fatalf("expected one periodic stats log, got %#v", logs)
	}
}

func assertFallbackDiscard(t *testing.T, action *pb.PlayerAction) {
	t.Helper()
	if action == nil || action.Type != pb.ActionType_ACTION_DISCARD || action.Tile == nil {
		t.Fatalf("expected fallback discard action, got %+v", action)
	}
}

func assertStats(t *testing.T, stats HTTPPolicyStats, calls, successes, fallbacks uint64, reason string) {
	t.Helper()
	if stats.RemoteCalls != calls || stats.RemoteSuccesses != successes || stats.Fallbacks != fallbacks {
		t.Fatalf("unexpected stats: %+v", stats)
	}
	if reason != "" {
		if got := stats.FallbackReasons[reason]; got != fallbacks {
			t.Fatalf("expected fallback reason %q count %d, got %d in %+v", reason, fallbacks, got, stats)
		}
	}
}

func testDiscardState() *pb.GameState {
	hand := testTiles(
		testMan(1), testMan(2), testMan(3), testMan(4), testMan(5),
		testPin(1), testPin(2), testPin(3),
		testSou(1), testSou(2), testSou(3),
		testJihai(1), testJihai(1), testJihai(2),
	)
	return &pb.GameState{
		Phase:        pb.GamePhase_PHASE_PLAYER_TURN,
		ActivePlayer: 0,
		Players: []*pb.PlayerState{
			{
				Seat:       0,
				ClosedHand: hand,
				HandSize:   uint32(len(hand)),
				OpenMelds:  []*pb.Meld{},
				ValidActions: []*pb.PlayerAction{
					{Type: pb.ActionType_ACTION_DISCARD},
				},
			},
			{Seat: 1},
			{Seat: 2},
			{Seat: 3},
		},
		WallCount:        70,
		WangpaiTilesLeft: 14,
		DiceSum:          7,
	}
}

func testTiles(specs ...*pb.Tile) []*pb.Tile {
	out := make([]*pb.Tile, len(specs))
	for index, tile := range specs {
		copyTile := tiles.CloneTile(tile)
		copyTile.Id = uint32(index + 1)
		out[index] = copyTile
	}
	return out
}

func testMan(value uint32) *pb.Tile   { return &pb.Tile{Suit: pb.Suit_SUIT_MAN, Value: value} }
func testPin(value uint32) *pb.Tile   { return &pb.Tile{Suit: pb.Suit_SUIT_PIN, Value: value} }
func testSou(value uint32) *pb.Tile   { return &pb.Tile{Suit: pb.Suit_SUIT_SOU, Value: value} }
func testJihai(value uint32) *pb.Tile { return &pb.Tile{Suit: pb.Suit_SUIT_JIHAI, Value: value} }

// Every /act response reports which checkpoint served it; the policy must
// track the distinct identities in serving order so a mid-match hot reload
// stays attributable in the dataset.
func TestHTTPPolicyTracksObservedPolicyIDs(t *testing.T) {
	state := testDiscardState()
	checkpoints := []struct {
		path string
		step int64
	}{
		{"/models/a.pt", 100},
		{"/models/a.pt", 100}, // repeat must not duplicate
		{"/models/b.pt", 200}, // hot reload mid-match
	}
	var call int
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		ck := checkpoints[call]
		call++
		_ = json.NewEncoder(w).Encode(actResponse{ActionID: 5, CheckpointPath: ck.path, CheckpointStep: ck.step})
	}))
	defer server.Close()

	policy := NewHTTPPolicy(server.URL+"/act", WithLogger(nil))
	for range checkpoints {
		if action := policy.ChooseAction(state, 0); action == nil {
			t.Fatal("expected remote action")
		}
	}

	got := policy.ObservedPolicyIDs()
	want := []string{"a.pt@step100", "b.pt@step200"}
	if len(got) != len(want) || got[0] != want[0] || got[1] != want[1] {
		t.Fatalf("ObservedPolicyIDs() = %v, want %v", got, want)
	}
}

// Responses without checkpoint info (older servers) must not record noise.
func TestHTTPPolicyObservedPolicyIDsEmptyWithoutCheckpoint(t *testing.T) {
	state := testDiscardState()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(actResponse{ActionID: 5})
	}))
	defer server.Close()

	policy := NewHTTPPolicy(server.URL+"/act", WithLogger(nil))
	if action := policy.ChooseAction(state, 0); action == nil {
		t.Fatal("expected remote action")
	}
	if got := policy.ObservedPolicyIDs(); len(got) != 0 {
		t.Fatalf("ObservedPolicyIDs() = %v, want empty", got)
	}
}

// A response whose action fails validation must NOT attribute the checkpoint:
// the heuristic fallback played that turn, not the remote policy.
func TestHTTPPolicyDoesNotAttributeRejectedActions(t *testing.T) {
	state := testDiscardState()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(actResponse{ActionID: 999999, CheckpointPath: "/models/bad.pt", CheckpointStep: 1})
	}))
	defer server.Close()

	policy := NewHTTPPolicy(server.URL+"/act", WithLogger(nil))
	if action := policy.ChooseAction(state, 0); action == nil {
		t.Fatal("expected heuristic fallback action")
	}
	if got := policy.ObservedPolicyIDs(); len(got) != 0 {
		t.Fatalf("rejected action must not be attributed, got %v", got)
	}
}

// Identities are bounded at ingestion so a hostile/misconfigured server
// cannot bloat the persisted labels (which share a transaction with the
// match write).
func TestHTTPPolicyBoundsObservedIdentities(t *testing.T) {
	state := testDiscardState()
	long := strings.Repeat("x", 5000)
	var call int
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		call++
		_ = json.NewEncoder(w).Encode(actResponse{ActionID: 5, CheckpointPath: fmt.Sprintf("%s-%d", long, call), CheckpointStep: 1})
	}))
	defer server.Close()

	policy := NewHTTPPolicy(server.URL+"/act", WithLogger(nil))
	for i := 0; i < 20; i++ {
		if action := policy.ChooseAction(state, 0); action == nil {
			t.Fatal("expected remote action")
		}
	}
	got := policy.ObservedPolicyIDs()
	if len(got) > maxObservedPolicyIDs {
		t.Fatalf("observed list unbounded: %d entries", len(got))
	}
	for _, id := range got {
		if len(id) > maxObservedPolicyIDLen {
			t.Fatalf("identity unbounded: %d chars", len(id))
		}
	}
}

// DecisionCounts exposes how many decisions the remote actually served vs how
// many fell back to the heuristic, so persisted seats can be filtered for
// pure-RL play.
func TestHTTPPolicyDecisionCounts(t *testing.T) {
	state := testDiscardState()
	var call int
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		call++
		if call == 2 {
			http.Error(w, "boom", http.StatusInternalServerError)
			return
		}
		_ = json.NewEncoder(w).Encode(actResponse{ActionID: 5})
	}))
	defer server.Close()

	policy := NewHTTPPolicy(server.URL+"/act", WithLogger(nil))
	for i := 0; i < 3; i++ {
		if action := policy.ChooseAction(state, 0); action == nil {
			t.Fatal("expected an action (remote or fallback)")
		}
	}
	remote, fallback := policy.DecisionCounts()
	if remote != 2 || fallback != 1 {
		t.Fatalf("DecisionCounts() = (%d, %d), want (2, 1)", remote, fallback)
	}
}

func testPublicEvents(n int) []engine.PublicEvent {
	events := make([]engine.PublicEvent, 0, n)
	for i := 0; i < n; i++ {
		events = append(events, engine.PublicEvent{
			Type:     engine.EventDiscard,
			Seat:     uint32(i % 4),
			Face:     int16(i % 34),
			FromSeat: -1,
		})
	}
	return events
}

// ChooseActionCtx must encode via rl.EncodeObservationWithEvents using the
// context's decision index (not the internal p.decisionIndex counter), and
// the wire payload's compact event history must be exactly that observation's
// EventHistory: len(event_history) == event_count <= event_window, no padding.
func TestHTTPPolicyChooseActionCtxSendsCompactEventHistory(t *testing.T) {
	state := testDiscardState()
	events := testPublicEvents(10)
	const window = 4
	const decisionIndex = uint64(777)

	wantObs, err := rl.EncodeObservationWithEvents(state, 0, decisionIndex, events, window)
	if err != nil {
		t.Fatalf("EncodeObservationWithEvents: %v", err)
	}

	var got actRequest
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if err := json.NewDecoder(r.Body).Decode(&got); err != nil {
			t.Fatalf("decode request: %v", err)
		}
		_ = json.NewEncoder(w).Encode(actResponse{ActionID: 5})
	}))
	defer server.Close()

	policy := NewHTTPPolicy(server.URL+"/act", WithLogger(nil), WithEventWindow(window))
	action := policy.ChooseActionCtx(&bot.DecisionContext{
		State:         state,
		Seat:          0,
		DecisionIndex: decisionIndex,
		Events:        events,
	})
	if action == nil {
		t.Fatal("expected remote action")
	}

	if got.EventWindow != window {
		t.Fatalf("event_window = %d, want %d", got.EventWindow, window)
	}
	if got.ContractVersion != rl.EventContractV1 {
		t.Fatalf("contract_version = %d, want %d", got.ContractVersion, rl.EventContractV1)
	}
	if len(got.EventHistory) != got.EventCount {
		t.Fatalf("len(event_history)=%d != event_count=%d", len(got.EventHistory), got.EventCount)
	}
	if got.EventCount > window {
		t.Fatalf("event_count=%d exceeds window=%d", got.EventCount, window)
	}
	if len(got.EventHistory) != len(wantObs.EventHistory) {
		t.Fatalf("event_history len = %d, want %d", len(got.EventHistory), len(wantObs.EventHistory))
	}
	for i := range wantObs.EventHistory {
		if got.EventHistory[i] != wantObs.EventHistory[i] {
			t.Fatalf("event_history[%d] = %d, want %d", i, got.EventHistory[i], wantObs.EventHistory[i])
		}
	}
	// Metadata's decision_index must come from the context, never from the
	// internal (and here untouched/zero) p.decisionIndex counter.
	if got.Metadata["decision_index"].(float64) != float64(decisionIndex) {
		t.Fatalf("metadata decision_index = %v, want %d", got.Metadata["decision_index"], decisionIndex)
	}
}

// When the window exceeds the available events, the compact wire form is
// exactly len(events) long — no zero-padding out to the window size.
func TestHTTPPolicyChooseActionCtxShortHistoryNotPadded(t *testing.T) {
	state := testDiscardState()
	events := testPublicEvents(3)
	const window = 50

	var got actRequest
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if err := json.NewDecoder(r.Body).Decode(&got); err != nil {
			t.Fatalf("decode request: %v", err)
		}
		_ = json.NewEncoder(w).Encode(actResponse{ActionID: 5})
	}))
	defer server.Close()

	policy := NewHTTPPolicy(server.URL+"/act", WithLogger(nil), WithEventWindow(window))
	action := policy.ChooseActionCtx(&bot.DecisionContext{
		State:         state,
		Seat:          0,
		DecisionIndex: 1,
		Events:        events,
	})
	if action == nil {
		t.Fatal("expected remote action")
	}
	if got.EventCount != len(events) {
		t.Fatalf("event_count = %d, want %d (no padding)", got.EventCount, len(events))
	}
	if len(got.EventHistory) != len(events) {
		t.Fatalf("len(event_history) = %d, want %d (no padding)", len(got.EventHistory), len(events))
	}
}

// The legacy ChooseAction path must keep working unchanged, and must now
// always send the additive event_window/event_count/contract_version scalars
// (event_window:0) so the server can distinguish it from an event caller.
func TestHTTPPolicyChooseActionSendsLegacyEventScalars(t *testing.T) {
	state := testDiscardState()
	var got actRequest
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if err := json.NewDecoder(r.Body).Decode(&got); err != nil {
			t.Fatalf("decode request: %v", err)
		}
		_ = json.NewEncoder(w).Encode(actResponse{ActionID: 5})
	}))
	defer server.Close()

	policy := NewHTTPPolicy(server.URL+"/act", WithLogger(nil))
	action := policy.ChooseAction(state, 0)
	if action == nil {
		t.Fatal("expected remote action")
	}
	if got.EventWindow != 0 {
		t.Fatalf("legacy event_window = %d, want 0", got.EventWindow)
	}
	if got.EventCount != 0 {
		t.Fatalf("legacy event_count = %d, want 0", got.EventCount)
	}
	if got.ContractVersion != rl.EventContractV1 {
		t.Fatalf("legacy contract_version = %d, want %d", got.ContractVersion, rl.EventContractV1)
	}
	if len(got.EventHistory) != 0 {
		t.Fatalf("legacy event_history = %v, want empty", got.EventHistory)
	}
}

func TestHTTPPolicyValidateServer(t *testing.T) {
	const window = 8

	matchingServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/healthz" {
			w.WriteHeader(http.StatusNotFound)
			return
		}
		_ = json.NewEncoder(w).Encode(map[string]any{
			"ok":               true,
			"event_window":     window,
			"contract_version": rl.EventContractV1,
		})
	}))
	defer matchingServer.Close()

	mismatchedServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{
			"event_window":     window + 1,
			"contract_version": rl.EventContractV1,
		})
	}))
	defer mismatchedServer.Close()

	legacyServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{"ok": true})
	}))
	defer legacyServer.Close()

	// Matching window+version passes for an event-enabled policy.
	eventPolicy := NewHTTPPolicy(matchingServer.URL+"/act", WithLogger(nil), WithEventWindow(window))
	if err := eventPolicy.ValidateServer(context.Background()); err != nil {
		t.Fatalf("expected matching healthz to pass, got %v", err)
	}

	// Mismatched window fails for an event-enabled policy.
	mismatchedPolicy := NewHTTPPolicy(mismatchedServer.URL+"/act", WithLogger(nil), WithEventWindow(window))
	if err := mismatchedPolicy.ValidateServer(context.Background()); err == nil {
		t.Fatal("expected mismatched event_window to fail validation")
	}

	// A legacy healthz body (no event-contract fields) fails validation for
	// an event-enabled policy...
	legacyForEventPolicy := NewHTTPPolicy(legacyServer.URL+"/act", WithLogger(nil), WithEventWindow(window))
	if err := legacyForEventPolicy.ValidateServer(context.Background()); err == nil {
		t.Fatal("expected legacy healthz to fail validation for an event-enabled policy")
	}

	// ...but passes for a window-0 (event-free) policy.
	legacyForZeroPolicy := NewHTTPPolicy(legacyServer.URL+"/act", WithLogger(nil))
	if err := legacyForZeroPolicy.ValidateServer(context.Background()); err != nil {
		t.Fatalf("expected legacy healthz to pass for a window-0 policy, got %v", err)
	}

	// FINDING 1 (adversarial round 2): a window-0 policy (default
	// RL_AGENT_EVENT_WINDOW=0) talking to a server that EXPLICITLY PUBLISHES
	// an incompatible event_window (e.g. the policy service is serving
	// iter_075 at window 128) must fail validation — every /act would 400
	// and silently fall back to the heuristic otherwise.
	zeroVsPublished128Policy := NewHTTPPolicy(matchingServer.URL+"/act", WithLogger(nil))
	if err := zeroVsPublished128Policy.ValidateServer(context.Background()); err == nil {
		t.Fatal("expected window-0 policy vs server explicitly publishing event_window=8 to fail validation")
	}

	// A window-0 policy vs a server that explicitly publishes event_window=0
	// (a claim that matches) still passes.
	zeroServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{
			"ok":               true,
			"event_window":     0,
			"contract_version": rl.EventContractV1,
		})
	}))
	defer zeroServer.Close()
	zeroVsPublished0Policy := NewHTTPPolicy(zeroServer.URL+"/act", WithLogger(nil))
	if err := zeroVsPublished0Policy.ValidateServer(context.Background()); err != nil {
		t.Fatalf("expected window-0 policy vs server explicitly publishing event_window=0 to pass, got %v", err)
	}

	// FINDING 1 (round 16): non-JSON/undecodable healthz body must fail
	// validation for EVERY window, including window-0 — aligned with
	// HealthChecker.probe (health.go). Every real policy server always
	// returns JSON on /healthz, so a 2xx/non-JSON body only ever means a
	// misrouted URL, reverse-proxy error page, or SPA fallback; treating it
	// as "legacy reachability" let such an endpoint pass validation while
	// every /act would then silently fall back to the heuristic.
	nonJSONServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte("not json"))
	}))
	defer nonJSONServer.Close()

	nonJSONForZeroPolicy := NewHTTPPolicy(nonJSONServer.URL+"/act", WithLogger(nil))
	if err := nonJSONForZeroPolicy.ValidateServer(context.Background()); err == nil {
		t.Fatal("expected non-JSON healthz body to fail validation for a window-0 policy (no longer tolerated as legacy reachability)")
	}

	nonJSONForEventPolicy := NewHTTPPolicy(nonJSONServer.URL+"/act", WithLogger(nil), WithEventWindow(window))
	if err := nonJSONForEventPolicy.ValidateServer(context.Background()); err == nil {
		t.Fatal("expected non-JSON healthz body to fail validation for an event-enabled (window>0) policy")
	}

	// A misrouted URL / reverse-proxy error page / SPA fallback typically
	// returns a 2xx HTML document, not a plain string — pin that this is
	// also rejected for a window-0 policy.
	htmlServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/html")
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("<!doctype html><html><body>404 - not found</body></html>"))
	}))
	defer htmlServer.Close()

	htmlForZeroPolicy := NewHTTPPolicy(htmlServer.URL+"/act", WithLogger(nil))
	if err := htmlForZeroPolicy.ValidateServer(context.Background()); err == nil {
		t.Fatal("expected misrouted 2xx HTML/SPA-fallback body to fail validation for a window-0 policy")
	}

	// FINDING 1 (round 17): {}, null, and {"ok":false} must all fail
	// validation for a window-0 policy — serve_policy.py's /healthz ALWAYS
	// emits "ok": true on success, so anything else (including a vacuous but
	// decodable body) is never legitimate legacy reachability.
	emptyObjectServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte(`{}`))
	}))
	defer emptyObjectServer.Close()
	emptyObjectPolicy := NewHTTPPolicy(emptyObjectServer.URL+"/act", WithLogger(nil))
	if err := emptyObjectPolicy.ValidateServer(context.Background()); err == nil {
		t.Fatal("expected empty JSON object healthz body to fail validation for a window-0 policy")
	}

	nullBodyServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte(`null`))
	}))
	defer nullBodyServer.Close()
	nullBodyPolicy := NewHTTPPolicy(nullBodyServer.URL+"/act", WithLogger(nil))
	if err := nullBodyPolicy.ValidateServer(context.Background()); err == nil {
		t.Fatal("expected JSON null healthz body to fail validation for a window-0 policy")
	}

	okFalseServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{"ok": false, "checkpoint": "/models/champ.pt"})
	}))
	defer okFalseServer.Close()
	okFalsePolicy := NewHTTPPolicy(okFalseServer.URL+"/act", WithLogger(nil))
	if err := okFalsePolicy.ValidateServer(context.Background()); err == nil {
		t.Fatal("expected explicit ok=false healthz body to fail validation for a window-0 policy")
	}

	// The reconstructed true legacy /healthz payload (mirrors main's
	// serve_policy.py do_GET: always "ok": true plus checkpoint/step/sample_*
	// fields, never event_window) must pass for a window-0 policy and fail
	// for an event-enabled one.
	trueLegacyBody := map[string]any{
		"ok":                   true,
		"checkpoint":           "/models/champ.pt",
		"checkpoint_step":      1234,
		"sample_temperature":   nil,
		"sample_top_k":         nil,
		"sample_action_family": nil,
		"sample_seed":          42,
	}
	trueLegacyServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(trueLegacyBody)
	}))
	defer trueLegacyServer.Close()

	trueLegacyZeroPolicy := NewHTTPPolicy(trueLegacyServer.URL+"/act", WithLogger(nil))
	if err := trueLegacyZeroPolicy.ValidateServer(context.Background()); err != nil {
		t.Fatalf("expected true legacy healthz payload to pass for a window-0 policy, got %v", err)
	}

	trueLegacyEventPolicy := NewHTTPPolicy(trueLegacyServer.URL+"/act", WithLogger(nil), WithEventWindow(window))
	if err := trueLegacyEventPolicy.ValidateServer(context.Background()); err == nil {
		t.Fatal("expected true legacy healthz payload (no event_window) to fail validation for an event-enabled policy")
	}
}
