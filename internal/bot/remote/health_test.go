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
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(`{}`))
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
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{}`))
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
// primary-policy case) talking to a server that never mentions the event
// contract at all (a genuinely legacy /healthz body) keeps reachability-only
// behavior: absent fields never make it unhealthy.
func TestHealthChecker_WindowZeroLegacyNoFieldsIsHealthy(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"checkpoint":"/models/champ.pt","checkpoint_step":1}`))
	}))
	defer srv.Close()

	h := NewHealthChecker(srv.URL + "/act")
	if !h.Healthy() {
		t.Fatal("expected healthy: window-0 checker vs legacy server with no event-contract fields at all")
	}
}

// FINDING 1 (adversarial round 2): a window-0 checker (default
// RL_AGENT_EVENT_WINDOW=0) must NOT accept a server that explicitly PUBLISHES
// an incompatible event_window (e.g. the policy service is serving iter_075
// at window 128 while the backend is still configured for window 0) — every
// /act call would 400 and silently fall back to the heuristic. Publishing the
// contract is a claim that must match, even for a window-0 client.
func TestHealthChecker_WindowZeroRejectsExplicitlyPublishedMismatch(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"checkpoint":"/models/iter_075.pt","checkpoint_step":1,"event_window":128,"contract_version":1}`))
	}))
	defer srv.Close()

	h := NewHealthChecker(srv.URL + "/act")
	if h.Healthy() {
		t.Fatal("expected unhealthy: window-0 checker vs server explicitly publishing event_window=128")
	}
}

// A window-0 checker vs a server that explicitly publishes event_window=0
// (a claim that matches) stays healthy.
func TestHealthChecker_WindowZeroAcceptsExplicitlyPublishedMatch(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"checkpoint":"/models/champ.pt","checkpoint_step":1,"event_window":0,"contract_version":1}`))
	}))
	defer srv.Close()

	h := NewHealthChecker(srv.URL + "/act")
	if !h.Healthy() {
		t.Fatal("expected healthy: window-0 checker vs server explicitly publishing event_window=0")
	}
}

// FINDING 1 (round 16): a non-JSON/undecodable 2xx healthz body must be
// UNHEALTHY for every window, including window-0. This reverses the previous
// alignment decision (window-0 used to tolerate non-JSON as "legacy
// reachability") because every real policy server, including the pre-B2c
// legacy one, always returns JSON on /healthz — a 2xx/non-JSON body only ever
// means a misrouted URL, a reverse-proxy error page, or an SPA fallback, and
// tolerating it let a misconfigured endpoint advertise itself as a healthy RL
// agent while every /act silently fell back to the heuristic.
func TestHealthChecker_NonJSONBodyWindowZeroIsUnhealthy(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte("not json"))
	}))
	defer srv.Close()

	h := NewHealthChecker(srv.URL + "/act")
	if h.Healthy() {
		t.Fatal("expected unhealthy: window-0 checker vs non-JSON healthz body (no longer tolerated as legacy reachability)")
	}
}

func TestHealthChecker_NonJSONBodyWindowNonZeroIsUnhealthy(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte("not json"))
	}))
	defer srv.Close()

	h := NewHealthChecker(srv.URL+"/act", WithExpectedEventWindow(128))
	if h.Healthy() {
		t.Fatal("expected unhealthy: window>0 checker vs non-JSON healthz body (contract unverifiable)")
	}
}

// A misrouted URL / reverse-proxy error page / SPA fallback typically returns
// a 2xx HTML document, not a plain string — pin that this is also unhealthy
// for a window-0 checker, since that's the realistic shape of the failure
// this fix guards against.
func TestHealthChecker_MisroutedHTMLBodyWindowZeroIsUnhealthy(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/html")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("<!doctype html><html><body>404 - not found</body></html>"))
	}))
	defer srv.Close()

	h := NewHealthChecker(srv.URL + "/act")
	if h.Healthy() {
		t.Fatal("expected unhealthy: window-0 checker vs a misrouted 2xx HTML/SPA-fallback body")
	}
}
