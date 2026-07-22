package api

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/plasma/fh-mahjong/internal/storage"
)

// doAuthedReviewRequest issues method/path against server with a fresh
// authenticated session (cookie + CSRF header when required), mirroring
// private_tables_test.go's doPrivateTableRequest for the review routes. Only
// safe to call sequentially — concurrent tests must create ONE session with
// authedReviewSession and reuse it via doAuthedReviewRequestWithSession, since
// this creates a new test user/session per call (a race on the same user id
// across goroutines).
func doAuthedReviewRequest(t *testing.T, server *Server, method, path string) *httptest.ResponseRecorder {
	t.Helper()
	cookie, csrf, _, _ := privateTableSession(t, server, privateTableAuthToken(t, 900, "reviewer"))
	return doAuthedReviewRequestWithSession(t, server, method, path, cookie, csrf)
}

// authedReviewSession creates one authenticated test session, safe to share
// across concurrent requests in the same test.
func authedReviewSession(t *testing.T, server *Server, userID uint) (*http.Cookie, string) {
	t.Helper()
	cookie, csrf, _, _ := privateTableSession(t, server, privateTableAuthToken(t, userID, "reviewer"))
	return cookie, csrf
}

func doAuthedReviewRequestWithSession(t *testing.T, server *Server, method, path string, cookie *http.Cookie, csrf string) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(method, path, nil)
	req.AddCookie(cookie)
	if requiresCSRF(method) {
		req.Header.Set(csrfHeaderName, csrf)
	}
	recorder := httptest.NewRecorder()
	server.Router.ServeHTTP(recorder, req)
	return recorder
}

// --- Finding 1: POST /matches/:matchId/review must be authenticated -------

func TestPostReviewRequiresAuth(t *testing.T) {
	stub := newStubPolicyServer(t, nil)
	defer stub.Close()
	t.Setenv("POLICY_SERVER_URL", stub.URL)

	server := newReviewTestServer(t, true)
	server.StorePaipu("review-fixture", reviewFixtureJSON(t))

	rec := doReviewRequest(t, server, http.MethodPost, "/api/v1/matches/review-fixture/review")
	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401 for unauthenticated POST, got %d: %s", rec.Code, rec.Body.String())
	}
}

func TestPostReviewAuthenticatedWorks(t *testing.T) {
	stub := newStubPolicyServer(t, nil)
	defer stub.Close()
	t.Setenv("POLICY_SERVER_URL", stub.URL)

	server := newReviewTestServer(t, true)
	server.StorePaipu("review-fixture", reviewFixtureJSON(t))

	rec := doAuthedReviewRequest(t, server, http.MethodPost, "/api/v1/matches/review-fixture/review")
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200 for authenticated POST, got %d: %s", rec.Code, rec.Body.String())
	}
}

// TestGetReviewStaysPublic pins that the pure cache-read GET route is
// unaffected by the auth move — it never triggers a build.
func TestGetReviewStaysPublic(t *testing.T) {
	server := newReviewTestServer(t, true)
	rec := doReviewRequest(t, server, http.MethodGet, "/api/v1/matches/unknown-match/review")
	if rec.Code != http.StatusNotFound {
		t.Fatalf("expected 404 for unauthenticated GET (still public), got %d: %s", rec.Code, rec.Body.String())
	}
}

// --- Finding 1: per-match singleflight ------------------------------------

// blockingPolicyStub serves /evaluate (and optionally /healthz) but blocks
// each /evaluate request on release until it is closed, letting tests hold a
// build "in flight" to observe concurrency.
type blockingPolicyStub struct {
	release   chan struct{}
	evalCount int32
	inFlight  int32
	maxInFlight int32
}

func newBlockingPolicyStub(t *testing.T) (*httptest.Server, *blockingPolicyStub) {
	t.Helper()
	stub := &blockingPolicyStub{release: make(chan struct{})}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/healthz":
			w.Header().Set("Content-Type", "application/json")
			w.Write([]byte(`{"ok":true}`))
			return
		case "/evaluate":
			atomic.AddInt32(&stub.evalCount, 1)
			n := atomic.AddInt32(&stub.inFlight, 1)
			for {
				old := atomic.LoadInt32(&stub.maxInFlight)
				if n <= old || atomic.CompareAndSwapInt32(&stub.maxInFlight, old, n) {
					break
				}
			}
			<-stub.release
			atomic.AddInt32(&stub.inFlight, -1)

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
			})
		default:
			http.NotFound(w, r)
		}
	}))
	return srv, stub
}

