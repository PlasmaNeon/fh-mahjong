package api

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/plasma/fh-mahjong/internal/review"
	"github.com/plasma/fh-mahjong/internal/storage"
)

// doAuthedReviewRequestWithCtx is doAuthedReviewRequestWithSession plus an
// explicit request context, so a test can cancel one caller's wait without
// affecting any other caller sharing the same singleflight key.
func doAuthedReviewRequestWithCtx(t *testing.T, server *Server, method, path string, cookie *http.Cookie, csrf string, ctx context.Context) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(method, path, nil).WithContext(ctx)
	req.AddCookie(cookie)
	if requiresCSRF(method) {
		req.Header.Set(csrfHeaderName, csrf)
	}
	recorder := httptest.NewRecorder()
	server.Router.ServeHTTP(recorder, req)
	return recorder
}

// --- Finding 1a/1c: bounded, non-blocking-forever build admission ---------

// TestPostReviewBuildAdmissionRejectsExcessQueueWithRetryAfter pins round 22,
// Finding 1a: once reviewBuildConcurrencyLimit builds are running AND
// reviewBuildWaitQueueLimit more are already queued waiting for a slot, one
// more DISTINCT-match build request is rejected immediately with 429 and a
// Retry-After header, rather than growing the wait queue (or blocking)
// unboundedly.
func TestPostReviewBuildAdmissionRejectsExcessQueueWithRetryAfter(t *testing.T) {
	stub, ctrl := newBlockingPolicyStub(t)
	defer stub.Close()
	t.Setenv("POLICY_SERVER_URL", stub.URL)

	server := newReviewTestServer(t, true)
	fixture := reviewFixtureJSON(t)

	totalAdmitted := reviewBuildConcurrencyLimit + reviewBuildWaitQueueLimit
	matchIDs := make([]string, totalAdmitted)
	for i := range matchIDs {
		matchIDs[i] = "admission-match-" + string(rune('a'+i))
		server.StorePaipu(matchIDs[i], fixture)
	}
	cookie, csrf := authedReviewSession(t, server, 950)

	var wg sync.WaitGroup
	for _, id := range matchIDs {
		wg.Add(1)
		go func(id string) {
			defer wg.Done()
			rec := doAuthedReviewRequestWithSession(t, server, http.MethodPost, "/api/v1/matches/"+id+"/review", cookie, csrf)
			if rec.Code != http.StatusOK {
				t.Errorf("match %s: expected 200 (eventually admitted), got %d: %s", id, rec.Code, rec.Body.String())
			}
		}(id)
	}

	// Wait until every one of the totalAdmitted requests is either running
	// (occupying a semaphore slot) or parked in the bounded wait queue.
	deadline := time.Now().Add(5 * time.Second)
	for {
		inFlight := atomic.LoadInt32(&ctrl.inFlight)
		waiters := atomic.LoadInt32(&server.reviewBuildWaiters)
		if inFlight >= reviewBuildConcurrencyLimit && waiters >= reviewBuildWaitQueueLimit {
			break
		}
		if time.Now().After(deadline) {
			t.Fatalf("timed out waiting for admission to fill: inFlight=%d waiters=%d", inFlight, waiters)
		}
		time.Sleep(2 * time.Millisecond)
	}

	// One more DISTINCT match id, with capacity+queue both already full,
	// must be rejected immediately — not queued, not blocked.
	overflowID := "admission-match-overflow"
	server.StorePaipu(overflowID, fixture)
	rec := doAuthedReviewRequestWithSession(t, server, http.MethodPost, "/api/v1/matches/"+overflowID+"/review", cookie, csrf)
	if rec.Code != http.StatusTooManyRequests {
		t.Fatalf("expected 429 when admission queue is full, got %d: %s", rec.Code, rec.Body.String())
	}
	if ra := rec.Header().Get("Retry-After"); ra == "" {
		t.Fatal("expected a Retry-After header on the 429 admission rejection")
	}

	close(ctrl.release)
	wg.Wait()
}

// --- Finding 1d: per-user rate limit --------------------------------------

