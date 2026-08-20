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

	"github.com/plasma/fh-mahjong/internal/storage"
)

// blockingPolicyStub serves /evaluate (and optionally /healthz) but blocks
// each /evaluate request on release until it is closed, letting tests hold a
// build "in flight" to observe concurrency.
type blockingPolicyStub struct {
	release     chan struct{}
	evalCount   int32
	inFlight    int32
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

// TestPostReviewBuildTotalTimeoutReleasesSlotAndUnwedges pins round 25,
// Finding 1: a build that stalls beyond the (test-shortened)
// whole-lifecycle bound must NOT wedge its server-wide build slot forever.
// Before the fix, the 120s /evaluate timeout only wrapped the policy-server
// call itself — established well after admission — so a hang anywhere
// earlier (admission wait, the contextless paipu load) held the slot open
// with no ceiling at all. Here the stall is modeled at the policy-evaluate
// step (the same place a hung DB call would have wedged things pre-fix): the
// bounded context now covers that step too, so once it expires the slot is
// released and a later, distinct-match build can still be admitted and
// complete instead of piling into a permanent 429/503.
func TestPostReviewBuildTotalTimeoutReleasesSlotAndUnwedges(t *testing.T) {
	oldTimeout := reviewBuildTotalTimeout
	// Generous enough to survive scheduling/DB contention under -race and
	// concurrent package tests, but still far shorter than the production
	// default so the test stays fast.
	reviewBuildTotalTimeout = 1 * time.Second
	defer func() { reviewBuildTotalTimeout = oldTimeout }()

	stub, ctrl := newBlockingPolicyStub(t)
	defer stub.Close()
	t.Setenv("POLICY_SERVER_URL", stub.URL)

	server := newReviewTestServer(t, true)
	fixture := reviewFixtureJSON(t)
	cookie, csrf := authedReviewSession(t, server, 2501)

	// Occupy BOTH build slots with requests that will never see their
	// /evaluate call released — they must instead be unwedged by the
	// shortened total-lifecycle bound expiring.
	stalledIDs := []string{"round25-stall-a", "round25-stall-b"}
	var wg sync.WaitGroup
	for _, id := range stalledIDs {
		server.StorePaipu(id, fixture)
		wg.Add(1)
		go func(id string) {
			defer wg.Done()
			rec := doAuthedReviewRequestWithSession(t, server, http.MethodPost, "/api/v1/matches/"+id+"/review", cookie, csrf)
			// The bounded context aborts the in-flight /evaluate call, so
			// this surfaces as a policy-evaluation failure, not a hang.
			if rec.Code == http.StatusOK {
				t.Errorf("match %s: expected a non-200 outcome once the total build bound expired mid-evaluate, got 200: %s", id, rec.Body.String())
			}
		}(id)
	}

	// Wait until both stalled builds have actually started (occupying both
	// slots) before relying on the bound to unwedge them.
	deadline := time.Now().Add(15 * time.Second)
	for atomic.LoadInt32(&ctrl.inFlight) < 2 {
		if time.Now().After(deadline) {
			t.Fatal("timed out waiting for both stalled builds to start")
		}
		time.Sleep(2 * time.Millisecond)
	}

	wg.Wait() // both stalled requests must return once their bound expires

	// The slots must be released: a THIRD, distinct-match build must still
	// be admissible (not 429 "queue is full") — proving no permanent wedge.
	// It will itself stall against the same policy stub and time out the
	// same way, but it must at least be ADMITTED rather than rejected for
	// lack of a free slot.
	overflowID := "round25-stall-overflow"
	server.StorePaipu(overflowID, fixture)
	rec := doAuthedReviewRequestWithSession(t, server, http.MethodPost, "/api/v1/matches/"+overflowID+"/review", cookie, csrf)
	if rec.Code == http.StatusTooManyRequests {
		t.Fatalf("expected the previously-stalled slots to have been released, got 429 (queue still full): %s", rec.Body.String())
	}

	close(ctrl.release)
}

// TestPostReviewQueuedWaiterTimesOutWith503 pins round 25, Finding 1's other
// half: a request that queues (rather than immediately admits) for a build
// slot must not wait unboundedly either — once ITS bounded context expires
// while still queued, it gets 503 and its queue slot is released, rather
// than blocking forever behind two already-occupied (but otherwise healthy,
// not-yet-expired) build slots.
func TestPostReviewQueuedWaiterTimesOutWith503(t *testing.T) {
	oldTimeout := reviewBuildTotalTimeout
	reviewBuildTotalTimeout = 30 * time.Second // generous: A and B must not expire during this test
	defer func() { reviewBuildTotalTimeout = oldTimeout }()

	stub, ctrl := newBlockingPolicyStub(t)
	defer stub.Close()
	t.Setenv("POLICY_SERVER_URL", stub.URL)

	server := newReviewTestServer(t, true)
	fixture := reviewFixtureJSON(t)
	cookie, csrf := authedReviewSession(t, server, 2502)

	occupyIDs := []string{"round25-queue-a", "round25-queue-b"}
	var wg sync.WaitGroup
	for _, id := range occupyIDs {
		server.StorePaipu(id, fixture)
		wg.Add(1)
		go func(id string) {
			defer wg.Done()
			rec := doAuthedReviewRequestWithSession(t, server, http.MethodPost, "/api/v1/matches/"+id+"/review", cookie, csrf)
			if rec.Code != http.StatusOK {
				t.Errorf("match %s: expected eventual 200 once released, got %d: %s", id, rec.Code, rec.Body.String())
			}
		}(id)
	}

	// Wait until both slots are genuinely occupied (their /evaluate calls
	// in flight) before shrinking the timeout for the NEXT build only.
	deadline := time.Now().Add(15 * time.Second)
	for atomic.LoadInt32(&ctrl.inFlight) < 2 {
		if time.Now().After(deadline) {
			t.Fatal("timed out waiting for both occupying builds to start")
		}
		time.Sleep(2 * time.Millisecond)
	}

	// Now shrink the bound sharply for the queued waiter created below —
	// A's and B's contexts were already created (with the generous bound)
	// before this line, so they are unaffected. Generous enough to survive
	// scheduling overhead under -race while still exercising the timeout
	// path well within the test's own timeout.
	reviewBuildTotalTimeout = 500 * time.Millisecond

	queuedID := "round25-queue-waiter"
	server.StorePaipu(queuedID, fixture)
	rec := doAuthedReviewRequestWithSession(t, server, http.MethodPost, "/api/v1/matches/"+queuedID+"/review", cookie, csrf)
	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected 503 for a waiter whose bound expired while queued for a slot, got %d: %s", rec.Code, rec.Body.String())
	}

	waiters := atomic.LoadInt32(&server.reviewBuildWaiters)
	if waiters != 0 {
		t.Fatalf("expected the timed-out waiter's queue slot to be released, got %d waiters still counted", waiters)
	}

	// A and B must still be running, unaffected by the waiter's own timeout.
	if atomic.LoadInt32(&ctrl.inFlight) != 2 {
		t.Fatal("expected both occupying builds to still be in flight, unaffected by the queued waiter's own timeout")
	}

	close(ctrl.release)
	wg.Wait()
}

