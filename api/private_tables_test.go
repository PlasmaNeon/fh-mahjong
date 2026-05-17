package api

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
	pb "github.com/plasma/fh-mahjong/proto"
)

func privateTableAuthToken(t *testing.T, userID uint, username string) string {
	t.Helper()

	token := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.MapClaims{
		"sub":      userID,
		"username": username,
		"exp":      time.Now().Add(time.Hour).Unix(),
	})
	tokenString, err := token.SignedString(jwtSecret)
	if err != nil {
		t.Fatalf("failed to sign test token: %v", err)
	}
	return tokenString
}

func doPrivateTableRequest(t *testing.T, server *Server, method, path, token string, body any) (*httptest.ResponseRecorder, map[string]any) {
	t.Helper()

	var payload []byte
	if body != nil {
		var err error
		payload, err = json.Marshal(body)
		if err != nil {
			t.Fatalf("marshal body: %v", err)
		}
	}

	req := httptest.NewRequest(method, path, bytes.NewReader(payload))
	if payload != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	if token != "" {
		req.Header.Set("Authorization", "Bearer "+token)
	}
	recorder := httptest.NewRecorder()
	server.Router.ServeHTTP(recorder, req)

	var parsed map[string]any
	if recorder.Body.Len() > 0 {
		_ = json.Unmarshal(recorder.Body.Bytes(), &parsed)
	}
	return recorder, parsed
}

func newPrivateTableTestServer() *Server {
	hub := NewHub()
	go hub.Run()
	matchmaker := NewMatchmaker(NewInMemoryQueue(), nil, hub)
	return NewServer(nil, hub, matchmaker)
}

func TestPrivateTableJoinAssignsHost(t *testing.T) {
	server := newPrivateTableTestServer()

	recorder, body := doPrivateTableRequest(t, server, http.MethodPost, "/api/v1/private-tables/test-room/join", privateTableAuthToken(t, 101, "alice"), map[string]any{})

	if recorder.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", recorder.Code, recorder.Body.String())
	}
	if got, _ := body["hostUserId"].(float64); uint(got) != 101 {
		t.Fatalf("expected host 101, got %#v", body["hostUserId"])
	}
	seats, _ := body["seats"].([]any)
	if len(seats) != 4 {
		t.Fatalf("expected 4 seats, got %d", len(seats))
	}
	first, _ := seats[0].(map[string]any)
	if first["kind"] != "human" || uint(first["userId"].(float64)) != 101 {
		t.Fatalf("expected seat 0 = alice, got %#v", first)
	}
}

func TestPrivateTableSecondJoinClaimsNextSeat(t *testing.T) {
	server := newPrivateTableTestServer()
	doPrivateTableRequest(t, server, http.MethodPost, "/api/v1/private-tables/test-room/join", privateTableAuthToken(t, 101, "alice"), map[string]any{})

	recorder, body := doPrivateTableRequest(t, server, http.MethodPost, "/api/v1/private-tables/test-room/join", privateTableAuthToken(t, 102, "bob"), map[string]any{})
	if recorder.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", recorder.Code)
	}
	seats, _ := body["seats"].([]any)
	second, _ := seats[1].(map[string]any)
	if second["kind"] != "human" || uint(second["userId"].(float64)) != 102 {
		t.Fatalf("expected seat 1 = bob, got %#v", second)
	}
}

func TestPrivateTableHostSetsBotSeat(t *testing.T) {
	server := newPrivateTableTestServer()
	doPrivateTableRequest(t, server, http.MethodPost, "/api/v1/private-tables/test-room/join", privateTableAuthToken(t, 101, "alice"), map[string]any{})

	recorder, body := doPrivateTableRequest(t, server, http.MethodPost, "/api/v1/private-tables/test-room/seat", privateTableAuthToken(t, 101, "alice"), map[string]any{
		"seat":       1,
		"kind":       "bot",
		"difficulty": int(pb.Difficulty_DIFFICULTY_HEURISTIC),
	})
	if recorder.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", recorder.Code, recorder.Body.String())
	}
	seats, _ := body["seats"].([]any)
	second, _ := seats[1].(map[string]any)
	if second["kind"] != "bot" {
		t.Fatalf("expected seat 1 kind=bot, got %#v", second)
	}
}

func TestPrivateTableNonHostCannotMutateSeat(t *testing.T) {
	server := newPrivateTableTestServer()
	doPrivateTableRequest(t, server, http.MethodPost, "/api/v1/private-tables/test-room/join", privateTableAuthToken(t, 101, "alice"), map[string]any{})
	doPrivateTableRequest(t, server, http.MethodPost, "/api/v1/private-tables/test-room/join", privateTableAuthToken(t, 102, "bob"), map[string]any{})

	recorder, _ := doPrivateTableRequest(t, server, http.MethodPost, "/api/v1/private-tables/test-room/seat", privateTableAuthToken(t, 102, "bob"), map[string]any{
		"seat":       2,
		"kind":       "bot",
		"difficulty": int(pb.Difficulty_DIFFICULTY_HEURISTIC),
	})
	if recorder.Code != http.StatusForbidden {
		t.Fatalf("expected 403 for non-host, got %d", recorder.Code)
	}
}

