package api

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"net/http"
	"os"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"github.com/plasma/fh-mahjong/internal/review"
	"github.com/plasma/fh-mahjong/internal/storage"
	"gorm.io/gorm"
	"gorm.io/gorm/clause"
)

const studyJobTimeout = 30 * time.Minute
const studyLease = 90 * time.Second

type studyExecution struct {
	cancel context.CancelFunc
	token  string
}

func studySource(c *gin.Context) (string, string) {
	if id := c.Param("importId"); id != "" {
		return "import", id
	}
	return "match", c.Param("matchId")
}

func (s *Server) studySourceJSON(ctx context.Context, kind, id string, user uint) (string, bool) {
	if kind == "match" {
		return s.loadPaipuJSON(ctx, id)
	}
	var row storage.ReplayImport
	err := s.DB.WithContext(ctx).Where("id = ? AND owner_id = ?", id, user).First(&row).Error
	return row.PaipuJSON, err == nil
}

func studyResponse(row storage.ReplayStudyJob) gin.H {
	state := row.State
	if state != "complete" && state != "failed" && state != "cancelled" && row.LeaseUntil.Before(time.Now()) {
		state = "interrupted"
	}
	var report *review.Report
	if row.ReportJSON != "" {
		_ = json.Unmarshal([]byte(row.ReportJSON), &report)
	}
	return gin.H{"id": row.ID, "state": state, "completed": row.Completed, "total": row.Total, "error": row.Error, "report": report}
}

func studyBuildKey(input, sha string, window uint32, cfg review.StudyConfig) string {
	configJSON, _ := json.Marshal(cfg)
	digest := sha256.Sum256([]byte(fmt.Sprintf("%s|%s|%d|%d|%s|%s", input, sha, review.SchemaVersion, window, review.StudyMethod, configJSON)))
	return hex.EncodeToString(digest[:])
}

func (s *Server) handleGetStudy(c *gin.Context) {
	kind, id := studySource(c)
	user := c.GetUint("userID")
	input, ok := s.studySourceJSON(c.Request.Context(), kind, id, user)
	if !ok {
		respondError(c, 404, "replay not found")
		return
	}
	var row storage.ReplayStudyJob
	query := s.DB.WithContext(c.Request.Context()).Where("source_kind = ? AND source_id = ? AND owner_id = ?", kind, id, user)
	if err := query.Order("updated_at DESC").First(&row).Error; err != nil {
		respondError(c, 404, "no analysis yet")
		return
	}
	// Historical jobs can be opened by id. The source's default analysis only
	// represents the currently served checkpoint, mirroring the existing cache.
	if url := os.Getenv("POLICY_SERVER_URL"); url != "" {
		sha, legacy, err := s.reviewLiveSha(c.Request.Context(), url)
		if err != nil {
			respondError(c, 503, "policy server identity unavailable")
			return
		}
		if legacy {
			respondError(c, 503, "full analysis requires checkpoint identity support")
			return
		}
		key := studyBuildKey(input, sha, reviewEventWindow(url), review.DefaultStudyConfig())
		if err := query.Where("build_key = ?", key).Order("updated_at DESC").First(&row).Error; err != nil {
			respondError(c, 404, "no analysis for the current checkpoint and settings")
			return
		}
	}
	c.JSON(200, studyResponse(row))
}