// TestPostReviewForcedAndNonForcedSameIdentityCoalesceToOneBuild pins round
// 25, Finding 2: a forced and a non-forced request for the SAME (match,
// checkpoint sha) identity, arriving concurrently, must share exactly ONE
// build — not race two separate builds that both try to persist the same
// (match_id, checkpoint_id) row and have the loser 500.
func TestPostReviewForcedAndNonForcedSameIdentityCoalesceToOneBuild(t *testing.T) {
	stub, ctrl := newBlockingPolicyStub(t)
	defer stub.Close()
	t.Setenv("POLICY_SERVER_URL", stub.URL)

	server := newReviewTestServer(t, true)
	server.StorePaipu("round25-force-fixture", reviewFixtureJSON(t))
	cookie, csrf := authedReviewSession(t, server, 2503)

	resultForced := make(chan *httptest.ResponseRecorder, 1)
	resultPlain := make(chan *httptest.ResponseRecorder, 1)
	go func() {
		resultForced <- doAuthedReviewRequestWithSession(t, server, http.MethodPost, "/api/v1/matches/round25-force-fixture/review?force=1", cookie, csrf)
	}()
	go func() {
		resultPlain <- doAuthedReviewRequestWithSession(t, server, http.MethodPost, "/api/v1/matches/round25-force-fixture/review", cookie, csrf)
	}()

	deadline := time.Now().Add(15 * time.Second)
	for atomic.LoadInt32(&ctrl.evalCount) < 1 {
		if time.Now().After(deadline) {
			t.Fatal("timed out waiting for the shared build to start")
		}
		time.Sleep(2 * time.Millisecond)
	}
	// Give the second request a moment to also reach the build path (or
	// coalesce onto the in-flight one) before releasing.
	time.Sleep(100 * time.Millisecond)
	close(ctrl.release)

	var recForced, recPlain *httptest.ResponseRecorder
	select {
	case recForced = <-resultForced:
	case <-time.After(15 * time.Second):
		t.Fatal("timed out waiting for the forced request")
	}
	select {
	case recPlain = <-resultPlain:
	case <-time.After(15 * time.Second):
		t.Fatal("timed out waiting for the plain request")
	}

	if recForced.Code != http.StatusOK {
		t.Fatalf("expected forced request to get 200, got %d: %s", recForced.Code, recForced.Body.String())
	}
	if recPlain.Code != http.StatusOK {
		t.Fatalf("expected plain (cache-miss) request to get 200, got %d: %s", recPlain.Code, recPlain.Body.String())
	}

	if got := atomic.LoadInt32(&ctrl.evalCount); got != 1 {
		t.Fatalf("expected exactly 1 /evaluate call (coalesced build), got %d", got)
	}

	var count int64
	if err := server.DB.Model(&storage.MatchReview{}).Where("match_id = ?", "round25-force-fixture").Count(&count).Error; err != nil {
		t.Fatalf("count MatchReview rows: %v", err)
	}
	if count != 1 {
		t.Fatalf("expected exactly 1 cached row, got %d", count)
	}
}

