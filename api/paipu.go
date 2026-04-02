package api

import (
	"encoding/json"
	"io"
	"net/http"
	"os"
	"path/filepath"

	"github.com/google/uuid"
	"github.com/gin-gonic/gin"
	"github.com/plasma/fh-mahjong/models"
	"gorm.io/gorm"
)

func (s *Server) handleGetPaipu(c *gin.Context) {
	matchID := c.Param("matchId")
	if matchID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "matchId is required"})
		return
	}

	// Try in-memory store first (works with or without DB)
	if data, ok := s.GetPaipu(matchID); ok {
		c.Data(http.StatusOK, "application/json", []byte(data))
		return
	}

	// Local dev fallback: allow replaying checked-in paipu fixtures even when DB
	// persistence is unavailable or the requested hand was never imported.
	if data, ok := loadPaipuFixture(matchID); ok {
		c.Data(http.StatusOK, "application/json", data)
		return
	}

	// Fall back to database
	if s.DB == nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Match not found"})
		return
	}

	// Check paipu_records table (per-round paipus)
	var record models.PaipuRecord
	if err := s.DB.Where("id = ?", matchID).First(&record).Error; err == nil {
		c.Data(http.StatusOK, "application/json", []byte(record.Data))
		return
	} else if err != nil && err != gorm.ErrRecordNotFound {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to load paipu"})
		return
	}

	// Fall back to legacy Match.PaipuJSON, but only for canonical match UUIDs.
	if _, err := uuid.Parse(matchID); err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Match not found"})
		return
	}

	var match models.Match
	if err := s.DB.Where("id = ?", matchID).First(&match).Error; err != nil {
		if err == gorm.ErrRecordNotFound {
			c.JSON(http.StatusNotFound, gin.H{"error": "Match not found"})
			return
		}
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to load paipu"})
		return
	}

	if match.PaipuJSON == "" {
		c.JSON(http.StatusNotFound, gin.H{"error": "Paipu not available for this match"})
		return
	}

	c.Data(http.StatusOK, "application/json", []byte(match.PaipuJSON))
}

func (s *Server) handleUploadPaipu(c *gin.Context) {
	secret := os.Getenv("ADMIN_SECRET")
	if secret == "" || c.GetHeader("X-Admin-Secret") != secret {
		c.JSON(http.StatusForbidden, gin.H{"error": "Forbidden"})
		return
	}

	matchID := c.Param("matchId")
	if matchID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "matchId is required"})
		return
	}

	body, err := io.ReadAll(c.Request.Body)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Failed to read body"})
		return
	}

	if !json.Valid(body) {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid JSON"})
		return
	}

	s.StorePaipu(matchID, string(body))
	c.JSON(http.StatusOK, gin.H{"status": "ok", "matchId": matchID})
}

func loadPaipuFixture(matchID string) ([]byte, bool) {
	filename := matchID + ".json"
	candidates := []string{
		filepath.Join("testdata", "paipu", filename),
	}

	if exePath, err := os.Executable(); err == nil {
		exeDir := filepath.Dir(exePath)
		candidates = append(candidates,
			filepath.Join(exeDir, "testdata", "paipu", filename),
			filepath.Join(exeDir, "..", "testdata", "paipu", filename),
		)
	}

	for _, candidate := range candidates {
		data, err := os.ReadFile(candidate)
		if err == nil {
			return data, true
		}
	}

	return nil, false
}
