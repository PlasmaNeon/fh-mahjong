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

	var match models.Match
	if s.DB == nil {
		c.JSON(http.StatusServiceUnavailable, gin.H{"error": "Database not available"})
		return
	}
	if err := s.DB.Where("id = ?", matchID).First(&match).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Match not found"})
		return
	}

	if match.PaipuJSON == "" {
		c.JSON(http.StatusNotFound, gin.H{"error": "Paipu not available for this match"})
		return
	}

	// Return raw JSON string directly
	c.Data(http.StatusOK, "application/json", []byte(match.PaipuJSON))
}