// TestCacheMatchReviewUpsertIsRaceSafe is a focused unit test on
// cacheMatchReview itself (round 25, Finding 2): saving the same
// (matchID, checkpointID) identity twice must never error (no unique-index
// violation) and must leave exactly one row behind, reflecting the LATEST
// report.
func TestCacheMatchReviewUpsertIsRaceSafe(t *testing.T) {
	server := newReviewTestServer(t, true)

	if err := server.cacheMatchReview(context.Background(), "round25-upsert-fixture", "ckpt-1", []byte(`{"schemaVersion":1,"n":1}`)); err != nil {
		t.Fatalf("first save: %v", err)
	}
	if err := server.cacheMatchReview(context.Background(), "round25-upsert-fixture", "ckpt-1", []byte(`{"schemaVersion":1,"n":2}`)); err != nil {
		t.Fatalf("second save (same identity) must upsert without error, got: %v", err)
	}

	var rows []storage.MatchReview
	if err := server.DB.Where("match_id = ? AND checkpoint_id = ?", "round25-upsert-fixture", "ckpt-1").Find(&rows).Error; err != nil {
		t.Fatalf("query rows: %v", err)
	}
	if len(rows) != 1 {
		t.Fatalf("expected exactly 1 row after two saves of the same identity, got %d", len(rows))
	}
	if rows[0].ReportJSON != `{"schemaVersion":1,"n":2}` {
		t.Fatalf("expected the row to reflect the latest save, got %s", rows[0].ReportJSON)
	}
}

// TestCacheMatchReviewConcurrentSameIdentityNoUniqueViolation drives
// cacheMatchReview concurrently for the same identity from many goroutines,
// under -race, to pin that the upsert is safe under real concurrency, not
// just sequential re-saves.
func TestCacheMatchReviewConcurrentSameIdentityNoUniqueViolation(t *testing.T) {
	server := newReviewTestServer(t, true)

	const n = 8
	errCh := make(chan error, n)
	var wg sync.WaitGroup
	for i := 0; i < n; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			errCh <- server.cacheMatchReview(context.Background(), "round25-concurrent-fixture", "ckpt-1", []byte(`{"schemaVersion":1}`))
		}(i)
	}
	wg.Wait()
	close(errCh)
	for err := range errCh {
		if err != nil {
			t.Fatalf("concurrent cacheMatchReview must never error on a unique-index conflict, got: %v", err)
		}
	}

	var count int64
	if err := server.DB.Model(&storage.MatchReview{}).Where("match_id = ? AND checkpoint_id = ?", "round25-concurrent-fixture", "ckpt-1").Count(&count).Error; err != nil {
		t.Fatalf("count rows: %v", err)
	}
	if count != 1 {
		t.Fatalf("expected exactly 1 row after concurrent upserts of the same identity, got %d", count)
	}
}
