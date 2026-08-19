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

// shaHealthzStub serves /evaluate and /healthz reporting a mutable
// checkpoint_sha256, so tests can simulate promotion/reload/rollback of the
// serving checkpoint between requests to the SAME base URL.
type shaHealthzStub struct {
	mu        sync.Mutex
	sha       string
	evalCount int
}

func (s *shaHealthzStub) setSha(sha string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.sha = sha
}

func (s *shaHealthzStub) currentSha() string {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.sha
}

func newShaHealthzStub(t *testing.T, initialSha string) (*httptest.Server, *shaHealthzStub) {
	t.Helper()
	stub := &shaHealthzStub{sha: initialSha}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/healthz":
			w.Header().Set("Content-Type", "application/json")
			json.NewEncoder(w).Encode(map[string]any{"ok": true, "checkpoint_sha256": stub.currentSha()})
			return
		case "/evaluate":
			stub.mu.Lock()
			stub.evalCount++
			stub.mu.Unlock()
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
			json.NewEncoder(w).Encode(map[string]any{
				"results": results, "checkpoint_path": "stub.pt", "checkpoint_step": 42,
				"checkpoint_sha256": stub.currentSha(),
			})
		default:
			http.NotFound(w, r)
		}
	}))
	return srv, stub
}

func TestPostReviewRebuildsWhenServerReportsDifferentSha(t *testing.T) {
	stub, ctrl := newShaHealthzStub(t, "sha-A")
	defer stub.Close()
	t.Setenv("POLICY_SERVER_URL", stub.URL)

	server := newReviewTestServer(t, true)
	server.StorePaipu("review-fixture", reviewFixtureJSON(t))

	recA := doAuthedReviewRequest(t, server, http.MethodPost, "/api/v1/matches/review-fixture/review")
	if recA.Code != http.StatusOK {
		t.Fatalf("expected 200 building sha-A, got %d: %s", recA.Code, recA.Body.String())
	}

	// Server is now promoted/reloaded to a different checkpoint (sha-B).
	ctrl.setSha("sha-B")
	recB := doAuthedReviewRequest(t, server, http.MethodPost, "/api/v1/matches/review-fixture/review")
	if recB.Code != http.StatusOK {
		t.Fatalf("expected 200 building sha-B, got %d: %s", recB.Code, recB.Body.String())
	}
	if recB.Body.String() == recA.Body.String() {
		t.Fatal("expected a fresh build for sha-B, got sha-A's stale cached report")
	}

	var rows []storage.MatchReview
	if err := server.DB.Where("match_id = ?", "review-fixture").Find(&rows).Error; err != nil {
		t.Fatalf("query rows: %v", err)
	}
	if len(rows) != 2 {
		t.Fatalf("expected 2 rows (sha-A intact, sha-B new), got %d: %+v", len(rows), rows)
	}
	seen := map[string]bool{}
	for _, row := range rows {
		seen[row.CheckpointID] = true
	}
	if !seen["sha-A"] || !seen["sha-B"] {
		t.Fatalf("expected rows keyed by sha-A and sha-B, got %+v", seen)
	}

	// Rollback: server reports sha-A again. Must serve sha-A's row WITHOUT
	// rebuilding.
	ctrl.setSha("sha-A")
	ctrl.mu.Lock()
	evalCountBeforeRollback := ctrl.evalCount
	ctrl.mu.Unlock()

	recRollback := doAuthedReviewRequest(t, server, http.MethodPost, "/api/v1/matches/review-fixture/review")
	if recRollback.Code != http.StatusOK {
		t.Fatalf("expected 200 on rollback, got %d: %s", recRollback.Code, recRollback.Body.String())
	}
	if recRollback.Body.String() != recA.Body.String() {
		t.Fatalf("rollback to sha-A must re-serve sha-A's original row:\nwant: %s\ngot:  %s", recA.Body.String(), recRollback.Body.String())
	}
	ctrl.mu.Lock()
	evalCountAfterRollback := ctrl.evalCount
	ctrl.mu.Unlock()
	if evalCountAfterRollback != evalCountBeforeRollback {
		t.Fatalf("rollback to a cached sha must not rebuild: eval count went from %d to %d", evalCountBeforeRollback, evalCountAfterRollback)
	}
}

