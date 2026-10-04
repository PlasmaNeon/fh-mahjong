package api

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/glebarez/sqlite"
	"github.com/plasma/fh-mahjong/internal/review"
	"github.com/plasma/fh-mahjong/internal/review/reviewtest"
	"github.com/plasma/fh-mahjong/internal/storage"
	"golang.org/x/crypto/bcrypt"
	"gorm.io/gorm"
	"gorm.io/gorm/clause"
)

func studySession(t *testing.T, s *Server, id uint) (*http.Cookie, string) {
	cookie, csrf, _, _ := privateTableSession(t, s, privateTableAuthToken(t, id, fmt.Sprintf("reviewer-%d", id)))
	return cookie, csrf
}

func importRequest(t *testing.T, s *Server, body string, cookie *http.Cookie, csrf string) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest("POST", "/api/v1/replay-imports", strings.NewReader(body))
	req.AddCookie(cookie)
	req.Header.Set(csrfHeaderName, csrf)
	req.Header.Set("X-Paipu-Filename", "native.json")
	w := httptest.NewRecorder()
	s.Router.ServeHTTP(w, req)
	return w
}
func TestReplayImportOwnershipDedupAndValidation(t *testing.T) {
	s := newReviewTestServer(t, true)
	a, csrf := studySession(t, s, 910)
	b, bcsrf := studySession(t, s, 911)
	w := importRequest(t, s, reviewFixtureJSON(t), a, csrf)
	if w.Code != 201 {
		t.Fatalf("upload %d %s", w.Code, w.Body.String())
	}
	var row storage.ReplayImport
	if err := json.Unmarshal(w.Body.Bytes(), &row); err != nil {
		t.Fatal(err)
	}
	again := importRequest(t, s, reviewFixtureJSON(t), a, csrf)
	if again.Code != 200 || !strings.Contains(again.Body.String(), row.ID) {
		t.Fatal("dedup failed")
	}
	if w = doAuthedReviewRequestWithSession(t, s, "GET", "/api/v1/replay-imports/"+row.ID, b, bcsrf); w.Code != 404 {
		t.Fatal("cross-owner read")
	}
	if w = doAuthedReviewRequestWithSession(t, s, "POST", "/api/v1/replay-imports/"+row.ID+"/review", b, bcsrf); w.Code != 503 && w.Code != 404 {
		t.Fatal("cross-owner build")
	}
	if w = importRequest(t, s, `{"version":2}`, a, csrf); w.Code != 422 {
		t.Fatal("malformed import accepted")
	}
	if w = importRequest(t, s, reviewFixtureJSON(t), a, ""); w.Code != 403 {
		t.Fatal("CSRF missing")
	}
	stored := doAuthedReviewRequestWithSession(t, s, "GET", "/api/v1/replay-imports/"+row.ID, a, csrf)
	if stored.Code != 200 || !strings.Contains(stored.Body.String(), "import-"+row.ID) {
		t.Fatal("immutable namespace")
	}
	var matches int64
	s.DB.Model(&storage.Match{}).Count(&matches)
	if matches != 0 {
		t.Fatal("upload entered live match table")
	}
	list := doAuthedReviewRequestWithSession(t, s, "GET", "/api/v1/replay-imports", a, csrf)
	if strings.Contains(list.Body.String(), "wallSeed") {
		t.Fatal("listing leaks paipu JSON")
	}
}

func TestStudyAdmissionDedupCancellationAndExpiredLease(t *testing.T) {
	block := make(chan struct{})
	defer close(block)
	stub, _ := reviewtest.NewEvaluateStub(t, reviewtest.Options{Sha: func() string { return "study-sha" }, Block: block})
	t.Setenv("POLICY_SERVER_URL", stub.URL)
	s := newReviewTestServer(t, true)
	s.StorePaipu("study-fixture", reviewFixtureJSON(t))
	cookie, csrf := studySession(t, s, 930)
	w := doAuthedReviewRequestWithSession(t, s, "POST", "/api/v1/matches/study-fixture/study", cookie, csrf)
	if w.Code != 202 {
		t.Fatalf("admission %d %s", w.Code, w.Body.String())
	}
	var body struct{ ID string }
	json.Unmarshal(w.Body.Bytes(), &body)
	again := doAuthedReviewRequestWithSession(t, s, "POST", "/api/v1/matches/study-fixture/study", cookie, csrf)
	if again.Code != 200 || !strings.Contains(again.Body.String(), body.ID) {
		t.Fatal("active job duplicated")
	}
	other, otherCSRF := studySession(t, s, 931)
	if w = doAuthedReviewRequestWithSession(t, s, "GET", "/api/v1/review-jobs/"+body.ID, other, otherCSRF); w.Code != 404 {
		t.Fatal("cross-owner job")
	}
	if w = doAuthedReviewRequestWithSession(t, s, "DELETE", "/api/v1/review-jobs/"+body.ID, cookie, csrf); w.Code != 200 {
		t.Fatal("cancel failed")
	}
	var row storage.ReplayStudyJob
	s.DB.First(&row, "id = ?", body.ID)
	if row.State != "cancelled" {
		t.Fatal("cancellation not durable")
	}
	oldWorker := row.WorkerID
	resumed := doAuthedReviewRequestWithSession(t, s, "POST", "/api/v1/matches/study-fixture/study", cookie, csrf)
	if resumed.Code != 202 {
		t.Fatalf("resume %d %s", resumed.Code, resumed.Body.String())
	}
	s.DB.First(&row, "id = ?", body.ID)
	if row.WorkerID == oldWorker || row.State == "cancelled" {
		t.Fatal("resume reused stale execution identity")
	}
	expired := storage.ReplayStudyJob{ID: "expired", State: "evaluation", LeaseUntil: time.Now().Add(-time.Minute)}
	if studyResponse(expired)["state"] != "interrupted" {
		t.Fatal("expired worker called running")
	}
	s.studyMu.Lock()
	for _, active := range s.studyActive {
		active.cancel()
	}
	s.studyMu.Unlock()
}

