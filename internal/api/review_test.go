package api

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/glebarez/sqlite"
	"github.com/plasma/fh-mahjong/internal/storage"
	"gorm.io/gorm"
)

func newReviewTestServer(t *testing.T, withDB bool) *Server {
	t.Helper()
	var db *gorm.DB
	if withDB {
		var err error
		db, err = gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
		if err != nil {
			t.Fatalf("open sqlite: %v", err)
		}
		if err := storage.AutoMigrate(db); err != nil {
			t.Fatalf("automigrate: %v", err)
		}
	}
	hub := NewHub()
	go hub.Run()
	matchmaker := NewMatchmaker(NewInMemoryQueue(), nil, hub)
	return NewServer(db, hub, matchmaker)
}

func reviewFixtureJSON(t *testing.T) string {
	t.Helper()
	data, err := os.ReadFile(filepath.Join("..", "..", "testdata", "paipu", "review-fixture.json"))
	if err != nil {
		t.Fatalf("read fixture: %v", err)
	}
	return string(data)
}

// newStubPolicyServer mirrors internal/review/report_test.go's stub: uniform
// probabilities over the legal action mask.
func newStubPolicyServer(t *testing.T, requestCount *int) *httptest.Server {
	t.Helper()
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if requestCount != nil {
			*requestCount++
		}
		if r.URL.Path != "/evaluate" {
			http.NotFound(w, r)
			return
		}
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
	}))
}

func doReviewRequest(t *testing.T, server *Server, method, path string) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(method, path, nil)
	recorder := httptest.NewRecorder()
	server.Router.ServeHTTP(recorder, req)
	return recorder
}

func TestPostReviewNoPolicyServer(t *testing.T) {
	t.Setenv("POLICY_SERVER_URL", "")
	server := newReviewTestServer(t, true)
	server.StorePaipu("review-fixture", reviewFixtureJSON(t))

	rec := doReviewRequest(t, server, http.MethodPost, "/api/v1/matches/review-fixture/review")
	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected 503, got %d: %s", rec.Code, rec.Body.String())
	}
	var body map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode body: %v", err)
	}
	if body["error"] != "reviewer unavailable" {
		t.Fatalf("unexpected error body: %#v", body)
	}
}

func TestPostReviewBuildsAndCaches(t *testing.T) {
	var requestCount int
	stub := newStubPolicyServer(t, &requestCount)
	defer stub.Close()
	t.Setenv("POLICY_SERVER_URL", stub.URL)

	server := newReviewTestServer(t, true)
	server.StorePaipu("review-fixture", reviewFixtureJSON(t))

	rec := doReviewRequest(t, server, http.MethodPost, "/api/v1/matches/review-fixture/review")
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	var report map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &report); err != nil {
		t.Fatalf("decode report: %v", err)
	}
	if v, _ := report["schemaVersion"].(float64); v != 1 {
		t.Fatalf("expected schemaVersion 1, got %#v", report["schemaVersion"])
	}

	var count int64
	if err := server.DB.Model(&storage.MatchReview{}).Where("match_id = ?", "review-fixture").Count(&count).Error; err != nil {
		t.Fatalf("count MatchReview rows: %v", err)
	}
	if count != 1 {
		t.Fatalf("expected 1 MatchReview row, got %d", count)
	}

	firstRequestCount := requestCount
	if firstRequestCount == 0 {
		t.Fatal("expected at least one request to the stub policy server")
	}

	// POST again: should hit the cache, not the stub server.
	rec2 := doReviewRequest(t, server, http.MethodPost, "/api/v1/matches/review-fixture/review")
	if rec2.Code != http.StatusOK {
		t.Fatalf("expected 200 on cached POST, got %d: %s", rec2.Code, rec2.Body.String())
	}
	if requestCount != firstRequestCount {
		t.Fatalf("expected no new requests to stub on cache hit, got %d (was %d)", requestCount, firstRequestCount)
	}

	// GET returns the same cached report.
	getRec := doReviewRequest(t, server, http.MethodGet, "/api/v1/matches/review-fixture/review")
	if getRec.Code != http.StatusOK {
		t.Fatalf("expected 200 on GET, got %d: %s", getRec.Code, getRec.Body.String())
	}
	if getRec.Body.String() != rec.Body.String() {
		t.Fatalf("GET body differs from POST body:\nPOST: %s\nGET:  %s", rec.Body.String(), getRec.Body.String())
	}
}

