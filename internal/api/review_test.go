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
		// A single shared connection: an in-memory sqlite db is scoped to
		// its connection, so multiple pooled connections would each see
		// their own empty database. This matters once callers exercise
		// concurrent requests against the same server (round 21's
		// singleflight/concurrency-cap tests), mirroring
		// newPrivateTableTestServer's same fix.
		if sqlDB, err := db.DB(); err == nil {
			sqlDB.SetMaxOpenConns(1)
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
//
// Serves a genuine "ok":true /healthz with NO checkpoint_sha256 field (round
// 22, Finding 3): a TRUE legacy policy server, so CurrentCheckpointSha256
// resolves cleanly to ("", nil) and callers fall back to newest-row caching.
// Before round 22 this stub had no /healthz route at all (a 404, i.e. a
// healthz ERROR) and relied on that being folded into the same fallback —
// round 22 tightened handlePostReview to fail closed (503) on an actual
// healthz error, so this stub now answers /healthz explicitly to keep
// exercising the "true legacy" path it's meant to.
func newStubPolicyServer(t *testing.T, requestCount *int) *httptest.Server {
	t.Helper()
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/healthz" {
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"ok":true}`))
			return
		}
		if r.URL.Path != "/evaluate" {
			// requestCount only counts /evaluate calls — the thing that
			// actually costs the policy server RL-serving capacity.
			http.NotFound(w, r)
			return
		}
		if requestCount != nil {
			*requestCount++
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

// newStubPolicyServerWithSha behaves like newStubPolicyServer but reports a
// checkpoint_sha256, so cache-identity tests can simulate a same-path hot
// reload (new bytes, same checkpoint_path) by varying sha across servers.
// /healthz reports the SAME sha (round 22, Finding 3): a real serve_policy.py
// exposes its currently-loaded checkpoint's sha256 on both routes.
func newStubPolicyServerWithSha(t *testing.T, requestCount *int, sha string) *httptest.Server {
	t.Helper()
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/healthz" {
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(map[string]any{"ok": true, "checkpoint_sha256": sha})
			return
		}
		if r.URL.Path != "/evaluate" {
			http.NotFound(w, r)
			return
		}
		if requestCount != nil {
			*requestCount++
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
			"checkpoint_sha256": sha,
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

	rec := doAuthedReviewRequest(t, server, http.MethodPost, "/api/v1/matches/review-fixture/review")
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

	rec := doAuthedReviewRequest(t, server, http.MethodPost, "/api/v1/matches/review-fixture/review")
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
	rec2 := doAuthedReviewRequest(t, server, http.MethodPost, "/api/v1/matches/review-fixture/review")
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

// TestPostReviewPolicyServerDown: an entirely unreachable POLICY_SERVER_URL
// fails /healthz too, so this now surfaces round 22's fail-closed 503
// (Finding 3) rather than reaching a build attempt at all — the previous
// 502 came from /evaluate failing AFTER a (round-21) healthz fallback let
// the request through. See TestPostReviewEvaluateDownAfterHealthzUp below
// for the still-covered "healthz fine, /evaluate fails" 502 path.
func TestPostReviewPolicyServerDown(t *testing.T) {
	const policyURL = "http://127.0.0.1:1"
	t.Setenv("POLICY_SERVER_URL", policyURL)
	server := newReviewTestServer(t, true)
	server.StorePaipu("review-fixture", reviewFixtureJSON(t))

	rec := doAuthedReviewRequest(t, server, http.MethodPost, "/api/v1/matches/review-fixture/review")
	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected 503, got %d: %s", rec.Code, rec.Body.String())
	}
	// The body must not leak the internal policy server address: Go
	// http.Client errors embed the full request URL, and even an
	// authenticated caller should never see it.
	if body := rec.Body.String(); strings.Contains(body, policyURL) || strings.Contains(body, "127.0.0.1") {
		t.Fatalf("503 body leaks internal policy server URL: %s", body)
	}
}

// TestPostReviewEvaluateDownAfterHealthzUp covers the 502 path that
// TestPostReviewPolicyServerDown used to (before round 22's healthz
// fail-closed change intercepted it earlier): /healthz succeeds (server
// identity is known), but /evaluate itself fails.
func TestPostReviewEvaluateDownAfterHealthzUp(t *testing.T) {
	stub := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/healthz" {
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"ok":true,"checkpoint_sha256":"sha-eval-down"}`))
			return
		}
		http.Error(w, "internal error", http.StatusInternalServerError)
	}))
	defer stub.Close()
	t.Setenv("POLICY_SERVER_URL", stub.URL)

	server := newReviewTestServer(t, true)
	server.StorePaipu("review-fixture", reviewFixtureJSON(t))

	rec := doAuthedReviewRequest(t, server, http.MethodPost, "/api/v1/matches/review-fixture/review")
	if rec.Code != http.StatusBadGateway {
		t.Fatalf("expected 502, got %d: %s", rec.Code, rec.Body.String())
	}
	if body := rec.Body.String(); strings.Contains(body, stub.URL) {
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

	rec := doAuthedReviewRequest(t, server, http.MethodPost, "/api/v1/matches/review-fixture/review")
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200 on initial build, got %d: %s", rec.Code, rec.Body.String())
	}
	firstRequestCount := requestCount
	if firstRequestCount == 0 {
		t.Fatal("expected at least one request to the stub policy server")
	}

	// ?force=1 must rebuild against the policy server even with a cached row.
	rec2 := doAuthedReviewRequest(t, server, http.MethodPost, "/api/v1/matches/review-fixture/review?force=1")
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

