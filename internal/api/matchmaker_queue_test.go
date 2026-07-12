package api

import (
	"net/http"
	"testing"
)

func TestJoinQueueIsIdempotentPerRuleset(t *testing.T) {
	m := NewMatchmaker(NewInMemoryQueue(), nil, NewHub())

	if err := m.JoinQueue(42, "fenghua"); err != nil {
		t.Fatal(err)
	}
	if err := m.JoinQueue(42, "fenghua"); err != nil {
		t.Fatal(err)
	}

	if got := m.Queue.LRange("queue:fenghua"); len(got) != 1 || got[0] != "42" {
		t.Fatalf("queue = %v, want one entry for user 42", got)
	}
}

func TestLeaveQueueRemovesOnlyTheRequestedRuleset(t *testing.T) {
	m := NewMatchmaker(NewInMemoryQueue(), nil, NewHub())
	_ = m.JoinQueue(42, "fenghua")
	_ = m.JoinQueue(42, "chongci-fh")

	removed := m.LeaveQueue(42, "fenghua")

	if !removed {
		t.Fatal("expected the fenghua queue entry to be removed")
	}
	if got := m.Queue.LRange("queue:fenghua"); len(got) != 0 {
		t.Fatalf("fenghua queue = %v, want empty", got)
	}
	if got := m.Queue.LRange("queue:chongci-fh"); len(got) != 1 || got[0] != "42" {
		t.Fatalf("chongci queue = %v, want user 42 preserved", got)
	}
}

func TestLeaveQueueReportsAlreadyClaimedPlayer(t *testing.T) {
	m := NewMatchmaker(NewInMemoryQueue(), nil, NewHub())
	_ = m.JoinQueue(42, "fenghua")
	if got := m.Queue.LPopCount("queue:fenghua", 1); len(got) != 1 {
		t.Fatalf("popped = %v, want user 42", got)
	}

	if removed := m.LeaveQueue(42, "fenghua"); removed {
		t.Fatal("expected false after the matchmaker claimed the player")
	}
}

func TestLeaveQueueEndpointReturnsConflictAfterClaim(t *testing.T) {
	server := newPrivateTableTestServer()
	token := privateTableAuthToken(t, 42, "rain-player")

	joined, _ := doPrivateTableRequest(t, server, http.MethodPost, "/api/v1/matchmaking/join", token, map[string]any{"ruleset": "fenghua"})
	if joined.Code != http.StatusOK {
		t.Fatalf("join status = %d, body = %s", joined.Code, joined.Body.String())
	}
	server.Matchmaker.Queue.LPopCount("queue:fenghua", 1)

	left, body := doPrivateTableRequest(t, server, http.MethodPost, "/api/v1/matchmaking/leave", token, map[string]any{"ruleset": "fenghua"})
	if left.Code != http.StatusConflict {
		t.Fatalf("leave status = %d, want 409; body = %s", left.Code, left.Body.String())
	}
	if body["status"] != "match_forming" {
		t.Fatalf("status = %#v, want match_forming", body["status"])
	}
}
