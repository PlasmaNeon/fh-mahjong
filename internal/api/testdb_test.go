package api

import (
	"testing"

	"github.com/glebarez/sqlite"
	"gorm.io/gorm"

	"github.com/plasma/fh-mahjong/internal/storage"
)

// newTestDB opens an in-memory sqlite database with the schema applied. Every
// api test that needs persistence goes through this so the migration set cannot
// drift between suites.
func newTestDB(t *testing.T) *gorm.DB {
	t.Helper()
	db, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	if err := storage.AutoMigrate(db); err != nil {
		t.Fatalf("automigrate: %v", err)
	}
	return db
}

// newTestServer wires the full server stack -- db, hub, matchmaker -- against a
// fresh in-memory database. The hub goroutine is started, matching production.
func newTestServer(t *testing.T) *Server {
	t.Helper()
	db := newTestDB(t)
	hub := NewHub()
	go hub.Run()
	return NewServer(db, hub, NewMatchmaker(NewInMemoryQueue(), db, hub))
}