func TestPostReviewPolicyServerDown(t *testing.T) {
	const policyURL = "http://127.0.0.1:1"
	t.Setenv("POLICY_SERVER_URL", policyURL)
	server := newReviewTestServer(t, true)
	server.StorePaipu("review-fixture", reviewFixtureJSON(t))

	rec := doReviewRequest(t, server, http.MethodPost, "/api/v1/matches/review-fixture/review")
	if rec.Code != http.StatusBadGateway {
		t.Fatalf("expected 502, got %d: %s", rec.Code, rec.Body.String())
	}
	// The 502 body must not leak the internal policy server address: Go
	// http.Client errors embed the full request URL, and this route is
	// unauthenticated.
	if body := rec.Body.String(); strings.Contains(body, policyURL) || strings.Contains(body, "127.0.0.1") {
		t.Fatalf("502 body leaks internal policy server URL: %s", body)
	}
}

func TestPostReviewForceRebuildsAndOverwrites(t *testing.T) {
	var requestCount int
	stub := newStubPolicyServer(t, &requestCount)
	defer stub.Close()
	t.Setenv("POLICY_SERVER_URL", stub.URL)

	server := newReviewTestServer(t, true)
	server.StorePaipu("review-fixture", reviewFixtureJSON(t))

	rec := doReviewRequest(t, server, http.MethodPost, "/api/v1/matches/review-fixture/review")
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200 on initial build, got %d: %s", rec.Code, rec.Body.String())
	}
	firstRequestCount := requestCount
	if firstRequestCount == 0 {
		t.Fatal("expected at least one request to the stub policy server")
	}

	// ?force=1 must rebuild against the policy server even with a cached row.
	rec2 := doReviewRequest(t, server, http.MethodPost, "/api/v1/matches/review-fixture/review?force=1")
	if rec2.Code != http.StatusOK {
		t.Fatalf("expected 200 on forced rebuild, got %d: %s", rec2.Code, rec2.Body.String())
	}
	if requestCount <= firstRequestCount {
		t.Fatalf("expected forced rebuild to hit the stub again, request count still %d", requestCount)
	}

	// Same match + same checkpoint: the row is overwritten in place, not duplicated.
	var count int64
	if err := server.DB.Model(&storage.MatchReview{}).
		Where("match_id = ? AND checkpoint_id = ?", "review-fixture", "stub.pt").
		Count(&count).Error; err != nil {
		t.Fatalf("count MatchReview rows: %v", err)
	}
	if count != 1 {
		t.Fatalf("expected exactly 1 MatchReview row after forced rebuild, got %d", count)
	}
}

func TestGetReviewMissing(t *testing.T) {
	server := newReviewTestServer(t, true)
	rec := doReviewRequest(t, server, http.MethodGet, "/api/v1/matches/unknown-match/review")
	if rec.Code != http.StatusNotFound {
		t.Fatalf("expected 404, got %d: %s", rec.Code, rec.Body.String())
	}
}

func TestPostReviewBadPaipu(t *testing.T) {
	stub := newStubPolicyServer(t, nil)
	defer stub.Close()
	t.Setenv("POLICY_SERVER_URL", stub.URL)

	server := newReviewTestServer(t, true)
	server.StorePaipu("bad", `{"rounds":[]}`)

	rec := doReviewRequest(t, server, http.MethodPost, "/api/v1/matches/bad/review")
	if rec.Code != http.StatusUnprocessableEntity {
		t.Fatalf("expected 422, got %d: %s", rec.Code, rec.Body.String())
	}
}
