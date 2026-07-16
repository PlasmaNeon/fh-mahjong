package storage

import (
	"fmt"
	"testing"
	"time"
)

func legacyPaipuJSON(matchID string, players string, scores string) string {
	return fmt.Sprintf(`{"version":1,"matchId":%q,"ruleset":"fenghua","players":%s,"rounds":[{"round":1}],"finalScores":%s}`,
		matchID, players, scores)
}

func TestBackfillLegacyMatchPlayersRecoversCompletedPaipu(t *testing.T) {
	db := newMemDB(t)
	if err := AutoMigrate(db); err != nil {
		t.Fatalf("AutoMigrate: %v", err)
	}
	matchID := "00000000-0000-0000-0000-000000000101"
	ended := time.Date(2026, 7, 14, 22, 30, 0, 0, time.UTC)
	match := Match{
		ID: matchID, Status: "completed", StartTime: ended.Add(-time.Hour), EndTime: &ended,
		PaipuJSON: legacyPaipuJSON(matchID,
			`[{"seat":0,"name":"East","userId":12001,"kind":"human"},{"seat":1,"name":"South","userId":0,"kind":"bot","difficulty":"heuristic"},{"seat":2,"name":"West","userId":12002,"kind":"human"},{"seat":3,"name":"North","userId":0,"kind":"bot","difficulty":"rl","policyId":"rain.pt"}]`,
			`[40,40,-10,-70]`),
	}
	if err := db.Create(&match).Error; err != nil {
		t.Fatalf("seed legacy match: %v", err)
	}

	stats, err := backfillLegacyMatchPlayers(db)
	if err != nil {
		t.Fatalf("backfill: %v", err)
	}
	if stats.RecoveredMatches != 1 || stats.SkippedMatches != 0 {
		t.Fatalf("stats = %#v", stats)
	}

	var rows []MatchPlayer
	if err := db.Order("seat ASC").Find(&rows).Error; err != nil {
		t.Fatalf("load rows: %v", err)
	}
	if len(rows) != 4 {
		t.Fatalf("rows = %d, want 4", len(rows))
	}
	wantPlacement := []uint{1, 1, 3, 4}
	for seat, row := range rows {
		if row.Seat != uint(seat) || row.Placement != wantPlacement[seat] {
			t.Fatalf("seat %d row = %#v", seat, row)
		}
	}
	if !rows[1].IsBot || rows[1].Difficulty != "heuristic" || rows[3].PolicyID != "rain.pt" {
		t.Fatalf("seat labels not recovered: %#v", rows)
	}
}

func TestBackfillLegacyMatchPlayersIsIdempotentAndSkipsInvalidRecords(t *testing.T) {
	db := newMemDB(t)
	if err := AutoMigrate(db); err != nil {
		t.Fatalf("AutoMigrate: %v", err)
	}
	ended := time.Now().UTC()
	validID := "00000000-0000-0000-0000-000000000102"
	invalidSeatID := "00000000-0000-0000-0000-000000000103"
	existingID := "00000000-0000-0000-0000-000000000104"
	matches := []Match{
		{ID: validID, Status: "completed", StartTime: ended.Add(-time.Hour), EndTime: &ended, PaipuJSON: legacyPaipuJSON(validID, `[{"seat":0,"name":"Rain","userId":13001},{"seat":8,"name":"Invalid","userId":13002}]`, `[12,0,0,0]`)},
		{ID: invalidSeatID, Status: "completed", StartTime: ended.Add(-time.Hour), EndTime: &ended, PaipuJSON: `{not-json`},
		{ID: existingID, Status: "completed", StartTime: ended.Add(-time.Hour), EndTime: &ended, PaipuJSON: legacyPaipuJSON(existingID, `[{"seat":0,"name":"Keep","userId":14001}]`, `[99,0,0,0]`)},
		{ID: "00000000-0000-0000-0000-000000000105", Status: "aborted", StartTime: ended.Add(-time.Hour), EndTime: &ended, PaipuJSON: legacyPaipuJSON("00000000-0000-0000-0000-000000000105", `[{"seat":0,"name":"Abort","userId":15001}]`, `[5,0,0,0]`)},
	}
	if err := db.Create(&matches).Error; err != nil {
		t.Fatalf("seed matches: %v", err)
	}
	if err := db.Create(&MatchPlayer{MatchID: existingID, UserID: 14001, Seat: 0, FinalScore: 7, Placement: 2}).Error; err != nil {
		t.Fatalf("seed existing row: %v", err)
	}

	first, err := backfillLegacyMatchPlayers(db)
	if err != nil {
		t.Fatalf("first backfill: %v", err)
	}
	second, err := backfillLegacyMatchPlayers(db)
	if err != nil {
		t.Fatalf("second backfill: %v", err)
	}
	if first.RecoveredMatches != 1 || first.SkippedMatches != 1 {
		t.Fatalf("first stats = %#v", first)
	}
	if second.RecoveredMatches != 0 || second.SkippedMatches != 1 {
		t.Fatalf("second stats = %#v", second)
	}

	var validRows []MatchPlayer
	if err := db.Where("match_id = ?", validID).Find(&validRows).Error; err != nil {
		t.Fatalf("load recovered rows: %v", err)
	}
	if len(validRows) != 1 || validRows[0].UserID != 13001 {
		t.Fatalf("valid rows = %#v", validRows)
	}
	var existing MatchPlayer
	if err := db.Where("match_id = ?", existingID).First(&existing).Error; err != nil {
		t.Fatalf("load existing row: %v", err)
	}
	if existing.FinalScore != 7 || existing.Placement != 2 {
		t.Fatalf("existing row was replaced: %#v", existing)
	}
}
