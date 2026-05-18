package remote

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

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
	tiles := make([]*pb.Tile, len(specs))
	for index, tile := range specs {
		copyTile := *tile
		copyTile.Id = uint32(index + 1)
		tiles[index] = &copyTile
	}
	return tiles
}

func testMan(value uint32) *pb.Tile   { return &pb.Tile{Suit: pb.Suit_SUIT_MAN, Value: value} }
func testPin(value uint32) *pb.Tile   { return &pb.Tile{Suit: pb.Suit_SUIT_PIN, Value: value} }
func testSou(value uint32) *pb.Tile   { return &pb.Tile{Suit: pb.Suit_SUIT_SOU, Value: value} }
func testJihai(value uint32) *pb.Tile { return &pb.Tile{Suit: pb.Suit_SUIT_JIHAI, Value: value} }
