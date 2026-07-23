# Username + Password Auth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Registration takes only a username and a password; email becomes an optional profile field that can receive a password-reset verification code.

**Architecture:** `users.email` changes from a required NOT NULL column to a nullable `*string`, so any number of accounts can exist without one while set addresses stay unique. A new `password_reset_codes` table holds bcrypt-hashed, single-use, expiring codes. Two new public endpoints issue and redeem those codes; they are registered but nothing in the frontend links to them, and the mail sender is a logging stub.

**Tech Stack:** Go 1.25, Gin, GORM (Postgres in production, in-memory SQLite in tests), `golang.org/x/crypto/bcrypt`, React 19 + TypeScript + Vitest.

**Spec:** `docs/superpowers/specs/2026-07-23-username-password-auth-design.md`

## Global Constraints

- No new Go module dependencies. Everything uses the standard library plus packages already in `go.mod`.
- `internal/engine/game.go` must never import `internal/rules/`. Not touched by this plan, but the rule stands.
- Run `go test ./...` after any logic change.
- Error-response shape is always `{"error": "..."}` via `respondError` / `abortError` — never write a bare `c.JSON` error body.
- Password minimum length is 8 everywhere it is validated (`binding:"required,min=8"`).
- Every mutating endpoint under the protected group already requires the CSRF header; the two new reset endpoints are public and take no session, so they must not be added to the protected group.
- No "forgot password" or "reset password" link, button, route, or copy may appear anywhere in `web/`.
- Every new user-visible string needs a key in **both** `web/src/i18n/locales/en.ts` and `web/src/i18n/locales/zh-CN.ts`.
- Commit after every task.

## File Structure

**Create:**
- `internal/mail/mail.go` — `Sender` interface + `LogSender`. Sole responsibility: delivering account email.
- `internal/mail/mail_test.go`
- `internal/api/ratelimit.go` — `keyedRateLimiter`, a string-keyed token bucket.
- `internal/api/ratelimit_test.go`
- `internal/api/password_reset.go` — code generation, both reset handlers, shared identifier lookup.
- `internal/api/password_reset_test.go`

**Modify:**
- `internal/storage/db.go` — `User.Email` → `*string`, add `User.EmailVerifiedAt`, add `PasswordResetCode`, extend `AutoMigrate`.
- `internal/storage/migrate_test.go` — pointer emails, two new migration tests.
- `internal/api/auth.go` — `RegisterRequest` loses `Email`; `Register` stops writing one; `Login` delegates lookup; `UpdateMe` handles set/change/clear.
- `internal/api/server.go` — wire `Mail` + `ResetLimiter` into `AuthHandler`, register two routes.
- `internal/api/session_auth_test.go` — register bodies drop email; new registration/profile tests.
- `internal/api/private_room_creation_test.go` — `registerSession` helper signature.
- `internal/api/replay_history_test.go` — `registerSession` call sites.
- `internal/api/private_tables_test.go` — one `storage.User` literal.
- `web/src/features/auth/authClient.ts` — `AuthUser.email` nullable, `authRequestBody` helper.
- `web/src/features/auth/authClient.test.ts` — tests for that helper.
- `web/src/features/auth/AuthTicket.tsx` — register form drops email.
- `web/src/features/auth/Account.tsx` — email optional, clearable, null-safe.
- `web/src/i18n/locales/en.ts`, `web/src/i18n/locales/zh-CN.ts` — copy changes.
- `internal/storage/AGENTS.md`, `internal/api/AGENTS.md`, `web/src/features/AGENTS.md`.

---

### Task 1: Nullable email, reset-code table, migration

**Files:**
- Modify: `internal/storage/db.go:16-27` (User), `internal/storage/db.go:196-270` (AutoMigrate)
- Modify: `internal/storage/migrate_test.go:37`, `:40`, `:138`, `:141`
- Modify: `internal/api/auth.go:198-204`, `internal/api/auth.go:332-337`, `internal/api/auth.go:363-366` — mechanical only
- Modify: `internal/api/private_tables_test.go:37`
- Modify: `internal/storage/AGENTS.md:12`
- Test: `internal/storage/migrate_test.go`

**Interfaces:**
- Consumes: nothing.
- Produces: `storage.User.Email *string`, `storage.User.EmailVerifiedAt *time.Time`, and `storage.PasswordResetCode{ID uint, UserID uint, CodeHash string, ExpiresAt time.Time, Attempts uint8, ConsumedAt *time.Time, CreatedAt time.Time}`.

**Why this task also touches `internal/api`:** changing `Email` to a pointer stops `internal/api` compiling — `auth.go` assigns a `string` to it and compares it with `!=`. Steps 7 and 8 are the smallest edits that restore the build with *identical* behaviour. The behaviour changes land in Tasks 2 and 3. Do not go further here; a task must not end with a tree that does not build.

- [ ] **Step 1: Add the pointer-email test helper and convert existing literals**

In `internal/storage/migrate_test.go`, add this helper directly below `newMemDB`:

```go
// emailPtr is a literal helper: User.Email is a nullable *string, so tests
// that want a concrete address need an addressable value.
func emailPtr(value string) *string { return &value }
```

Then replace the four existing struct literals. Lines 37 and 40:

```go
	if err := db.Create(&User{Email: emailPtr("a@x.com"), Username: "Sam", UsernameKey: "sam", PasswordHash: "h"}).Error; err != nil {
		t.Fatalf("create first user: %v", err)
	}
	if err := db.Create(&User{Email: emailPtr("b@x.com"), Username: "SAM", UsernameKey: "sam", PasswordHash: "h"}).Error; err == nil {
		t.Fatal("expected duplicate normalized username to be rejected")
	}
```

Lines 138 and 141:

```go
	if err := db.Create(&User{Email: emailPtr("a@x.com"), Username: "Sam", UsernameKey: "sam", PasswordHash: "h"}).Error; err != nil {
		t.Fatalf("create first user: %v", err)
	}
	if err := db.Create(&User{Email: emailPtr("b@x.com"), Username: "Sam", UsernameKey: "sam", PasswordHash: "h"}).Error; err == nil {
		t.Fatal("expected duplicate normalized username after migration to be rejected")
	}
```

- [ ] **Step 2: Write the failing migration tests**

Append to `internal/storage/migrate_test.go`:

```go
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
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `go test ./internal/storage/ -run 'TestAutoMigrateAllowsManyAccountsWithoutEmail|TestAutoMigrateConvertsEmptyEmailsToNull|TestAutoMigrateCreatesPasswordResetCodes' -v`

Expected: FAIL — compile errors, because `User.Email` is still a `string` (so `emailPtr("")` and `reloaded.Email != nil` do not type-check) and `PasswordResetCode` is undefined.

- [ ] **Step 4: Change the User model**

In `internal/storage/db.go`, replace the `User` comment and struct (lines 16-27) with:

```go
// User represents a player account. Username (through the case-insensitive
// UsernameKey) is the required login identity. Email is OPTIONAL: NULL means
// no address is on file. When set it is unique, doubles as a second login
// identity, and is where a password-reset code is delivered.
//
// EmailVerifiedAt is reserved for a future ownership-confirmation flow and is
// always nil today; the column exists now so adding verification later needs
// no migration.
type User struct {
	ID              uint       `gorm:"primaryKey;autoIncrement:false" json:"id"` // random sparse id, app-generated
	Email           *string    `gorm:"uniqueIndex;size:255" json:"email"`
	EmailVerifiedAt *time.Time `json:"emailVerifiedAt,omitempty"`
	Username        string     `gorm:"not null;size:255" json:"username"`
	UsernameKey     string     `gorm:"size:255" json:"-"`
	PasswordHash    string     `gorm:"not null" json:"-"`
	Rating          int        `gorm:"default:1500" json:"rating"`
	CreatedAt       time.Time  `json:"createdAt"`
	UpdatedAt       time.Time  `json:"updatedAt"`
}
```

- [ ] **Step 5: Add the PasswordResetCode model**

In `internal/storage/db.go`, directly below the `UserSession` struct, add:

```go
// PasswordResetCode is one issued password-reset verification code. CodeHash
// is a BCRYPT hash, not SHA-256: a 6-digit code carries only ~20 bits of
// entropy, so a fast digest would be reversible from a database dump in
// milliseconds. Bcrypt puts a full sweep of the space in the hours range, by
// which point the short TTL has already expired the code.
//
// A code is dead once ConsumedAt is set, once ExpiresAt passes, or once
// Attempts reaches the API's cap.
type PasswordResetCode struct {
	ID         uint       `gorm:"primaryKey" json:"-"`
	UserID     uint       `gorm:"index;not null" json:"-"`
	CodeHash   string     `gorm:"not null" json:"-"`
	ExpiresAt  time.Time  `gorm:"index;not null" json:"-"`
	Attempts   uint8      `gorm:"not null;default:0" json:"-"`
	ConsumedAt *time.Time `json:"-"`
	CreatedAt  time.Time  `json:"-"`
}
```

- [ ] **Step 6: Extend AutoMigrate**

In `internal/storage/db.go`, add `&PasswordResetCode{},` to the `db.AutoMigrate(...)` list, directly after `&UserSession{},`.

Then, immediately after that `if err := db.AutoMigrate(...); err != nil { return err }` block and **before** the `db.Transaction` that backfills usernames, insert:

```go
	// users.email was NOT NULL while registration demanded an address. It is
	// now optional, so the constraint has to come off before any row can be
	// nulled. Postgres accepts DROP NOT NULL on an already-nullable column, so
	// this is idempotent. SQLite is skipped deliberately: GORM builds test
	// databases fresh from the model above (already nullable), and the sqlite
	// driver would need a full table rebuild to change nullability.
	if db.Dialector.Name() == "postgres" && m.HasColumn(&User{}, "email") {
		if err := db.Exec("ALTER TABLE users ALTER COLUMN email DROP NOT NULL").Error; err != nil {
			return fmt.Errorf("making users.email nullable: %w", err)
		}
	}
	// An empty string is not NULL, and two empty strings collide under the
	// unique index. Normalize any that exist to a real NULL.
	if err := db.Exec("UPDATE users SET email = NULL WHERE email = ''").Error; err != nil {
		return fmt.Errorf("clearing empty user emails: %w", err)
	}
