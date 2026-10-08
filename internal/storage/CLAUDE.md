# internal/storage/

> GORM models and migrations for PostgreSQL.

## Key files

- **models.go** — the models:
  - `User` — normalized email and case-insensitive `UsernameKey` are unique login identities;
    `Username` keeps the display form. Ids are random in [10000, 99999] (`BeforeCreate`).
  - `UserSession` — revocable 30-day session: the SHA-256 of the opaque cookie, its CSRF token,
    and expiry. Raw credentials never reach the database.
  - `Match` — status, ruleset, binary replay, and paipu JSON.
  - `MatchPlayer` — seat, final score, placement, rating delta, seat-composition labels. No
    foreign key to users: bot rows use user id 0 and old guest matches may reference deleted
    accounts.
  - `PaipuRecord` — per-hand paipu rows.
  - `MatchReview` — one cached review report per `(MatchID, CheckpointID)`; `SchemaVersion`
    keeps old reports from being served as current.
  - `ReplayImport` — immutable account-owned paipu uploads, unique per owner and content hash.
  - `ReplayStudyJob` — study job state: frozen input, checkpoint sha, event window, config,
    lease and worker identity, progress, durable report chunks.
- **migrate.go** — `AutoMigrate`, including the username cutover (sanitize, keep the oldest of a
  collision, suffix `-2`/`-3`, then the unique index).
- **match_history.go** — idempotently recovers missing `MatchPlayer` rows from valid completed
  legacy paipu; malformed records are counted and skipped.

## Notes

- The database connection is opened in `cmd/server/main.go` (`DATABASE_URL`, else the
  docker-compose database on `localhost:5433`).
- `User.Rating` and `MatchPlayer.RatingDelta` exist, but nothing updates them.
- Imports and study jobs are never live matches, history entries, or training records.
