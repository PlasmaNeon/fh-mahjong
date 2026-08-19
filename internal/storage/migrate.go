package storage

import (
	"fmt"
	"log"
	"strings"
	"unicode/utf8"

	"gorm.io/gorm"
)

// AutoMigrate brings the schema up to date and safely transitions legacy user
// identities to case-insensitively unique username keys.
//
// The legacy schema is detected as a `users` table that has no `email` column.
// If such a table still holds rows we FAIL CLOSED with a diagnostic, because the
// email-based model has no backfill path and migrating must never silently
// destroy or half-migrate accounts. An empty legacy table is migrated in place.
// Finally, any stale unique index on `username` (left by the old schema) is
// dropped so display names are non-unique as designed. This runs at startup, so
// a failure surfaces immediately instead of depending on an out-of-band manual
// step executed at the right moment.
func AutoMigrate(db *gorm.DB) error {
	m := db.Migrator()

	if m.HasTable(&User{}) && !m.HasColumn(&User{}, "email") {
		var count int64
		if err := db.Table("users").Count(&count).Error; err != nil {
			return fmt.Errorf("inspecting legacy users table: %w", err)
		}
		if count > 0 {
			return fmt.Errorf("refusing to migrate: legacy %q table has %d row(s) and no email column; "+
				"the email-based schema has no backfill path — migrate or remove that data, then restart", "users", count)
		}
		// Empty legacy table: AutoMigrate below adds the email column in place.
	}

	// The prior schema used username as either a unique legacy identity or a
	// non-unique display name. Remove that old index before adding/backfilling
	// the dedicated normalized key.
	if m.HasIndex(&User{}, "idx_users_username") {
		if err := m.DropIndex(&User{}, "idx_users_username"); err != nil {
			return fmt.Errorf("dropping stale unique username index: %w", err)
		}
	}

	if err := db.AutoMigrate(
		&User{},
		&UserSession{},
		&Match{},
		&MatchPlayer{},
		&PaipuRecord{},
		&MatchReview{},
	); err != nil {
		return err
	}

	if err := db.Transaction(func(tx *gorm.DB) error {
		if err := backfillUniqueUsernames(tx); err != nil {
			return err
		}
		if !tx.Migrator().HasIndex(&User{}, "idx_users_username_key") {
			if err := tx.Exec("CREATE UNIQUE INDEX idx_users_username_key ON users(username_key)").Error; err != nil {
				return fmt.Errorf("creating unique username key index: %w", err)
			}
		}
		return nil
	}); err != nil {
		return err
	}

	// Drop the users foreign key(s) the old User↔MatchPlayer relations put on
	// match_players. Bots persist with user_id 0 and guest accounts have no
	// users row, so the constraint would reject bot and historical guest rows.
	// Both historical GORM constraint names are handled; idempotent.
	for _, constraint := range []string{"fk_users_matches", "fk_match_players_user"} {
		if m.HasConstraint(&MatchPlayer{}, constraint) {
			if err := m.DropConstraint(&MatchPlayer{}, constraint); err != nil {
				return fmt.Errorf("dropping match_players users FK %q: %w", constraint, err)
			}
		}
	}

	// Backfill the legacy ruleset key: "hometown" was renamed to "fenghua" in
	// 2026-06. Idempotent — only touches rows that still hold the old value.
	if err := db.Model(&Match{}).Where("ruleset = ?", "hometown").Update("ruleset", "fenghua").Error; err != nil {
		return fmt.Errorf("backfilling legacy ruleset key: %w", err)
	}
	stats, err := backfillLegacyMatchPlayers(db)
	if err != nil {
		return err
	}
	if stats.RecoveredMatches > 0 || stats.SkippedMatches > 0 {
		log.Printf("match history backfill: recovered=%d skipped=%d", stats.RecoveredMatches, stats.SkippedMatches)
	}
	return nil
}

func backfillUniqueUsernames(db *gorm.DB) error {
	var users []User
	if err := db.Order("created_at ASC").Order("id ASC").Find(&users).Error; err != nil {
		return fmt.Errorf("loading users for username migration: %w", err)
	}
	used := make(map[string]struct{}, len(users))
	for _, user := range users {
		display, key := NormalizeUsername(user.Username)
		if utf8.RuneCountInString(display) < 2 {
			display = fmt.Sprintf("Player-%d", user.ID)
			key = strings.ToLower(display)
		}
		display = truncateRunes(display, 30)
		key = strings.ToLower(display)
		baseDisplay := display
		for suffix := 2; ; suffix++ {
			if _, exists := used[key]; !exists {
				break
			}
			tail := fmt.Sprintf("-%d", suffix)
			display = truncateRunes(baseDisplay, 30-utf8.RuneCountInString(tail)) + tail
			key = strings.ToLower(display)
		}
		used[key] = struct{}{}
		if err := db.Model(&User{}).Where("id = ?", user.ID).Updates(map[string]any{
			"username":     display,
			"username_key": key,
		}).Error; err != nil {
			return fmt.Errorf("backfilling username for user %d: %w", user.ID, err)
		}
	}
	return nil
}
