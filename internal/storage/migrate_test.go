package storage

import (
	"strings"
	"testing"
	"time"

	"github.com/glebarez/sqlite"
	"gorm.io/gorm"
)

func newMemDB(t *testing.T) *gorm.DB {
	t.Helper()
	db, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	return db
}

const legacyUsersDDL = `CREATE TABLE users (
	id integer PRIMARY KEY,
	username text NOT NULL,
	password_hash text NOT NULL,
	rating integer,
	created_at datetime,
	updated_at datetime
)`

// A fresh database migrates cleanly and allows two accounts to share a display
// name (the new schema must NOT enforce username uniqueness).
func TestAutoMigrateFreshAllowsDuplicateUsernames(t *testing.T) {
	db := newMemDB(t)
	if err := AutoMigrate(db); err != nil {
		t.Fatalf("AutoMigrate fresh: %v", err)
	}
	if err := db.Create(&User{Email: "a@x.com", Username: "Sam", PasswordHash: "h"}).Error; err != nil {
		t.Fatalf("create first user: %v", err)
	}
	if err := db.Create(&User{Email: "b@x.com", Username: "Sam", PasswordHash: "h"}).Error; err != nil {
		t.Fatalf("expected duplicate display name to be allowed, got: %v", err)
	}
}

// A legacy users table (no email column) that still holds rows must FAIL CLOSED
// rather than silently destroying or half-migrating accounts.
func TestAutoMigrateRefusesPopulatedLegacyTable(t *testing.T) {
	db := newMemDB(t)
	if err := db.Exec(legacyUsersDDL).Error; err != nil {
		t.Fatalf("create legacy table: %v", err)
	}
	if err := db.Exec(`INSERT INTO users (id, username, password_hash) VALUES (1, 'old', 'h')`).Error; err != nil {
		t.Fatalf("seed legacy row: %v", err)
	}

	err := AutoMigrate(db)
	if err == nil {
		t.Fatal("expected AutoMigrate to fail closed on a populated legacy table")
	}
	if !strings.Contains(err.Error(), "refusing to migrate") {
		t.Fatalf("expected fail-closed diagnostic, got: %v", err)
	}
}

// An empty legacy users table (no email column, with the old prod-named unique
// username index) is migrated in place: the email column is added and the stale
// unique index is dropped so display names become non-unique.
func TestAutoMigrateEmptyLegacyTableMigratesInPlace(t *testing.T) {
	db := newMemDB(t)
	if err := db.Exec(legacyUsersDDL).Error; err != nil {
		t.Fatalf("create legacy table: %v", err)
	}
	if err := db.Exec(`CREATE UNIQUE INDEX idx_users_username ON users(username)`).Error; err != nil {
		t.Fatalf("create legacy unique index: %v", err)
	}

	if err := AutoMigrate(db); err != nil {
		t.Fatalf("AutoMigrate empty legacy: %v", err)
	}

	if !db.Migrator().HasColumn(&User{}, "email") {
		t.Fatal("expected email column to be added by migration")
	}
	if db.Migrator().HasIndex(&User{}, "idx_users_username") {
		t.Fatal("expected stale unique username index to be dropped")
	}
	// Stale index gone -> duplicate display names allowed.
	if err := db.Create(&User{Email: "a@x.com", Username: "Sam", PasswordHash: "h"}).Error; err != nil {
		t.Fatalf("create first user: %v", err)
	}
	if err := db.Create(&User{Email: "b@x.com", Username: "Sam", PasswordHash: "h"}).Error; err != nil {
		t.Fatalf("expected duplicate display name after migration, got: %v", err)
	}
}

// legacyMatchPlayersDDL mirrors the schema GORM created before seat labels:
// a users foreign key on match_players (from the then-declared relations).
// Bots (user_id 0) and guest users (9000000-range, no users row by design)
// cannot satisfy it, so AutoMigrate must drop it.
const legacyMatchPlayersDDL = `CREATE TABLE match_players (
	id integer PRIMARY KEY AUTOINCREMENT,
	match_id uuid,
	user_id integer NOT NULL,
	seat integer NOT NULL,
	final_score integer NOT NULL DEFAULT 0,
	placement integer NOT NULL DEFAULT 0,
	rating_delta integer NOT NULL DEFAULT 0,
	CONSTRAINT fk_users_matches FOREIGN KEY (user_id) REFERENCES users(id)
)`

// After AutoMigrate, rows for bots (user_id 0) and guests (no users row) must
// insert cleanly even with foreign-key enforcement on.
func TestAutoMigrateDropsMatchPlayerUserFK(t *testing.T) {
	db := newMemDB(t)
	if err := db.Exec(`PRAGMA foreign_keys = ON`).Error; err != nil {
		t.Fatalf("enable fk enforcement: %v", err)
	}
	// Seed the legacy schema: users table + match_players with the users FK.
	if err := AutoMigrate(db); err != nil {
		t.Fatalf("bootstrap users: %v", err)
	}
	if err := db.Migrator().DropTable("match_players"); err != nil {
		t.Fatalf("drop fresh match_players: %v", err)
	}
	if err := db.Exec(legacyMatchPlayersDDL).Error; err != nil {
		t.Fatalf("create legacy match_players: %v", err)
	}
	if !db.Migrator().HasConstraint(&MatchPlayer{}, "fk_users_matches") {
		t.Fatal("test premise broken: legacy FK not present")
	}

	if err := AutoMigrate(db); err != nil {
		t.Fatalf("AutoMigrate over legacy match_players: %v", err)
	}
	if db.Migrator().HasConstraint(&MatchPlayer{}, "fk_users_matches") {
		t.Fatal("expected AutoMigrate to drop the match_players users FK")
	}

	if err := db.Create(&Match{ID: "00000000-0000-0000-0000-000000000001", Status: "completed", StartTime: time.Now()}).Error; err != nil {
		t.Fatalf("insert match: %v", err)
	}
	rows := []MatchPlayer{
		{MatchID: "00000000-0000-0000-0000-000000000001", UserID: 0, Seat: 1, IsBot: true, Difficulty: "rl", PolicyID: "champ.pt@step9"},
		{MatchID: "00000000-0000-0000-0000-000000000001", UserID: 9000123, Seat: 0},
	}
	if err := db.Create(&rows).Error; err != nil {
		t.Fatalf("bot/guest MatchPlayer rows must insert without a users row: %v", err)
	}
}
