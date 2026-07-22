package api

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/plasma/fh-mahjong/internal/review"
	"github.com/plasma/fh-mahjong/internal/storage"
)

// --- Finding 1: GET must not serve a stale-checkpoint report as current ----

// TestGetReviewDoesNotServeStaleShaRow pins round 23, Finding 1: a cached row
// under sha-A must NOT be served by GET once the policy server reports it is
// now serving sha-B — the whole point of checkpoint-keyed caching is
// defeated if GET just returns "the newest row" regardless of what's live.
func TestGetReviewDoesNotServeStaleShaRow(t *testing.T) {
	// Shrink the sha cache TTL to 0 so each GET below re-resolves the live
	// sha instead of trusting the previous request's short-TTL cache entry —
	// this test asserts on immediate promotion/rollback detection, not on
	// what happens to slip through within the (deliberately nonzero, in
	// production) cache window.
	oldTTL := reviewShaCacheTTL
	reviewShaCacheTTL = 0
	defer func() { reviewShaCacheTTL = oldTTL }()

	stub, ctrl := newShaSwapStub(t, "sha-A")
	defer stub.Close()
	t.Setenv("POLICY_SERVER_URL", stub.URL)

	server := newReviewTestServer(t, true)
	server.StorePaipu("stale-fixture", reviewFixtureJSON(t))

	// Build+cache a report under sha-A.
	close(ctrl.release)
	rec := doAuthedReviewRequest(t, server, http.MethodPost, "/api/v1/matches/stale-fixture/review")
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200 warming sha-A cache, got %d: %s", rec.Code, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), "sha-A") {
		t.Fatalf("expected warmed report to reflect sha-A: %s", rec.Body.String())
	}

	// GET immediately after: live sha still A, so the cached row is current.
	getA := doReviewRequest(t, server, http.MethodGet, "/api/v1/matches/stale-fixture/review")
	if getA.Code != http.StatusOK {
		t.Fatalf("expected 200 serving the current sha-A row, got %d: %s", getA.Code, getA.Body.String())
	}

	// Server is promoted to sha-B. No report has been built for sha-B yet.
	ctrl.setSha("sha-B")

	getB := doReviewRequest(t, server, http.MethodGet, "/api/v1/matches/stale-fixture/review")
	if getB.Code == http.StatusOK {
		t.Fatalf("must not serve the stale sha-A row once the live checkpoint is sha-B: %s", getB.Body.String())
	}
	if getB.Code != http.StatusNotFound {
		t.Fatalf("expected 404 on a live-sha cache miss, got %d: %s", getB.Code, getB.Body.String())
	}

	// Rollback to sha-A: its own old report must be servable again.
	ctrl.setSha("sha-A")
	getA2 := doReviewRequest(t, server, http.MethodGet, "/api/v1/matches/stale-fixture/review")
	if getA2.Code != http.StatusOK {
		t.Fatalf("expected 200 re-serving sha-A after rollback, got %d: %s", getA2.Code, getA2.Body.String())
	}
	if getA2.Body.String() != rec.Body.String() {
		t.Fatalf("expected rollback GET to reproduce the original sha-A report:\nwant: %s\ngot:  %s", rec.Body.String(), getA2.Body.String())
	}
}

// TestGetReviewLegacyServerFallsBackToNewestRow pins round 23, Finding 1's
// legacy carve-out: a policy server whose /healthz predates checkpoint_sha256
// entirely keeps today's behavior — GET serves the newest cached row.
func TestGetReviewLegacyServerFallsBackToNewestRow(t *testing.T) {
	var requestCount int
	stub := newStubPolicyServer(t, &requestCount) // legacy: no sha field anywhere
	defer stub.Close()
	t.Setenv("POLICY_SERVER_URL", stub.URL)

	server := newReviewTestServer(t, true)
	server.StorePaipu("legacy-fixture", reviewFixtureJSON(t))

	rec := doAuthedReviewRequest(t, server, http.MethodPost, "/api/v1/matches/legacy-fixture/review")
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200 warming the cache, got %d: %s", rec.Code, rec.Body.String())
	}

	getRec := doReviewRequest(t, server, http.MethodGet, "/api/v1/matches/legacy-fixture/review")
	if getRec.Code != http.StatusOK {
		t.Fatalf("expected 200 falling back to newest row on a legacy server, got %d: %s", getRec.Code, getRec.Body.String())
	}
	if getRec.Body.String() != rec.Body.String() {
		t.Fatalf("expected GET to return the newest cached row on a legacy server:\nwant: %s\ngot:  %s", rec.Body.String(), getRec.Body.String())
	}
}

// TestGetReviewHealthzDownFailsClosed pins round 23, Finding 1: GET must fail
// closed (503) when the policy server's identity can't be established,
// rather than silently serving whatever the newest cached row happens to be.
//
// Round 24, Finding 1 added a cheaper pre-check: a match with NO cached
// review row at all is now rejected (404) before ever touching healthz (see
// TestGetReviewNoCachedRowReturnsNotFoundWithoutHealthzCall). To keep
// exercising THIS test's actual point — a healthz outage fails closed rather
// than silently serving a stale row — a row must exist first, same as it
// would once a match has actually been reviewed at least once.
func TestGetReviewHealthzDownFailsClosed(t *testing.T) {
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
	server.StorePaipu("healthz-down-fixture", reviewFixtureJSON(t))
	if err := server.cacheMatchReview(context.Background(), "healthz-down-fixture", "some-checkpoint", []byte(`{"schemaVersion":1}`)); err != nil {
		t.Fatalf("seed cache: %v", err)
	}

	rec := doReviewRequest(t, server, http.MethodGet, "/api/v1/matches/healthz-down-fixture/review")
	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected 503 when healthz is down, got %d: %s", rec.Code, rec.Body.String())
	}
}

// TestGetReviewNoPolicyServerConfiguredFallsBackToNewestRow: with no
// POLICY_SERVER_URL at all (dev/test setups without a reviewer), GET keeps
// its pre-round-23 behavior — there is no live checkpoint identity to
// contradict a cached row, so the newest one is served as-is.
func TestGetReviewNoPolicyServerConfiguredFallsBackToNewestRow(t *testing.T) {
	server := newReviewTestServer(t, true)
	if err := server.cacheMatchReview(context.Background(), "no-policy-fixture", "some-checkpoint", []byte(`{"schemaVersion":1}`)); err != nil {
		t.Fatalf("seed cache: %v", err)
	}

	rec := doReviewRequest(t, server, http.MethodGet, "/api/v1/matches/no-policy-fixture/review")
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200 falling back to newest row with no policy server configured, got %d: %s", rec.Code, rec.Body.String())
	}
}

// --- Finding 2: /evaluate omitting checkpoint_sha256 must not be cached ---

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
