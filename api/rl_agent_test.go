package api

import (
	"net/http"
	"testing"

	"github.com/plasma/fh-mahjong/bot"
	pb "github.com/plasma/fh-mahjong/proto"
)

// rlTestResolver maps DIFFICULTY_RL to a stand-in policy and defers everything
// else to bot.NewPolicy, mirroring how cmd/server installs the real remote
// resolver when AI_BOT_POLICY_URL is set.
func rlTestResolver(d pb.Difficulty) (bot.Policy, error) {
	if d == pb.Difficulty_DIFFICULTY_RL {
		return bot.NewHeuristicPolicy(), nil
	}
	return bot.NewPolicy(d)
}

func TestResolveSeatPolicy_DefaultRejectsRL(t *testing.T) {
	m := NewMatchmaker(NewInMemoryQueue(), nil, NewHub())

	if _, err := m.resolveSeatPolicy(pb.Difficulty_DIFFICULTY_HEURISTIC); err != nil {
		t.Fatalf("heuristic should resolve without a custom resolver: %v", err)
	}
	if _, err := m.resolveSeatPolicy(pb.Difficulty_DIFFICULTY_RL); err == nil {
		t.Fatal("expected error resolving DIFFICULTY_RL with no resolver installed")
	}
}

func TestResolveSeatPolicy_WithResolver(t *testing.T) {
	m := NewMatchmaker(NewInMemoryQueue(), nil, NewHub())
	m.SeatPolicyResolver = rlTestResolver

	policy, err := m.resolveSeatPolicy(pb.Difficulty_DIFFICULTY_RL)
	if err != nil {
		t.Fatalf("expected RL to resolve with resolver installed: %v", err)
	}
	if policy == nil {
		t.Fatal("expected non-nil policy for DIFFICULTY_RL")
	}
}

func TestPrivateTableSeat_RLRejectedWhenUnavailable(t *testing.T) {
	server := newPrivateTableTestServer()
	hostToken := privateTableAuthToken(t, 101, "alice")
	doPrivateTableRequest(t, server, http.MethodPost, "/api/v1/rooms/rl-off/join", hostToken, map[string]any{})

	recorder, _ := doPrivateTableRequest(t, server, http.MethodPost, "/api/v1/rooms/rl-off/seat", hostToken, map[string]any{
		"seat":       1,
		"kind":       "bot",
		"difficulty": int(pb.Difficulty_DIFFICULTY_RL),
	})
	if recorder.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 assigning RL seat when unavailable, got %d: %s", recorder.Code, recorder.Body.String())
	}
}

func TestPrivateTableSeat_RLAcceptedWhenAvailable(t *testing.T) {
	server := newPrivateTableTestServer()
	server.Matchmaker.SeatPolicyResolver = rlTestResolver
	server.Matchmaker.RLAgentAvailable = func() bool { return true }

	hostToken := privateTableAuthToken(t, 101, "alice")
	doPrivateTableRequest(t, server, http.MethodPost, "/api/v1/rooms/rl-on/join", hostToken, map[string]any{})

	recorder, body := doPrivateTableRequest(t, server, http.MethodPost, "/api/v1/rooms/rl-on/seat", hostToken, map[string]any{
		"seat":       1,
		"kind":       "bot",
		"difficulty": int(pb.Difficulty_DIFFICULTY_RL),
	})
	if recorder.Code != http.StatusOK {
		t.Fatalf("expected 200 assigning RL seat when available, got %d: %s", recorder.Code, recorder.Body.String())
	}
	seats, _ := body["seats"].([]any)
	second, _ := seats[1].(map[string]any)
	if second["kind"] != "bot" {
		t.Fatalf("expected seat 1 kind=bot, got %#v", second)
	}
	if got, _ := second["difficulty"].(float64); pb.Difficulty(got) != pb.Difficulty_DIFFICULTY_RL {
		t.Fatalf("expected seat 1 difficulty=RL(2), got %#v", second["difficulty"])
	}
}

func TestPrivateTableSeat_RLRejectedWhenUnhealthy(t *testing.T) {
	// Resolver is installed (so the policy is buildable), but the health probe
	// reports the endpoint down. The seat assignment must still be rejected so
	// the host can't pick an agent that isn't actually reachable.
	server := newPrivateTableTestServer()
	server.Matchmaker.SeatPolicyResolver = rlTestResolver
	server.Matchmaker.RLAgentAvailable = func() bool { return false }

	hostToken := privateTableAuthToken(t, 101, "alice")
	doPrivateTableRequest(t, server, http.MethodPost, "/api/v1/rooms/rl-down/join", hostToken, map[string]any{})

	recorder, _ := doPrivateTableRequest(t, server, http.MethodPost, "/api/v1/rooms/rl-down/seat", hostToken, map[string]any{
		"seat":       1,
		"kind":       "bot",
		"difficulty": int(pb.Difficulty_DIFFICULTY_RL),
	})
	if recorder.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 assigning RL seat while unhealthy, got %d: %s", recorder.Code, recorder.Body.String())
	}
}

func TestHandleConfig_DefaultUnavailable(t *testing.T) {
	server := newPrivateTableTestServer()

	recorder, body := doPrivateTableRequest(t, server, http.MethodGet, "/api/v1/config", "", nil)
	if recorder.Code != http.StatusOK {
		t.Fatalf("expected 200 from /config, got %d", recorder.Code)
	}
	if available, _ := body["rlAgentAvailable"].(bool); available {
		t.Fatalf("expected rlAgentAvailable=false by default, got %#v", body["rlAgentAvailable"])
	}
}

func TestHandleConfig_Available(t *testing.T) {
	server := newPrivateTableTestServer()
	server.Matchmaker.RLAgentAvailable = func() bool { return true }

	recorder, body := doPrivateTableRequest(t, server, http.MethodGet, "/api/v1/config", "", nil)
	if recorder.Code != http.StatusOK {
		t.Fatalf("expected 200 from /config, got %d", recorder.Code)
	}
	if available, _ := body["rlAgentAvailable"].(bool); !available {
		t.Fatalf("expected rlAgentAvailable=true, got %#v", body["rlAgentAvailable"])
	}
}
