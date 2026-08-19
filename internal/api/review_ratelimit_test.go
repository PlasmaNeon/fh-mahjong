package api

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

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
