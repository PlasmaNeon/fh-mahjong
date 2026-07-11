package remote

import (
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestDeriveHealthURL(t *testing.T) {
	cases := map[string]string{
		"http://127.0.0.1:8765/act":        "http://127.0.0.1:8765/healthz",
		"http://example.com/act":           "http://example.com/healthz",
		"https://host:9000/policy/act?x=1": "https://host:9000/healthz",
		"":                                 "",
		"not-a-url":                        "",
	}
	for in, want := range cases {
		if got := deriveHealthURL(in); got != want {
			t.Errorf("deriveHealthURL(%q) = %q, want %q", in, got, want)
		}
	}
}

func TestHealthChecker_Healthy(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/healthz" {
			w.WriteHeader(http.StatusOK)
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	defer srv.Close()

	h := NewHealthChecker(srv.URL + "/act")
	if !h.Healthy() {
		t.Fatal("expected Healthy()=true while server is up")
	}
}

func TestHealthChecker_UnreachableIsUnhealthy(t *testing.T) {
	// Nothing is listening on this port; the probe should fail fast.
	h := NewHealthChecker("http://127.0.0.1:1/act")
	if h.Healthy() {
		t.Fatal("expected Healthy()=false for an unreachable endpoint")
	}
}

func TestHealthChecker_CachesResult(t *testing.T) {
	var hits int
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		hits++
		w.WriteHeader(http.StatusOK)
	}))

	h := NewHealthChecker(srv.URL + "/act")
	h.ttl = time.Minute

	if !h.Healthy() {
		t.Fatal("expected first probe to be healthy")
	}
	// Server is now closed, but a cached healthy result should persist.
	srv.Close()
	if !h.Healthy() {
		t.Fatal("expected cached healthy result within TTL")
	}
	if hits != 1 {
		t.Fatalf("expected exactly 1 probe within TTL, got %d", hits)
	}
}

func TestHealthChecker_NilReceiver(t *testing.T) {
	var h *HealthChecker
	if h.Healthy() {
		t.Fatal("nil HealthChecker should report unhealthy")
	}
}

func TestHealthChecker_IdentityFromHealthz(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"ok":true,"checkpoint":"/models/champ.pt","checkpoint_step":1234}`))
	}))
	defer srv.Close()

	h := NewHealthChecker(srv.URL + "/act")
	if got, want := h.Identity(), "champ.pt@step1234"; got != want {
		t.Fatalf("Identity() = %q, want %q", got, want)
	}
}

func TestHealthChecker_IdentityEmptyWithoutCheckpoint(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte(`{"ok":true}`))
	}))
	defer srv.Close()

	h := NewHealthChecker(srv.URL + "/act")
	if got := h.Identity(); got != "" {
		t.Fatalf("Identity() = %q, want empty when healthz reports no checkpoint", got)
	}
	if !h.Healthy() {
		t.Fatal("endpoint without checkpoint info must still count as healthy")
	}
}

func TestHealthChecker_IdentityUnreachableAndNil(t *testing.T) {
	h := NewHealthChecker("http://127.0.0.1:1/act")
	if got := h.Identity(); got != "" {
		t.Fatalf("Identity() = %q, want empty for unreachable endpoint", got)
	}
	var nilChecker *HealthChecker
	if got := nilChecker.Identity(); got != "" {
		t.Fatalf("nil Identity() = %q, want empty", got)
	}
}