func (s *Server) handlePostStudy(c *gin.Context) {
	user := c.GetUint("userID")
	kind, id := studySource(c)
	if !s.reviewRateLimiter.Allow(user) {
		c.Header("Retry-After", "10")
		respondError(c, 429, "too many analysis requests; retry shortly")
		return
	}
	url := os.Getenv("POLICY_SERVER_URL")
	if url == "" {
		respondError(c, 503, "reviewer unavailable")
		return
	}
	window := reviewEventWindow(url)
	client := review.NewHTTPPolicyClientWithToken(url, window, os.Getenv("POLICY_SERVER_TOKEN"))
	sha, err := client.CurrentCheckpointSha256(c.Request.Context())
	if err != nil || sha == "" {
		respondError(c, 503, "policy server identity unavailable")
		return
	}
	input, ok := s.studySourceJSON(c.Request.Context(), kind, id, user)
	if !ok {
		respondError(c, 404, "replay not found")
		return
	}
	cfg := review.DefaultStudyConfig()
	configJSON, _ := json.Marshal(cfg)
	key := studyBuildKey(input, sha, window, cfg)

	s.studyMu.Lock()
	defer s.studyMu.Unlock()
	var row storage.ReplayStudyJob
	err = s.DB.WithContext(c.Request.Context()).Where("owner_id = ? AND build_key = ?", user, key).First(&row).Error
	if err != nil && !errors.Is(err, gorm.ErrRecordNotFound) {
		respondError(c, 500, "cannot check analysis")
		return
	}
	if err == nil && (row.State == "complete" || (row.State != "failed" && row.State != "cancelled" && row.LeaseUntil.After(time.Now()))) {
		c.JSON(200, studyResponse(row))
		return
	}
	if len(s.studyActive) >= reviewBuildConcurrencyLimit+reviewBuildWaitQueueLimit {
		c.Header("Retry-After", "5")
		respondError(c, 429, "analysis queue is full; retry shortly")
		return
	}
	if row.ID == "" {
		row = storage.ReplayStudyJob{ID: uuid.NewString(), OwnerID: user, BuildKey: key, SourceKind: kind, SourceID: id, SourceJSON: input, CheckpointSHA: sha, EventWindow: window, ConfigJSON: string(configJSON), State: "queued", WorkerID: uuid.NewString(), LeaseUntil: time.Now().Add(studyLease)}
		// Multiple processes may race admission. The unique key is the authority;
		// only the instance that inserted this row may start it.
		result := s.DB.WithContext(c.Request.Context()).Clauses(clause.OnConflict{DoNothing: true}).Create(&row)
		if result.Error != nil {
			respondError(c, 500, "cannot create analysis")
			return
		}
		if result.RowsAffected == 0 {
			s.DB.Where("owner_id = ? AND build_key = ?", user, key).First(&row)
			c.JSON(200, studyResponse(row))
			return
		}
	} else {
		row.WorkerID = uuid.NewString()
		result := s.DB.WithContext(c.Request.Context()).Model(&storage.ReplayStudyJob{}).Where("id = ? AND (lease_until < ? OR state IN ?)", row.ID, time.Now(), []string{"failed", "cancelled"}).Updates(map[string]any{"state": "queued", "error": "", "worker_id": row.WorkerID, "lease_until": time.Now().Add(studyLease)})
		if result.Error != nil {
			respondError(c, 500, "cannot resume analysis")
			return
		}
		if result.RowsAffected == 0 {
			respondError(c, 409, "analysis is already running")
			return
		}
		row.State = "queued"
		row.Error = ""
		row.LeaseUntil = time.Now().Add(studyLease)
	}
	ctx, cancel := context.WithTimeout(context.Background(), studyJobTimeout)
	s.studyActive[row.ID] = studyExecution{cancel: cancel, token: row.WorkerID}
	go s.runStudyJob(ctx, cancel, row, client, cfg)
	c.JSON(202, studyResponse(row))
}

