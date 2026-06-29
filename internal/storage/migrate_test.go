package storage

import (
	"strings"
	"testing"

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
