package api

import (
	"encoding/json"
	"fmt"
	"net/http"
	"testing"
	"time"

	"github.com/plasma/fh-mahjong/internal/storage"
)

func historyPaipu(matchID string, ownerID uint, ownerName string, rounds int) string {
	roundData := make([]map[string]any, rounds)
	for i := range roundData {
		roundData[i] = map[string]any{"round": i + 1}
	}
	payload := map[string]any{
		"version": 1, "matchId": matchID, "ruleset": "fenghua",
		"players": []map[string]any{
			{"seat": 0, "name": ownerName, "userId": ownerID},
			{"seat": 1, "name": "South", "userId": 0},
			{"seat": 2, "name": "West", "userId": 0},
			{"seat": 3, "name": "North", "userId": 0},
		},
		"rounds": roundData, "finalScores": []int32{42, 5, -12, -35},
	}
	raw, _ := json.Marshal(payload)
	return string(raw)
}

func seedHistoryMatch(t *testing.T, server *Server, id, status string, ended time.Time, ownerID uint, paipu string) {
	t.Helper()
	match := storage.Match{ID: id, Status: status, StartTime: ended.Add(-time.Hour), EndTime: &ended, Ruleset: "fenghua", PaipuJSON: paipu}
	if err := server.DB.Create(&match).Error; err != nil {
		t.Fatalf("seed match %s: %v", id, err)
	}
	if ownerID != 0 {
		rows := []storage.MatchPlayer{
			{MatchID: id, UserID: ownerID, Seat: 0, FinalScore: 42, Placement: 1},
			{MatchID: id, UserID: 0, Seat: 1, FinalScore: 5, Placement: 2, IsBot: true},
			{MatchID: id, UserID: 0, Seat: 2, FinalScore: -12, Placement: 3, IsBot: true},
			{MatchID: id, UserID: 0, Seat: 3, FinalScore: -35, Placement: 4, IsBot: true},
		}
		if err := server.DB.Create(&rows).Error; err != nil {
			t.Fatalf("seed match players %s: %v", id, err)
		}
	}
}

func TestReplayHistoryRequiresAuthentication(t *testing.T) {
	server := newAuthenticatedPrivateTableServer(t)
	rec := authRequest(t, server.Router, http.MethodGet, "/api/v1/users/me/replays", "", nil, "")
	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("history without session = %d: %s", rec.Code, rec.Body.String())
	}
}

func TestReplayHistoryReturnsOnlyOwnedCompletedValidMatches(t *testing.T) {
	server := newAuthenticatedPrivateTableServer(t)
	cookie, _ := registerSession(t, server, "History Wind")
	var owner storage.User
	if err := server.DB.Where("username_key = ?", "history wind").First(&owner).Error; err != nil {
		t.Fatalf("load owner: %v", err)
	}
	ended := time.Date(2026, 7, 15, 2, 0, 0, 0, time.UTC)
	ownedID := "00000000-0000-0000-0000-000000000201"
	seedHistoryMatch(t, server, ownedID, "completed", ended, owner.ID, historyPaipu(ownedID, owner.ID, owner.Username, 3))
	seedHistoryMatch(t, server, "00000000-0000-0000-0000-000000000202", "aborted", ended.Add(time.Minute), owner.ID, historyPaipu("00000000-0000-0000-0000-000000000202", owner.ID, owner.Username, 1))
	seedHistoryMatch(t, server, "00000000-0000-0000-0000-000000000203", "in_progress", ended.Add(2*time.Minute), owner.ID, historyPaipu("00000000-0000-0000-0000-000000000203", owner.ID, owner.Username, 1))
	seedHistoryMatch(t, server, "00000000-0000-0000-0000-000000000204", "completed", ended.Add(3*time.Minute), owner.ID, `{bad-json`)
	seedHistoryMatch(t, server, "00000000-0000-0000-0000-000000000205", "completed", ended.Add(4*time.Minute), 99999, historyPaipu("00000000-0000-0000-0000-000000000205", 99999, "Other", 1))

	rec := authRequest(t, server.Router, http.MethodGet, "/api/v1/users/me/replays", "", cookie, "")
	if rec.Code != http.StatusOK {
		t.Fatalf("history = %d: %s", rec.Code, rec.Body.String())
	}
	var response replayHistoryResponse
	if err := json.Unmarshal(rec.Body.Bytes(), &response); err != nil {
		t.Fatalf("decode history: %v", err)
	}
	if len(response.Replays) != 1 || response.Replays[0].MatchID != ownedID {
		t.Fatalf("replays = %#v", response.Replays)
	}
	got := response.Replays[0]
	if got.Seat != 0 || got.Placement != 1 || got.FinalScore != 42 || got.RoundCount != 3 {
		t.Fatalf("owned summary = %#v", got)
	}
	if len(got.Players) != 4 || got.Players[0].Name != owner.Username {
		t.Fatalf("player summaries = %#v", got.Players)
	}
	if response.NextCursor != nil {
		t.Fatalf("unexpected cursor: %q", *response.NextCursor)
	}
}