// TestPostReviewPerUserRateLimitReturns429 pins round 22, Finding 1d: an
// authenticated user spamming distinct-match review POSTs is turned away
// with 429 once their small token bucket is exhausted, well before touching
// the shared build-admission machinery at all.
func TestPostReviewPerUserRateLimitReturns429(t *testing.T) {
	var requestCount int
	stub := newStubPolicyServer(t, &requestCount)
	defer stub.Close()
	t.Setenv("POLICY_SERVER_URL", stub.URL)

	server := newReviewTestServer(t, true)
	fixture := reviewFixtureJSON(t)
	cookie, csrf := authedReviewSession(t, server, 960)

	var lastRec *httptest.ResponseRecorder
	rejected := false
	// Comfortably exceed reviewRateLimitBurst against distinct match ids so
	// each request is a genuine build attempt, never a cache hit.
	for i := 0; i < int(reviewRateLimitBurst)+3; i++ {
		matchID := "rate-limit-match-" + string(rune('a'+i))
		server.StorePaipu(matchID, fixture)
		lastRec = doAuthedReviewRequestWithSession(t, server, http.MethodPost, "/api/v1/matches/"+matchID+"/review", cookie, csrf)
		if lastRec.Code == http.StatusTooManyRequests {
			rejected = true
			break
		}
		if lastRec.Code != http.StatusOK {
			t.Fatalf("request %d: expected 200 or 429, got %d: %s", i, lastRec.Code, lastRec.Body.String())
		}
	}

	if !rejected {
		t.Fatalf("expected the per-user rate limit to reject at least one request after %d bursts, last status %d", int(reviewRateLimitBurst)+3, lastRec.Code)
	}
	if ra := lastRec.Header().Get("Retry-After"); ra == "" {
		t.Fatal("expected a Retry-After header on the rate-limited 429")
	}
}

// --- Finding 1b: a caller giving up doesn't kill a shared build ----------

// TestPostReviewCallerContextCancelDoesNotAbortSharedBuild pins round 22,
// Finding 1b/1c: two requests for the same match/checkpoint/force-ness share
// one in-flight build. If ONE caller's context is cancelled while waiting,
// that caller gets back a fast 504 without the build being aborted — the
// OTHER caller still gets its normal 200, and exactly one row is cached.
func TestPostReviewCallerContextCancelDoesNotAbortSharedBuild(t *testing.T) {
	stub, ctrl := newBlockingPolicyStub(t)
	defer stub.Close()
	t.Setenv("POLICY_SERVER_URL", stub.URL)

	server := newReviewTestServer(t, true)
	server.StorePaipu("cancel-fixture", reviewFixtureJSON(t))
	cookie, csrf := authedReviewSession(t, server, 970)

	cancelCtx, cancel := context.WithCancel(context.Background())

	// Results cross goroutine boundaries only via these channels (never a
	// plain shared variable polled from another goroutine) so the test
	// itself stays race-free under -race.
	resultA := make(chan *httptest.ResponseRecorder, 1)
	resultB := make(chan *httptest.ResponseRecorder, 1)
	go func() {
		resultA <- doAuthedReviewRequestWithCtx(t, server, http.MethodPost, "/api/v1/matches/cancel-fixture/review", cookie, csrf, cancelCtx)
	}()
	go func() {
		resultB <- doAuthedReviewRequestWithSession(t, server, http.MethodPost, "/api/v1/matches/cancel-fixture/review", cookie, csrf)
	}()

	// Wait for the shared build to actually start (one /evaluate call),
	// then cancel request A while it's still in flight.
	deadline := time.Now().Add(5 * time.Second)
	for atomic.LoadInt32(&ctrl.evalCount) < 1 {
		if time.Now().After(deadline) {
			t.Fatal("timed out waiting for the shared build to start")
		}
		time.Sleep(2 * time.Millisecond)
	}
	cancel()

	// Request A's handler should observe the cancellation and return, while
	// the build (still blocked on ctrl.release) has NOT been released yet —
	// proving the build itself is unaffected.
	var recA *httptest.ResponseRecorder
	select {
	case recA = <-resultA:
	case <-time.After(2 * time.Second):
		t.Fatal("timed out waiting for the cancelled caller to return")
	}
	if recA.Code != http.StatusGatewayTimeout {
		t.Fatalf("expected 504 for the cancelled caller, got %d: %s", recA.Code, recA.Body.String())
	}
	if atomic.LoadInt32(&ctrl.inFlight) == 0 {
		t.Fatal("expected the shared build to still be in flight after one waiter's context was cancelled")
	}

	close(ctrl.release)

	var recB *httptest.ResponseRecorder
	select {
	case recB = <-resultB:
	case <-time.After(5 * time.Second):
		t.Fatal("timed out waiting for the still-waiting caller to return")
	}

	if recB.Code != http.StatusOK {
		t.Fatalf("expected the still-waiting caller to get 200, got %d: %s", recB.Code, recB.Body.String())
	}
	if got := atomic.LoadInt32(&ctrl.evalCount); got != 1 {
		t.Fatalf("expected exactly 1 /evaluate call (build shared, not duplicated), got %d", got)
	}

	var count int64
	if err := server.DB.Model(&storage.MatchReview{}).Where("match_id = ?", "cancel-fixture").Count(&count).Error; err != nil {
		t.Fatalf("count MatchReview rows: %v", err)
	}
	if count != 1 {
		t.Fatalf("expected exactly 1 cached row, got %d", count)
	}
}

// --- Finding 2: singleflight key includes checkpoint identity ------------