```

- [ ] **Step 7: Run the storage tests**

Run: `go test ./internal/storage/ -v`

Expected: PASS, including the three new tests and every pre-existing migration test.

- [ ] **Step 8: Restore the build in internal/api (mechanical, no behaviour change)**

Run `go build ./...` first to see the three breakages.

In `internal/api/auth.go`, `Register` assigns a `string` to a `*string`. Replace the `user := storage.User{...}` literal (lines 198-204) with:

```go
	// Task 2 removes email from registration entirely; for now this preserves
	// today's behaviour against a pointer field.
	registeredEmail := normalizeEmail(req.Email)
	user := storage.User{
		Email:        &registeredEmail,
		Username:     username,
		UsernameKey:  usernameKey,
		PasswordHash: string(hashedPassword),
		Rating:       1500,
	}
```

In `UpdateMe`, the change detection compares a `string` with a `*string`. Replace lines 332-337 with:

```go
	newEmail := ""
	emailChange := false
	if req.Email != nil {
		newEmail = normalizeEmail(*req.Email)
		emailChange = user.Email == nil || *user.Email != newEmail
	}
```

The `updates["email"] = newEmail` assignment further down still compiles and still means the same thing — leave it alone.

In `internal/api/private_tables_test.go:37`, the fixture seeds an email it never logs in with. Drop it:

```go
	user := storage.User{ID: userID, Username: username, PasswordHash: "test", Rating: 1500}
```

If `fmt` is now unused in that file, remove it from the import block.

- [ ] **Step 9: Verify the whole tree builds and passes**

Run: `go build ./... && go test ./... 2>&1 | grep -v "no test files"`

Expected: no build output, every package `ok`. Behaviour is unchanged from before this task — only the column's nullability and the new table are new.

- [ ] **Step 10: Update the storage AGENTS.md**

In `internal/storage/AGENTS.md`, replace the `User` bullet (line 12) with:

```markdown
  - `User` — Player account: the case-insensitive `UsernameKey` is the required unique login identity; `Username` preserves the visible friendly form. `Email` is **optional and nullable** (`*string`) — NULL means no address on file, and when set it is unique, usable as a second login identifier, and the password-reset destination. `EmailVerifiedAt` is reserved for a future ownership check and is always nil today. Existing duplicate usernames are deterministically suffixed during migration. IDs remain random sparse values in [10000, 99999]
```

Add a bullet below it, in the same list:

```markdown
  - `PasswordResetCode` — One issued reset code: bcrypt `CodeHash` (never the plaintext), `ExpiresAt`, `Attempts`, and `ConsumedAt`. Bcrypt rather than SHA-256 because a 6-digit code is only ~20 bits of entropy
```

- [ ] **Step 11: Commit**

```bash
git add internal/storage/db.go internal/storage/migrate_test.go internal/storage/AGENTS.md internal/api/auth.go internal/api/private_tables_test.go
git commit -m "feat(storage): make user email optional and add password reset codes"
```

---

### Task 2: Registration takes only username and password

**Files:**
- Modify: `internal/api/auth.go:31-36` (RegisterRequest), `internal/api/auth.go:173-226` (Register)
- Modify: `internal/api/private_room_creation_test.go:28-40` (helper) and its call sites at `:44`, `:66`, `:78`, `:87`
- Modify: `internal/api/replay_history_test.go:61`, `:99`, `:147`
- Test: `internal/api/session_auth_test.go`

**Interfaces:**
- Consumes: `storage.User.Email *string` from Task 1.
- Produces: `registerSession(t *testing.T, server *Server, username string) (*http.Cookie, string)` — the email argument is gone. `RegisterRequest{Username, DisplayName, Password}`.

- [ ] **Step 1: Write the failing registration tests**

Append to `internal/api/session_auth_test.go`:

```go
func TestRegisterNeedsOnlyUsernameAndPassword(t *testing.T) {
	fx := newAuthSessionFixture(t)
	rec := authRequest(t, fx.router, http.MethodPost, "/api/v1/auth/register",
		`{"username":"Wind Only","password":"hunter2pw"}`, nil, "")
	if rec.Code != http.StatusCreated {
		t.Fatalf("register = %d: %s", rec.Code, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), `"email":null`) {
		t.Fatalf("a new account must carry no email: %s", rec.Body.String())
	}
}

// Two accounts created without an email must both persist: NULL emails are
// distinct under the unique index.
func TestRegisterAllowsSeveralAccountsWithoutEmail(t *testing.T) {
	fx := newAuthSessionFixture(t)
	for _, username := range []string{"North Wind", "South Wind"} {
		rec := authRequest(t, fx.router, http.MethodPost, "/api/v1/auth/register",
			`{"username":"`+username+`","password":"hunter2pw"}`, nil, "")
		if rec.Code != http.StatusCreated {
			t.Fatalf("register %s = %d: %s", username, rec.Code, rec.Body.String())
		}
	}
}

func TestRegisterRejectsDuplicateUsername(t *testing.T) {
	fx := newAuthSessionFixture(t)
	first := authRequest(t, fx.router, http.MethodPost, "/api/v1/auth/register",
		`{"username":"Only Wind","password":"hunter2pw"}`, nil, "")
	if first.Code != http.StatusCreated {
		t.Fatalf("first register = %d: %s", first.Code, first.Body.String())
	}
	second := authRequest(t, fx.router, http.MethodPost, "/api/v1/auth/register",
		`{"username":"ONLY WIND","password":"hunter2pw"}`, nil, "")
	if second.Code != http.StatusConflict {
		t.Fatalf("duplicate register = %d, want 409: %s", second.Code, second.Body.String())
	}
	var payload map[string]string
	_ = json.Unmarshal(second.Body.Bytes(), &payload)
	if payload["error"] != "Username is already registered" {
		t.Fatalf("conflict message = %q", payload["error"])
	}
}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `go test ./internal/api/ -run 'TestRegisterNeedsOnlyUsernameAndPassword|TestRegisterAllowsSeveralAccountsWithoutEmail|TestRegisterRejectsDuplicateUsername' -v`

Expected: FAIL — `TestRegisterNeedsOnlyUsernameAndPassword` returns 400 (`Email` is still `binding:"required,email"`), and the conflict message still reads "Email or username is already registered".

- [ ] **Step 3: Drop email from the register request and handler**

Task 1 left `Register` writing `registeredEmail`; this step removes that entirely.

In `internal/api/auth.go`, replace `RegisterRequest` (lines 31-36) with:

```go
// RegisterRequest creates an account from a username and password only.
// Email is deliberately absent: it is an optional profile field set later
// through PATCH /users/me, never collected at signup. `displayName` remains
// as the legacy alias for `username`.
type RegisterRequest struct {
	Username    string `json:"username"`
	DisplayName string `json:"displayName"`
	Password    string `json:"password" binding:"required,min=8"`
}
```

In `Register`, replace the `registeredEmail` line and the `user := storage.User{...}` literal from Task 1 with:

```go
	user := storage.User{
		Username:     username,
		UsernameKey:  usernameKey,
		PasswordHash: string(hashedPassword),
		Rating:       1500,
	}
```

And replace the conflict message (line 217) with:

```go
			respondError(c, http.StatusConflict, "Username is already registered")
```

Leave `normalizeEmail` in place — `Login` and `UpdateMe` still use it.

- [ ] **Step 4: Strip email from every existing register body**

Run this from the repo root; it deletes the leading `"email":"..."` member from each register JSON literal:

```bash
sed -i '' -E 's/\{"email":"[^"]*",/{/g' internal/api/session_auth_test.go
```

Then verify no register body still carries one:

```bash
grep -n '"email"' internal/api/session_auth_test.go
```

Expected: only lines that belong to `PATCH /users/me` bodies or response assertions — no line containing `auth/register` context. Inspect each remaining hit by eye.

- [ ] **Step 5: Update the registerSession helper and its call sites**

In `internal/api/private_room_creation_test.go`, replace the helper (lines 28-40) with:

```go
func registerSession(t *testing.T, server *Server, username string) (*http.Cookie, string) {
	t.Helper()
	rec := authRequest(t, server.Router, http.MethodPost, "/api/v1/auth/register",
		`{"username":"`+username+`","password":"hunter2pw"}`, nil, "")
	if rec.Code != http.StatusCreated {
		t.Fatalf("register %s = %d: %s", username, rec.Code, rec.Body.String())
	}
	var response AuthResponse
	if err := json.Unmarshal(rec.Body.Bytes(), &response); err != nil {
		t.Fatalf("decode auth response: %v", err)
	}
	return sessionCookieFrom(t, rec), response.CSRFToken
}
```