func TestPostReviewConcurrentSameMatchSharesOneBuild(t *testing.T) {
	stub, ctrl := newBlockingPolicyStub(t)
	defer stub.Close()
	t.Setenv("POLICY_SERVER_URL", stub.URL)

	server := newReviewTestServer(t, true)
	server.StorePaipu("review-fixture", reviewFixtureJSON(t))
	cookie, csrf := authedReviewSession(t, server, 900)

	var wg sync.WaitGroup
	results := make([]*httptest.ResponseRecorder, 2)
	for i := 0; i < 2; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			results[i] = doAuthedReviewRequestWithSession(t, server, http.MethodPost, "/api/v1/matches/review-fixture/review", cookie, csrf)
		}(i)
	}

	// Wait for the leader to reach the stub, then release it once.
	deadline := time.Now().Add(5 * time.Second)
	for atomic.LoadInt32(&ctrl.evalCount) < 1 {
		if time.Now().After(deadline) {
			t.Fatal("timed out waiting for stub to receive a request")
		}
		time.Sleep(5 * time.Millisecond)
	}
	// Give the follower request a moment to also arrive at singleflight.Do
	// (it should NOT generate a second stub request).
	time.Sleep(50 * time.Millisecond)
	close(ctrl.release)

	wg.Wait()

	for i, rec := range results {
		if rec.Code != http.StatusOK {
			t.Fatalf("request %d: expected 200, got %d: %s", i, rec.Code, rec.Body.String())
		}
	}
	if got := atomic.LoadInt32(&ctrl.evalCount); got != 1 {
		t.Fatalf("expected exactly 1 /evaluate call for 2 concurrent identical-match POSTs, got %d", got)
	}

	var count int64
	if err := server.DB.Model(&storage.MatchReview{}).Where("match_id = ?", "review-fixture").Count(&count).Error; err != nil {
		t.Fatalf("count MatchReview rows: %v", err)
	}
	if count != 1 {
		t.Fatalf("expected exactly 1 cached MatchReview row, got %d", count)
	}
}

// --- Finding 1: server-wide build concurrency cap -------------------------

func TestPostReviewBuildConcurrencyCapIsRespected(t *testing.T) {
	stub, ctrl := newBlockingPolicyStub(t)
	defer stub.Close()
	t.Setenv("POLICY_SERVER_URL", stub.URL)

	server := newReviewTestServer(t, true)
	fixture := reviewFixtureJSON(t)
	matchIDs := []string{"match-a", "match-b", "match-c"}
	for _, id := range matchIDs {
		server.StorePaipu(id, fixture)
	}
	cookie, csrf := authedReviewSession(t, server, 901)

	var wg sync.WaitGroup
	for _, id := range matchIDs {
		wg.Add(1)
		go func(id string) {
			defer wg.Done()
			rec := doAuthedReviewRequestWithSession(t, server, http.MethodPost, "/api/v1/matches/"+id+"/review", cookie, csrf)
			if rec.Code != http.StatusOK {
				t.Errorf("match %s: expected 200, got %d: %s", id, rec.Code, rec.Body.String())
			}
		}(id)
	}

	// Give all 3 goroutines a chance to reach the semaphore/stub.
	deadline := time.Now().Add(5 * time.Second)
	for atomic.LoadInt32(&ctrl.inFlight) < reviewBuildConcurrencyLimit {
		if time.Now().After(deadline) {
			t.Fatal("timed out waiting for in-flight builds to reach the concurrency cap")
		}
		time.Sleep(5 * time.Millisecond)
	}
	// Settle a bit longer to let a would-be 3rd concurrent build show up if
	// the cap were not enforced.
	time.Sleep(100 * time.Millisecond)
	if got := atomic.LoadInt32(&ctrl.inFlight); got > reviewBuildConcurrencyLimit {
		t.Fatalf("expected at most %d in-flight builds, observed %d in-flight", reviewBuildConcurrencyLimit, got)
	}

	close(ctrl.release)
	wg.Wait()

	if got := atomic.LoadInt32(&ctrl.maxInFlight); got > reviewBuildConcurrencyLimit {
		t.Fatalf("expected max observed in-flight builds <= %d, got %d", reviewBuildConcurrencyLimit, got)
	}
}

// --- Finding 2: cache keyed on the currently-served checkpoint -----------

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
