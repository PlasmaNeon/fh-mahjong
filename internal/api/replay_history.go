package api

import (
	"encoding/base64"
	"encoding/json"
	"fmt"
	"net/http"
	"sort"
	"strconv"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/plasma/fh-mahjong/internal/engine"
	"github.com/plasma/fh-mahjong/internal/storage"
)

const (
	defaultReplayHistoryLimit = 20
	maxReplayHistoryLimit     = 50
)

type replayHistoryPlayer struct {
	Seat       uint32 `json:"seat"`
	Name       string `json:"name"`
	FinalScore int32  `json:"finalScore"`
}

type replayHistoryItem struct {
	MatchID    string                `json:"matchId"`
	EndedAt    time.Time             `json:"endedAt"`
	Ruleset    string                `json:"ruleset"`
	Seat       uint                  `json:"seat"`
	Placement  uint                  `json:"placement"`
	FinalScore int32                 `json:"finalScore"`
	RoundCount int                   `json:"roundCount"`
	Players    []replayHistoryPlayer `json:"players"`
}

type replayHistoryResponse struct {
	Replays    []replayHistoryItem `json:"replays"`
	NextCursor *string             `json:"nextCursor"`
}

type replayHistoryCursor struct {
	EndedAt string `json:"endedAt"`
	MatchID string `json:"matchId"`
}

type replayHistoryResult struct {
	item   replayHistoryItem
	cursor replayHistoryCursor
}

func encodeReplayHistoryCursor(cursor replayHistoryCursor) string {
	raw, _ := json.Marshal(cursor)
	return base64.RawURLEncoding.EncodeToString(raw)
}

func decodeReplayHistoryCursor(raw string) (*replayHistoryCursor, error) {
	if raw == "" {
		return nil, nil
	}
	decoded, err := base64.RawURLEncoding.DecodeString(raw)
	if err != nil {
		return nil, fmt.Errorf("decode cursor: %w", err)
	}
	var cursor replayHistoryCursor
	if err := json.Unmarshal(decoded, &cursor); err != nil {
		return nil, fmt.Errorf("parse cursor: %w", err)
	}
	if cursor.MatchID == "" {
		return nil, fmt.Errorf("cursor match id is empty")
	}
	if _, err := time.Parse(time.RFC3339Nano, cursor.EndedAt); err != nil {
		return nil, fmt.Errorf("cursor time is invalid: %w", err)
	}
	return &cursor, nil
}

func parseReplayHistoryLimit(raw string) (int, error) {
	if raw == "" {
		return defaultReplayHistoryLimit, nil
	}
	limit, err := strconv.Atoi(raw)
	if err != nil || limit <= 0 {
		return 0, fmt.Errorf("limit must be a positive number")
	}
	if limit > maxReplayHistoryLimit {
		limit = maxReplayHistoryLimit
	}
	return limit, nil
}

func (s *Server) handleReplayHistory(c *gin.Context) {
	limit, err := parseReplayHistoryLimit(c.Query("limit"))
	if err != nil {
		respondError(c, http.StatusBadRequest, "Invalid replay history limit")
		return
	}
	cursor, err := decodeReplayHistoryCursor(c.Query("cursor"))
	if err != nil {
		respondError(c, http.StatusBadRequest, "Invalid replay history cursor")
		return
	}
	userID, ok := c.Get("userID")
	if !ok {
		respondError(c, http.StatusUnauthorized, "Authentication required")
		return
	}

	results, err := s.loadReplayHistory(userID.(uint), limit+1, cursor)
	if err != nil {
		respondError(c, http.StatusInternalServerError, "Failed to load replay history")
		return
	}

	response := replayHistoryResponse{Replays: make([]replayHistoryItem, 0, min(limit, len(results)))}
	for index, result := range results {
		if index == limit {
			break
		}
		response.Replays = append(response.Replays, result.item)
	}
	if len(results) > limit {
		next := encodeReplayHistoryCursor(results[limit-1].cursor)
		response.NextCursor = &next
	}
	c.JSON(http.StatusOK, response)
}

func (s *Server) loadReplayHistory(userID uint, target int, initialCursor *replayHistoryCursor) ([]replayHistoryResult, error) {
	results := make([]replayHistoryResult, 0, target)
	cursor := initialCursor
	const batchSize = 100

	for len(results) < target {
		query := s.DB.Model(&storage.Match{}).
			Select("matches.*").
			Joins("JOIN match_players AS ownership ON ownership.match_id = matches.id AND ownership.user_id = ?", userID).
			Where("matches.status = ? AND matches.end_time IS NOT NULL AND matches.paipu_json <> ''", "completed").
			Preload("Players").
			Order("matches.end_time DESC").Order("matches.id DESC").
			Limit(batchSize)
		if cursor != nil {
			endedAt, _ := time.Parse(time.RFC3339Nano, cursor.EndedAt)
			query = query.Where("matches.end_time < ? OR (matches.end_time = ? AND matches.id < ?)", endedAt, endedAt, cursor.MatchID)
		}

		var matches []storage.Match
		if err := query.Find(&matches).Error; err != nil {
			return nil, err
		}
		if len(matches) == 0 {
			break
		}

		for _, match := range matches {
			if match.EndTime == nil {
				continue
			}
			position := replayHistoryCursor{EndedAt: match.EndTime.UTC().Format(time.RFC3339Nano), MatchID: match.ID}
			cursor = &position
			result, ok := replayHistoryResultForMatch(match, userID, position)
			if !ok {
				continue
			}
			results = append(results, result)
			if len(results) == target {
				break
			}
		}
		if len(matches) < batchSize {
			break
		}
	}

	return results, nil
}

func replayHistoryResultForMatch(match storage.Match, userID uint, cursor replayHistoryCursor) (replayHistoryResult, bool) {
	var paipu engine.Paipu
	if err := json.Unmarshal([]byte(match.PaipuJSON), &paipu); err != nil || len(paipu.Players) == 0 || match.EndTime == nil {
		return replayHistoryResult{}, false
	}

	rowsBySeat := make(map[uint]storage.MatchPlayer, len(match.Players))
	var owner storage.MatchPlayer
	ownerFound := false
	for _, row := range match.Players {
		rowsBySeat[row.Seat] = row
		if row.UserID == userID {
			owner = row
			ownerFound = true
		}
	}
	if !ownerFound {
		return replayHistoryResult{}, false
	}

	players := make([]replayHistoryPlayer, 0, len(paipu.Players))
	for _, player := range paipu.Players {
		if player.Seat >= 4 {
			continue
		}
		score := paipu.FinalScores[player.Seat]
		if row, ok := rowsBySeat[uint(player.Seat)]; ok {
			score = row.FinalScore
		}
		players = append(players, replayHistoryPlayer{Seat: player.Seat, Name: player.Name, FinalScore: score})
	}
	sort.Slice(players, func(i, j int) bool { return players[i].Seat < players[j].Seat })

	return replayHistoryResult{
		item: replayHistoryItem{
			MatchID: match.ID, EndedAt: match.EndTime.UTC(), Ruleset: match.Ruleset,
			Seat: owner.Seat, Placement: owner.Placement, FinalScore: owner.FinalScore,
			RoundCount: len(paipu.Rounds), Players: players,
		},
		cursor: cursor,
	}, true
}
