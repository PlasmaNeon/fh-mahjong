package api

import (
	"net/http"
	"testing"
)

// The reported bug was that opening different private-room links dropped the
// user into the same game. The root cause was front-end (a global socket +
// stale game state + an unconditional redirect), but the backend must give the
// waiting-room page a strictly room-scoped signal so the redirect can be made
// safe: "is THIS room's match active for me?" — never a global "am I in any
// match" answer. These tests pin that contract on GET /rooms/:roomId.

// A participant of an active table learns the live match via GET on that table,
// so a genuine reload/rejoin lands back in the right match.
func TestPrivateTableGetReportsActiveMatchForParticipant(t *testing.T) {
	server := newPrivateTableTestServer()
	server.Matchmaker.registerActivePrivateTable("alpha", "match-alpha", []uint{101, 102, 103, 104}, nil)

	rec, body := doPrivateTableRequest(t, server, http.MethodGet, "/api/v1/rooms/alpha", privateTableAuthToken(t, 101, "alice"), nil)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	if body["status"] != "active" || body["matchId"] != "match-alpha" {
		t.Fatalf("expected active+match-alpha, got %#v", body)
	}
}

// Opening a DIFFERENT room link while you have a live match elsewhere must not
// leak (or redirect into) that match. The other room is simply not active, so
// GET reports "not found" rather than the active match in alpha.
func TestPrivateTableGetDifferentRoomDoesNotLeakActiveMatch(t *testing.T) {
	server := newPrivateTableTestServer()
	server.Matchmaker.registerActivePrivateTable("alpha", "match-alpha", []uint{101, 102, 103, 104}, nil)

	rec, body := doPrivateTableRequest(t, server, http.MethodGet, "/api/v1/rooms/beta", privateTableAuthToken(t, 101, "alice"), nil)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("expected 404 for a different, non-active room, got %d: %#v", rec.Code, body)
	}
	if body["matchId"] == "match-alpha" {
		t.Fatalf("BUG: GET on a different room leaked the active match in alpha: %#v", body)
	}
}

// A user who is creating a fresh, different room can still do so while a prior
// match is live elsewhere — distinct links are distinct rooms.
func TestPrivateTableJoinDifferentRoomCreatesDistinctTable(t *testing.T) {
	server := newPrivateTableTestServer()
	server.Matchmaker.registerActivePrivateTable("alpha", "match-alpha", []uint{101, 102, 103, 104}, nil)

	rec, body := doPrivateTableRequest(t, server, http.MethodPost, "/api/v1/rooms/beta/join", privateTableAuthToken(t, 101, "alice"), map[string]any{})
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200 creating a distinct room, got %d: %s", rec.Code, rec.Body.String())
	}
	if body["tableId"] != "beta" || body["state"] != "configuring" {
		t.Fatalf("expected a fresh configuring table 'beta', got %#v", body)
	}
}