// Local browser harness uses real auth/routes/SQLite and the real configured
// checkpoint. It never supplies synthetic advice and is skipped in CI.
func TestReplayBrowserHarness(t *testing.T) {
	if os.Getenv("FH_REVIEW_BROWSER") != "1" {
		t.Skip("opt-in browser harness")
	}
	t.Setenv("FRONTEND_ORIGINS", "http://127.0.0.1:3002")
	db, err := gorm.Open(sqlite.Open("/tmp/fh-review-browser.sqlite"), &gorm.Config{})
	if err != nil {
		t.Fatal(err)
	}
	if err := storage.AutoMigrate(db); err != nil {
		t.Fatal(err)
	}
	hub := NewHub()
	go hub.Run()
	s := NewServer(db, hub, NewMatchmaker(NewInMemoryQueue(), nil, hub))
	// Explicit developer-only refresh verifies real stored reports through the
	// normal resume builder, retaining genuine completed candidate rollouts.
	if os.Getenv("FH_REVIEW_BROWSER_REFRESH_DRAWS") == "1" {
		client := review.NewHTTPPolicyClientWithToken(os.Getenv("POLICY_SERVER_URL"), 0, os.Getenv("POLICY_SERVER_TOKEN"))
		ctx, cancel := context.WithTimeout(context.Background(), time.Minute)
		defer cancel()
		sha, err := client.CurrentCheckpointSha256(ctx)
		if err != nil {
			t.Fatal(err)
		}
		var jobs []storage.ReplayStudyJob
		if err := db.Where("state = ? AND checkpoint_sha = ?", "complete", sha).Find(&jobs).Error; err != nil {
			t.Fatal(err)
		}
		for _, job := range jobs {
			p, err := review.ValidateImport([]byte(job.SourceJSON))
			if err != nil {
				t.Fatal(err)
			}
			var saved review.Report
			var config review.StudyConfig
			if err := json.Unmarshal([]byte(job.ReportJSON), &saved); err != nil {
				t.Fatal(err)
			}
			if err := json.Unmarshal([]byte(job.ConfigJSON), &config); err != nil {
				t.Fatal(err)
			}
			updated, err := review.BuildStudy(ctx, p, client, job.EventWindow, config, sha, &saved, nil)
			if err != nil {
				t.Fatal(err)
			}
			body, err := json.Marshal(updated)
			if err != nil {
				t.Fatal(err)
			}
			if err := db.Model(&job).Update("report_json", string(body)).Error; err != nil {
				t.Fatal(err)
			}
		}
	}
	password, _ := bcrypt.GenerateFromPassword([]byte("ReplayStudyDemo42!"), bcrypt.DefaultCost)
	if err := s.DB.Clauses(clause.OnConflict{DoNothing: true}).Create(&storage.User{ID: 1000, Username: "replay-demo", UsernameKey: "replay-demo", Email: "replay-demo@example.test", PasswordHash: string(password)}).Error; err != nil {
		t.Fatal(err)
	}
	input, err := os.ReadFile("/tmp/fh-review-native.json")
	if err != nil {
		t.Fatal(err)
	}
	s.StorePaipu("study-local", string(input))
	listener := &http.Server{Addr: "127.0.0.1:8080", Handler: s.Router, ReadHeaderTimeout: 5 * time.Second}
	t.Cleanup(func() {
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		listener.Shutdown(ctx)
	})
	if err := listener.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		t.Fatal(err)
	}
}