Update the eight call sites to drop the email argument:

- `internal/api/private_room_creation_test.go:44` → `registerSession(t, server, "Rain Host")`
- `internal/api/private_room_creation_test.go:66` → `registerSession(t, server, "Invitee")`
- `internal/api/private_room_creation_test.go:78` → `registerSession(t, server, "Host")`
- `internal/api/private_room_creation_test.go:87` → `registerSession(t, server, "Guest")`
- `internal/api/replay_history_test.go:61` → `registerSession(t, server, "History Wind")`
- `internal/api/replay_history_test.go:99` → `registerSession(t, server, "Page Wind")`
- `internal/api/replay_history_test.go:147` → `registerSession(t, server, "Limit Wind")`

- [ ] **Step 6: Repair the login-by-email test**

`TestLoginAcceptsUsernameOrEmail` in `internal/api/session_auth_test.go` can no longer get an email at registration. Replace the whole function with one that registers, attaches an email through the profile endpoint, and then signs in both ways:

```go
func TestLoginAcceptsUsernameOrEmail(t *testing.T) {
	fx := newAuthSessionFixture(t)
	register := authRequest(t, fx.router, http.MethodPost, "/api/v1/auth/register",
		`{"username":"River Wind","password":"hunter2pw"}`, nil, "")
	if register.Code != http.StatusCreated {
		t.Fatalf("register = %d: %s", register.Code, register.Body.String())
	}
	cookie := sessionCookieFrom(t, register)
	var session AuthResponse
	if err := decodeJSONBody(register.Body.Bytes(), &session); err != nil {
		t.Fatalf("decode registration: %v", err)
	}
	attach := authRequest(t, fx.router, http.MethodPatch, "/api/v1/users/me",
		`{"email":"river@example.com","currentPassword":"hunter2pw"}`, cookie, session.CSRFToken)
	if attach.Code != http.StatusOK {
		t.Fatalf("attach email = %d: %s", attach.Code, attach.Body.String())
	}
	for _, identifier := range []string{"river wind", "RIVER@EXAMPLE.COM"} {
		rec := authRequest(t, fx.router, http.MethodPost, "/api/v1/auth/login",
			`{"identifier":"`+identifier+`","password":"hunter2pw"}`, nil, "")
		if rec.Code != http.StatusOK {
			t.Fatalf("login as %q = %d: %s", identifier, rec.Code, rec.Body.String())
		}
	}
}
```

This passes at this task: Task 1's `emailChange = user.Email == nil || *user.Email != newEmail` already treats "no address yet" as a change, so adding the first email works once the current password is supplied. Task 3 only adds the ability to clear one.

- [ ] **Step 7: Run the whole API suite**

Run: `go test ./internal/api/ 2>&1 | tail -30`

Expected: PASS (`ok github.com/plasma/fh-mahjong/internal/api`).

- [ ] **Step 8: Commit**

```bash
git add internal/api/auth.go internal/api/session_auth_test.go internal/api/private_room_creation_test.go internal/api/replay_history_test.go internal/api/private_tables_test.go
git commit -m "feat(api): register with username and password only"
```

---

### Task 3: Profile email can be set, changed, and cleared

**Files:**
- Modify: `internal/api/auth.go:292-385` (`UpdateProfileRequest`, `UpdateMe`)
- Test: `internal/api/session_auth_test.go`

**Interfaces:**
- Consumes: `storage.User.Email *string`, `storage.User.EmailVerifiedAt *time.Time`.
- Produces: `PATCH /api/v1/users/me` accepts `email` as an absent key (no change), a non-empty string (set/change), or `""` (clear to NULL). Any of those changes requires `currentPassword`.

- [ ] **Step 1: Write the failing profile tests**

Replace `TestProfileEmailChangeRequiresCurrentPassword` in `internal/api/session_auth_test.go` with the following three tests:

```go
func TestProfileEmailAddChangeAndClearRequireCurrentPassword(t *testing.T) {
	fx := newAuthSessionFixture(t)
	registered := authRequest(t, fx.router, http.MethodPost, "/api/v1/auth/register",
		`{"username":"Email Wind","password":"hunter2pw"}`, nil, "")
	cookie := sessionCookieFrom(t, registered)
	var session AuthResponse
	if err := decodeJSONBody(registered.Body.Bytes(), &session); err != nil {
		t.Fatalf("decode registration: %v", err)
	}

	missing := authRequest(t, fx.router, http.MethodPatch, "/api/v1/users/me",
		`{"email":"first@example.com"}`, cookie, session.CSRFToken)
	if missing.Code != http.StatusBadRequest {
		t.Fatalf("adding an email without a password = %d: %s", missing.Code, missing.Body.String())
	}

	added := authRequest(t, fx.router, http.MethodPatch, "/api/v1/users/me",
		`{"email":"first@example.com","currentPassword":"hunter2pw"}`, cookie, session.CSRFToken)
	if added.Code != http.StatusOK || !strings.Contains(added.Body.String(), `"email":"first@example.com"`) {
		t.Fatalf("adding an email = %d: %s", added.Code, added.Body.String())
	}

	changed := authRequest(t, fx.router, http.MethodPatch, "/api/v1/users/me",
		`{"email":"Second@Example.com","currentPassword":"hunter2pw"}`, cookie, session.CSRFToken)
	if changed.Code != http.StatusOK || !strings.Contains(changed.Body.String(), `"email":"second@example.com"`) {
		t.Fatalf("changing an email = %d: %s", changed.Code, changed.Body.String())
	}

	clearedWithoutPassword := authRequest(t, fx.router, http.MethodPatch, "/api/v1/users/me",
		`{"email":""}`, cookie, session.CSRFToken)
	if clearedWithoutPassword.Code != http.StatusBadRequest {
		t.Fatalf("clearing without a password = %d: %s", clearedWithoutPassword.Code, clearedWithoutPassword.Body.String())
	}

	cleared := authRequest(t, fx.router, http.MethodPatch, "/api/v1/users/me",
		`{"email":"","currentPassword":"hunter2pw"}`, cookie, session.CSRFToken)
	if cleared.Code != http.StatusOK || !strings.Contains(cleared.Body.String(), `"email":null`) {
		t.Fatalf("clearing an email = %d: %s", cleared.Code, cleared.Body.String())
	}
}

func TestProfileEmailChangeRejectsWrongCurrentPassword(t *testing.T) {
	fx := newAuthSessionFixture(t)
	registered := authRequest(t, fx.router, http.MethodPost, "/api/v1/auth/register",
		`{"username":"Wrong Wind","password":"hunter2pw"}`, nil, "")
	cookie := sessionCookieFrom(t, registered)
	var session AuthResponse
	if err := decodeJSONBody(registered.Body.Bytes(), &session); err != nil {
		t.Fatalf("decode registration: %v", err)
	}
	rec := authRequest(t, fx.router, http.MethodPatch, "/api/v1/users/me",
		`{"email":"nope@example.com","currentPassword":"not-my-password"}`, cookie, session.CSRFToken)
	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("wrong password = %d, want 401: %s", rec.Code, rec.Body.String())
	}
}

func TestProfileRejectsAnEmailAlreadyOnAnotherAccount(t *testing.T) {
	fx := newAuthSessionFixture(t)
	for _, username := range []string{"Taken Wind", "Other Wind"} {
		rec := authRequest(t, fx.router, http.MethodPost, "/api/v1/auth/register",
			`{"username":"`+username+`","password":"hunter2pw"}`, nil, "")
		if rec.Code != http.StatusCreated {
			t.Fatalf("register %s = %d: %s", username, rec.Code, rec.Body.String())
		}
		var session AuthResponse
		if err := decodeJSONBody(rec.Body.Bytes(), &session); err != nil {
			t.Fatalf("decode registration: %v", err)
		}
		attach := authRequest(t, fx.router, http.MethodPatch, "/api/v1/users/me",
			`{"email":"shared@example.com","currentPassword":"hunter2pw"}`, sessionCookieFrom(t, rec), session.CSRFToken)
		if username == "Taken Wind" && attach.Code != http.StatusOK {
			t.Fatalf("first claim = %d: %s", attach.Code, attach.Body.String())
		}
		if username == "Other Wind" && attach.Code != http.StatusConflict {
			t.Fatalf("second claim = %d, want 409: %s", attach.Code, attach.Body.String())
		}
	}
}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `go test ./internal/api/ -run 'TestProfileEmail|TestProfileRejects' -v`

Expected: FAIL — the handler does not compile against a `*string` email (`newEmail != user.Email` compares `string` to `*string`).

- [ ] **Step 3: Rewrite the email branch of UpdateMe**

In `internal/api/auth.go`, update the request doc comment and struct (lines 292-297):

```go
// UpdateProfileRequest carries an optional username and/or email change. For
// Email the three JSON states are distinct: key absent (or null) means "no
// change", a non-empty string sets or replaces the address, and "" clears it
// back to NULL. `omitempty` on the binding tag is what lets "" through the
// format check.
type UpdateProfileRequest struct {
	Email           *string `json:"email" binding:"omitempty,email"`
	Username        *string `json:"username"`
	DisplayName     *string `json:"displayName"`
	CurrentPassword *string `json:"currentPassword"`
}
```

Replace the email-resolution block Task 1 left behind — the four lines starting `newEmail := ""` — with:

```go
	// newEmail nil while emailChange is true means "clear it".
	var newEmail *string
	emailChange := false
	if req.Email != nil {
		normalized := normalizeEmail(*req.Email)
		switch {
		case normalized == "":
			emailChange = user.Email != nil
		case user.Email == nil || *user.Email != normalized:
			emailChange = true
			newEmail = &normalized
		}
	}