func TestReplayHistoryUsesStableCursorPagination(t *testing.T) {
	server := newAuthenticatedPrivateTableServer(t)
	cookie, _ := registerSession(t, server, "Page Wind")
	var owner storage.User
	if err := server.DB.Where("username_key = ?", "page wind").First(&owner).Error; err != nil {
		t.Fatalf("load owner: %v", err)
	}
	ended := time.Date(2026, 7, 15, 3, 0, 0, 0, time.UTC)
	for i := 1; i <= 3; i++ {
		id := fmt.Sprintf("00000000-0000-0000-0000-%012d", 300+i)
		seedHistoryMatch(t, server, id, "completed", ended, owner.ID, historyPaipu(id, owner.ID, owner.Username, i))
	}

	first := authRequest(t, server.Router, http.MethodGet, "/api/v1/users/me/replays?limit=2", "", cookie, "")
	if first.Code != http.StatusOK {
		t.Fatalf("first page = %d: %s", first.Code, first.Body.String())
	}
	var page1 replayHistoryResponse
	if err := json.Unmarshal(first.Body.Bytes(), &page1); err != nil {
		t.Fatalf("decode first page: %v", err)
	}
	if len(page1.Replays) != 2 || page1.NextCursor == nil {
		t.Fatalf("first page = %#v", page1)
	}
	if page1.Replays[0].MatchID <= page1.Replays[1].MatchID {
		t.Fatalf("same-time ordering is not descending: %#v", page1.Replays)
	}

	second := authRequest(t, server.Router, http.MethodGet, "/api/v1/users/me/replays?limit=2&cursor="+*page1.NextCursor, "", cookie, "")
	if second.Code != http.StatusOK {
		t.Fatalf("second page = %d: %s", second.Code, second.Body.String())
	}
	var page2 replayHistoryResponse
	if err := json.Unmarshal(second.Body.Bytes(), &page2); err != nil {
		t.Fatalf("decode second page: %v", err)
	}
	if len(page2.Replays) != 1 || page2.NextCursor != nil {
		t.Fatalf("second page = %#v", page2)
	}
	seen := map[string]bool{}
	for _, replay := range append(page1.Replays, page2.Replays...) {
		if seen[replay.MatchID] {
			t.Fatalf("duplicate match across pages: %s", replay.MatchID)
		}
		seen[replay.MatchID] = true
	}
}

func TestReplayHistoryRejectsInvalidCursorAndClampsLimit(t *testing.T) {
	server := newAuthenticatedPrivateTableServer(t)
	cookie, _ := registerSession(t, server, "Limit Wind")
	invalid := authRequest(t, server.Router, http.MethodGet, "/api/v1/users/me/replays?cursor=not-a-cursor", "", cookie, "")
	if invalid.Code != http.StatusBadRequest {
		t.Fatalf("invalid cursor = %d: %s", invalid.Code, invalid.Body.String())
	}

	var owner storage.User
	if err := server.DB.Where("username_key = ?", "limit wind").First(&owner).Error; err != nil {
		t.Fatalf("load owner: %v", err)
	}
	ended := time.Now().UTC()
	for i := 1; i <= 51; i++ {
		id := fmt.Sprintf("10000000-0000-0000-0000-%012d", i)
		seedHistoryMatch(t, server, id, "completed", ended.Add(time.Duration(i)*time.Second), owner.ID, historyPaipu(id, owner.ID, owner.Username, 1))
	}
	clamped := authRequest(t, server.Router, http.MethodGet, "/api/v1/users/me/replays?limit=999", "", cookie, "")
	if clamped.Code != http.StatusOK {
		t.Fatalf("clamped history = %d: %s", clamped.Code, clamped.Body.String())
	}
	var response replayHistoryResponse
	if err := json.Unmarshal(clamped.Body.Bytes(), &response); err != nil {
		t.Fatalf("decode clamped history: %v", err)
	}
	if len(response.Replays) != 50 || response.NextCursor == nil {
		t.Fatalf("clamped response count=%d cursor=%v", len(response.Replays), response.NextCursor)
	}
}
