# Email + Password Login — Design

**Date:** 2026-06-27
**Status:** Approved (pending implementation plan)

## Summary

Switch the account system from **username + password** to **email + password**.
Email becomes the login identity (unique, case-insensitive); the existing
`Username` field is repurposed as a non-unique **display name** shown on seats at
the table. Registration collects email + password + display name and auto-logs the
user in. User primary keys become **app-generated, random, sparse 5-digit integers**
instead of a DB auto-increment sequence. A new **account settings page** lets users
change their email and display name.

No verification codes, no OTP, no email sending, no Redis. Guest login is unchanged.
This is a fresh-start cutover — no migration of existing username/password accounts.

## Background: current auth and what is contained

Today (`internal/api/auth.go`, `internal/storage/db.go`):

- `User` has `Username` (`uniqueIndex;not null`), `PasswordHash` (`not null`),
  `Rating`, and an auto-increment `ID uint` primary key. **No `Email` field.**
- `Register` / `Login` authenticate by `username` + `password` (bcrypt).
- `GuestLogin` mints a throwaway JWT for a random `uint` id in
  `[9_000_000, 9_999_999]` with **no DB row**.
- JWT (HS256, `JWT_SECRET` env) carries `sub` (user id) + `username` + `exp` (72h
  for accounts, 24h for guests).
- `AuthMiddleware` reads `sub` → `userID` and `username` → `username` onto the gin
  context.

**Why the blast radius is small:** the only code that queries or writes by
`username` lives in `internal/api/auth.go`. Everything downstream (`room.go`,
`private_tables.go`, the paipu recorder, the middleware) reads the **display name**
from the JWT `username` claim and the user id from `sub`. As long as the `username`
claim keeps carrying the display name and `sub` stays a `uint`, nothing downstream
changes. There are no HTTP-level auth integration tests to update.

## Decisions (from brainstorming)

| Question | Decision |
|---|---|
| Auth method | Email + password. **No** verification code / OTP / email sending. |
| Identity vs. display | Email = login identity (unique). `Username` kept as **non-unique display name**. |
| Existing accounts | **Fresh start.** Email is required + unique; dev rows wiped / re-registered. No backward compat with username login. |
| Primary key | App-generated **random sparse integer**, range `[10000, 99999]`, stays `uint`. Not a UUID, not auto-increment. |
| Editable profile | Users can change email + display name on a new `/account` page. |
| Register UX | **Auto-login** on successful registration (return token, skip the "now log in" step). |
| Guest login | **Unchanged.** |

### Why a random 5-digit integer (not UUID, not auto-increment)

- **Sparse + random** satisfies the requirement: ids are non-sequential and not
  enumerable by counting up, and they don't leak the user count the way
  auto-increment does.
- **Stays `uint`** → zero churn on `MatchPlayer.UserID`, `Client.UserID`, the
  recorder, the JWT `sub` claim, and tests. A UUID string would force
  `uint → string` across all of those for no functional gain at this scale.
- **`[10000, 99999]`** (90k space) is sized for the expected small user base (~10k).
  With random allocation + collision-retry on insert this stays correct until the
  space is densely full; at a few thousand users the retry rate is negligible.
- **Naturally disjoint from the guest band** `[9_000_000, 9_999_999]`, so a guest id
  can never collide with a persisted user id — no extra handling.
- Both ranges are well within 2^53, so they round-trip exactly through the JWT
  `float64` claim path (`uint(claims["sub"].(float64))`).

**Tradeoff (documented, accepted):** a 90k space makes ids *somewhat* more guessable
than a large random space. Acceptable for a mahjong game. If stronger enumeration
resistance is ever wanted, widening the range is a one-constant change.

## Data model changes (`internal/storage/db.go`)

```go
type User struct {
    ID           uint   `gorm:"primaryKey;autoIncrement:false" json:"id"` // random sparse id, app-generated
    Email        string `gorm:"uniqueIndex;not null;size:255" json:"email"` // NEW — login identity (lowercased)
    Username     string `gorm:"not null;size:255" json:"username"`          // display name; uniqueIndex DROPPED
    PasswordHash string `gorm:"not null" json:"-"`
    Rating       int    `gorm:"default:1500" json:"rating"`
    CreatedAt    time.Time `json:"createdAt"`
    UpdatedAt    time.Time `json:"updatedAt"`
    Matches      []MatchPlayer `gorm:"foreignKey:UserID" json:"-"`
}
```

Changes vs. today:
- Add `Email` (`uniqueIndex;not null`), JSON-serialized (needed by the account page).
- `Username`: drop `uniqueIndex`, keep `not null`. It is now a display name; two
  players may share one.
- `ID`: add `autoIncrement:false` so GORM doesn't expect a DB sequence; the value is
  set by the app before insert.

### Random id generation