func (s *Server) runStudyJob(ctx context.Context, cancel context.CancelFunc, row storage.ReplayStudyJob, client *review.HTTPPolicyClient, cfg review.StudyConfig) {
	defer func() {
		cancel()
		s.studyMu.Lock()
		if active, ok := s.studyActive[row.ID]; ok && active.token == row.WorkerID {
			delete(s.studyActive, row.ID)
		}
		s.studyMu.Unlock()
	}()
	// Heartbeat renews the lease during long decision batches, and also observes
	// cancellation requested through another process. Every query is bounded.
	go func() {
		tick := time.NewTicker(5 * time.Second)
		defer tick.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-tick.C:
				hctx, stop := context.WithTimeout(ctx, 3*time.Second)
				result := s.DB.WithContext(hctx).Model(&storage.ReplayStudyJob{}).Where("id = ? AND worker_id = ? AND state NOT IN ?", row.ID, row.WorkerID, []string{"cancelled", "complete", "failed"}).Update("lease_until", time.Now().Add(studyLease))
				stop()
				if result.Error != nil || result.RowsAffected == 0 {
					cancel()
					return
				}
			}
		}
	}()
	fail := func(err error) {
		log.Printf("replay study %s failed: %v", row.ID, err)
		message := "analysis failed; retry to resume completed decisions"
		if errors.Is(err, review.ErrUnreviewable) {
			message = err.Error()
		}
		if errors.Is(err, context.DeadlineExceeded) {
			message = "analysis time limit reached; retry to resume"
		}
		if errors.Is(err, errReviewBuildQueueFull) {
			message = "analysis queue is full; retry shortly"
		}
		fctx, stop := context.WithTimeout(context.Background(), 5*time.Second)
		defer stop()
		s.DB.WithContext(fctx).Model(&storage.ReplayStudyJob{}).Where("id = ? AND worker_id = ? AND state <> ?", row.ID, row.WorkerID, "cancelled").Updates(map[string]any{"state": "failed", "error": message, "lease_until": time.Now()})
	}
	if err := s.acquireReviewBuildSlot(ctx); err != nil {
		fail(err)
		return
	}
	defer s.releaseReviewBuildSlot()
	p, err := review.ValidateImport([]byte(row.SourceJSON))
	if err != nil {
		fail(fmt.Errorf("%w: %v", review.ErrUnreviewable, err))
		return
	}
	var resume *review.Report
	if row.ReportJSON != "" {
		_ = json.Unmarshal([]byte(row.ReportJSON), &resume)
	}
	save := func(report *review.Report, phase string, done, total int) error {
		body, err := json.Marshal(report)
		if err != nil {
			return err
		}
		result := s.DB.WithContext(ctx).Model(&storage.ReplayStudyJob{}).Where("id = ? AND worker_id = ? AND state <> ?", row.ID, row.WorkerID, "cancelled").Updates(map[string]any{"report_json": string(body), "state": phase, "completed": done, "total": total, "lease_until": time.Now().Add(studyLease)})
		if result.Error != nil {
			return result.Error
		}
		if result.RowsAffected == 0 {
			return context.Canceled
		}
		return nil
	}
	_, err = review.BuildStudy(ctx, p, client, row.EventWindow, cfg, row.CheckpointSHA, resume, save)
	if err != nil {
		fail(err)
	}
}

func (s *Server) handleGetStudyJob(c *gin.Context) {
	var row storage.ReplayStudyJob
	if err := s.DB.WithContext(c.Request.Context()).Where("id = ? AND owner_id = ?", c.Param("jobId"), c.GetUint("userID")).First(&row).Error; err != nil {
		respondError(c, 404, "analysis not found")
		return
	}
	c.JSON(200, studyResponse(row))
}

func (s *Server) handleCancelStudyJob(c *gin.Context) {
	s.studyMu.Lock()
	defer s.studyMu.Unlock()
	var row storage.ReplayStudyJob
	if err := s.DB.WithContext(c.Request.Context()).Where("id = ? AND owner_id = ?", c.Param("jobId"), c.GetUint("userID")).First(&row).Error; err != nil {
		respondError(c, 404, "analysis not found")
		return
	}
	if row.State == "complete" {
		c.JSON(200, studyResponse(row))
		return
	}
	if err := s.DB.WithContext(c.Request.Context()).Model(&row).Updates(map[string]any{"state": "cancelled", "lease_until": time.Now()}).Error; err != nil {
		respondError(c, 500, "cannot cancel analysis")
		return
	}
	if active, ok := s.studyActive[row.ID]; ok {
		active.cancel()
	}
	row.State = "cancelled"
	c.JSON(http.StatusOK, studyResponse(row))
}
