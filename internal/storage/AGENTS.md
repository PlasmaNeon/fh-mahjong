# internal/storage/

> GORM database models for PostgreSQL persistence.

## Overview

Defines the database schema for user accounts and match history using GORM (Go ORM). These models are used by the `internal/api/` package for user registration, authentication, and match record keeping.

## Key Files

- **db.go** — Database models and migration:
  - `User` — Player account: the case-insensitive `UsernameKey` is the required unique login identity; `Username` preserves the visible friendly form. `Email` is **optional and nullable** (`*string`) — NULL means no address on file, and when set it is unique, usable as a second login identifier, and the password-reset destination. `EmailVerifiedAt` is reserved for a future ownership check and is always nil today. Existing duplicate usernames are deterministically suffixed during migration. IDs remain random sparse values in [10000, 99999]
  - `PasswordResetCode` — One issued reset code: bcrypt `CodeHash` (never the plaintext), `ExpiresAt`, `Attempts`, and `ConsumedAt`. Bcrypt rather than SHA-256 because a 6-digit code is only ~20 bits of entropy
  - `UserSession` — Revocable 30-day browser session. Stores only the SHA-256 hash of the opaque cookie plus its CSRF token and expiry; raw session credentials never enter the database
  - `Match` — Single game record: match ID, status, ruleset name, binary replay URL/blob, and structured paipu JSON
  - `MatchPlayer` — Join table linking users to matches: seat position, final score, placement, rating delta, and seat-composition labels. There is deliberately no users foreign key because bot rows use user ID 0 and historical guest matches can reference accounts that no longer exist
  - `MatchReview` — Caches one champion's post-game review report (`internal/review.Report`, JSON-encoded) for a match: `MatchID` (size:255 — also covers per-round `matchID-handNum` `PaipuRecord` keys and dev fixtures, not just canonical UUIDs), `CheckpointID` (size:512, the serving policy checkpoint path), `ReportJSON` (raw JSON text), `CreatedAt`. Unique index `idx_match_reviews_match_ckpt` on `(MatchID, CheckpointID)` — one row per match+champion pair, so re-reviewing with the same champion overwrites in place while a new champion adds a new row instead of clobbering the old report. `internal/api/review.go` reads/writes this table: cache policy is "newest row wins" (`ORDER BY created_at DESC`) unless the caller passes `?force=1` to `POST /api/v1/matches/:matchId/review`, which rebuilds against the current champion.
  - `generateUserID()` — Package-private function that returns a cryptographically-random user ID in [10000, 99999]
  - `User.BeforeCreate(tx)` — GORM hook that assigns a random sparse ID when one isn't already set
  - `AutoMigrate(db)` — Creates/updates tables from struct definitions
  - `match_history.go` — Idempotently recovers missing `MatchPlayer` ownership/result rows from valid completed legacy paipu. Existing indexed matches are never replaced; malformed records are counted and skipped without blocking startup

## Architecture Notes

- Used by `internal/api/auth.go` for user CRUD and `internal/api/room.go` / `internal/api/paipu.go` for match replay persistence and retrieval.
- `AutoMigrate` owns the username cutover: sanitize friendly names, preserve the oldest collision, append `-2`/`-3`, backfill `username_key`, then create its unique index.
- `AutoMigrate` also owns the completed-match history cutover. It parses only the minimum paipu player/final-score fields, preserves competition ranking for ties, and logs recovered/skipped counts.
- PostgreSQL connection is established in `cmd/server/main.go` and passed through.
- Rating system and match history are Phase 3 features (not yet fully implemented).
