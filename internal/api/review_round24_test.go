package api

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

// --- adversarial round 24, Finding 1: GET must not amplify healthz load ---

// healthzCountingStub is a policy-server stub whose /healthz route counts
// every request it serves and can be told to hold responses until released
// (simulating a slow/in-flight refresh so concurrent GETs are forced to
// overlap), and can be switched to always fail (simulating an outage).
type healthzCountingStub struct {
	mu       sync.Mutex
	failing  bool
	sha      string
	release  chan struct{} // if non-nil, /healthz blocks on this before responding
	requests int32
}

func newHealthzCountingStub(t *testing.T, sha string) (*httptest.Server, *healthzCountingStub) {
	t.Helper()
	ctrl := &healthzCountingStub{sha: sha}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/healthz" {
			http.NotFound(w, r)
			return
		}
		atomic.AddInt32(&ctrl.requests, 1)

		ctrl.mu.Lock()
		release := ctrl.release
		failing := ctrl.failing
		sha := ctrl.sha
		ctrl.mu.Unlock()

		if release != nil {
			<-release
		}
		if failing {
			http.Error(w, "internal error", http.StatusInternalServerError)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{"ok": true, "checkpoint_sha256": sha})
	}))
	return srv, ctrl
}

func (c *healthzCountingStub) setFailing(failing bool) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.failing = failing
}

func (c *healthzCountingStub) setRelease(release chan struct{}) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.release = release
}

func (c *healthzCountingStub) count() int32 {
	return atomic.LoadInt32(&c.requests)
}

// TestGetReviewNoCachedRowReturnsNotFoundWithoutHealthzCall pins Finding 1's
// pre-check: a match with NO cached MatchReview row at all must 404
// immediately, without ever contacting the policy server's /healthz — a
// nonexistent (or never-reviewed) match can never resolve to a 200 no
// matter what the live checkpoint turns out to be, so there is nothing to
// gain from resolving it first.
func TestGetReviewNoCachedRowReturnsNotFoundWithoutHealthzCall(t *testing.T) {
	stub, ctrl := newHealthzCountingStub(t, "sha-unused")
	defer stub.Close()
	t.Setenv("POLICY_SERVER_URL", stub.URL)

	server := newReviewTestServer(t, true)
	// Deliberately no cacheMatchReview call for this match id — and no
	// StorePaipu either, since the point is that GET never needs to look
	// past "does any row exist" to answer 404.

	rec := doReviewRequest(t, server, http.MethodGet, "/api/v1/matches/never-reviewed/review")
	if rec.Code != http.StatusNotFound {
		t.Fatalf("expected 404 for a match with no cached review row, got %d: %s", rec.Code, rec.Body.String())
	}
	if got := ctrl.count(); got != 0 {
		t.Fatalf("expected zero healthz calls for a match with no cached review row, got %d", got)
	}
}

// TestGetReviewConcurrentRefreshesCoalesceToOneHealthzCall pins Finding 1's
// coalescing requirement: many concurrent GETs, all forced to refresh the
// live-sha cache at once (TTL shrunk to 0), must produce exactly ONE
// /healthz request, not one per concurrent caller.
func TestGetReviewConcurrentRefreshesCoalesceToOneHealthzCall(t *testing.T) {
	oldTTL := reviewShaCacheTTL
	reviewShaCacheTTL = 0
	defer func() { reviewShaCacheTTL = oldTTL }()

	stub, ctrl := newHealthzCountingStub(t, "sha-coalesce")
	defer stub.Close()
	t.Setenv("POLICY_SERVER_URL", stub.URL)

	release := make(chan struct{})
	ctrl.setRelease(release)

	server := newReviewTestServer(t, true)
	if err := server.cacheMatchReview(context.Background(), "coalesce-fixture", "sha-coalesce", []byte(`{"schemaVersion":1,"checkpointSha256":"sha-coalesce"}`)); err != nil {
		t.Fatalf("seed cache: %v", err)
	}

	const concurrent = 20
	var wg sync.WaitGroup
	codes := make([]int, concurrent)
	wg.Add(concurrent)
	for i := 0; i < concurrent; i++ {
		i := i
		go func() {
			defer wg.Done()
			rec := doReviewRequest(t, server, http.MethodGet, "/api/v1/matches/coalesce-fixture/review")
			codes[i] = rec.Code
		}()
	}

	// Give every goroutine a chance to actually reach reviewLiveSha and
	// block inside the shared singleflight call before releasing it —
	// otherwise some callers might not yet be waiting when we release,
	// which would still pass but wouldn't actually exercise concurrency.
	time.Sleep(50 * time.Millisecond)
	close(release)
	wg.Wait()

	if got := ctrl.count(); got != 1 {
		t.Fatalf("expected exactly 1 healthz request for %d concurrent GETs during a forced refresh, got %d", concurrent, got)
	}
	for i, code := range codes {
		if code != http.StatusOK {
			t.Fatalf("request %d: expected 200 once the shared healthz resolution completes, got %d", i, code)
		}
	}
}

// TestGetReviewHealthzOutageNegativeCachesAcrossRepeatedGETs pins Finding
// 1's negative-cache requirement: once /healthz starts failing, repeated
// GETs within the negative-cache TTL must make at most ONE healthz request
// total (not one per GET), and every one of those GETs must still see 503 —
// a request is never silently served a stale row just because the identity
// check itself was skipped.
func TestGetReviewHealthzOutageNegativeCachesAcrossRepeatedGETs(t *testing.T) {
	stub, ctrl := newHealthzCountingStub(t, "sha-outage")
	ctrl.setFailing(true)
	defer stub.Close()
	t.Setenv("POLICY_SERVER_URL", stub.URL)

	server := newReviewTestServer(t, true)
	if err := server.cacheMatchReview(context.Background(), "outage-fixture", "sha-outage", []byte(`{"schemaVersion":1}`)); err != nil {
		t.Fatalf("seed cache: %v", err)
	}

	for i := 0; i < 5; i++ {
		rec := doReviewRequest(t, server, http.MethodGet, "/api/v1/matches/outage-fixture/review")
		if rec.Code != http.StatusServiceUnavailable {
			t.Fatalf("GET %d: expected 503 during a healthz outage, got %d: %s", i, rec.Code, rec.Body.String())
		}
	}

	if got := ctrl.count(); got != 1 {
		t.Fatalf("expected exactly 1 healthz request across 5 sequential GETs within the negative-cache TTL, got %d", got)
	}
}