// shaSwapStub serves /healthz with a mutable, externally-set sha and
// /evaluate blocking on release, capturing the CURRENT sha at request
// ENTRY (before blocking) as the value it reports in its response — modeling
// a real serve_policy.py, whose /evaluate response reflects whichever
// checkpoint was loaded when it started handling the request.
type shaSwapStub struct {
	mu        sync.Mutex
	sha       string
	evalCount int32
	release   chan struct{}
}

func (s *shaSwapStub) setSha(sha string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.sha = sha
}

func (s *shaSwapStub) currentSha() string {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.sha
}

func newShaSwapStub(t *testing.T, initialSha string) (*httptest.Server, *shaSwapStub) {
	t.Helper()
	stub := &shaSwapStub{sha: initialSha, release: make(chan struct{})}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/healthz":
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(map[string]any{"ok": true, "checkpoint_sha256": stub.currentSha()})
		case "/evaluate":
			shaAtEntry := stub.currentSha()
			atomic.AddInt32(&stub.evalCount, 1)
			<-stub.release
			var req struct {
				Observations []map[string]any `json:"observations"`
			}
			if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
				t.Errorf("decode: %v", err)
				return
			}
			results := make([]map[string]any, len(req.Observations))
			for i, o := range req.Observations {
				mask := o["action_mask"].([]any)
				probs := make([]float64, len(mask))
				legal := 0
				for _, m := range mask {
					if m.(float64) == 1 {
						legal++
					}
				}
				for j, m := range mask {
					if m.(float64) == 1 {
						probs[j] = 1.0 / float64(legal)
					}
				}
				results[i] = map[string]any{"probs": probs, "value": 0.25}
			}
			_ = json.NewEncoder(w).Encode(map[string]any{
				"results": results, "checkpoint_path": "swap.pt", "checkpoint_step": 1,
				"checkpoint_sha256": shaAtEntry,
			})
		default:
			http.NotFound(w, r)
		}
	}))
	return srv, stub
}

// TestPostReviewSecondRequestDoesNotJoinStaleShaBuild pins round 22, Finding
// 2: matchID-only singleflight keys let a request expecting sha-B coalesce
// into a request's in-flight build for sha-A. With the checkpoint identity
// folded into the key, a request that resolves a DIFFERENT sha must get its
// OWN build and OWN report, never the other request's result.
func TestPostReviewSecondRequestDoesNotJoinStaleShaBuild(t *testing.T) {
	stub, ctrl := newShaSwapStub(t, "sha-A")
	defer stub.Close()
	t.Setenv("POLICY_SERVER_URL", stub.URL)

	server := newReviewTestServer(t, true)
	server.StorePaipu("swap-fixture", reviewFixtureJSON(t))
	cookie, csrf := authedReviewSession(t, server, 980)

	var wg sync.WaitGroup
	var recA, recB *httptest.ResponseRecorder
	wg.Add(1)
	go func() {
		defer wg.Done()
		recA = doAuthedReviewRequestWithSession(t, server, http.MethodPost, "/api/v1/matches/swap-fixture/review", cookie, csrf)
	}()

	// Wait for request A's build to actually start (healthz resolved
	// sha-A, cache missed, /evaluate reached and blocked).
	deadline := time.Now().Add(5 * time.Second)
	for atomic.LoadInt32(&ctrl.evalCount) < 1 {
		if time.Now().After(deadline) {
			t.Fatal("timed out waiting for request A's build to start")
		}
		time.Sleep(2 * time.Millisecond)
	}

	// Server is promoted/reloaded to a different checkpoint before request B
	// arrives.
	ctrl.setSha("sha-B")

	wg.Add(1)
	go func() {
		defer wg.Done()
		recB = doAuthedReviewRequestWithSession(t, server, http.MethodPost, "/api/v1/matches/swap-fixture/review", cookie, csrf)
	}()

	// Wait for request B's OWN build to also start (a second /evaluate
	// call) — proving it did NOT coalesce into request A's in-flight call.
	deadline = time.Now().Add(5 * time.Second)
	for atomic.LoadInt32(&ctrl.evalCount) < 2 {
		if time.Now().After(deadline) {
			t.Fatal("timed out waiting for request B to start its OWN build (it may have wrongly coalesced into A's)")
		}
		time.Sleep(2 * time.Millisecond)
	}

	close(ctrl.release)
	wg.Wait()

	if recA.Code != http.StatusOK || recB.Code != http.StatusOK {
		t.Fatalf("expected both requests to succeed: A=%d B=%d", recA.Code, recB.Code)
	}
	if recA.Body.String() == recB.Body.String() {
		t.Fatal("request B must NOT receive request A's report — they resolved different checkpoints")
	}
	if !strings.Contains(recA.Body.String(), "sha-A") {
		t.Fatalf("request A's report should reflect sha-A: %s", recA.Body.String())
	}
	if !strings.Contains(recB.Body.String(), "sha-B") {
		t.Fatalf("request B's report should reflect sha-B: %s", recB.Body.String())
	}

	var rows []storage.MatchReview
	if err := server.DB.Where("match_id = ?", "swap-fixture").Find(&rows).Error; err != nil {
		t.Fatalf("query rows: %v", err)
	}
	if len(rows) != 2 {
		t.Fatalf("expected 2 distinct cached rows (sha-A and sha-B), got %d: %+v", len(rows), rows)
	}
}

