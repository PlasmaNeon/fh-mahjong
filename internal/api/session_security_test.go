package api

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/glebarez/sqlite"
	"github.com/plasma/fh-mahjong/internal/storage"
	"gorm.io/gorm"
)

func newSecurityTestServer(t *testing.T) *Server {
	t.Helper()
	db, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	if err := storage.AutoMigrate(db); err != nil {
		t.Fatalf("migrate: %v", err)
	}
	return NewServer(db, NewHub(), nil)
}

func TestOriginAllowlistUsesExactOrigins(t *testing.T) {
	t.Setenv("FRONTEND_ORIGINS", "https://club.example, https://app.example")
	request := httptest.NewRequest(http.MethodPost, "https://api.example/api/v1/auth/login", nil)

	request.Header.Set("Origin", "https://club.example")
	if !originAllowed(request) {
		t.Fatal("configured exact origin should be allowed")
	}
	request.Header.Set("Origin", "https://club.example.evil.test")
	if originAllowed(request) {
		t.Fatal("origin suffix must not bypass the exact allowlist")
	}
	request.Header.Del("Origin")
	if !originAllowed(request) {
		t.Fatal("non-browser request without Origin should be allowed")
	}
}

func TestCredentialedCORSPreflight(t *testing.T) {
	t.Setenv("FRONTEND_ORIGINS", "https://club.example")
	server := newSecurityTestServer(t)
	req := httptest.NewRequest(http.MethodOptions, "/api/v1/auth/login", nil)
	req.Header.Set("Origin", "https://club.example")
	req.Header.Set("Access-Control-Request-Method", http.MethodPost)
	rec := httptest.NewRecorder()
	server.Router.ServeHTTP(rec, req)
	if rec.Code != http.StatusNoContent {
		t.Fatalf("preflight = %d: %s", rec.Code, rec.Body.String())
	}
	if got := rec.Header().Get("Access-Control-Allow-Origin"); got != "https://club.example" {
		t.Fatalf("allow origin = %q", got)
	}
	if got := rec.Header().Get("Access-Control-Allow-Credentials"); got != "true" {
		t.Fatalf("allow credentials = %q", got)
	}
	if got := rec.Header().Get("Access-Control-Allow-Origin"); got == "*" {
		t.Fatal("credentialed CORS must never use wildcard origin")
	}
}

func TestWebSocketRejectsLegacyQueryTokenWithoutCookie(t *testing.T) {
	t.Setenv("FRONTEND_ORIGINS", "https://club.example")
	server := newSecurityTestServer(t)
	req := httptest.NewRequest(http.MethodGet, "/api/v1/ws?token=legacy-jwt", nil)
	req.Header.Set("Origin", "https://club.example")
	rec := httptest.NewRecorder()
	server.Router.ServeHTTP(rec, req)
	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("legacy websocket token = %d, want 401", rec.Code)
	}
}

func TestGuestAndBearerAuthenticationAreDisabled(t *testing.T) {
	server := newSecurityTestServer(t)
	guest := httptest.NewRecorder()
	guestRequest := httptest.NewRequest(http.MethodPost, "/api/v1/auth/guest", nil)
	server.Router.ServeHTTP(guest, guestRequest)
	if guest.Code != http.StatusNotFound {
		t.Fatalf("guest auth = %d, want 404", guest.Code)
	}

	bearer := httptest.NewRecorder()
	bearerRequest := httptest.NewRequest(http.MethodGet, "/api/v1/users/me", nil)
	bearerRequest.Header.Set("Authorization", "Bearer obsolete-token")
	server.Router.ServeHTTP(bearer, bearerRequest)
	if bearer.Code != http.StatusUnauthorized {
		t.Fatalf("bearer auth = %d, want 401", bearer.Code)
	}
}