```

Leave the `if emailChange { ... current password ... }` gate exactly as it is: it already covers adds, changes, and clears, because all three now set `emailChange`.

Replace the updates map assembly (the `updates := map[string]any{}` block) with:

```go
	updates := map[string]any{}
	if emailChange {
		if newEmail == nil {
			updates["email"] = nil
		} else {
			updates["email"] = *newEmail
		}
		// A newly set or cleared address is never a verified one.
		updates["email_verified_at"] = nil
	}
	if usernameChange {
		updates["username"] = newUsername
		updates["username_key"] = newUsernameKey
	}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `go test ./internal/api/ -run 'TestProfileEmail|TestProfileRejects|TestLoginAcceptsUsernameOrEmail' -v`

Expected: PASS for all four.

- [ ] **Step 5: Run the whole suite**

Run: `go test ./... 2>&1 | grep -v "no test files"`

Expected: every package `ok`.

- [ ] **Step 6: Commit**

```bash
git add internal/api/auth.go internal/api/session_auth_test.go
git commit -m "feat(api): allow setting, changing, and clearing the profile email"
```

---

### Task 4: internal/mail package

**Files:**
- Create: `internal/mail/mail.go`
- Create: `internal/mail/mail_test.go`

**Interfaces:**
- Consumes: nothing.
- Produces: `mail.Sender` interface with `SendPasswordResetCode(ctx context.Context, to, code string) error`, and `mail.LogSender` implementing it.

- [ ] **Step 1: Write the failing test**

Create `internal/mail/mail_test.go`:

```go
package mail

import (
	"bytes"
	"context"
	"log"
	"os"
	"strings"
	"testing"
)

// The shipped sender does not send: it records the code where an operator can
// read it. Both the recipient and the code must appear, or the flow is
// untestable in the environments this stub exists for.
func TestLogSenderRecordsRecipientAndCode(t *testing.T) {
	var buf bytes.Buffer
	log.SetOutput(&buf)
	t.Cleanup(func() { log.SetOutput(os.Stderr) })

	if err := (LogSender{}).SendPasswordResetCode(context.Background(), "wind@example.com", "123456"); err != nil {
		t.Fatalf("send: %v", err)
	}

	out := buf.String()
	if !strings.Contains(out, "wind@example.com") || !strings.Contains(out, "123456") {
		t.Fatalf("log output = %q", out)
	}
}

// LogSender must satisfy Sender, since that is the seam a real provider slots
// into later.
func TestLogSenderImplementsSender(t *testing.T) {
	var sender Sender = LogSender{}
	if sender == nil {
		t.Fatal("LogSender must satisfy Sender")
	}
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `go test ./internal/mail/ -v`

Expected: FAIL — `internal/mail/mail.go` does not exist, so `Sender` and `LogSender` are undefined.

- [ ] **Step 3: Write the package**

Create `internal/mail/mail.go`:

```go
// Package mail delivers transactional account email.
//
// No real provider is configured for this deployment yet. The shipped Sender
// writes messages to the server log instead of sending them, which keeps the
// password-reset flow exercisable end to end without an outbound dependency.
// Wiring SMTP or a transactional API later is a second implementation of
// Sender and one line in server.go — no call site changes.
package mail

import (
	"context"
	"log"
)

// Sender delivers account email. Implementations must be safe for concurrent
// use: one instance is shared by every request.
type Sender interface {
	SendPasswordResetCode(ctx context.Context, to, code string) error
}

// LogSender writes the reset code to the server log and reports success. It is
// the deliberate stand-in for a real provider, not a fallback: callers cannot
// distinguish it from a working sender, which is exactly what keeps the
// password-reset endpoint's response identical in every case.
type LogSender struct{}