A package-level helper plus a GORM hook:

```go
// generateUserID returns a cryptographically-random id in [10000, 99999].
func generateUserID() (uint, error) {
    n, err := rand.Int(rand.Reader, big.NewInt(90000)) // crypto/rand
    if err != nil {
        return 0, err
    }
    return uint(n.Int64()) + 10000, nil
}

// BeforeCreate populates a random id when one isn't already set.
func (u *User) BeforeCreate(tx *gorm.DB) error {
    if u.ID == 0 {
        id, err := generateUserID()
        if err != nil {
            return err
        }
        u.ID = id
    }
    return nil
}
```

Collision handling lives at the call site (`Register`): retry `Create` up to N times
(e.g. 5), zeroing `user.ID` between attempts so `BeforeCreate` regenerates, breaking
on success and treating a persistent unique-constraint failure as a 500.

## Backend (`internal/api/auth.go`, `internal/api/server.go`)

### Shared helpers

```go
func normalizeEmail(s string) string { return strings.ToLower(strings.TrimSpace(s)) }

func issueToken(id uint, username string, ttl time.Duration) (string, error) // factors the JWT build
```

`issueToken` is used by `Login`, `Register`, `GuestLogin`, and the new profile
update so the claim shape (`sub`, `username`, `exp`) stays in one place.

### Register — `POST /api/v1/auth/register`

Request:
```go
type RegisterRequest struct {
    Email       string `json:"email" binding:"required,email"`
    Password    string `json:"password" binding:"required,min=8"`
    DisplayName string `json:"displayName" binding:"required,min=2,max=30"`
}
```
Flow:
1. `DB == nil` → 503 (existing guest-fallback message).
2. Normalize email. Reject duplicate email (lookup by `email`) → 409.
3. Hash password (bcrypt, unchanged).
4. Create `User{Email, Username: DisplayName, Rating: 1500}` with id-collision retry.
5. **Auto-login:** issue a 72h token and return `AuthResponse{Token, User}` (201),
   with `PasswordHash` blanked.

### Login — `POST /api/v1/auth/login`

Request:
```go
type LoginRequest struct {
    Email    string `json:"email" binding:"required,email"`
    Password string `json:"password" binding:"required"`
}
```
Flow: normalize email → lookup by `email` → bcrypt compare → issue 72h token →
return `AuthResponse`. Invalid email or password → 401 with a single generic
"Invalid email or password" message (no account-enumeration via distinct errors).

### Update profile — `PATCH /api/v1/users/me` (protected, NEW)

