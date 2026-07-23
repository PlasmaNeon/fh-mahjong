# Username + password registration, optional email, code-based password reset

Date: 2026-07-23
Supersedes parts of: `2026-06-27-email-password-login-design.md`

## Goal

Registration requires only a username and a password. Email becomes an optional
profile field. A user who has set an email can request a verification code that
resets their password.

The mail sender is a logging stub in this change, and no UI links to the reset
flow. The reset backend is built and tested now so that wiring a real mail
provider later is a small, low-risk change.

## Scope

In scope:

- Drop email from registration.
- Make `users.email` nullable and optional in the profile.
- Add `password_reset_codes` and two unlinked reset endpoints.
- Add `internal/mail` with a `Sender` interface and a log-only implementation.
- Frontend: remove the register email field, mark profile email optional.

Out of scope (deliberate, follow-up work):

- A real SMTP or HTTP mail provider.
- Any "forgot password" / "reset password" UI entry point.
- Email ownership verification. The `email_verified_at` column is added now and
  left null so that adding verification later needs no schema migration.

## Data model

`internal/storage/db.go`.

### User

```go
Email           *string    `gorm:"uniqueIndex;size:255" json:"email"`
EmailVerifiedAt *time.Time `json:"emailVerifiedAt,omitempty"`
```

`Email` changes from `string` with `not null` to a nullable pointer. Both
Postgres and SQLite treat NULLs as distinct within a unique index, so any number
of accounts without an email coexist while set emails stay unique. `Email`
serializes as JSON `null` when unset.

`EmailVerifiedAt` is always nil in this change. It exists so the reset flow can
later be narrowed to verified addresses without a migration.

### PasswordResetCode

```go
type PasswordResetCode struct {
    ID         uint       `gorm:"primaryKey"`
    UserID     uint       `gorm:"index;not null"`
    CodeHash   string     `gorm:"not null"`
    ExpiresAt  time.Time  `gorm:"index;not null"`
    Attempts   uint8      `gorm:"not null;default:0"`
    ConsumedAt *time.Time
    CreatedAt  time.Time
}
```

`CodeHash` is a bcrypt hash, not SHA-256. A 6-digit code has ~20 bits of
entropy, so a SHA-256 digest is reversible in milliseconds from a database dump.
Bcrypt at the default cost puts a full sweep of the 10^6 space in the hours
range, by which time the 15-minute TTL has expired the code.

### Migration

Inside `AutoMigrate`, following the explicit-step style already in that
function:

1. `UPDATE users SET email = NULL WHERE email = ''` — runs on both dialects, so
   any row that reached an empty string becomes a proper NULL.
2. Postgres only, guarded on `db.Dialector.Name() == "postgres"` and on the
   column existing: `ALTER TABLE users ALTER COLUMN email DROP NOT NULL`. The
   statement is idempotent. SQLite test databases are created fresh from the new
   model, so they never carry the old NOT NULL.

The existing fail-closed check for a legacy `users` table with no `email` column
is unchanged.

## API

`internal/api/auth.go`.

### POST /api/v1/auth/register

`RegisterRequest` loses its `Email` field entirely. `Username` becomes
`binding:"required"`; the `displayName` legacy alias and its `resolveAlias`
disagreement check stay. Password stays `min=8`. Username validation
(`validateUsername`: 2–30 runes, letters/numbers/space/`_`/`-`, no `@`) is
unchanged.

New users are created with `Email` nil. The unique-constraint conflict message
narrows from "Email or username is already registered" to "Username is already
registered", since email can no longer collide at registration.

### POST /api/v1/auth/login

Unchanged. An identifier containing `@` resolves by email, otherwise by
`username_key`. Accounts created before this change keep both login paths;
accounts created after it have no email until the user sets one.

### PATCH /api/v1/users/me

`UpdateProfileRequest.Email` stays `*string` with `binding:"omitempty,email"`,
with these semantics:

- key absent / JSON `null` — no change (unchanged behaviour).
- non-empty string — set or change the email.
- `""` — clear the email back to NULL.

`omitempty` on the binding tag already permits `""` past the email format check.

A current password is required for any email change, including the first time an
email is added and including clearing it. This matches today's rule and keeps a
stolen session from silently attaching an attacker-controlled recovery address.

Setting or clearing an email writes `email_verified_at = NULL`.

The "No changes requested" 400 still fires when neither email nor username
changes.

### POST /api/v1/auth/password-reset/request

Body: `{"identifier": "..."}` — a username or an email, resolved with the same
logic as login.

