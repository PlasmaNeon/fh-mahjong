package api

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

func makeTestAuthToken(t *testing.T, userID uint, username string) string {
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

func TestJoinPrivateTableQueuesWhenInactive(t *testing.T) {
	hub := NewHub()
	matchmaker := NewMatchmaker(NewInMemoryQueue(), nil, hub)
	server := NewServer(nil, hub, matchmaker)

	body, _ := json.Marshal(map[string]string{"tableId": "test-room"})
	req := httptest.NewRequest(http.MethodPost, "/api/v1/matchmaking/private", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+makeTestAuthToken(t, 101, "alice"))
	recorder := httptest.NewRecorder()

	server.Router.ServeHTTP(recorder, req)

	if recorder.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", recorder.Code, recorder.Body.String())
	}

	if got := matchmaker.Queue.LLen("table:test-room"); got != 1 {
		t.Fatalf("expected one queued player, got %d", got)
	}
}

func TestJoinPrivateTableReturnsActiveForExistingParticipant(t *testing.T) {
	hub := NewHub()
	matchmaker := NewMatchmaker(NewInMemoryQueue(), nil, hub)
	matchmaker.registerActivePrivateTable("test-room", "match-123", []uint{101, 102, 103, 104})
	server := NewServer(nil, hub, matchmaker)

	body, _ := json.Marshal(map[string]string{"tableId": "test-room"})
	req := httptest.NewRequest(http.MethodPost, "/api/v1/matchmaking/private", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+makeTestAuthToken(t, 101, "alice"))
	recorder := httptest.NewRecorder()

	server.Router.ServeHTTP(recorder, req)

	if recorder.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", recorder.Code, recorder.Body.String())
	}

	var response map[string]any
	if err := json.Unmarshal(recorder.Body.Bytes(), &response); err != nil {
		t.Fatalf("failed to parse response JSON: %v", err)
	}

	if response["status"] != "active" {
		t.Fatalf("expected active status, got %#v", response["status"])
	}
	if response["matchId"] != "match-123" {
		t.Fatalf("expected match-123, got %#v", response["matchId"])
	}
	if got := matchmaker.Queue.LLen("table:test-room"); got != 0 {
		t.Fatalf("expected queue length 0, got %d", got)
	}
}

func TestJoinPrivateTableRejectsNonParticipantWhileGameActive(t *testing.T) {
	hub := NewHub()
	matchmaker := NewMatchmaker(NewInMemoryQueue(), nil, hub)
	matchmaker.registerActivePrivateTable("test-room", "match-123", []uint{101, 102, 103, 104})
	server := NewServer(nil, hub, matchmaker)

	body, _ := json.Marshal(map[string]string{"tableId": "test-room"})
	req := httptest.NewRequest(http.MethodPost, "/api/v1/matchmaking/private", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+makeTestAuthToken(t, 999, "eve"))
	recorder := httptest.NewRecorder()

	server.Router.ServeHTTP(recorder, req)

	if recorder.Code != http.StatusConflict {
		t.Fatalf("expected 409, got %d: %s", recorder.Code, recorder.Body.String())
	}

	if got := matchmaker.Queue.LLen("table:test-room"); got != 0 {
		t.Fatalf("expected queue length 0, got %d", got)
	}
}
