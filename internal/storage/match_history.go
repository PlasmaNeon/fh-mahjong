package storage

import (
	"encoding/json"
	"fmt"

	"gorm.io/gorm"
)

// LegacyMatchBackfillStats summarizes the startup recovery without making
// malformed historical records fatal to an otherwise healthy deployment.
type LegacyMatchBackfillStats struct {
	RecoveredMatches int
	SkippedMatches   int
}

type legacyPaipuPlayer struct {
	Seat               uint32 `json:"seat"`
	UserID             uint   `json:"userId"`
	Kind               string `json:"kind"`
	Difficulty         string `json:"difficulty"`
	PolicyID           string `json:"policyId"`
	RemoteDecisions    uint64 `json:"remoteDecisions"`
	FallbackDecisions  uint64 `json:"fallbackDecisions"`
	AutomatedDecisions uint64 `json:"automatedDecisions"`
}

type legacyPaipuIndex struct {
	Players     []legacyPaipuPlayer `json:"players"`
	FinalScores [4]int32            `json:"finalScores"`
}

// backfillLegacyMatchPlayers recovers the relational ownership index for
// completed paipu written before MatchPlayer persistence existed. Matches
// that already have any seat row are deliberately left untouched.
func backfillLegacyMatchPlayers(db *gorm.DB) (LegacyMatchBackfillStats, error) {
	var stats LegacyMatchBackfillStats
	var matches []Match
	err := db.Model(&Match{}).
		Where("status = ? AND paipu_json <> ''", "completed").
		Where("NOT EXISTS (SELECT 1 FROM match_players WHERE match_players.match_id = matches.id)").
		Order("end_time ASC").Order("id ASC").
		Find(&matches).Error
	if err != nil {
		return stats, fmt.Errorf("loading legacy matches for player backfill: %w", err)
	}

	for _, match := range matches {
		var paipu legacyPaipuIndex
		if err := json.Unmarshal([]byte(match.PaipuJSON), &paipu); err != nil || len(paipu.Players) == 0 {
			stats.SkippedMatches++
			continue
		}

		placements := PlacementsFromScores(paipu.FinalScores)
		seenSeats := make(map[uint32]struct{}, 4)
		rows := make([]MatchPlayer, 0, len(paipu.Players))
		for _, player := range paipu.Players {
			if player.Seat >= 4 {
				continue
			}
			if _, duplicate := seenSeats[player.Seat]; duplicate {
				continue
			}
			seenSeats[player.Seat] = struct{}{}

			score := paipu.FinalScores[player.Seat]
			placement := placements[player.Seat]
			policyID := player.PolicyID
			if len(policyID) > 512 {
				policyID = policyID[:512]
			}
			rows = append(rows, MatchPlayer{
				MatchID: match.ID, UserID: player.UserID, Seat: uint(player.Seat),
				FinalScore: score, Placement: placement, IsBot: player.Kind == "bot",
				Difficulty: player.Difficulty, PolicyID: policyID,
				RemoteDecisions: player.RemoteDecisions, FallbackDecisions: player.FallbackDecisions,
				AutomatedDecisions: player.AutomatedDecisions,
			})
		}
		if len(rows) == 0 {
			stats.SkippedMatches++
			continue
		}

		inserted := false
		err := db.Transaction(func(tx *gorm.DB) error {
			var count int64
			if err := tx.Model(&MatchPlayer{}).Where("match_id = ?", match.ID).Count(&count).Error; err != nil {
				return err
			}
			if count > 0 {
				return nil
			}
			if err := tx.Create(&rows).Error; err != nil {
				return err
			}
			inserted = true
			return nil
		})
		if err != nil {
			return stats, fmt.Errorf("backfilling match players for %s: %w", match.ID, err)
		}
		if inserted {
			stats.RecoveredMatches++
		}
	}

	return stats, nil
}

// PlacementsFromScores computes each seat's competition ranking from the four
// final scores, preserving seat index: 1st place is shared by ties, and the
// next distinct score takes the place after the tied group (scores 30/30/20/10
// rank 1/1/3/4).
//
// Shared by the live persist path (internal/api) and the backfill above so the
// ranking rule cannot drift between what a match records at the time and what a
// re-import computes later.
func PlacementsFromScores(finalScores [4]int32) [4]uint {
	var placements [4]uint
	for seat, score := range finalScores {
		placement := uint(1)
		for _, other := range finalScores {
			if other > score {
				placement++
			}
		}
		placements[seat] = placement
	}
	return placements
}
