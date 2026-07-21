package remote

import (
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/plasma/fh-mahjong/internal/rl"
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

// FINDING 3: a reachable server whose healthz reports a different
// event_window than this checker expects must be reported unhealthy — a
// contract mismatch means every /act on this endpoint would be rejected (or
// worse, silently mis-decoded), so RLAgentAvailable must not offer the seat.
func TestHealthChecker_ExpectedEventWindowMismatchIsUnhealthy(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"checkpoint":"/models/champ.pt","checkpoint_step":1,"event_window":64,"contract_version":1}`))
	}))
	defer srv.Close()

	h := NewHealthChecker(srv.URL+"/act", WithExpectedEventWindow(128))
	if h.Healthy() {
		t.Fatal("expected unhealthy: reachable server reports event_window=64, checker expects 128")
	}
}

// A matching event_window/contract_version must still report healthy.
func TestHealthChecker_ExpectedEventWindowMatchIsHealthy(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"checkpoint":"/models/champ.pt","checkpoint_step":1,"event_window":128,"contract_version":1}`))
	}))
	defer srv.Close()

	h := NewHealthChecker(srv.URL+"/act", WithExpectedEventWindow(128))
	if !h.Healthy() {
		t.Fatal("expected healthy: event_window/contract_version match the checker's expectation")
	}
	_ = rl.EventContractV1 // pin: the server's contract_version field must match this constant
}

// A window-0 checker (no WithExpectedEventWindow, the default / legacy
// primary-policy case) must keep reachability-only behavior: a mismatched or
// entirely absent event_window field never makes it unhealthy.
func TestHealthChecker_WindowZeroIgnoresContractMismatch(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"checkpoint":"/models/champ.pt","checkpoint_step":1,"event_window":64,"contract_version":1}`))
	}))
	defer srv.Close()

	h := NewHealthChecker(srv.URL + "/act")
	if !h.Healthy() {
		t.Fatal("expected healthy: window-0 checker validates reachability only, not contract fields")
	}
}