// TestPostReviewDistinctShasYieldDistinctRows covers a same-path hot reload
// (round 18): two reports for the same match+checkpoint_path but different
// checkpoint_sha256 must land in two distinct, independently retrievable
// MatchReview rows, not collide on the path alone.
func TestPostReviewDistinctShasYieldDistinctRows(t *testing.T) {
	stubA := newStubPolicyServerWithSha(t, nil, "sha-aaaa")
	defer stubA.Close()

	server := newReviewTestServer(t, true)
	server.StorePaipu("review-fixture", reviewFixtureJSON(t))

	t.Setenv("POLICY_SERVER_URL", stubA.URL)
	recA := doAuthedReviewRequest(t, server, http.MethodPost, "/api/v1/matches/review-fixture/review")
	if recA.Code != http.StatusOK {
		t.Fatalf("expected 200 for sha-aaaa build, got %d: %s", recA.Code, recA.Body.String())
	}

	stubB := newStubPolicyServerWithSha(t, nil, "sha-bbbb")
	defer stubB.Close()
	t.Setenv("POLICY_SERVER_URL", stubB.URL)
	recB := doAuthedReviewRequest(t, server, http.MethodPost, "/api/v1/matches/review-fixture/review?force=1")
	if recB.Code != http.StatusOK {
		t.Fatalf("expected 200 for sha-bbbb build, got %d: %s", recB.Code, recB.Body.String())
	}

	var rows []storage.MatchReview
	if err := server.DB.Where("match_id = ?", "review-fixture").Find(&rows).Error; err != nil {
		t.Fatalf("query MatchReview rows: %v", err)
	}
	if len(rows) != 2 {
		t.Fatalf("expected 2 distinct MatchReview rows for 2 shas, got %d: %+v", len(rows), rows)
	}

	shaSeen := map[string]bool{}
	for _, row := range rows {
		shaSeen[row.CheckpointID] = true
		if !strings.Contains(row.ReportJSON, row.CheckpointID) {
			t.Fatalf("row CheckpointID %q not reflected in its own ReportJSON: %s", row.CheckpointID, row.ReportJSON)
		}
	}
	if !shaSeen["sha-aaaa"] || !shaSeen["sha-bbbb"] {
		t.Fatalf("expected rows keyed by both shas, got keys: %+v", shaSeen)
	}
}

// TestPostReviewForcedRefreshWithNewShaPreservesOldRow: a forced refresh that
// picks up a NEW sha (simulating a hot reload landing between requests) must
// insert a new row rather than overwriting the row for the OLD sha, so the
// old checkpoint's report is never destroyed.
func TestPostReviewForcedRefreshWithNewShaPreservesOldRow(t *testing.T) {
	stubOld := newStubPolicyServerWithSha(t, nil, "sha-old")
	defer stubOld.Close()

	server := newReviewTestServer(t, true)
	server.StorePaipu("review-fixture", reviewFixtureJSON(t))

	t.Setenv("POLICY_SERVER_URL", stubOld.URL)
	recOld := doAuthedReviewRequest(t, server, http.MethodPost, "/api/v1/matches/review-fixture/review")
	if recOld.Code != http.StatusOK {
		t.Fatalf("expected 200 for sha-old build, got %d: %s", recOld.Code, recOld.Body.String())
	}

	stubNew := newStubPolicyServerWithSha(t, nil, "sha-new")
	defer stubNew.Close()
	t.Setenv("POLICY_SERVER_URL", stubNew.URL)
	recNew := doAuthedReviewRequest(t, server, http.MethodPost, "/api/v1/matches/review-fixture/review?force=1")
	if recNew.Code != http.StatusOK {
		t.Fatalf("expected 200 for forced sha-new build, got %d: %s", recNew.Code, recNew.Body.String())
	}

	var oldRow storage.MatchReview
	err := server.DB.Where("match_id = ? AND checkpoint_id = ?", "review-fixture", "sha-old").First(&oldRow).Error
	if err != nil {
		t.Fatalf("expected sha-old row to survive the forced refresh, got err: %v", err)
	}
	if !strings.Contains(oldRow.ReportJSON, "sha-old") {
		t.Fatalf("sha-old row's report was overwritten with new content: %s", oldRow.ReportJSON)
	}

	var newRow storage.MatchReview
	err = server.DB.Where("match_id = ? AND checkpoint_id = ?", "review-fixture", "sha-new").First(&newRow).Error
	if err != nil {
		t.Fatalf("expected sha-new row to exist after forced refresh, got err: %v", err)
	}
}

// TestPostReviewLegacyShalessKeepsPathKeyedCaching pins today's behavior for
// a policy server predating checkpoint_sha256 (empty sha): caching still
// keys on checkpoint_path, exactly as before this fix.
func TestPostReviewLegacyShalessKeepsPathKeyedCaching(t *testing.T) {
	var requestCount int
	stub := newStubPolicyServer(t, &requestCount) // no sha field in response
	defer stub.Close()
	t.Setenv("POLICY_SERVER_URL", stub.URL)

	server := newReviewTestServer(t, true)
	server.StorePaipu("review-fixture", reviewFixtureJSON(t))

	rec := doAuthedReviewRequest(t, server, http.MethodPost, "/api/v1/matches/review-fixture/review")
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}

	var row storage.MatchReview
	if err := server.DB.Where("match_id = ?", "review-fixture").First(&row).Error; err != nil {
		t.Fatalf("expected a cached row, got err: %v", err)
	}
	if row.CheckpointID != "stub.pt" {
		t.Fatalf("expected legacy sha-less caching to key on checkpoint_path, got CheckpointID=%q", row.CheckpointID)
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

	rec := doAuthedReviewRequest(t, server, http.MethodPost, "/api/v1/matches/bad/review")
	if rec.Code != http.StatusUnprocessableEntity {
		t.Fatalf("expected 422, got %d: %s", rec.Code, rec.Body.String())
	}
}
