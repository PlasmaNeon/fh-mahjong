# internal/storage/

> GORM database models for PostgreSQL persistence.

## Overview

Defines the database schema for user accounts and match history using GORM (Go ORM). These models are used by the `internal/api/` package for user registration, authentication, and match record keeping.

## Key Files

- **db.go** — Database models and migration:
  - `User` — Player account: email is the unique login identity, username is a non-unique display name, random sparse ID in [10000, 99999] (app-generated via `BeforeCreate`), hashed password, rating, created/updated timestamps
  - `Match` — Single game record: match ID, status, ruleset name, binary replay URL/blob, and structured paipu JSON
  - `MatchPlayer` — Join table linking users to matches: seat position, final score, placement, rating delta, plus seat-composition labels (`IsBot`, `Difficulty` "heuristic"/"rl", `PolicyID` RL checkpoint identity) mirroring the paipu players so datasets can be filtered in SQL without parsing `PaipuJSON`. Rows are inserted by `Room.persistMatch` at room shutdown, in one transaction with the Match update (bots have `UserID` 0). There is deliberately NO users foreign key on `match_players` — bots (user_id 0) and guest accounts (9000000-range, no users row) must insert cleanly; `AutoMigrate` drops the legacy constraint. Unique index on `(match_id, seat)` keeps retried persists idempotent. Provenance columns: `RemoteDecisions`/`FallbackDecisions` (RL remote vs heuristic-fallback decisions; pure-RL filter `fallback_decisions = 0 AND remote_decisions > 0`) and `AutomatedDecisions` (bot-takeover decisions on a human seat; pure-human filter `is_bot = false AND automated_decisions = 0`). Matches persisted before this existed have no rows — fall back to parsing the paipu
  - `MatchReview` — Caches one champion's post-game review report (`internal/review.Report`, JSON-encoded) for a match: `MatchID` (size:255 — also covers per-round `matchID-handNum` `PaipuRecord` keys and dev fixtures, not just canonical UUIDs), `CheckpointID` (size:512, the serving policy checkpoint path), `ReportJSON` (raw JSON text), `CreatedAt`. Unique index `idx_match_reviews_match_ckpt` on `(MatchID, CheckpointID)` — one row per match+champion pair, so re-reviewing with the same champion overwrites in place while a new champion adds a new row instead of clobbering the old report. `internal/api/review.go` reads/writes this table: cache policy is "newest row wins" (`ORDER BY created_at DESC`) unless the caller passes `?force=1` to `POST /api/v1/matches/:matchId/review`, which rebuilds against the current champion.
  - `generateUserID()` — Package-private function that returns a cryptographically-random user ID in [10000, 99999]
  - `User.BeforeCreate(tx)` — GORM hook that assigns a random sparse ID when one isn't already set
  - `AutoMigrate(db)` — Creates/updates tables from struct definitions

## Architecture Notes

- Used by `internal/api/auth.go` for user CRUD and `internal/api/room.go` / `internal/api/paipu.go` for match replay persistence and retrieval.
- PostgreSQL connection is established in `cmd/server/main.go` and passed through.
- Rating system and match history are Phase 3 features (not yet fully implemented).
