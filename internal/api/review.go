package api

import (
	"encoding/json"
	"errors"
	"net/http"
	"os"

	"github.com/gin-gonic/gin"
	"github.com/plasma/fh-mahjong/internal/engine"
	"github.com/plasma/fh-mahjong/internal/review"
	"github.com/plasma/fh-mahjong/internal/storage"
	"gorm.io/gorm"
)

// handleGetReview serves the newest cached MatchReview for a match. It is a
// pure cache lookup — it never builds a report. DB nil or no cached row →
// 404.
func (s *Server) handleGetReview(c *gin.Context) {
	matchID := c.Param("matchId")
	if matchID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "matchId is required"})
		return
	}

	if s.DB == nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "no cached review for this match"})
		return
	}

	var row storage.MatchReview
	err := s.DB.Where("match_id = ?", matchID).Order("created_at DESC").First(&row).Error
	if errors.Is(err, gorm.ErrRecordNotFound) {
		c.JSON(http.StatusNotFound, gin.H{"error": "no cached review for this match"})
		return
	}
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to load cached review"})
		return
	}

	c.Data(http.StatusOK, "application/json", []byte(row.ReportJSON))
}

// handlePostReview builds (or serves the cached) review report for a match.
//
// Status contract: 503 when POLICY_SERVER_URL is unset (no reviewer
// configured); 404 when no paipu exists for matchId; 422 when the paipu
// can't be reconstructed into reviewable decisions
// (errors.Is(err, review.ErrUnreviewable)); 502 when the policy server call
// itself fails; 200 with the report JSON otherwise.
//
// Cache policy: with a DB present, the newest cached MatchReview for the
// match is returned as-is unless ?force=1 is passed, in which case a fresh
// report is built and upserted keyed on (MatchID, CheckpointID=report's
// serving checkpoint). Without a DB (dev mode), every call builds fresh and
// nothing is cached.
func (s *Server) handlePostReview(c *gin.Context) {
	matchID := c.Param("matchId")
	if matchID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "matchId is required"})
		return
	}

	policyURL := os.Getenv("POLICY_SERVER_URL")
	if policyURL == "" {
		c.JSON(http.StatusServiceUnavailable, gin.H{"error": "reviewer unavailable"})
		return
	}

	force := c.Query("force") == "1"
	if s.DB != nil && !force {
		var cached storage.MatchReview
		err := s.DB.Where("match_id = ?", matchID).Order("created_at DESC").First(&cached).Error
		if err == nil {
			c.Data(http.StatusOK, "application/json", []byte(cached.ReportJSON))
			return
		}
		if !errors.Is(err, gorm.ErrRecordNotFound) {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to check cached review"})
			return
		}
	}

	paipuJSON, ok := s.loadPaipuJSON(matchID)
	if !ok {
		c.JSON(http.StatusNotFound, gin.H{"error": "Match not found"})
		return
	}

	var paipu engine.Paipu
	if err := json.Unmarshal([]byte(paipuJSON), &paipu); err != nil {
		c.JSON(http.StatusUnprocessableEntity, gin.H{"error": "unreviewable paipu: " + err.Error()})
		return
	}

	report, err := review.BuildReport(&paipu, review.NewHTTPPolicyClient(policyURL))
	if err != nil {
		if errors.Is(err, review.ErrUnreviewable) {
			c.JSON(http.StatusUnprocessableEntity, gin.H{"error": "unreviewable paipu: " + err.Error()})
			return
		}
		c.JSON(http.StatusBadGateway, gin.H{"error": "policy server evaluation failed: " + err.Error()})
		return
	}

	reportJSON, err := json.Marshal(report)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to encode report"})
		return
	}

	if s.DB != nil {
		if err := s.cacheMatchReview(matchID, report.CheckpointPath, reportJSON); err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to cache review"})
			return
		}
	}

	c.Data(http.StatusOK, "application/json", reportJSON)
}

// cacheMatchReview upserts the MatchReview row keyed on (matchID,
// checkpointID): an existing row for that exact pair is overwritten in
// place (refreshing CreatedAt so it stays "newest"); otherwise a new row is
// inserted. This keeps prior champions' reports around under their own
// CheckpointID while a re-review with the same champion replaces its own
// cache entry rather than accumulating duplicates.
func (s *Server) cacheMatchReview(matchID, checkpointID string, reportJSON []byte) error {
	var existing storage.MatchReview
	err := s.DB.Where("match_id = ? AND checkpoint_id = ?", matchID, checkpointID).First(&existing).Error
	if err == nil {
		existing.ReportJSON = string(reportJSON)
		return s.DB.Save(&existing).Error
	}
	if !errors.Is(err, gorm.ErrRecordNotFound) {
		return err
	}
	row := storage.MatchReview{
		MatchID:      matchID,
		CheckpointID: checkpointID,
		ReportJSON:   string(reportJSON),
	}
	return s.DB.Create(&row).Error
}