// TestBuildReviewOutcomeRejectsShaMismatch is a focused unit test on the
// defense-in-depth validation in buildReviewOutcome (round 22, Finding 2):
// even if a build somehow ran under the wrong key, a result whose
// CheckpointSha256 doesn't match what the caller expected must never be
// cached or served as current — it's discarded with a 503.
func TestBuildReviewOutcomeRejectsShaMismatch(t *testing.T) {
	stub := newStubPolicyServerWithSha(t, nil, "sha-actual")
	defer stub.Close()

	server := newReviewTestServer(t, true)
	server.StorePaipu("mismatch-fixture", reviewFixtureJSON(t))

	policyClient := review.NewHTTPPolicyClient(stub.URL, 0)
	outcome := server.buildReviewOutcome(context.Background(), "mismatch-fixture", policyClient, 0, "sha-expected", false)
	if outcome.status != http.StatusServiceUnavailable {
		t.Fatalf("expected 503 on sha mismatch, got %d: %s", outcome.status, string(outcome.body))
	}

	var count int64
	if err := server.DB.Model(&storage.MatchReview{}).Where("match_id = ?", "mismatch-fixture").Count(&count).Error; err != nil {
		t.Fatalf("count MatchReview rows: %v", err)
	}
	if count != 0 {
		t.Fatalf("expected no cached row for a rejected sha-mismatched build, got %d", count)
	}
}

// --- Finding 3: healthz failure fails closed ------------------------------

// TestPostReviewHealthzTimeoutFailsClosed pins round 22, Finding 3: a
// /healthz call that hangs past its timeout must return 503, never a
// silently-served stale cached row.
func TestPostReviewHealthzTimeoutFailsClosed(t *testing.T) {
	var requestCount int
	evalStub := newStubPolicyServerWithSha(t, &requestCount, "sha-cached")

	// First, build and cache a row against a healthy server.
	t.Setenv("POLICY_SERVER_URL", evalStub.URL)
	server := newReviewTestServer(t, true)
	server.StorePaipu("healthz-timeout-fixture", reviewFixtureJSON(t))
	warm := doAuthedReviewRequest(t, server, http.MethodPost, "/api/v1/matches/healthz-timeout-fixture/review")
	if warm.Code != http.StatusOK {
		t.Fatalf("expected 200 warming the cache, got %d: %s", warm.Code, warm.Body.String())
	}
	evalStub.Close()

	// Now point at a server whose /healthz hangs forever (never responds) —
	// simulating a timeout without waiting out the real 5s budget in a test.
	// hang must be closed BEFORE hangingStub.Close() (defers run LIFO, so
	// deferring Close() first / close(hang) second gets this order at
	// return): otherwise Close() blocks forever waiting for the still-open
	// connection whose handler is itself blocked on <-hang.
	hang := make(chan struct{})
	hangingStub := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/healthz" {
			<-hang
			return
		}
		http.NotFound(w, r)
	}))
	defer hangingStub.Close()
	defer close(hang)
	t.Setenv("POLICY_SERVER_URL", hangingStub.URL)

	rec := doAuthedReviewRequest(t, server, http.MethodPost, "/api/v1/matches/healthz-timeout-fixture/review")
	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected 503 when healthz hangs, got %d: %s", rec.Code, rec.Body.String())
	}
	if rec.Body.String() == warm.Body.String() {
		t.Fatal("must not silently serve the stale cached row when healthz is unreachable")
	}
}

// TestPostReviewHealthz500FailsClosed pins the same Finding 3 contract for a
// /healthz that responds but with a server error status.
func TestPostReviewHealthz500FailsClosed(t *testing.T) {
	stub := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/healthz" {
			http.Error(w, "internal error", http.StatusInternalServerError)
			return
		}
		http.NotFound(w, r)
	}))
	defer stub.Close()
	t.Setenv("POLICY_SERVER_URL", stub.URL)

	server := newReviewTestServer(t, true)
	server.StorePaipu("healthz-500-fixture", reviewFixtureJSON(t))

	rec := doAuthedReviewRequest(t, server, http.MethodPost, "/api/v1/matches/healthz-500-fixture/review")
	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected 503 when healthz returns 500, got %d: %s", rec.Code, rec.Body.String())
	}
}
