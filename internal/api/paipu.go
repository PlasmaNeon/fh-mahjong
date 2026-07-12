package api

import (
	"encoding/json"
	"io"
	"net/http"
	"os"
	"path/filepath"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"github.com/plasma/fh-mahjong/internal/storage"
	"gorm.io/gorm"
)

func (s *Server) handleGetPaipu(c *gin.Context) {
	matchID := c.Param("matchId")
	if matchID == "" {
		respondError(c, http.StatusBadRequest, "matchId is required")
		return
	}

	data, ok, errMsg := s.loadPaipuJSONWithErr(matchID)
	if errMsg != "" {
		respondError(c, http.StatusInternalServerError, errMsg)
		return
	}
	if !ok {
		respondError(c, http.StatusNotFound, "Match not found")
		return
	}
	c.Data(http.StatusOK, "application/json", []byte(data))
}

// loadPaipuJSON is the paipu source chain shared by handleGetPaipu and the
// review API: in-memory store → paipu_records → legacy Match.PaipuJSON →
// checked-in local-dev fixtures. Internal DB errors are swallowed and treated
// as "not found" — callers that need to distinguish a DB failure from a
// genuine miss should use loadPaipuJSONWithErr instead.
func (s *Server) loadPaipuJSON(matchID string) (string, bool) {
	data, ok, _ := s.loadPaipuJSONWithErr(matchID)
	return data, ok
}

// loadPaipuJSONWithErr is the same source chain as loadPaipuJSON but
// surfaces a non-empty errMsg when a DB lookup itself failed (as opposed to
// simply finding no record), so handleGetPaipu can keep returning 500 for
// that case exactly as it did before this helper was extracted.
func (s *Server) loadPaipuJSONWithErr(matchID string) (data string, ok bool, errMsg string) {
	// Try in-memory store first (works with or without DB)
	if data, ok := s.GetPaipu(matchID); ok {
		return data, true, ""
	}

	// Fall back to database
	if s.DB == nil {
		// No DB: fall back to local dev fixtures
		if raw, ok := loadPaipuFixture(matchID); ok {
			return string(raw), true, ""
		}
		return "", false, ""
	}

	// Check paipu_records table (per-round paipus)
	var record storage.PaipuRecord
	if err := s.DB.Where("id = ?", matchID).First(&record).Error; err == nil {
		return record.Data, true, ""
	} else if err != gorm.ErrRecordNotFound {
		return "", false, "Failed to load paipu"
	}

	// Fall back to legacy Match.PaipuJSON, but only for canonical match UUIDs.
	if _, err := uuid.Parse(matchID); err == nil {
		var match storage.Match
		if err := s.DB.Where("id = ?", matchID).First(&match).Error; err == nil {
			if match.PaipuJSON != "" {
				return match.PaipuJSON, true, ""
			}
		} else if err != gorm.ErrRecordNotFound {
			return "", false, "Failed to load paipu"
		}
	}

	// Local dev fallback: serve checked-in fixtures when no DB record exists.
	if raw, ok := loadPaipuFixture(matchID); ok {
		return string(raw), true, ""
	}

	return "", false, ""
}

func (s *Server) handleUploadPaipu(c *gin.Context) {
	secret := os.Getenv("ADMIN_SECRET")
	if secret == "" || c.GetHeader("X-Admin-Secret") != secret {
		respondError(c, http.StatusForbidden, "Forbidden")
		return
	}

	matchID := c.Param("matchId")
	if matchID == "" {
		respondError(c, http.StatusBadRequest, "matchId is required")
		return
	}

	body, err := io.ReadAll(c.Request.Body)
	if err != nil {
		respondError(c, http.StatusBadRequest, "Failed to read body")
		return
	}

	if !json.Valid(body) {
		respondError(c, http.StatusBadRequest, "Invalid JSON")
		return
	}

	s.StorePaipu(matchID, string(body))
	c.JSON(http.StatusOK, gin.H{"status": "ok", "matchId": matchID})
}

func loadPaipuFixture(matchID string) ([]byte, bool) {
	matchID = filepath.Base(matchID) // sanitize: strip any path separators
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