// TestPostReviewLegacyNoShaHealthzKeepsNewestRowBehavior pins that a TRUE
// legacy policy server — /healthz answers "ok":true but omits
// checkpoint_sha256 entirely, predating round 21 — falls back to today's
// newest-cached-row behavior unchanged (round 22, Finding 3's one
// grandfathered stale-serve path).
func TestPostReviewLegacyNoShaHealthzKeepsNewestRowBehavior(t *testing.T) {
	var requestCount int
	stub := newStubPolicyServer(t, &requestCount) // healthz ok, no sha field
	defer stub.Close()
	t.Setenv("POLICY_SERVER_URL", stub.URL)

	server := newReviewTestServer(t, true)
	server.StorePaipu("review-fixture", reviewFixtureJSON(t))

	rec := doAuthedReviewRequest(t, server, http.MethodPost, "/api/v1/matches/review-fixture/review")
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	first := requestCount

	rec2 := doAuthedReviewRequest(t, server, http.MethodPost, "/api/v1/matches/review-fixture/review")
	if rec2.Code != http.StatusOK {
		t.Fatalf("expected 200 on second call, got %d: %s", rec2.Code, rec2.Body.String())
	}
	if requestCount != first {
		t.Fatalf("expected no new /evaluate calls for a legacy no-healthz server's cached row, got %d (was %d)", requestCount, first)
	}
	if rec.Body.String() != rec2.Body.String() {
		t.Fatalf("expected cached body to be reused unchanged for legacy no-healthz server")
	}
}

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

// TestBuildReviewOutcomeRejectsMissingSha pins round 23, Finding 2: when the
// caller resolved a known live sha via /healthz (legacy==false,
// expectedSha!=""), a build whose /evaluate response OMITS checkpoint_sha256
// entirely (rolling deploy / proxy skew) must be rejected exactly like an
// explicit mismatch — 503, nothing cached — never silently accepted and
// filed under expectedSha.
func TestBuildReviewOutcomeRejectsMissingSha(t *testing.T) {
	// newStubPolicyServer's /evaluate response has no checkpoint_sha256 field
	// at all, simulating a build response that omitted it even though
	// /healthz (not exercised by this focused unit test) reported a sha.
	stub := newStubPolicyServer(t, nil)
	defer stub.Close()

	server := newReviewTestServer(t, true)
	server.StorePaipu("missing-sha-fixture", reviewFixtureJSON(t))

	policyClient := review.NewHTTPPolicyClient(stub.URL, 0)
	outcome := server.buildReviewOutcome(context.Background(), "missing-sha-fixture", policyClient, 0, "sha-expected", false)
	if outcome.status != http.StatusServiceUnavailable {
		t.Fatalf("expected 503 when /evaluate omits checkpoint_sha256 but a sha was expected, got %d: %s", outcome.status, string(outcome.body))
	}

	var count int64
	if err := server.DB.Model(&storage.MatchReview{}).Where("match_id = ?", "missing-sha-fixture").Count(&count).Error; err != nil {
		t.Fatalf("count MatchReview rows: %v", err)
	}
	if count != 0 {
		t.Fatalf("expected no cached row for a rejected missing-sha build, got %d", count)
	}
}

// TestBuildReviewOutcomeAcceptsMissingShaWhenLegacy pins the flip side: when
// the caller itself resolved NO live sha (legacy==true, a true legacy
// /healthz), a build response that also omits checkpoint_sha256 is expected
// and must still be accepted/cached under its checkpoint_path — unaffected
// by Finding 2's stricter guard, which only applies when a sha was actually
// expected.
func TestBuildReviewOutcomeAcceptsMissingShaWhenLegacy(t *testing.T) {
	stub := newStubPolicyServer(t, nil)
	defer stub.Close()

	server := newReviewTestServer(t, true)
	server.StorePaipu("legacy-missing-sha-fixture", reviewFixtureJSON(t))

	policyClient := review.NewHTTPPolicyClient(stub.URL, 0)
	outcome := server.buildReviewOutcome(context.Background(), "legacy-missing-sha-fixture", policyClient, 0, "", true)
	if outcome.status != http.StatusOK {
		t.Fatalf("expected 200 for a legacy build with no expected sha, got %d: %s", outcome.status, string(outcome.body))
	}

	var count int64
	if err := server.DB.Model(&storage.MatchReview{}).Where("match_id = ?", "legacy-missing-sha-fixture").Count(&count).Error; err != nil {
		t.Fatalf("count MatchReview rows: %v", err)
	}
	if count != 1 {
		t.Fatalf("expected exactly 1 cached row for the accepted legacy build, got %d", count)
	}
}
