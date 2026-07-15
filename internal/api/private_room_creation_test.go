package api

import (
	"encoding/json"
	"net/http"
	"testing"

	"github.com/glebarez/sqlite"
	"github.com/plasma/fh-mahjong/internal/storage"
	"gorm.io/gorm"
)

func newAuthenticatedPrivateTableServer(t *testing.T) *Server {
	t.Helper()
	db, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	if err := storage.AutoMigrate(db); err != nil {
		t.Fatalf("migrate: %v", err)
	}
	hub := NewHub()
	go hub.Run()
	matchmaker := NewMatchmaker(NewInMemoryQueue(), db, hub)
	return NewServer(db, hub, matchmaker)
}

func registerSession(t *testing.T, server *Server, email, username string) (*http.Cookie, string) {
	t.Helper()
	rec := authRequest(t, server.Router, http.MethodPost, "/api/v1/auth/register",
		`{"email":"`+email+`","username":"`+username+`","password":"hunter2pw"}`, nil, "")
	if rec.Code != http.StatusCreated {
		t.Fatalf("register %s = %d: %s", email, rec.Code, rec.Body.String())
	}
	var response AuthResponse
	if err := json.Unmarshal(rec.Body.Bytes(), &response); err != nil {
		t.Fatalf("decode auth response: %v", err)
	}
	return sessionCookieFrom(t, rec), response.CSRFToken
}

func TestCreatePrivateRoomIsExplicitAndSeatsHost(t *testing.T) {
	server := newAuthenticatedPrivateTableServer(t)
	cookie, csrf := registerSession(t, server, "host@example.com", "Rain Host")
	rec := authRequest(t, server.Router, http.MethodPost, "/api/v1/rooms", `{}`, cookie, csrf)
	if rec.Code != http.StatusCreated {
		t.Fatalf("create room = %d: %s", rec.Code, rec.Body.String())
	}
	var room map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &room); err != nil {
		t.Fatalf("decode room: %v", err)
	}
	roomID, _ := room["tableId"].(string)
	if len(roomID) != 8 {
		t.Fatalf("room id = %q, want eight characters", roomID)
	}
	seats, _ := room["seats"].([]any)
	first := seats[0].(map[string]any)
	if first["kind"] != "human" || first["username"] != "Rain Host" {
		t.Fatalf("host seat = %#v", first)
	}
}

func TestJoinMissingPrivateRoomDoesNotCreateIt(t *testing.T) {
	server := newAuthenticatedPrivateTableServer(t)
	cookie, csrf := registerSession(t, server, "invitee@example.com", "Invitee")
	rec := authRequest(t, server.Router, http.MethodPost, "/api/v1/rooms/not-real/join", `{}`, cookie, csrf)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("join missing room = %d: %s", rec.Code, rec.Body.String())
	}
	if table := server.Matchmaker.GetConfiguringPrivateTable("not-real"); table != nil {
		t.Fatal("joining a missing invite must never create a room")
	}
}

func TestAuthenticatedInviteeJoinsExistingRoom(t *testing.T) {
	server := newAuthenticatedPrivateTableServer(t)
	hostCookie, hostCSRF := registerSession(t, server, "host@example.com", "Host")
	created := authRequest(t, server.Router, http.MethodPost, "/api/v1/rooms", `{}`, hostCookie, hostCSRF)
	if created.Code != http.StatusCreated {
		t.Fatalf("create room = %d: %s", created.Code, created.Body.String())
	}
	var room map[string]any
	_ = json.Unmarshal(created.Body.Bytes(), &room)
	roomID := room["tableId"].(string)

	guestCookie, guestCSRF := registerSession(t, server, "guest@example.com", "Guest")
	joined := authRequest(t, server.Router, http.MethodPost, "/api/v1/rooms/"+roomID+"/join", `{}`, guestCookie, guestCSRF)
	if joined.Code != http.StatusOK {
		t.Fatalf("join existing room = %d: %s", joined.Code, joined.Body.String())
	}
	var joinedRoom map[string]any
	_ = json.Unmarshal(joined.Body.Bytes(), &joinedRoom)
	seats := joinedRoom["seats"].([]any)
	second := seats[1].(map[string]any)
	if second["username"] != "Guest" {
		t.Fatalf("second seat = %#v", second)
	}
}