Always responds `204`, regardless of whether the identifier matches an account,
whether that account has an email, or whether delivery succeeded. The status and
body are byte-identical across all of those cases.

Response timing is not equalized: only a resolved user with an email reaches the
bcrypt hash, so a determined attacker could in principle distinguish the cases by
latency. That is accepted here rather than papered over with a dummy hash — the
per-IP rate limit bounds how fast the endpoint can be probed, and the same
membership fact is already obtainable from registration's `409` on a duplicate
username. Equalizing it is a reasonable hardening follow-up if the endpoint is
ever exposed in the UI.

When the identifier does resolve to a user with an email:

1. Generate a 6-digit code from `crypto/rand`.
2. Mark every unconsumed, unexpired code for that user as consumed, so only the
   newest code works.
3. Insert a `PasswordResetCode` with the bcrypt hash and `ExpiresAt = now + 15m`.
4. Hand the plaintext code to the `mail.Sender`.

Rate limited per resolved user and per client IP with the token bucket shape
from `review_ratelimit.go` (in-memory, single-process, resets on restart). The
per-IP bucket is what protects the unresolved-identifier path, which has no user
id to key on. A throttled request still returns `204`.

### POST /api/v1/auth/password-reset/confirm

Body: `{"identifier": "...", "code": "...", "newPassword": "..."}`. New password
is validated at `min=8`, the same rule as registration.

Responds `204` on success. Every failure — unknown identifier, no code on file,
expired, already consumed, attempts exhausted, wrong code — returns the same
`400` with a single generic message.

On a wrong code, `Attempts` increments; at 5 the code is treated as dead and
must be re-requested.

On success, in one transaction:

1. Rehash and store the new password.
2. Set `ConsumedAt` on the code.
3. Delete every `UserSession` row for that user, logging out all devices.

### Route registration

Both routes are registered on the public `v1` group in `server.go`, next to
`/auth/register` and `/auth/login`. Nothing in the frontend links to them.

## internal/mail

A new package, deliberately tiny:

```go
type Sender interface {
    SendPasswordResetCode(ctx context.Context, to, code string) error
}

type LogSender struct{}
```

`LogSender.SendPasswordResetCode` writes the recipient and code to the server
log and returns nil. `AuthHandler` holds a `Sender`; `server.go` wires
`LogSender`. A real provider becomes a second implementation of the interface
with no call-site changes.

A send failure never changes the HTTP response — it is logged and the handler
still returns `204`.

## Frontend

- `web/src/features/auth/authClient.ts` — `AuthUser.email` becomes
  `string | null`.
- `web/src/features/auth/AuthTicket.tsx` — the register branch drops the email
  `Field` and the `email` state; the register body is `{username, password}`;
  the submit-disabled condition drops `!email`.
- `web/src/features/auth/Account.tsx` — the email `Field` is labelled optional
  with a note that it is used for account recovery. It renders `''` when
  `user.email` is null, and submitting an empty value where one was previously
  set clears the email. The current-password copy is updated to cover setting
  and clearing, not only changing.
- No forgot-password or reset link is added anywhere.
- i18n keys updated and added in both `en.ts` and `zh-CN.ts`.

## Testing

Go, `internal/api`:

- Register with only username and password succeeds and returns `email: null`.
- Register rejects a duplicate username with `409`.
- Two accounts registered without an email both persist (NULL uniqueness).
- Login by username works for an email-less account.
- Login by email still works for an account that has set one.
- `PATCH /users/me` sets an email, changes it, and clears it to null; each
  requires the current password; a wrong password is rejected.
- Reset request returns `204` for an unknown identifier, for a known user with
  no email, and for a known user with an email.
- Reset request supersedes a previously issued unconsumed code.
- Reset confirm rejects a wrong code, an expired code, a consumed code, and a
  code whose attempts are exhausted, all with the same status and message.
- Reset confirm with a valid code changes the password, and every pre-existing
  session for that user stops authenticating.

Go, `internal/storage`:

- Migration test: a users row with `email = ''` becomes NULL after
  `AutoMigrate`, and inserting two email-less users succeeds.

Existing tests: the 8 `registerSession` call sites in `internal/api` drop their
email argument. `TestNormalizeEmail` stays as is.

Web:

- A vitest asserting the register request body contains no `email` key.
  Rendering `AuthTicket` itself needs the auth context, so the absence of the
  input is confirmed by manual check rather than by a unit test.

## Docs

Update `internal/api/AGENTS.md`, `internal/storage/AGENTS.md`, and
`web/src/features/AGENTS.md` to describe username-only registration, optional
email, and the unlinked reset endpoints with their log-only sender.