// SendPasswordResetCode records the recipient and code in the server log.
func (LogSender) SendPasswordResetCode(_ context.Context, to, code string) error {
	log.Printf("mail: password reset code for %s: %s", to, code)
	return nil
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `go test ./internal/mail/ -v`

Expected: PASS for both tests.

- [ ] **Step 5: Commit**

```bash
git add internal/mail/
git commit -m "feat(mail): add Sender interface with a log-only implementation"
```

---

### Task 5: String-keyed rate limiter

**Files:**
- Create: `internal/api/ratelimit.go`
- Create: `internal/api/ratelimit_test.go`

**Interfaces:**
- Consumes: nothing.
- Produces: `newKeyedRateLimiter(perMinute, burst float64) *keyedRateLimiter` and `(*keyedRateLimiter).Allow(key string) bool`.

**Note on duplication:** `reviewRateLimiter` in `internal/api/review_ratelimit.go` has the same token-bucket shape but is keyed by user id and has fixed constants, and it is covered by several adversarial-round regression tests. It is deliberately left alone rather than refactored — the risk of disturbing that tested path outweighs sharing forty lines. If a third limiter ever appears, merge all three then.

- [ ] **Step 1: Write the failing test**

Create `internal/api/ratelimit_test.go`:

```go
package api

import (
	"fmt"
	"testing"
)

func TestKeyedRateLimiterSpendsBurstThenRefuses(t *testing.T) {
	limiter := newKeyedRateLimiter(60, 3)
	for i := 0; i < 3; i++ {
		if !limiter.Allow("ip:203.0.113.7") {
			t.Fatalf("request %d within burst was refused", i+1)
		}
	}
	if limiter.Allow("ip:203.0.113.7") {
		t.Fatal("request beyond the burst must be refused")
	}
}

func TestKeyedRateLimiterIsolatesKeys(t *testing.T) {
	limiter := newKeyedRateLimiter(60, 1)
	if !limiter.Allow("user:1") {
		t.Fatal("first key refused")
	}
	if !limiter.Allow("user:2") {
		t.Fatal("a different key must have its own bucket")
	}
	if limiter.Allow("user:1") {
		t.Fatal("the exhausted key must stay refused")
	}
}

// The map is keyed by client IP among other things, so a long-lived process
// seeing many distinct callers must not grow without bound.
func TestKeyedRateLimiterPrunesIdleBuckets(t *testing.T) {
	limiter := newKeyedRateLimiter(60, 1)
	for i := 0; i < maxTrackedRateKeys+10; i++ {
		limiter.Allow(fmt.Sprintf("ip:198.51.100.%d", i))
	}
	limiter.mu.Lock()
	size := len(limiter.buckets)
	limiter.mu.Unlock()
	if size > maxTrackedRateKeys {
		t.Fatalf("tracked keys = %d, want at most %d", size, maxTrackedRateKeys)
	}
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `go test ./internal/api/ -run TestKeyedRateLimiter -v`

Expected: FAIL — `newKeyedRateLimiter` and `maxTrackedRateKeys` are undefined.

- [ ] **Step 3: Write the limiter**

Create `internal/api/ratelimit.go`:

```go
package api

import (
	"sync"
	"time"
)

// maxTrackedRateKeys bounds the bucket map. Keys include client IPs, so a
// long-running process can otherwise accumulate one entry per caller
// indefinitely. When the map crosses this size, buckets that have refilled to
// full (i.e. their owner has gone quiet) are dropped — dropping a full bucket
// is free, because recreating it yields the same full bucket.
const maxTrackedRateKeys = 4096

type rateBucket struct {
	tokens     float64
	lastRefill time.Time
}

// keyedRateLimiter is an in-memory token bucket keyed by an arbitrary string,
// so one limiter can cover several dimensions at once (per-IP and per-user,
// say) by namespacing its keys.
//
// Like reviewRateLimiter, which predates it, this is intentionally not a
// general-purpose package: no persistence and no cross-process coordination,
// matching this repo's single-process deployment. A restart resets every
// bucket, which is fine — the goal is smoothing request storms, not enforcing
// a hard security boundary.
type keyedRateLimiter struct {
	mu        sync.Mutex
	perMinute float64
	burst     float64
	buckets   map[string]*rateBucket
}

func newKeyedRateLimiter(perMinute, burst float64) *keyedRateLimiter {
	return &keyedRateLimiter{
		perMinute: perMinute,
		burst:     burst,
		buckets:   make(map[string]*rateBucket),
	}
}

// Allow reports whether key may act once more right now, consuming a token if
// so. Safe for concurrent use.
func (l *keyedRateLimiter) Allow(key string) bool {
	l.mu.Lock()
	defer l.mu.Unlock()

	now := time.Now()
	bucket, ok := l.buckets[key]
	if !ok {
		if len(l.buckets) >= maxTrackedRateKeys {
			l.pruneFullLocked(now)
		}
		bucket = &rateBucket{tokens: l.burst, lastRefill: now}
		l.buckets[key] = bucket
	}

	if elapsed := now.Sub(bucket.lastRefill).Seconds(); elapsed > 0 {
		bucket.tokens += elapsed * (l.perMinute / 60.0)
		if bucket.tokens > l.burst {
			bucket.tokens = l.burst
		}
		bucket.lastRefill = now
	}

	if bucket.tokens < 1 {
		return false
	}
	bucket.tokens -= 1
	return true
}

// pruneFullLocked drops every bucket that has refilled to capacity. The caller
// must hold l.mu.
func (l *keyedRateLimiter) pruneFullLocked(now time.Time) {
	for key, bucket := range l.buckets {
		tokens := bucket.tokens + now.Sub(bucket.lastRefill).Seconds()*(l.perMinute/60.0)
		if tokens >= l.burst {
			delete(l.buckets, key)
		}
	}
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `go test ./internal/api/ -run TestKeyedRateLimiter -v`

Expected: PASS for all three.

- [ ] **Step 5: Commit**

```bash
git add internal/api/ratelimit.go internal/api/ratelimit_test.go
git commit -m "feat(api): add a string-keyed token bucket rate limiter"
```

---

### Task 6: Password-reset request endpoint

**Files:**
- Create: `internal/api/password_reset.go`
- Create: `internal/api/password_reset_test.go`
- Modify: `internal/api/auth.go:27-29` (`AuthHandler`), `internal/api/auth.go:228-269` (`Login`)
- Modify: `internal/api/server.go:164`, `:171`

**Interfaces:**
- Consumes: `mail.Sender` (Task 4), `newKeyedRateLimiter` (Task 5), `storage.PasswordResetCode` (Task 1).
- Produces: `lookupUserByIdentifier(db *gorm.DB, identifier string) (storage.User, bool)`, `generatePasswordResetCode() (string, error)`, `(*AuthHandler).RequestPasswordReset(c *gin.Context)`, the constants `passwordResetCodeTTL` and `passwordResetMaxAttempts`, and the `AuthHandler` fields `Mail mail.Sender` and `ResetLimiter *keyedRateLimiter`.

- [ ] **Step 1: Write the failing tests**

Create `internal/api/password_reset_test.go`:

```go
package api

import (
	"context"
	"net/http"
	"sync"
	"testing"

	"github.com/plasma/fh-mahjong/internal/storage"
)

// captureSender records what would have been mailed, so a test can read the
// code the user would have received.
type captureSender struct {
	mu   sync.Mutex
	sent []sentMessage
}

type sentMessage struct {
	To   string
	Code string
}

func (s *captureSender) SendPasswordResetCode(_ context.Context, to, code string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.sent = append(s.sent, sentMessage{To: to, Code: code})
	return nil
}

func (s *captureSender) messages() []sentMessage {
	s.mu.Lock()
	defer s.mu.Unlock()
	return append([]sentMessage(nil), s.sent...)
}

// resetFixture is an auth fixture whose mail sender is captured.
// authSessionFixture is embedded by value — newAuthSessionFixture returns a
// value, not a pointer.
type resetFixture struct {
	authSessionFixture
	mail *captureSender
}

// registerWithEmail creates an account and attaches an address to it,
// returning the session cookie and CSRF token.
func registerWithEmail(t *testing.T, fx *resetFixture, username, email string) (*http.Cookie, string) {
	t.Helper()
	rec := authRequest(t, fx.router, http.MethodPost, "/api/v1/auth/register",
		`{"username":"`+username+`","password":"hunter2pw"}`, nil, "")
	if rec.Code != http.StatusCreated {
		t.Fatalf("register %s = %d: %s", username, rec.Code, rec.Body.String())
	}
	var session AuthResponse
	if err := decodeJSONBody(rec.Body.Bytes(), &session); err != nil {
		t.Fatalf("decode registration: %v", err)
	}
	cookie := sessionCookieFrom(t, rec)
	attach := authRequest(t, fx.router, http.MethodPatch, "/api/v1/users/me",
		`{"email":"`+email+`","currentPassword":"hunter2pw"}`, cookie, session.CSRFToken)
	if attach.Code != http.StatusOK {
		t.Fatalf("attach email = %d: %s", attach.Code, attach.Body.String())
	}
	return cookie, session.CSRFToken
}

func requestReset(t *testing.T, fx *resetFixture, identifier string) {
	t.Helper()
	rec := authRequest(t, fx.router, http.MethodPost, "/api/v1/auth/password-reset/request",
		`{"identifier":"`+identifier+`"}`, nil, "")
	if rec.Code != http.StatusNoContent {
		t.Fatalf("reset request for %q = %d, want 204: %s", identifier, rec.Code, rec.Body.String())
	}
}

// Nothing about the response may reveal whether an account exists or has an
// address on file.
func TestPasswordResetRequestIsAlways204AndSilentForUnknownAccounts(t *testing.T) {
	fx := newPasswordResetFixture(t)
	registerWithEmail(t, fx, "Known Wind", "known@example.com")
	// A second account with no address at all.
	rec := authRequest(t, fx.router, http.MethodPost, "/api/v1/auth/register",
		`{"username":"Bare Wind","password":"hunter2pw"}`, nil, "")
	if rec.Code != http.StatusCreated {
		t.Fatalf("register bare account = %d: %s", rec.Code, rec.Body.String())
	}

	for _, identifier := range []string{"nobody-at-all", "nobody@example.com", "Bare Wind", ""} {
		requestReset(t, fx, identifier)
	}
	if got := fx.mail.messages(); len(got) != 0 {
		t.Fatalf("no code should have been sent, got %#v", got)
	}
	var codes int64
	if err := fx.db.Model(&storage.PasswordResetCode{}).Count(&codes).Error; err != nil {
		t.Fatalf("count codes: %v", err)
	}
	if codes != 0 {
		t.Fatalf("stored codes = %d, want 0", codes)
	}
}

func TestPasswordResetRequestIssuesOneSixDigitCode(t *testing.T) {
	fx := newPasswordResetFixture(t)
	registerWithEmail(t, fx, "Code Wind", "code@example.com")

	requestReset(t, fx, "Code Wind")

	sent := fx.mail.messages()
	if len(sent) != 1 {
		t.Fatalf("sent = %#v, want exactly one message", sent)
	}
	if sent[0].To != "code@example.com" {
		t.Fatalf("recipient = %q", sent[0].To)
	}
	if len(sent[0].Code) != 6 {
		t.Fatalf("code = %q, want 6 digits", sent[0].Code)
	}
	for _, r := range sent[0].Code {
		if r < '0' || r > '9' {
			t.Fatalf("code %q must be all digits", sent[0].Code)
		}
	}
	var stored storage.PasswordResetCode
	if err := fx.db.First(&stored).Error; err != nil {
		t.Fatalf("load stored code: %v", err)
	}
	if stored.CodeHash == sent[0].Code {
		t.Fatal("the plaintext code must never be stored")
	}
}

// Requesting again invalidates the previous code, so only the newest one works.
func TestPasswordResetRequestSupersedesTheEarlierCode(t *testing.T) {
	fx := newPasswordResetFixture(t)
	registerWithEmail(t, fx, "Fresh Wind", "fresh@example.com")

	requestReset(t, fx, "fresh@example.com")
	requestReset(t, fx, "fresh@example.com")

	var live int64
	if err := fx.db.Model(&storage.PasswordResetCode{}).Where("consumed_at IS NULL").Count(&live).Error; err != nil {
		t.Fatalf("count live codes: %v", err)
	}
	if live != 1 {
		t.Fatalf("live codes = %d, want 1", live)
	}
}

// A caller hammering the endpoint is throttled, and still sees a plain 204.
func TestPasswordResetRequestThrottlesWithoutChangingTheResponse(t *testing.T) {
	fx := newPasswordResetFixture(t)
	registerWithEmail(t, fx, "Storm Wind", "storm@example.com")

	for i := 0; i < 20; i++ {
		requestReset(t, fx, "Storm Wind")
	}
	// Every one of the 20 answered 204 (requestReset asserts that). Only the
	// burst may actually have been sent.
	got := len(fx.mail.messages())
	if got == 0 {
		t.Fatal("the first request should have sent a code")
	}
	if got > int(passwordResetRateBurst) {
		t.Fatalf("sent %d codes for 20 requests, want at most the burst of %d", got, int(passwordResetRateBurst))
	}
}
```

- [ ] **Step 2: Extend the shared fixture and add the reset constructor**

`authSessionFixture` (`internal/api/session_auth_test.go:20-23`) exposes only `router` and `db`, and `newAuthSessionFixture` returns it by value. Add a handler reference, wire the limiter, and register the two reset routes. Replace lines 20-23 with:

```go
type authSessionFixture struct {
	router  *gin.Engine
	db      *gorm.DB
	handler *AuthHandler
}
```

In `newAuthSessionFixture` (line 42), replace the handler construction and add the two routes:

```go
	h := &AuthHandler{
		DB:           db,
		Mail:         mail.LogSender{},
		ResetLimiter: newKeyedRateLimiter(passwordResetRatePerMinute, passwordResetRateBurst),
	}
```

Add these two registrations after the `/api/v1/auth/login` line:

```go
	r.POST("/api/v1/auth/password-reset/request", h.RequestPasswordReset)
	r.POST("/api/v1/auth/password-reset/confirm", h.ConfirmPasswordReset)
```

And return the handler (line 49):

```go
	return authSessionFixture{router: r, db: db, handler: h}
```

Add `"github.com/plasma/fh-mahjong/internal/mail"` to that file's imports.

Then add the reset fixture to `internal/api/password_reset_test.go`:

```go
func newPasswordResetFixture(t *testing.T) *resetFixture {
	t.Helper()
	base := newAuthSessionFixture(t)
	sender := &captureSender{}
	base.handler.Mail = sender
	return &resetFixture{authSessionFixture: base, mail: sender}
}
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `go test ./internal/api/ -run TestPasswordResetRequest -v`

Expected: FAIL — `RequestPasswordReset`, `ConfirmPasswordReset`, `passwordResetRatePerMinute`, and the `AuthHandler.Mail` field are all undefined.

- [ ] **Step 4: Extend AuthHandler and share the identifier lookup**

In `internal/api/auth.go`, add the import `"github.com/plasma/fh-mahjong/internal/mail"` and replace the `AuthHandler` struct (lines 27-29) with:

```go
// AuthHandler owns account creation, login, and password recovery. Mail and
// ResetLimiter are only used by the password-reset endpoints.
type AuthHandler struct {
	DB           *gorm.DB
	Mail         mail.Sender
	ResetLimiter *keyedRateLimiter
}
```

Then replace the lookup block inside `Login` (lines 244-256) with a call to the shared helper, keeping the timing-equalizing dummy compare:

```go
	user, found := lookupUserByIdentifier(h.DB, identifier)
	if !found {
		bcrypt.CompareHashAndPassword(dummyPasswordHash, []byte(req.Password))
		respondError(c, http.StatusUnauthorized, "Invalid username/email or password")
		return
	}
```

- [ ] **Step 5: Write the request handler**

Create `internal/api/password_reset.go`:

```go
package api

import (
	"context"
	"crypto/rand"
	"fmt"
	"log"
	"math/big"
	"net/http"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/plasma/fh-mahjong/internal/storage"
	"golang.org/x/crypto/bcrypt"
	"gorm.io/gorm"
)

const (
	// A code is short-lived on purpose: it is the only thing standing between
	// an inbox and an account, and the short window also keeps a leaked
	// database of bcrypt-hashed codes worthless before it could be cracked.
	passwordResetCodeTTL     = 15 * time.Minute
	passwordResetMaxAttempts = 5

	// Generous for a person who mistypes an address or waits for a slow
	// inbox, tight enough that scripted probing gets nothing useful.
	passwordResetRatePerMinute = 3.0
	passwordResetRateBurst     = 5.0
)

// lookupUserByIdentifier resolves a username-or-email login identifier. Login
// and password reset share it so a given string always means the same account
// in both places.
func lookupUserByIdentifier(db *gorm.DB, identifier string) (storage.User, bool) {
	identifier = strings.TrimSpace(identifier)
	if db == nil || identifier == "" {
		return storage.User{}, false
	}
	var user storage.User
	var err error
	if strings.Contains(identifier, "@") {
		err = db.Where("email = ?", normalizeEmail(identifier)).First(&user).Error
	} else {
		_, key := storage.NormalizeUsername(identifier)
		err = db.Where("username_key = ?", key).First(&user).Error
	}
	if err != nil {
		return storage.User{}, false
	}
	return user, true
}

// generatePasswordResetCode returns a uniformly random 6-digit code, zero
// padded so every code is the same length.
func generatePasswordResetCode() (string, error) {
	n, err := rand.Int(rand.Reader, big.NewInt(1000000))
	if err != nil {
		return "", err
	}
	return fmt.Sprintf("%06d", n.Int64()), nil
}

type passwordResetRequestBody struct {
	Identifier string `json:"identifier"`
}

// RequestPasswordReset issues a reset code to the address on file.
//
// It ALWAYS answers 204 with an empty body — for a malformed request, an
// unknown identifier, a known account with no address, a throttled caller, and
// a successful send alike. Any difference would turn this endpoint into an
// account-existence oracle. Response timing is not equalized (only a real
// account reaches the bcrypt hash); the per-IP limit bounds how fast that can
// be probed, and registration's 409 already discloses whether a username is
// taken.
func (h *AuthHandler) RequestPasswordReset(c *gin.Context) {
	var req passwordResetRequestBody
	// A malformed body simply yields an empty identifier, which resolves to
	// no account — the same silent 204 as every other miss.
	_ = c.ShouldBindJSON(&req)
	h.issuePasswordResetCode(c.Request.Context(), c.ClientIP(), req.Identifier)
	c.Header("Cache-Control", "no-store")
	c.Status(http.StatusNoContent)
}

// issuePasswordResetCode does the work behind RequestPasswordReset. Every
// failure path is logged and swallowed: the caller must not learn which one
// was taken.
func (h *AuthHandler) issuePasswordResetCode(ctx context.Context, clientIP, identifier string) {
	if h.DB == nil || h.Mail == nil || h.ResetLimiter == nil {
		return
	}
	// The per-IP bucket is what covers identifiers that resolve to nothing —
	// there is no user id to key on for those.
	if !h.ResetLimiter.Allow("ip:" + clientIP) {
		return
	}
	user, found := lookupUserByIdentifier(h.DB, identifier)
	if !found || user.Email == nil {
		return
	}
	if !h.ResetLimiter.Allow(fmt.Sprintf("user:%d", user.ID)) {
		return
	}

	code, err := generatePasswordResetCode()
	if err != nil {
		log.Printf("password reset: generating code: %v", err)
		return
	}
	hashed, err := bcrypt.GenerateFromPassword([]byte(code), bcrypt.DefaultCost)
	if err != nil {
		log.Printf("password reset: hashing code: %v", err)
		return
	}

	now := time.Now()
	if err := h.DB.Transaction(func(tx *gorm.DB) error {
		// Only the newest code may work, so retire any outstanding ones.
		if err := tx.Model(&storage.PasswordResetCode{}).
			Where("user_id = ? AND consumed_at IS NULL", user.ID).
			Update("consumed_at", now).Error; err != nil {
			return err
		}
		return tx.Create(&storage.PasswordResetCode{
			UserID:    user.ID,
			CodeHash:  string(hashed),
			ExpiresAt: now.Add(passwordResetCodeTTL),
		}).Error
	}); err != nil {
		log.Printf("password reset: storing code: %v", err)
		return
	}

	if err := h.Mail.SendPasswordResetCode(ctx, *user.Email, code); err != nil {
		log.Printf("password reset: sending code: %v", err)
	}
}
```

- [ ] **Step 6: Add a temporary confirm stub so the package compiles**

The fixture registers both routes. Add this to the bottom of `internal/api/password_reset.go`; Task 7 replaces the body:

```go
// ConfirmPasswordReset is implemented in the next task.
func (h *AuthHandler) ConfirmPasswordReset(c *gin.Context) {
	respondError(c, http.StatusNotImplemented, "Not implemented")
}
```

- [ ] **Step 7: Wire the handler and routes in server.go**

In `internal/api/server.go`, replace line 164 with:

```go
	authHandler := &AuthHandler{
		DB:           s.DB,
		Mail:         mail.LogSender{},
		ResetLimiter: newKeyedRateLimiter(passwordResetRatePerMinute, passwordResetRateBurst),
	}
```

Add the import `"github.com/plasma/fh-mahjong/internal/mail"`.

Directly after the `v1.POST("/auth/login", authHandler.Login)` line, add:

```go
		// Password recovery. Public by design (a locked-out user has no
		// session) and deliberately NOT linked from the frontend yet: the
		// configured mail sender only writes codes to the server log.
		v1.POST("/auth/password-reset/request", authHandler.RequestPasswordReset)
		v1.POST("/auth/password-reset/confirm", authHandler.ConfirmPasswordReset)
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `go test ./internal/api/ -run TestPasswordResetRequest -v`

Expected: PASS for all four.

- [ ] **Step 9: Run the whole suite**

Run: `go test ./... 2>&1 | grep -v "no test files"`

Expected: every package `ok`.

- [ ] **Step 10: Commit**

```bash
git add internal/api/password_reset.go internal/api/password_reset_test.go internal/api/auth.go internal/api/server.go internal/api/session_auth_test.go
git commit -m "feat(api): issue password reset codes to the address on file"
```

---

### Task 7: Password-reset confirm endpoint

**Files:**
- Modify: `internal/api/password_reset.go` (replace the `ConfirmPasswordReset` stub)
- Modify: `internal/api/password_reset_test.go`
- Modify: `internal/api/AGENTS.md:12`, `:30`

**Interfaces:**
- Consumes: everything from Task 6.
- Produces: `POST /api/v1/auth/password-reset/confirm` accepting `{identifier, code, newPassword}` → 204, or 400 with the single message `Invalid or expired reset code`.

- [ ] **Step 1: Write the failing tests**

Append to `internal/api/password_reset_test.go`:

```go
func confirmReset(t *testing.T, fx *resetFixture, identifier, code, newPassword string) *httptest.ResponseRecorder {
	t.Helper()
	return authRequest(t, fx.router, http.MethodPost, "/api/v1/auth/password-reset/confirm",
		`{"identifier":"`+identifier+`","code":"`+code+`","newPassword":"`+newPassword+`"}`, nil, "")
}

func TestPasswordResetConfirmChangesPasswordAndKillsEverySession(t *testing.T) {
	fx := newPasswordResetFixture(t)
	cookie, _ := registerWithEmail(t, fx, "Reset Wind", "reset@example.com")
	requestReset(t, fx, "Reset Wind")
	code := fx.mail.messages()[0].Code

	rec := confirmReset(t, fx, "Reset Wind", code, "brand-new-pw")
	if rec.Code != http.StatusNoContent {
		t.Fatalf("confirm = %d, want 204: %s", rec.Code, rec.Body.String())
	}

	// Every device is logged out.
	if got := authRequest(t, fx.router, http.MethodGet, "/api/v1/auth/session", "", cookie, ""); got.Code != http.StatusUnauthorized {
		t.Fatalf("old session after reset = %d, want 401", got.Code)
	}
	var sessions int64
	if err := fx.db.Model(&storage.UserSession{}).Count(&sessions).Error; err != nil {
		t.Fatalf("count sessions: %v", err)
	}
	if sessions != 0 {
		t.Fatalf("sessions after reset = %d, want 0", sessions)
	}

	// The old password is dead and the new one works.
	old := authRequest(t, fx.router, http.MethodPost, "/api/v1/auth/login",
		`{"identifier":"Reset Wind","password":"hunter2pw"}`, nil, "")
	if old.Code != http.StatusUnauthorized {
		t.Fatalf("old password login = %d, want 401", old.Code)
	}
	fresh := authRequest(t, fx.router, http.MethodPost, "/api/v1/auth/login",
		`{"identifier":"Reset Wind","password":"brand-new-pw"}`, nil, "")
	if fresh.Code != http.StatusOK {
		t.Fatalf("new password login = %d: %s", fresh.Code, fresh.Body.String())
	}
}

// A code works exactly once.
func TestPasswordResetConfirmRefusesAConsumedCode(t *testing.T) {
	fx := newPasswordResetFixture(t)
	registerWithEmail(t, fx, "Once Wind", "once@example.com")
	requestReset(t, fx, "Once Wind")
	code := fx.mail.messages()[0].Code

	if rec := confirmReset(t, fx, "Once Wind", code, "brand-new-pw"); rec.Code != http.StatusNoContent {
		t.Fatalf("first confirm = %d: %s", rec.Code, rec.Body.String())
	}
	replay := confirmReset(t, fx, "Once Wind", code, "another-new-pw")
	if replay.Code != http.StatusBadRequest {
		t.Fatalf("replayed confirm = %d, want 400: %s", replay.Code, replay.Body.String())
	}
}

func TestPasswordResetConfirmExhaustsAttempts(t *testing.T) {
	fx := newPasswordResetFixture(t)
	registerWithEmail(t, fx, "Guess Wind", "guess@example.com")
	requestReset(t, fx, "Guess Wind")
	code := fx.mail.messages()[0].Code

	wrong := "000000"
	if wrong == code {
		wrong = "111111"
	}
	for i := 0; i < passwordResetMaxAttempts; i++ {
		if rec := confirmReset(t, fx, "Guess Wind", wrong, "brand-new-pw"); rec.Code != http.StatusBadRequest {
			t.Fatalf("wrong attempt %d = %d, want 400", i+1, rec.Code)
		}
	}
	// The real code is dead now that the attempt budget is spent.
	if rec := confirmReset(t, fx, "Guess Wind", code, "brand-new-pw"); rec.Code != http.StatusBadRequest {
		t.Fatalf("confirm after exhausted attempts = %d, want 400", rec.Code)
	}
}

func TestPasswordResetConfirmRefusesAnExpiredCode(t *testing.T) {
	fx := newPasswordResetFixture(t)
	registerWithEmail(t, fx, "Late Wind", "late@example.com")
	requestReset(t, fx, "Late Wind")
	code := fx.mail.messages()[0].Code

	if err := fx.db.Model(&storage.PasswordResetCode{}).
		Where("consumed_at IS NULL").
		Update("expires_at", time.Now().Add(-time.Minute)).Error; err != nil {
		t.Fatalf("backdate code: %v", err)
	}
	if rec := confirmReset(t, fx, "Late Wind", code, "brand-new-pw"); rec.Code != http.StatusBadRequest {
		t.Fatalf("expired confirm = %d, want 400", rec.Code)
	}
}

// Every rejection reads the same, so the endpoint discloses nothing about
// which accounts exist or have a code outstanding.
func TestPasswordResetConfirmFailuresShareOneMessage(t *testing.T) {
	fx := newPasswordResetFixture(t)
	registerWithEmail(t, fx, "Same Wind", "same@example.com")
	requestReset(t, fx, "Same Wind")

	var messages []string
	for _, args := range [][2]string{
		{"nobody-at-all", "123456"},
		{"Same Wind", "999999"},
	} {
		rec := confirmReset(t, fx, args[0], args[1], "brand-new-pw")
		if rec.Code != http.StatusBadRequest {
			t.Fatalf("confirm %v = %d, want 400", args, rec.Code)
		}
		var payload map[string]string
		_ = json.Unmarshal(rec.Body.Bytes(), &payload)
		messages = append(messages, payload["error"])
	}
	if messages[0] != "Invalid or expired reset code" || messages[1] != messages[0] {
		t.Fatalf("messages = %#v", messages)
	}
}
```

Add `"encoding/json"`, `"net/http/httptest"`, and `"time"` to that file's imports.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `go test ./internal/api/ -run TestPasswordResetConfirm -v`

Expected: FAIL — the stub returns 501 for every case.

- [ ] **Step 3: Implement the confirm handler**

In `internal/api/password_reset.go`, replace the stub with:

```go
// passwordResetGenericError is the single message every confirm failure gets:
// unknown identifier, no outstanding code, expired, already consumed, attempts
// spent, and simply wrong all read identically.
const passwordResetGenericError = "Invalid or expired reset code"

type passwordResetConfirmBody struct {
	Identifier  string `json:"identifier"`
	Code        string `json:"code"`
	NewPassword string `json:"newPassword" binding:"required,min=8"`
}

// ConfirmPasswordReset redeems a code and sets a new password.
//
// A rejected new password (too short) reports the binding error, since
// password-policy feedback says nothing about the account. Every other failure
// returns passwordResetGenericError. Success logs the account out everywhere:
// whoever triggered the reset may not be who was signed in.
func (h *AuthHandler) ConfirmPasswordReset(c *gin.Context) {
	var req passwordResetConfirmBody
	if err := c.ShouldBindJSON(&req); err != nil {
		respondError(c, http.StatusBadRequest, err.Error())
		return
	}
	if h.DB == nil {
		respondError(c, http.StatusServiceUnavailable, "Database is temporarily disabled.")
		return
	}

	user, found := lookupUserByIdentifier(h.DB, req.Identifier)
	if !found {
		respondError(c, http.StatusBadRequest, passwordResetGenericError)
		return
	}

	var record storage.PasswordResetCode
	if err := h.DB.Where("user_id = ? AND consumed_at IS NULL", user.ID).
		Order("id DESC").First(&record).Error; err != nil {
		respondError(c, http.StatusBadRequest, passwordResetGenericError)
		return
	}
	if time.Now().After(record.ExpiresAt) || record.Attempts >= passwordResetMaxAttempts {
		respondError(c, http.StatusBadRequest, passwordResetGenericError)
		return
	}
	if bcrypt.CompareHashAndPassword([]byte(record.CodeHash), []byte(req.Code)) != nil {
		// Spend one attempt. A failure to record it must not hand the caller
		// an unlimited guessing budget, so it is logged and still rejected.
		if err := h.DB.Model(&storage.PasswordResetCode{}).
			Where("id = ?", record.ID).
			Update("attempts", record.Attempts+1).Error; err != nil {
			log.Printf("password reset: recording attempt: %v", err)
		}
		respondError(c, http.StatusBadRequest, passwordResetGenericError)
		return
	}

	hashed, err := bcrypt.GenerateFromPassword([]byte(req.NewPassword), bcrypt.DefaultCost)
	if err != nil {
		respondError(c, http.StatusInternalServerError, "Failed to hash password")
		return
	}
	now := time.Now()
	if err := h.DB.Transaction(func(tx *gorm.DB) error {
		if err := tx.Model(&storage.User{}).Where("id = ?", user.ID).
			Update("password_hash", string(hashed)).Error; err != nil {
			return err
		}
		if err := tx.Model(&storage.PasswordResetCode{}).Where("id = ?", record.ID).
			Update("consumed_at", now).Error; err != nil {
			return err
		}
		// Sign out every device: a reset is exactly the moment an existing
		// session may belong to whoever the owner is locking out.
		return tx.Where("user_id = ?", user.ID).Delete(&storage.UserSession{}).Error
	}); err != nil {
		respondError(c, http.StatusInternalServerError, "Failed to reset password")
		return
	}

	c.Header("Cache-Control", "no-store")
	c.Status(http.StatusNoContent)
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `go test ./internal/api/ -run TestPasswordReset -v`

Expected: PASS for all nine reset tests.

- [ ] **Step 5: Run the whole suite and vet**

Run: `go vet ./... && go test ./... 2>&1 | grep -v "no test files"`

Expected: no vet output, every package `ok`.

- [ ] **Step 6: Update the API AGENTS.md**

In `internal/api/AGENTS.md`, replace line 12 with:

```markdown
  - Public: `/api/v1/auth/register` (username + password only — no email is collected at signup), `/api/v1/auth/login`
  - Public password recovery, **not linked from the frontend**: `POST /api/v1/auth/password-reset/request` (always 204, never discloses whether an account or address exists) and `POST /api/v1/auth/password-reset/confirm` (one generic 400 for every failure; success clears every session for that user). The configured `mail.Sender` is `LogSender`, which writes codes to the server log rather than sending them — swap in a real provider before exposing any UI
```

Replace line 30 with:

```markdown
- **auth.go** — Username + password auth backed by opaque revocable sessions. Registration takes a username and password only; email is an optional profile field (`PATCH /users/me` accepts a string to set it or `""` to clear it, and either way requires the current password). Login/register/session return `{user, csrfToken}` and set an HttpOnly cookie; no credential is serialized in JSON or stored by frontend JavaScript
- **password_reset.go** — Code-based recovery: `lookupUserByIdentifier` (shared with login), 6-digit codes bcrypt-hashed at rest with a 15-minute TTL and a 5-attempt cap, superseding any outstanding code. Bcrypt rather than a fast digest because a 6-digit code holds only ~20 bits of entropy
- **ratelimit.go** — `keyedRateLimiter`, a string-keyed token bucket used by password reset for per-IP and per-user limits. `review_ratelimit.go` predates it and stays keyed by user id
```

- [ ] **Step 7: Commit**

```bash
git add internal/api/password_reset.go internal/api/password_reset_test.go internal/api/AGENTS.md
git commit -m "feat(api): redeem password reset codes and revoke all sessions"
```

---

### Task 8: Register form drops the email field

**Files:**
- Modify: `web/src/features/auth/authClient.ts:3-8`
- Modify: `web/src/features/auth/AuthTicket.tsx`
- Test: `web/src/features/auth/authClient.test.ts`

**Interfaces:**
- Consumes: the register endpoint from Task 2.
- Produces: `AuthUser.email: string | null` and `authRequestBody(mode: AuthMode, fields: AuthFields)`.

- [ ] **Step 1: Write the failing test**

Append to `web/src/features/auth/authClient.test.ts` (add `authRequestBody` to the existing import from `./authClient`):

```ts
describe('authRequestBody', () => {
  const fields = { identifier: 'river wind', username: 'River Wind', password: 'hunter2pw' }

  it('registers with a username and password only', () => {
    const body = authRequestBody('register', fields)
    expect(body).toEqual({ username: 'River Wind', password: 'hunter2pw' })
    expect('email' in body).toBe(false)
  })

  it('signs in with the shared username-or-email identifier', () => {
    expect(authRequestBody('login', fields)).toEqual({ identifier: 'river wind', password: 'hunter2pw' })
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd web && npx vitest run src/features/auth/authClient.test.ts`

Expected: FAIL — `authRequestBody` is not exported from `./authClient`.

- [ ] **Step 3: Update authClient.ts**

In `web/src/features/auth/authClient.ts`, replace the `AuthUser` type and add the body builder below it:

```ts
export type AuthUser = {
  id: number
  // null when the account has no address on file. Email is optional and set
  // in the profile, never at registration.
  email: string | null
  username: string
  rating: number
}

export type AuthMode = 'login' | 'register'

export type AuthFields = {
  identifier: string
  username: string
  password: string
}

// Registration deliberately sends no email key at all: accounts are created
// from a username and password, and an address is added later in the profile.
export function authRequestBody(mode: AuthMode, fields: AuthFields) {
  return mode === 'register'
    ? { username: fields.username, password: fields.password }
    : { identifier: fields.identifier, password: fields.password }
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd web && npx vitest run src/features/auth/authClient.test.ts`

Expected: PASS.

- [ ] **Step 5: Strip email out of AuthTicket**

In `web/src/features/auth/AuthTicket.tsx`:

Replace the import of `authClient` so it also brings in the helper and the mode type:

```tsx
import { authenticatedFetch, authRequestBody, type AuthMode, type AuthPayload } from './authClient'
```

Delete the local `type Mode = 'login' | 'register'` declaration and change the state to use `AuthMode`:

```tsx
  const [mode, setMode] = useState<AuthMode>('login')
```

Delete the `email` state line (`const [email, setEmail] = useState('')`).

Replace the body of the fetch call:

```tsx
      const isRegister = mode === 'register'
      const response = await authenticatedFetch(isRegister ? '/api/v1/auth/register' : '/api/v1/auth/login', 'POST', undefined, {
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(authRequestBody(mode, { identifier, username, password })),
      })
```

Replace the register branch of the form so only the username field and its hint remain:

```tsx
        <>
          <Field label={t('auth.username')} value={username} onChange={event => setUsername(event.target.value)} autoComplete="username" />
          <Note>{t('auth.usernameHint')}</Note>
        </>
```

Replace the submit button's `disabled` expression:

```tsx
        <Button type="submit" variant="primary" disabled={submitting || !password || (mode === 'login' ? !identifier : !username)}>
```

- [ ] **Step 6: Typecheck and run the web suite**

Run: `cd web && npx tsc --noEmit && npm test`

Expected: no type errors; all vitest files pass.

- [ ] **Step 7: Commit**

```bash
git add web/src/features/auth/authClient.ts web/src/features/auth/authClient.test.ts web/src/features/auth/AuthTicket.tsx
git commit -m "feat(web): register with a username and password only"
```

---

### Task 9: Account page treats email as optional

**Files:**
- Modify: `web/src/features/auth/Account.tsx`
- Modify: `web/src/i18n/locales/en.ts:36`, `:37`, and the `account.*` block
- Modify: `web/src/i18n/locales/zh-CN.ts:38`, and the `account.*` block
- Modify: `web/src/features/AGENTS.md:20`, `:24`

**Interfaces:**
- Consumes: `AuthUser.email: string | null` from Task 8, and the `PATCH /users/me` semantics from Task 3.
- Produces: no new exports.

- [ ] **Step 1: Add the i18n keys**

In `web/src/i18n/locales/en.ts`, replace line 36 (`auth.currentPassword`) and add two keys after `auth.email`:

```ts
  'auth.email': 'Email',
  'auth.emailOptional': 'Email (optional)',
  'auth.password': 'Password',
  'auth.currentPassword': 'Current password (required to add, change, or remove your email)',
```

In the `account.*` block of the same file, replace `account.passwordRequired` and add `account.emailHelp`:

```ts
  'account.emailHelp': 'Optional. Kept only so your account can be recovered — leave it blank if you prefer.',
  'account.passwordRequired': 'Enter your current password to add, change, or remove your email.',
```

Mirror all four in `web/src/i18n/locales/zh-CN.ts`:

```ts
  'auth.email': '邮箱',
  'auth.emailOptional': '邮箱（选填）',
  'auth.password': '密码',
  'auth.currentPassword': '当前密码（添加、修改或移除邮箱时必填）',
```

```ts
  'account.emailHelp': '选填。仅用于找回账户，可以留空。',
  'account.passwordRequired': '请输入当前密码以添加、修改或移除邮箱。',
```

- [ ] **Step 2: Make Account.tsx null-safe and label the field optional**

In `web/src/features/auth/Account.tsx`, replace the hydration effect's body (the `if (user) { ... }` block) with:

```tsx
        if (user) {
            setEmail(user.email ?? '')
            setUsername(user.username)
            setInitialEmail(user.email ?? '')
            setInitialUsername(user.username)
        }
```

Replace the three post-save assignments:

```tsx
            setInitialEmail(data.user.email ?? '')
            setInitialUsername(data.user.username)
            setEmail(data.user.email ?? '')
```

Replace the email `Field` and add the help note under it:

```tsx
                        <Field label={t('auth.emailOptional')} type="email" value={email} onChange={event => setEmail(event.target.value)} autoComplete="email" style={{ marginTop: '0.85rem' }} />
                        <Note>{t('account.emailHelp')}</Note>
```

No change is needed to `save`: it already sends `body.email = email.trim()`, which is `""` when the field is emptied — exactly the clear signal the backend expects.

- [ ] **Step 3: Typecheck and run the web suite**

Run: `cd web && npx tsc --noEmit && npm test`

Expected: no type errors; all vitest files pass. A type error on `user.email` would mean a `?? ''` was missed.

- [ ] **Step 4: Verify in the browser**

Start the backend and frontend, then check the two flows by hand:

```bash
go run ./cmd/server
```

```bash
cd web && npm run dev
```

At `http://localhost:3000/login`, switch to "Create account": the form must show only username and password. Register, then visit `/account`: the email field is labelled optional and empty. Add an address with the current password, save, reload, confirm it persisted. Clear it, save, and confirm it is gone. Confirm no "forgot password" copy appears anywhere on either page.

- [ ] **Step 5: Update the features AGENTS.md**

In `web/src/features/AGENTS.md`, replace line 20 with:

```markdown
- **AuthTicket.tsx** — Shared sign-in/register ticket. Login accepts one username-or-email field; registration collects only the unique friendly username and a password. `authRequestBody` in `authClient.ts` builds the payload — the register body carries no email key at all
```

Replace line 24 with:

```markdown
- **Account.tsx** — Edits the unique username and the **optional** email (blank clears it; either way the current password is required), and exposes explicit current-device logout. `AuthUser.email` is `string | null` — always null-guard it. Password reset exists on the backend but is deliberately unlinked here
```

- [ ] **Step 6: Full verification**

Run: `go vet ./... && go test ./... 2>&1 | grep -v "no test files"`

Run: `cd web && npx tsc --noEmit && npm test`

Expected: no vet output, every Go package `ok`, no type errors, all vitest files pass.

- [ ] **Step 7: Commit**

```bash
git add web/src/features/auth/Account.tsx web/src/i18n/locales/en.ts web/src/i18n/locales/zh-CN.ts web/src/features/AGENTS.md
git commit -m "feat(web): make the profile email optional and clearable"
```
