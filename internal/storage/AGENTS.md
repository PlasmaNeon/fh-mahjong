# internal/storage/

> GORM database models for PostgreSQL persistence.

## Overview

Defines the database schema for user accounts and match history using GORM (Go ORM). These models are used by the `internal/api/` package for user registration, authentication, and match record keeping.

## Key Files

- **db.go** — Database models and migration:
  - `User` — Player account: email is the unique login identity, username is a non-unique display name, random sparse ID in [10000, 99999] (app-generated via `BeforeCreate`), hashed password, rating, created/updated timestamps
  - `Match` — Single game record: match ID, status, ruleset name, binary replay URL/blob, and structured paipu JSON
  - `MatchPlayer` — Join table linking users to matches: seat position, final score, placement, rating delta
  - `generateUserID()` — Package-private function that returns a cryptographically-random user ID in [10000, 99999]
  - `User.BeforeCreate(tx)` — GORM hook that assigns a random sparse ID when one isn't already set
  - `AutoMigrate(db)` — Creates/updates tables from struct definitions

## Architecture Notes

- Used by `internal/api/auth.go` for user CRUD and `internal/api/room.go` / `internal/api/paipu.go` for match replay persistence and retrieval.
- PostgreSQL connection is established in `cmd/server/main.go` and passed through.
- Rating system and match history are Phase 3 features (not yet fully implemented).