func TestPrivateTableStartRejectsEmptySeats(t *testing.T) {
	server := newPrivateTableTestServer()
	doPrivateTableRequest(t, server, http.MethodPost, "/api/v1/private-tables/test-room/join", privateTableAuthToken(t, 101, "alice"), map[string]any{})

	recorder, _ := doPrivateTableRequest(t, server, http.MethodPost, "/api/v1/private-tables/test-room/start", privateTableAuthToken(t, 101, "alice"), map[string]any{})
	if recorder.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 when seats not full, got %d", recorder.Code)
	}
}

func TestPrivateTableStartWithThreeBots(t *testing.T) {
	server := newPrivateTableTestServer()
	hostToken := privateTableAuthToken(t, 101, "alice")
	doPrivateTableRequest(t, server, http.MethodPost, "/api/v1/private-tables/test-room/join", hostToken, map[string]any{})

	for _, seat := range []uint32{1, 2, 3} {
		recorder, _ := doPrivateTableRequest(t, server, http.MethodPost, "/api/v1/private-tables/test-room/seat", hostToken, map[string]any{
			"seat":       seat,
			"kind":       "bot",
			"difficulty": int(pb.Difficulty_DIFFICULTY_HEURISTIC),
		})
		if recorder.Code != http.StatusOK {
			t.Fatalf("seat %d setup failed: %d", seat, recorder.Code)
		}
	}

	recorder, body := doPrivateTableRequest(t, server, http.MethodPost, "/api/v1/private-tables/test-room/start", hostToken, map[string]any{})
	if recorder.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", recorder.Code, recorder.Body.String())
	}
	if body["state"] != "started" {
		t.Fatalf("expected state=started, got %#v", body["state"])
	}
	matchID, _ := body["matchId"].(string)
	if matchID == "" {
		t.Fatal("matchId missing from response body")
	}

	active, ok := server.Matchmaker.GetActivePrivateTable("test-room")
	if !ok {
		t.Fatalf("expected active private table after start, but registry has none")
	}
	if active.MatchID != matchID {
		t.Fatalf("expected active MatchID %q, got %q", matchID, active.MatchID)
	}
	if _, isParticipant := active.ParticipantIDs[101]; !isParticipant {
		t.Fatalf("expected user 101 in active participant set, got %#v", active.ParticipantIDs)
	}
}

func TestPrivateTableStartRejectsNonHost(t *testing.T) {
	server := newPrivateTableTestServer()
	hostToken := privateTableAuthToken(t, 101, "alice")
	otherToken := privateTableAuthToken(t, 102, "bob")
	doPrivateTableRequest(t, server, http.MethodPost, "/api/v1/private-tables/test-room/join", hostToken, map[string]any{})
	doPrivateTableRequest(t, server, http.MethodPost, "/api/v1/private-tables/test-room/join", otherToken, map[string]any{})
	for _, seat := range []uint32{2, 3} {
		doPrivateTableRequest(t, server, http.MethodPost, "/api/v1/private-tables/test-room/seat", hostToken, map[string]any{
			"seat":       seat,
			"kind":       "bot",
			"difficulty": int(pb.Difficulty_DIFFICULTY_HEURISTIC),
		})
	}

	recorder, _ := doPrivateTableRequest(t, server, http.MethodPost, "/api/v1/private-tables/test-room/start", otherToken, map[string]any{})
	if recorder.Code != http.StatusForbidden {
		t.Fatalf("expected 403 for non-host start, got %d", recorder.Code)
	}
}

func TestPrivateTableJoinReturnsActiveForExistingParticipant(t *testing.T) {
	server := newPrivateTableTestServer()
	server.Matchmaker.registerActivePrivateTable("test-room", "match-123", []uint{101, 102, 103, 104})

	recorder, body := doPrivateTableRequest(t, server, http.MethodPost, "/api/v1/private-tables/test-room/join", privateTableAuthToken(t, 101, "alice"), map[string]any{})
	if recorder.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", recorder.Code)
	}
	if body["status"] != "active" || body["matchId"] != "match-123" {
		t.Fatalf("expected active+match-123, got %#v", body)
	}
}

func TestPrivateTableJoinRejectsOutsiderForActiveTable(t *testing.T) {
	server := newPrivateTableTestServer()
	server.Matchmaker.registerActivePrivateTable("test-room", "match-123", []uint{101, 102, 103, 104})

	recorder, _ := doPrivateTableRequest(t, server, http.MethodPost, "/api/v1/private-tables/test-room/join", privateTableAuthToken(t, 999, "eve"), map[string]any{})
	if recorder.Code != http.StatusConflict {
		t.Fatalf("expected 409, got %d", recorder.Code)
	}
}
