package api

import (
	"net/http"
	"testing"
)

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
