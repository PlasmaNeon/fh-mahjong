package api

import (
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"path/filepath"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"github.com/plasma/fh-mahjong/internal/review"
	"github.com/plasma/fh-mahjong/internal/storage"
	"gorm.io/gorm"
	"gorm.io/gorm/clause"
)

func (s *Server) handleReplayImport(c *gin.Context) {
	user := c.GetUint("userID")
	c.Request.Body = http.MaxBytesReader(c.Writer, c.Request.Body, review.MaxImportBytes)
	data, err := io.ReadAll(c.Request.Body)
	if err != nil {
		respondError(c, 413, "paipu must be at most 10 MiB")
		return
	}
	p, err := review.ValidateImport(data)
	if err != nil {
		respondError(c, 422, err.Error())
		return
	}
	hash := sha256.Sum256(data)
	contentHash := hex.EncodeToString(hash[:])
	// Serialize this instance's quota check and insert; the unique index also
	// resolves duplicate uploads across instances without duplicating data.
	s.studyMu.Lock()
	defer s.studyMu.Unlock()
	var existing storage.ReplayImport
	if err := s.DB.WithContext(c.Request.Context()).Where("owner_id = ? AND content_hash = ?", user, contentHash).First(&existing).Error; err == nil {
		c.JSON(200, existing)
		return
	} else if !errors.Is(err, gorm.ErrRecordNotFound) {
		respondError(c, 500, "cannot check import")
		return
	}
	var count int64
	if err := s.DB.WithContext(c.Request.Context()).Model(&storage.ReplayImport{}).Where("owner_id = ?", user).Count(&count).Error; err != nil {
		respondError(c, 500, "cannot check imports")
		return
	}
	if count >= 100 {
		respondError(c, 429, "import limit reached (100 files)")
		return
	}
	filenameRaw, _ := url.PathUnescape(c.GetHeader("X-Paipu-Filename"))
	filename := filepath.Base(filenameRaw)
	if filename == "." || filename == "" {
		filename = "paipu.json"
	}
	filename = strings.Map(func(r rune) rune {
		if r < 32 {
			return -1
		}
		return r
	}, filename)
	if len(filename) > 255 {
		filename = "paipu.json"
	}
	row := storage.ReplayImport{ID: uuid.NewString(), OwnerID: user, ContentHash: contentHash, SourceMatchID: p.MatchID, Filename: filename, CreatedAt: time.Now().UTC()}
	p.MatchID = "import-" + row.ID
	canonical, err := json.Marshal(p)
	if err != nil {
		respondError(c, 422, "cannot encode paipu")
		return
	}
	row.PaipuJSON = string(canonical)
	result := s.DB.WithContext(c.Request.Context()).Clauses(clause.OnConflict{DoNothing: true}).Create(&row)
	if result.Error != nil {
		respondError(c, 500, "cannot save import")
		return
	}
	if result.RowsAffected == 0 {
		if err := s.DB.WithContext(c.Request.Context()).Where("owner_id = ? AND content_hash = ?", user, contentHash).First(&row).Error; err != nil {
			respondError(c, 500, "cannot open import")
			return
		}
		c.JSON(200, row)
		return
	}
	c.JSON(201, row)
}

func (s *Server) handleReadReplayImport(c *gin.Context) {
	var row storage.ReplayImport
	if err := s.DB.WithContext(c.Request.Context()).Where("id = ? AND owner_id = ?", c.Param("importId"), c.GetUint("userID")).First(&row).Error; err != nil {
		respondError(c, 404, "import not found")
		return
	}
	c.Data(200, "application/json", []byte(row.PaipuJSON))
}

func (s *Server) handleListReplayImports(c *gin.Context) {
	db := s.DB.WithContext(c.Request.Context()).Where("owner_id = ?", c.GetUint("userID"))
	if cursor := c.Query("cursor"); cursor != "" {
		raw, err := base64.RawURLEncoding.DecodeString(cursor)
		parts := strings.SplitN(string(raw), "|", 2)
		if err != nil || len(parts) != 2 {
			respondError(c, 400, "invalid import cursor")
			return
		}
		at, err := time.Parse(time.RFC3339Nano, parts[0])
		if err != nil {
			respondError(c, 400, "invalid import cursor")
			return
		}
		db = db.Where("created_at < ? OR (created_at = ? AND id < ?)", at, at, parts[1])
	}
	var rows []storage.ReplayImport
	if err := db.Select("id", "source_match_id", "filename", "created_at").Order("created_at DESC, id DESC").Limit(21).Find(&rows).Error; err != nil {
		respondError(c, 500, "cannot load imports")
		return
	}
	next := ""
	if len(rows) > 20 {
		rows = rows[:20]
		last := rows[len(rows)-1]
		next = base64.RawURLEncoding.EncodeToString([]byte(fmt.Sprintf("%s|%s", last.CreatedAt.UTC().Format(time.RFC3339Nano), last.ID)))
	}
	if rows == nil {
		rows = []storage.ReplayImport{}
	}
	c.JSON(200, gin.H{"imports": rows, "nextCursor": next})
}
