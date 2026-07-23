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

// emailPtr is a literal helper: User.Email is a nullable *string, so tests
// that want a concrete address need an addressable value.
func emailPtr(value string) *string { return &value }

const legacyUsersDDL = `CREATE TABLE users (
	id integer PRIMARY KEY,
	username text NOT NULL,
	password_hash text NOT NULL,
	rating integer,
	created_at datetime,
	updated_at datetime
)`

// A fresh database migrates cleanly and enforces case-insensitive username
// uniqueness through the normalized username key.
func TestAutoMigrateFreshEnforcesUniqueUsernames(t *testing.T) {
	db := newMemDB(t)
	if err := AutoMigrate(db); err != nil {
		t.Fatalf("AutoMigrate fresh: %v", err)
	}
	if err := db.Create(&User{Email: emailPtr("a@x.com"), Username: "Sam", UsernameKey: "sam", PasswordHash: "h"}).Error; err != nil {
		t.Fatalf("create first user: %v", err)
	}
	if err := db.Create(&User{Email: emailPtr("b@x.com"), Username: "SAM", UsernameKey: "sam", PasswordHash: "h"}).Error; err == nil {
		t.Fatal("expected duplicate normalized username to be rejected")
	}
}

func TestAutoMigrateBackfillsAndSuffixesDuplicateUsernames(t *testing.T) {
	db := newMemDB(t)
	if err := db.Exec(`CREATE TABLE users (
		id integer PRIMARY KEY,
		email text NOT NULL,
		username text NOT NULL,
		password_hash text NOT NULL,
		rating integer,
		created_at datetime,
		updated_at datetime
	)`).Error; err != nil {
		t.Fatalf("create users table: %v", err)
	}
	created := time.Date(2026, 1, 2, 3, 4, 5, 0, time.UTC)
	rows := []struct {
		id       int
		email    string
		username string
		created  time.Time
	}{
		{10003, "third@example.com", " RIVER ", created.Add(2 * time.Hour)},
		{10001, "first@example.com", "River", created},
		{10002, "second@example.com", "river", created.Add(time.Hour)},
		{10004, "symbol@example.com", "雨@夜!!!", created.Add(3 * time.Hour)},
	}
	for _, row := range rows {
		if err := db.Exec(`INSERT INTO users (id, email, username, password_hash, created_at) VALUES (?, ?, ?, 'h', ?)`, row.id, row.email, row.username, row.created).Error; err != nil {
			t.Fatalf("seed user %d: %v", row.id, err)
		}
	}

	if err := AutoMigrate(db); err != nil {
		t.Fatalf("AutoMigrate: %v", err)
	}

	var users []User
	if err := db.Order("id").Find(&users).Error; err != nil {
		t.Fatalf("load migrated users: %v", err)
	}
	want := map[uint][2]string{
		10001: {"River", "river"},
		10002: {"river-2", "river-2"},
		10003: {"RIVER-3", "river-3"},
		10004: {"雨-at-夜", "雨-at-夜"},
	}
	for _, user := range users {
		if got := [2]string{user.Username, user.UsernameKey}; got != want[user.ID] {
			t.Fatalf("user %d migrated to %#v, want %#v", user.ID, got, want[user.ID])
		}
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
// username index) is migrated in place with the normalized username key.
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
	if !db.Migrator().HasColumn(&User{}, "username_key") {
		t.Fatal("expected username_key column to be added")
	}
	if err := db.Create(&User{Email: emailPtr("a@x.com"), Username: "Sam", UsernameKey: "sam", PasswordHash: "h"}).Error; err != nil {
		t.Fatalf("create first user: %v", err)
	}
	if err := db.Create(&User{Email: emailPtr("b@x.com"), Username: "Sam", UsernameKey: "sam", PasswordHash: "h"}).Error; err == nil {
		t.Fatal("expected duplicate normalized username after migration to be rejected")
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

// Email is optional, so any number of accounts may carry no address at all.
// Postgres and SQLite both treat NULLs as distinct under a unique index; a
// regression here would surface as the second insert colliding.
func TestAutoMigrateAllowsManyAccountsWithoutEmail(t *testing.T) {
	db := newMemDB(t)
	if err := AutoMigrate(db); err != nil {
		t.Fatalf("AutoMigrate fresh: %v", err)
	}
	for _, name := range []string{"North Wind", "South Wind"} {
		display, key := NormalizeUsername(name)
		if err := db.Create(&User{Username: display, UsernameKey: key, PasswordHash: "h"}).Error; err != nil {
			t.Fatalf("create %q without email: %v", name, err)
		}
	}
	var count int64
	if err := db.Model(&User{}).Where("email IS NULL").Count(&count).Error; err != nil {
		t.Fatalf("count email-less users: %v", err)
	}
	if count != 2 {
		t.Fatalf("email IS NULL count = %d, want 2", count)
	}
}

// An account whose email was stored as an empty string is normalized to a real
// NULL, so it cannot collide with other email-less accounts.
func TestAutoMigrateConvertsEmptyEmailsToNull(t *testing.T) {
	db := newMemDB(t)
	if err := AutoMigrate(db); err != nil {
		t.Fatalf("AutoMigrate fresh: %v", err)
	}
	if err := db.Create(&User{Email: emailPtr(""), Username: "Blank Wind", UsernameKey: "blank wind", PasswordHash: "h"}).Error; err != nil {
		t.Fatalf("create empty-email user: %v", err)
	}
	if err := AutoMigrate(db); err != nil {
		t.Fatalf("AutoMigrate again: %v", err)
	}
	var reloaded User
	if err := db.Where("username_key = ?", "blank wind").First(&reloaded).Error; err != nil {
		t.Fatalf("reload user: %v", err)
	}
	if reloaded.Email != nil {
		t.Fatalf("email = %q, want NULL", *reloaded.Email)
	}
}

// The reset-code table is created by AutoMigrate and accepts a row.
func TestAutoMigrateCreatesPasswordResetCodes(t *testing.T) {
	db := newMemDB(t)
	if err := AutoMigrate(db); err != nil {
		t.Fatalf("AutoMigrate fresh: %v", err)
	}
	if err := db.Create(&PasswordResetCode{UserID: 10001, CodeHash: "hash", ExpiresAt: time.Now().Add(time.Minute)}).Error; err != nil {
		t.Fatalf("create reset code: %v", err)
	}
	var stored PasswordResetCode
	if err := db.First(&stored).Error; err != nil {
		t.Fatalf("load reset code: %v", err)
	}
	if stored.Attempts != 0 || stored.ConsumedAt != nil {
		t.Fatalf("new code = attempts %d consumed %v, want 0 and nil", stored.Attempts, stored.ConsumedAt)
	}
}