Request (both fields optional; update only what's provided):
```go
type UpdateProfileRequest struct {
    Email       *string `json:"email"       binding:"omitempty,email"`
    DisplayName *string `json:"displayName" binding:"omitempty,min=2,max=30"`
}
```
Flow:
1. `DB == nil` → 503. Load the user by `userID` from context; 404 if missing
   (guests have no row → they cannot edit, by design).
2. If `Email` set: normalize; if changed, check uniqueness excluding self → 409 on
   conflict; assign.
3. If `DisplayName` set: assign to `Username`.
4. Save. Re-issue a fresh 72h token (so the `username` claim reflects a changed
   display name; `sub` is the stable id, unaffected by email changes).
5. Return `AuthResponse{Token, User}` (token always re-issued for simplicity).

Registered in the `protected` group alongside `GET /users/me`.

### Guest login — unchanged

`GuestLogin` keeps minting random ids in `[9_000_000, 9_999_999]` (disjoint from the
real-user band) and stays out of the DB.

### Unchanged

`AuthMiddleware`, `handleGetMe` (`First(&user, userID)` already returns email now that
the field exists and is JSON-serialized), `room.go`, `private_tables.go`, recorder.

## Frontend

### Login page (`web/src/features/auth/Login.tsx`)

Introduce an explicit `mode` state (`'login' | 'register'`) so the form shows the
right fields:

- **Sign in:** Email, Password.
- **Create account:** Email, Password, Display name.
- A link toggles between the two modes.
- On success in **either** mode: store `fh_token`, `connect(token)`, navigate to
  `/play`. Registration auto-logs in, so there is no second step / `alert(...)`.
- `autoComplete`: `email`, `current-password` (sign in) / `new-password` (register).

### Account settings page (`web/src/features/auth/Account.tsx`, NEW)

- Route `/account` (added in `web/src/App.tsx`).
- On mount: `GET /api/v1/users/me` to prefill current email + display name.
  - A guest token returns 404/503 → render a short "Guests can't edit a profile —
    register an account" note instead of the form.
- Fields: Email, Display name, Save button → `PATCH /api/v1/users/me`.
- On success: replace `fh_token` with the returned token, `connect(newToken)` so the
  live session/socket picks up a changed display name, show a saved confirmation.
- Reachable from a link in the lobby/home nav.

## Cutover / migration

**Verified against the deployed Zeabur DB (project `fhmj`, 2026-06-27):** the app
connects via `DATABASE_URL` and runs `AutoMigrate` on **every boot**. The `users`
table currently has:

- `id bigint NOT NULL default nextval('users_id_seq')` (auto-increment sequence)
- `username varchar NOT NULL` with a **UNIQUE** index `idx_users_username`
- `password_hash text NOT NULL`, `rating`, timestamps
- **0 rows** — empty, so the fresh-start cutover loses no data.

`AutoMigrate` is **additive-only**: it adds the new `email` column + unique index,
but it will **not** drop the stale `idx_users_username` unique index (display names
must be non-unique per this design) nor remove the `id` sequence default. Two
problems if we just deploy:

1. Display names would stay DB-unique in prod (wrong).
2. `id` keeps an unused `nextval` default (harmless cruft — the app sets random ids
   explicitly via `BeforeCreate`).

**Cutover plan (table is empty, so this is safe):**

- **Drop the `users` table once** before/at the new deploy so `AutoMigrate` rebuilds
  it cleanly: `email` unique + `not null`, `username` non-unique, and `id` as a plain
  `bigint` PK with **no sequence** (because of `autoIncrement:false`). One-liner,
  e.g. `DROP TABLE IF EXISTS users CASCADE;` against the Zeabur Postgres.
  - `match_players` references `user_id` but is also empty; `CASCADE` covers any
    DB-level FK. (If a real FK exists it is dropped/recreated with the table.)
- No backward compatibility with username-based login; any future accounts register
  fresh with email.
- `AutoMigrate` model list in `internal/storage/db.go` is unchanged (same four models).

**Note (optional, out of scope):** the app's `DATABASE_URL` points at the *external*
Postgres endpoint (`43.134.132.74:32315`). An internal service DSN (`DB_DSN` already
exists on the service: `host=service-…0a231 …`) would keep DB traffic on Zeabur's
private network. Not required for this feature; flagged for later.

## Testing

**Constraint discovered:** the repo has **no DB test harness**. Every existing test
builds the server with `DB: nil` (`api/server_test.go`, `api/private_tables_test.go`),
and `gorm.io/driver/postgres` is the only driver in `go.mod`. The auth handlers
require a real DB (they return 503 when `DB == nil`), so testing the register/login
flow needs a database the test can stand up itself.

**Recommended approach — add a pure-Go SQLite driver as a test dependency.** Use
`github.com/glebarez/sqlite` (no CGo, CI-friendly) to open an in-memory DB and
`AutoMigrate(&User{})` per test:

```go
db, _ := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
db.AutoMigrate(&storage.User{})
h := &AuthHandler{DB: db}
```

This gives real coverage of the handlers against a real (if lightweight) GORM
backend. Only the `User` table is migrated; its column types are standard and behave
identically on SQLite. (Alternative considered: gate DB-backed tests behind a
`TEST_DATABASE_URL` env pointing at a throwaway Postgres — heavier, needs a running
server, so not recommended.)

`internal/api/auth_test.go` cases:

- Register → Login happy path returns a token and a user with the email + display
  name; `PasswordHash` never serialized.
- Duplicate email on register → 409.
- Wrong password / unknown email on login → 401 (generic message).
- Missing/invalid fields (bad email format, password < 8, display name < 2) → 400.
- Email case-normalization: register `Foo@X.com`, log in as `foo@x.com`.
- `PATCH /users/me`: changes email + display name, returns a fresh token; email
  collision with another user → 409.

Plus DB-free unit tests for the pure helpers: `generateUserID` returns a value in
`[10000, 99999]`, and `normalizeEmail` lowercases + trims.

Run `go test ./...` and a frontend type-check/build before commit.

> **Decided:** add `github.com/glebarez/sqlite` as a test-only dependency to give the
> DB-backed handler paths real automated coverage (in-memory, pure-Go).

## Out of scope (YAGNI)

Verification codes, OTP, email sending / SMTP, Redis, password reset, email-change
confirmation, rate limiting, social login. A future "forgot password" flow is the
feature that would finally require real email delivery — explicitly deferred.

## Files touched

- `internal/storage/db.go` — `User` fields, `BeforeCreate` hook, `generateUserID`.
- `internal/api/auth.go` — request structs, `Register`, `Login`, `issueToken`,
  `normalizeEmail`, profile update handler.
- `internal/api/server.go` — register `PATCH /api/v1/users/me` in the protected group.
- `web/src/features/auth/Login.tsx` — email/password + mode toggle.
- `web/src/features/auth/Account.tsx` (new) + `web/src/App.tsx` route + nav link.
- `internal/api/auth_test.go` (new).
- Relevant `AGENTS.md` files updated to reflect email-based auth.
