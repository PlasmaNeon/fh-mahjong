package api

import (
	"net/http"

	"github.com/gin-gonic/gin"
	"github.com/plasma/fh-mahjong/models"
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
	}

	// Fall back to legacy Match.PaipuJSON
	var match models.Match
	if err := s.DB.Where("id = ?", matchID).First(&match).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Match not found"})
		return
	}

	if match.PaipuJSON == "" {
		c.JSON(http.StatusNotFound, gin.H{"error": "Paipu not available for this match"})
		return
	}

	c.Data(http.StatusOK, "application/json", []byte(match.PaipuJSON))
}
