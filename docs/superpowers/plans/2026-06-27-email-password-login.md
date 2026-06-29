# Email + Password Login Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace username+password auth with email+password auth (email = login identity, `Username` becomes a non-unique display name), give users app-generated random sparse 5-digit IDs, add an account settings page, and cut over the empty Zeabur Postgres cleanly.

**Architecture:** Backend changes are contained to `internal/storage/db.go` (User schema + random-id hook) and `internal/api/auth.go` (email-based Register/Login/UpdateMe + shared `issueToken`/`normalizeEmail` helpers), plus one route in `internal/api/server.go`. Everything downstream keeps reading the display name from the JWT `username` claim and the id from `sub`, so rooms, recorder, and middleware are untouched. Frontend rewrites `Login.tsx` (mode toggle) and adds `Account.tsx`.

**Tech Stack:** Go 1.25, Gin, GORM (postgres in prod, glebarez/sqlite in tests), golang-jwt v5, bcrypt; React 19 + TypeScript + Vite.

## Global Constraints

- Module path: `github.com/plasma/fh-mahjong`. Go 1.25.
- `internal/engine/game.go` must never import ruleset packages (unrelated here, but never violate).
- User IDs: random integer in **[10000, 99999]**, generated app-side, kept as Go `uint`. Never exceed 2^53 (JWT `sub` is read as `float64`).
- Guest IDs stay in **[9_000_000, 9_999_999]** (disjoint from real users) — do not change that range.
- JWT claims shape is fixed: `sub` (uint id), `username` (display name), `exp`. Account tokens TTL = 72h; guest TTL = 24h.
- Login/registration errors must not enable account enumeration: invalid login → single generic `"Invalid email or password"`.
- Emails are normalized with `strings.ToLower(strings.TrimSpace(...))` everywhere before lookup/store.
- Run `go test ./...` after backend changes; `cd web && npm run build` after frontend changes.
- After changes, update the relevant `AGENTS.md` files (folded into tasks below).

---

### Task 1: User model + random sparse ID

**Files:**
- Modify: `internal/storage/db.go` (User struct, add `generateUserID` + `BeforeCreate`)
- Test: `internal/storage/db_test.go` (create)
- Modify: `internal/storage/AGENTS.md`

**Interfaces:**
- Produces: `storage.User{ ID uint; Email string; Username string; PasswordHash string; Rating int; ... }` with `Email` as the unique login key and `Username` as a non-unique display name. `User.BeforeCreate(tx *gorm.DB) error` assigns a random id in `[10000, 99999]` when `ID == 0`. `generateUserID() (uint, error)` is package-private.

- [ ] **Step 1: Write the failing test**

Create `internal/storage/db_test.go`:
```go
package storage

import "testing"

func TestGenerateUserIDInRange(t *testing.T) {
	for i := 0; i < 2000; i++ {
		id, err := generateUserID()
		if err != nil {
			t.Fatalf("generateUserID error: %v", err)
		}
		if id < 10000 || id > 99999 {
			t.Fatalf("id %d out of range [10000,99999]", id)
		}
	}
}

func TestBeforeCreateAssignsIDWhenZero(t *testing.T) {
	u := &User{}
	if err := u.BeforeCreate(nil); err != nil {
		t.Fatalf("BeforeCreate error: %v", err)
	}
	if u.ID < 10000 || u.ID > 99999 {
		t.Fatalf("expected assigned id in range, got %d", u.ID)
	}
}

func TestBeforeCreatePreservesExistingID(t *testing.T) {
	u := &User{ID: 12345}
	if err := u.BeforeCreate(nil); err != nil {
		t.Fatalf("BeforeCreate error: %v", err)
	}
	if u.ID != 12345 {
		t.Fatalf("expected id preserved, got %d", u.ID)
	}
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `go test ./internal/storage/ -run TestGenerateUserIDInRange -v`
Expected: FAIL — compile error, `generateUserID` / `BeforeCreate` undefined.

- [ ] **Step 3: Update the User struct**

In `internal/storage/db.go`, replace the `User` struct with:
```go
// User represents a player account. Email is the login identity; Username is a
// (non-unique) display name shown at the table.
type User struct {
	ID           uint      `gorm:"primaryKey;autoIncrement:false" json:"id"` // random sparse id, app-generated
	Email        string    `gorm:"uniqueIndex;not null;size:255" json:"email"`
	Username     string    `gorm:"not null;size:255" json:"username"` // display name (no longer unique)
	PasswordHash string    `gorm:"not null" json:"-"`
	Rating       int       `gorm:"default:1500" json:"rating"`
	CreatedAt    time.Time `json:"createdAt"`
	UpdatedAt    time.Time `json:"updatedAt"`

	Matches []MatchPlayer `gorm:"foreignKey:UserID" json:"-"`
}
```

- [ ] **Step 4: Add the id generator + hook**

In `internal/storage/db.go`, add the `crypto/rand` and `math/big` imports, then add (e.g. just below the `User` struct):
```go
const (
	userIDMin  = 10000
	userIDSpan = 90000 // 99999 - 10000 + 1
)

// generateUserID returns a cryptographically-random id in [10000, 99999]. The
// range is kept well under 2^53 so the id round-trips exactly through the JWT
// `sub` claim, which is decoded as a float64.
func generateUserID() (uint, error) {
	n, err := rand.Int(rand.Reader, big.NewInt(userIDSpan))
	if err != nil {
		return 0, err
	}
	return uint(n.Int64()) + userIDMin, nil
}

// BeforeCreate assigns a random sparse id when one isn't already set, so users
// get non-sequential, unguessable ids instead of an auto-increment sequence.
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

The `internal/storage/db.go` import block becomes:
```go
import (
	"crypto/rand"
	"math/big"
	"time"

	"gorm.io/gorm"
)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `go test ./internal/storage/ -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Update internal/storage/AGENTS.md**

In `internal/storage/AGENTS.md`, update the `User` description to: email is the unique login identity, `Username` is a non-unique display name, and `ID` is an app-generated random integer in `[10000, 99999]` (via `BeforeCreate`), not an auto-increment sequence.

- [ ] **Step 7: Commit**

```bash
git add internal/storage/db.go internal/storage/db_test.go internal/storage/AGENTS.md
git commit -m "feat(models): email login identity + random sparse user ids"
```

---

### Task 2: Auth helpers — normalizeEmail + issueToken

**Files:**
- Modify: `internal/api/auth.go` (add helpers; refactor `Login`/`GuestLogin` to use `issueToken`)
- Test: `internal/api/auth_helpers_test.go` (create)

**Interfaces:**
- Produces: `normalizeEmail(s string) string` (lowercases + trims). `issueToken(id uint, username string, ttl time.Duration) (string, error)` — builds the HS256 JWT with `sub`/`username`/`exp` claims signed by `jwtSecret`.

- [ ] **Step 1: Write the failing test**

Create `internal/api/auth_helpers_test.go`:
```go
package api

import (
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

func TestNormalizeEmail(t *testing.T) {
	cases := map[string]string{
		"  Foo@X.com ": "foo@x.com",
		"BAR@Y.IO":     "bar@y.io",
		"baz@z.net":    "baz@z.net",
	}
	for in, want := range cases {
		if got := normalizeEmail(in); got != want {
			t.Fatalf("normalizeEmail(%q) = %q, want %q", in, got, want)
		}
	}
}

func TestIssueTokenClaims(t *testing.T) {
	tok, err := issueToken(54321, "Alex", time.Hour)
	if err != nil {
		t.Fatalf("issueToken: %v", err)
	}
	parsed, err := jwt.Parse(tok, func(*jwt.Token) (interface{}, error) { return jwtSecret, nil })
	if err != nil || !parsed.Valid {
		t.Fatalf("parse token: %v", err)
	}
	claims := parsed.Claims.(jwt.MapClaims)
	if uint(claims["sub"].(float64)) != 54321 {
		t.Fatalf("sub = %v, want 54321", claims["sub"])
	}
	if claims["username"].(string) != "Alex" {
		t.Fatalf("username = %v, want Alex", claims["username"])
	}
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `go test ./internal/api/ -run 'TestNormalizeEmail|TestIssueTokenClaims' -v`
Expected: FAIL — `normalizeEmail` / `issueToken` undefined.

- [ ] **Step 3: Add the helpers**

In `internal/api/auth.go`, add `"strings"` to the import block, then add near the top (below `getEnv`):
```go
func normalizeEmail(s string) string {
	return strings.ToLower(strings.TrimSpace(s))
}

// issueToken builds a signed HS256 JWT carrying the user id (sub), display name
// (username) and an expiry. Used by Login, Register, GuestLogin and UpdateMe.
func issueToken(id uint, username string, ttl time.Duration) (string, error) {
	token := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.MapClaims{
		"sub":      id,
		"username": username,
		"exp":      time.Now().Add(ttl).Unix(),
	})
	return token.SignedString(jwtSecret)
}
```

- [ ] **Step 4: Refactor GuestLogin to use issueToken**

In `internal/api/auth.go` `GuestLogin`, replace the inline `jwt.NewWithClaims(...)` + `token.SignedString(jwtSecret)` block with:
```go
	tokenString, err := issueToken(tempUserID, req.Username, 24*time.Hour)
	if err != nil {
		log.Printf("Failed to sign guest token: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to generate token"})
		return
	}
```
(Keep the `rand.Seed`, `tempUserID`, and `mockUser` lines as-is.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `go test ./internal/api/ -run 'TestNormalizeEmail|TestIssueTokenClaims' -v`
Expected: PASS. Also run `go build ./...` to confirm GuestLogin still compiles.

- [ ] **Step 6: Commit**

```bash
git add internal/api/auth.go internal/api/auth_helpers_test.go
git commit -m "refactor(api): add normalizeEmail + issueToken helpers"
```

---

### Task 3: Email-based Register (with test DB harness)

**Files:**
- Modify: `internal/api/auth.go` (`RegisterRequest`, `Register`)
- Modify: `go.mod`, `go.sum` (add `github.com/glebarez/sqlite`)
- Test: `internal/api/auth_test.go` (create harness + register tests)

**Interfaces:**
- Consumes: `storage.User`, `normalizeEmail`, `issueToken`, `AuthResponse{Token string; User storage.User}`.
- Produces: `POST /auth/register` accepting `{email, password, displayName}`; on success returns **201** with `AuthResponse` (auto-login). Test harness `newAuthTestRouter(t) (*gin.Engine, *gorm.DB)` and `doJSON(t, r, method, path, body) *httptest.ResponseRecorder` for later tasks.

- [ ] **Step 1: Add the test-only sqlite dependency**

Run:
```bash
go get github.com/glebarez/sqlite@latest
```
Expected: `go.mod`/`go.sum` updated; no error.

- [ ] **Step 2: Write the failing test (harness + register cases)**

Create `internal/api/auth_test.go`:
```go
package api

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/glebarez/sqlite"
	"github.com/plasma/fh-mahjong/internal/storage"
	"gorm.io/gorm"
)

func newAuthTestRouter(t *testing.T) (*gin.Engine, *gorm.DB) {
	t.Helper()
	gin.SetMode(gin.TestMode)
	db, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	if err := db.AutoMigrate(&storage.User{}); err != nil {
		t.Fatalf("migrate: %v", err)
	}
	h := &AuthHandler{DB: db}
	r := gin.New()
	r.POST("/api/v1/auth/register", h.Register)
	r.POST("/api/v1/auth/login", h.Login)
	// NOTE: the PATCH /users/me route is added to this harness in Task 5.
	return r, db
}

func doJSON(t *testing.T, r http.Handler, method, path, bearer string, body any) *httptest.ResponseRecorder {
	t.Helper()
	b, _ := json.Marshal(body)
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(method, path, bytes.NewReader(b))
	req.Header.Set("Content-Type", "application/json")
	if bearer != "" {
		req.Header.Set("Authorization", "Bearer "+bearer)
	}
	r.ServeHTTP(rec, req)
	return rec
}

func decodeAuth(t *testing.T, rec *httptest.ResponseRecorder) AuthResponse {
	t.Helper()
	var out AuthResponse
	if err := json.Unmarshal(rec.Body.Bytes(), &out); err != nil {
		t.Fatalf("decode AuthResponse: %v (body=%s)", err, rec.Body.String())
	}
	return out
}

func TestRegisterReturnsTokenAndUser(t *testing.T) {
	r, _ := newAuthTestRouter(t)
	rec := doJSON(t, r, http.MethodPost, "/api/v1/auth/register", "",
		map[string]string{"email": "Alice@Example.com", "password": "hunter2pw", "displayName": "Alice"})
	if rec.Code != http.StatusCreated {
		t.Fatalf("expected 201, got %d (%s)", rec.Code, rec.Body.String())
	}
	out := decodeAuth(t, rec)
	if out.Token == "" {
		t.Fatal("expected a token (auto-login)")
	}
	if out.User.Email != "alice@example.com" {
		t.Fatalf("email = %q, want normalized alice@example.com", out.User.Email)
	}
	if out.User.Username != "Alice" {
		t.Fatalf("display name = %q, want Alice", out.User.Username)
	}
	if out.User.ID < 10000 || out.User.ID > 99999 {
		t.Fatalf("id %d out of range", out.User.ID)
	}
	if out.User.PasswordHash != "" {
		t.Fatal("password hash must never be serialized")
	}
}

func TestRegisterDuplicateEmailConflicts(t *testing.T) {
	r, _ := newAuthTestRouter(t)
	body := map[string]string{"email": "dup@example.com", "password": "hunter2pw", "displayName": "One"}
	if rec := doJSON(t, r, http.MethodPost, "/api/v1/auth/register", "", body); rec.Code != http.StatusCreated {
		t.Fatalf("first register: expected 201, got %d", rec.Code)
	}
	// Same email, different case → still a conflict.
	body2 := map[string]string{"email": "DUP@example.com", "password": "hunter2pw", "displayName": "Two"}
	rec := doJSON(t, r, http.MethodPost, "/api/v1/auth/register", "", body2)
	if rec.Code != http.StatusConflict {
		t.Fatalf("expected 409 on duplicate email, got %d", rec.Code)
	}
}

func TestRegisterValidation(t *testing.T) {
	r, _ := newAuthTestRouter(t)
	bad := []map[string]string{
		{"email": "not-an-email", "password": "hunter2pw", "displayName": "X1"},
		{"email": "a@b.com", "password": "short", "displayName": "X1"},
		{"email": "a@b.com", "password": "hunter2pw", "displayName": "X"}, // name < 2
	}
	for i, body := range bad {
		rec := doJSON(t, r, http.MethodPost, "/api/v1/auth/register", "", body)
		if rec.Code != http.StatusBadRequest {
			t.Fatalf("case %d: expected 400, got %d", i, rec.Code)
		}
	}
}
```

- [ ] **Step 3: Run test to verify it fails**

Run: `go test ./internal/api/ -run TestRegister -v`
Expected: FAIL — the old `Register` still binds `username`+`password`, so the `{email,password,displayName}` body fails binding (400) instead of 201. (The harness does not reference `UpdateMe` yet — that route is added in Task 5 — so the package still compiles.)

- [ ] **Step 4: Rewrite RegisterRequest + Register**

In `internal/api/auth.go`, replace `RegisterRequest` and the `Register` function with:
```go
type RegisterRequest struct {
	Email       string `json:"email" binding:"required,email"`
	Password    string `json:"password" binding:"required,min=8"`
	DisplayName string `json:"displayName" binding:"required,min=2,max=30"`
}

// Register creates an account keyed by email and auto-logs the user in.
func (h *AuthHandler) Register(c *gin.Context) {
	var req RegisterRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	if h.DB == nil {
		c.JSON(http.StatusServiceUnavailable, gin.H{"error": "Database is temporarily disabled. Please use 'Guest Login'."})
		return
	}

	email := normalizeEmail(req.Email)

	var existing storage.User
	if err := h.DB.Where("email = ?", email).First(&existing).Error; err == nil {
		c.JSON(http.StatusConflict, gin.H{"error": "Email already registered"})
		return
	}

	hashed, err := bcrypt.GenerateFromPassword([]byte(req.Password), bcrypt.DefaultCost)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to hash password"})
		return
	}

	user := storage.User{
		Email:        email,
		Username:     req.DisplayName,
		PasswordHash: string(hashed),
		Rating:       1500,
	}

	// Random ids can (astronomically rarely) collide on the PK; retry a few times,
	// zeroing the id so BeforeCreate regenerates it.
	var createErr error
	for attempt := 0; attempt < 5; attempt++ {
		user.ID = 0
		createErr = h.DB.Create(&user).Error
		if createErr == nil {
			break
		}
	}
	if createErr != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to create user"})
		return
	}

	token, err := issueToken(user.ID, user.Username, 72*time.Hour)
	if err != nil {
		log.Printf("Failed to sign token: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to generate token"})
		return
	}

	user.PasswordHash = ""
	c.JSON(http.StatusCreated, AuthResponse{Token: token, User: user})
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `go test ./internal/api/ -run TestRegister -v`
Expected: PASS (3 tests). (`r.PATCH` line still commented if Task 5 not yet done.)

- [ ] **Step 6: Commit**

```bash
git add internal/api/auth.go internal/api/auth_test.go go.mod go.sum
git commit -m "feat(api): email-based registration with auto-login"
```

---

### Task 4: Email-based Login

**Files:**
- Modify: `internal/api/auth.go` (`LoginRequest`, `Login`)
- Test: `internal/api/auth_test.go` (add login cases)

**Interfaces:**
- Produces: `POST /auth/login` accepting `{email, password}`; returns **200** + `AuthResponse` on success, **401** generic on bad credentials.

- [ ] **Step 1: Write the failing test**

Append to `internal/api/auth_test.go`:
```go
func TestLoginAfterRegisterWithEmailNormalization(t *testing.T) {
	r, _ := newAuthTestRouter(t)
	reg := map[string]string{"email": "Bob@Example.com", "password": "hunter2pw", "displayName": "Bob"}
	if rec := doJSON(t, r, http.MethodPost, "/api/v1/auth/register", "", reg); rec.Code != http.StatusCreated {
		t.Fatalf("register: got %d", rec.Code)
	}
	// Different case on login still resolves to the same account.
	login := map[string]string{"email": "bob@example.com", "password": "hunter2pw"}
	rec := doJSON(t, r, http.MethodPost, "/api/v1/auth/login", "", login)
	if rec.Code != http.StatusOK {
		t.Fatalf("login: expected 200, got %d (%s)", rec.Code, rec.Body.String())
	}
	out := decodeAuth(t, rec)
	if out.Token == "" || out.User.Email != "bob@example.com" {
		t.Fatalf("unexpected login response: %+v", out.User)
	}
}

func TestLoginWrongPassword(t *testing.T) {
	r, _ := newAuthTestRouter(t)
	reg := map[string]string{"email": "carol@example.com", "password": "hunter2pw", "displayName": "Carol"}
	doJSON(t, r, http.MethodPost, "/api/v1/auth/register", "", reg)
	rec := doJSON(t, r, http.MethodPost, "/api/v1/auth/login", "",
		map[string]string{"email": "carol@example.com", "password": "wrongpass"})
	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401, got %d", rec.Code)
	}
}

func TestLoginUnknownEmail(t *testing.T) {
	r, _ := newAuthTestRouter(t)
	rec := doJSON(t, r, http.MethodPost, "/api/v1/auth/login", "",
		map[string]string{"email": "nobody@example.com", "password": "hunter2pw"})
	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401, got %d", rec.Code)
	}
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `go test ./internal/api/ -run TestLogin -v`
Expected: FAIL — old `Login` still binds `username`, so `email`-only login returns 400/401 incorrectly.

- [ ] **Step 3: Rewrite LoginRequest + Login**

In `internal/api/auth.go`, replace `LoginRequest` and `Login` with:
```go
type LoginRequest struct {
	Email    string `json:"email" binding:"required,email"`
	Password string `json:"password" binding:"required"`
}

// Login authenticates by email + password and returns a JWT.
func (h *AuthHandler) Login(c *gin.Context) {
	var req LoginRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	if h.DB == nil {
		c.JSON(http.StatusServiceUnavailable, gin.H{"error": "Database is temporarily disabled. Please use 'Guest Login'."})
		return
	}

	email := normalizeEmail(req.Email)

	var user storage.User
	if err := h.DB.Where("email = ?", email).First(&user).Error; err != nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Invalid email or password"})
		return
	}
	if err := bcrypt.CompareHashAndPassword([]byte(user.PasswordHash), []byte(req.Password)); err != nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Invalid email or password"})
		return
	}

	token, err := issueToken(user.ID, user.Username, 72*time.Hour)
	if err != nil {
		log.Printf("Failed to sign token: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to generate token"})
		return
	}

	user.PasswordHash = ""
	c.JSON(http.StatusOK, AuthResponse{Token: token, User: user})
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `go test ./internal/api/ -run TestLogin -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add internal/api/auth.go internal/api/auth_test.go
git commit -m "feat(api): email-based login"
```

---

### Task 5: Profile update — PATCH /users/me

**Files:**
- Modify: `internal/api/auth.go` (`UpdateProfileRequest`, `UpdateMe`)
- Modify: `internal/api/server.go` (register the route)
- Modify: `internal/api/auth_test.go` (re-enable PATCH route in harness if commented; add tests)
- Modify: `internal/api/AGENTS.md`

**Interfaces:**
- Consumes: `c.Get("userID")` (uint, set by `AuthMiddleware`), `storage.User`, `normalizeEmail`, `issueToken`, `AuthResponse`.
- Produces: `func (h *AuthHandler) UpdateMe(c *gin.Context)`. `PATCH /api/v1/users/me` accepting `{email?, displayName?}`; returns **200** + `AuthResponse` (always a fresh token), **409** on email taken by another user, **404** if no DB row (e.g. guest).

- [ ] **Step 1: Write the failing test**

Append to `internal/api/auth_test.go`:
```go
func TestUpdateMeChangesEmailAndName(t *testing.T) {
	r, _ := newAuthTestRouter(t)
	reg := map[string]string{"email": "dave@example.com", "password": "hunter2pw", "displayName": "Dave"}
	regRec := doJSON(t, r, http.MethodPost, "/api/v1/auth/register", "", reg)
	token := decodeAuth(t, regRec).Token

	rec := doJSON(t, r, http.MethodPatch, "/api/v1/users/me", token,
		map[string]string{"email": "DAVE2@example.com", "displayName": "Dave Two"})
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d (%s)", rec.Code, rec.Body.String())
	}
	out := decodeAuth(t, rec)
	if out.User.Email != "dave2@example.com" {
		t.Fatalf("email = %q, want dave2@example.com", out.User.Email)
	}
	if out.User.Username != "Dave Two" {
		t.Fatalf("name = %q, want Dave Two", out.User.Username)
	}
	if out.Token == "" {
		t.Fatal("expected a fresh token")
	}
}

func TestUpdateMeEmailCollision(t *testing.T) {
	r, _ := newAuthTestRouter(t)
	doJSON(t, r, http.MethodPost, "/api/v1/auth/register", "",
		map[string]string{"email": "taken@example.com", "password": "hunter2pw", "displayName": "Taken"})
	regRec := doJSON(t, r, http.MethodPost, "/api/v1/auth/register", "",
		map[string]string{"email": "mover@example.com", "password": "hunter2pw", "displayName": "Mover"})
	token := decodeAuth(t, regRec).Token

	rec := doJSON(t, r, http.MethodPatch, "/api/v1/users/me", token,
		map[string]string{"email": "taken@example.com"})
	if rec.Code != http.StatusConflict {
		t.Fatalf("expected 409, got %d", rec.Code)
	}
}

func TestUpdateMeRequiresAuth(t *testing.T) {
	r, _ := newAuthTestRouter(t)
	rec := doJSON(t, r, http.MethodPatch, "/api/v1/users/me", "",
		map[string]string{"displayName": "Nope"})
	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401 without token, got %d", rec.Code)
	}
}
```
Also add the PATCH route to the harness. In `newAuthTestRouter` (in `internal/api/auth_test.go`), add after the login route:
```go
	r.PATCH("/api/v1/users/me", AuthMiddleware(), h.UpdateMe)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `go test ./internal/api/ -run TestUpdateMe -v`
Expected: FAIL — `h.UpdateMe` undefined (compile error).

- [ ] **Step 3: Add UpdateProfileRequest + UpdateMe**

In `internal/api/auth.go`, add:
```go
type UpdateProfileRequest struct {
	Email       *string `json:"email" binding:"omitempty,email"`
	DisplayName *string `json:"displayName" binding:"omitempty,min=2,max=30"`
}

// UpdateMe lets an authenticated account change its email and/or display name.
// A fresh token is always returned so the `username` claim stays current.
func (h *AuthHandler) UpdateMe(c *gin.Context) {
	var req UpdateProfileRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	if h.DB == nil {
		c.JSON(http.StatusServiceUnavailable, gin.H{"error": "Database is temporarily disabled."})
		return
	}

	uid, _ := c.Get("userID")
	var user storage.User
	if err := h.DB.First(&user, uid).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "User not found"})
		return
	}

	if req.Email != nil {
		email := normalizeEmail(*req.Email)
		if email != user.Email {
			var other storage.User
			if err := h.DB.Where("email = ? AND id <> ?", email, user.ID).First(&other).Error; err == nil {
				c.JSON(http.StatusConflict, gin.H{"error": "Email already registered"})
				return
			}
			user.Email = email
		}
	}
	if req.DisplayName != nil {
		user.Username = *req.DisplayName
	}

	if err := h.DB.Save(&user).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to update profile"})
		return
	}

	token, err := issueToken(user.ID, user.Username, 72*time.Hour)
	if err != nil {
		log.Printf("Failed to sign token: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to generate token"})
		return
	}

	user.PasswordHash = ""
	c.JSON(http.StatusOK, AuthResponse{Token: token, User: user})
}
```

- [ ] **Step 4: Register the route**

In `internal/api/server.go` `setupRoutes`, inside the `protected` block, add the PATCH line right after the GET:
```go
		protected.GET("/users/me", s.handleGetMe)
		protected.PATCH("/users/me", authHandler.UpdateMe)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `go test ./internal/api/ -run TestUpdateMe -v`
Expected: PASS (3 tests). Then run the full backend suite:
Run: `go test ./...`
Expected: PASS (no regressions).

- [ ] **Step 6: Update internal/api/AGENTS.md**

In `internal/api/AGENTS.md`, document that auth is email+password (email is the unique identity, `Username` is the display name), registration auto-logs in, and `PATCH /api/v1/users/me` updates email/display name and returns a fresh token. Note guest login is unchanged.

- [ ] **Step 7: Commit**

```bash
git add internal/api/auth.go internal/api/server.go internal/api/auth_test.go internal/api/AGENTS.md
git commit -m "feat(api): PATCH /users/me profile update"
```

---

### Task 6: Frontend login page (email/password + mode toggle)

**Files:**
- Modify: `web/src/features/auth/Login.tsx` (full rewrite)

**Interfaces:**
- Consumes: backend `POST /auth/login` `{email,password}` and `POST /auth/register` `{email,password,displayName}`, both returning `{token, user}`. `useSocket().connect(token)`, `getApiUrl`, theme components.
- Produces: a `/login` screen with a Sign in / Create account toggle that stores `fh_token` and navigates to `/play`.

- [ ] **Step 1: Rewrite Login.tsx**

Replace the entire contents of `web/src/features/auth/Login.tsx` with:
```tsx
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useSocket } from '../../contexts/SocketContext';
import { getApiUrl } from '../../config';
import { Page, Shell, Card, PageHeader, Section, ToolsRow, Button, TextLink, Field, Note } from '../../theme';

type Mode = 'login' | 'register';

export default function Login() {
    const [mode, setMode] = useState<Mode>('login');
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [displayName, setDisplayName] = useState('');
    const [error, setError] = useState('');
    const navigate = useNavigate();
    const { connect } = useSocket();

    const submit = async () => {
        setError('');
        try {
            const isRegister = mode === 'register';
            const endpoint = isRegister ? '/api/v1/auth/register' : '/api/v1/auth/login';
            const body = isRegister ? { email, password, displayName } : { email, password };
            const res = await fetch(getApiUrl(endpoint), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.error || 'Authentication failed');

            localStorage.setItem('fh_token', data.token);
            connect(data.token);
            navigate('/play');
        } catch (err: any) {
            setError(err.message);
        }
    };

    return (
        <Page>
            <Shell>
                <Card>
                    <PageHeader
                        title={mode === 'login' ? 'Sign in' : 'Create account'}
                        subtitle="登录 · 奉化麻将"
                        nav={<>
                            <TextLink to="/">Home</TextLink>
                            <TextLink to="/room/new">Private room →</TextLink>
                        </>}
                    />

                    <Section
                        title="Account access"
                        subtitle={mode === 'login'
                            ? 'Sign in with your email and password.'
                            : 'Register a new account with your email.'}
                    >
                        <Field label="Email" type="email" value={email}
                            onChange={e => setEmail(e.target.value)} autoComplete="email" />

                        {mode === 'register' && (
                            <Field label="Display name" value={displayName}
                                onChange={e => setDisplayName(e.target.value)}
                                autoComplete="nickname" style={{ marginTop: '0.85rem' }} />
                        )}

                        <Field label="Password" type="password" value={password}
                            onChange={e => setPassword(e.target.value)}
                            autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                            style={{ marginTop: '0.85rem' }} />

                        {error && <Note tone="error">{error}</Note>}

                        <ToolsRow>
                            <Button variant="primary" onClick={submit}>
                                {mode === 'login' ? 'Sign in' : 'Create account'}
                            </Button>
                            <Button onClick={() => { setError(''); setMode(mode === 'login' ? 'register' : 'login'); }}>
                                {mode === 'login' ? 'Need an account?' : 'Have an account?'}
                            </Button>
                        </ToolsRow>
                    </Section>
                </Card>
            </Shell>
        </Page>
    );
}
```

- [ ] **Step 2: Type-check / build**

Run: `cd web && npm run build`
Expected: build succeeds with no TypeScript errors.

- [ ] **Step 3: Commit**

```bash
git add web/src/features/auth/Login.tsx
git commit -m "feat(web): email/password login with sign-in / register toggle"
```

---

### Task 7: Account settings page + route + nav link

**Files:**
- Create: `web/src/features/auth/Account.tsx`
- Modify: `web/src/App.tsx` (import + route)
- Modify: `web/src/features/lobby/Lobby.tsx` (nav link)
- Modify: `web/src/features/AGENTS.md`

**Interfaces:**
- Consumes: `GET /api/v1/users/me` (returns `{id,email,username,rating,...}`; 404/503 for guests/no-DB), `PATCH /api/v1/users/me` `{email,displayName}` returning `{token,user}`. `useSocket().connect`, `getApiUrl`, theme components.
- Produces: a `/account` route reachable from the lobby nav.

- [ ] **Step 1: Create Account.tsx**

Create `web/src/features/auth/Account.tsx`:
```tsx
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useSocket } from '../../contexts/SocketContext';
import { getApiUrl } from '../../config';
import { Page, Shell, Card, PageHeader, Section, ToolsRow, Button, TextLink, Field, Note } from '../../theme';

export default function Account() {
    const [email, setEmail] = useState('');
    const [displayName, setDisplayName] = useState('');
    const [status, setStatus] = useState('');
    const [error, setError] = useState('');
    const [loaded, setLoaded] = useState(false);
    const [editable, setEditable] = useState(true);
    const navigate = useNavigate();
    const { connect } = useSocket();

    useEffect(() => {
        const token = localStorage.getItem('fh_token');
        if (!token) { navigate('/login'); return; }
        (async () => {
            try {
                const res = await fetch(getApiUrl('/api/v1/users/me'), {
                    headers: { 'Authorization': `Bearer ${token}` },
                });
                if (res.status === 404 || res.status === 503) {
                    setEditable(false);
                    setLoaded(true);
                    return;
                }
                if (!res.ok) throw new Error('Failed to load profile');
                const data = await res.json();
                setEmail(data.email || '');
                setDisplayName(data.username || '');
                setLoaded(true);
            } catch (e: any) {
                setError(e.message || 'Failed to load profile');
                setLoaded(true);
            }
        })();
    }, [navigate]);

    const save = async () => {
        setError(''); setStatus('');
        const token = localStorage.getItem('fh_token');
        if (!token) { navigate('/login'); return; }
        try {
            const res = await fetch(getApiUrl('/api/v1/users/me'), {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
                body: JSON.stringify({ email, displayName }),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.error || 'Failed to save');
            localStorage.setItem('fh_token', data.token);
            connect(data.token);
            setStatus('Saved.');
        } catch (e: any) {
            setError(e.message || 'Failed to save');
        }
    };

    return (
        <Page>
            <Shell>
                <Card>
                    <PageHeader
                        title="Account"
                        subtitle="账户设置 · 奉化麻将"
                        nav={<>
                            <TextLink to="/play">← Play</TextLink>
                            <TextLink to="/">Home</TextLink>
                        </>}
                    />
                    <Section title="Profile" subtitle="Change your email or display name.">
                        {!loaded && <Note>Loading…</Note>}
                        {loaded && !editable && (
                            <Note tone="error">
                                Guests can't edit a profile. Register an account from the Sign in page.
                            </Note>
                        )}
                        {loaded && editable && (
                            <>
                                <Field label="Email" type="email" value={email}
                                    onChange={e => setEmail(e.target.value)} autoComplete="email" />
                                <Field label="Display name" value={displayName}
                                    onChange={e => setDisplayName(e.target.value)}
                                    autoComplete="nickname" style={{ marginTop: '0.85rem' }} />
                                {error && <Note tone="error">{error}</Note>}
                                {status && <Note tone="ok">{status}</Note>}
                                <ToolsRow>
                                    <Button variant="primary" onClick={save}>Save</Button>
                                </ToolsRow>
                            </>
                        )}
                    </Section>
                </Card>
            </Shell>
        </Page>
    );
}
```

- [ ] **Step 2: Add the route in App.tsx**

In `web/src/App.tsx`, add the import alongside the others:
```tsx
import Account from './features/auth/Account'
```
And add the route just after the `/play` route:
```tsx
                            <Route path="/play" element={<Lobby />} />
                            <Route path="/account" element={<Account />} />
```

- [ ] **Step 3: Add the lobby nav link**

In `web/src/features/lobby/Lobby.tsx`, update the `PageHeader` `nav` prop to include an Account link:
```tsx
                        nav={<>
                            <TextLink to="/">Home</TextLink>
                            <TextLink to="/account">Account</TextLink>
                            <TextLink to="/room/new">Private room →</TextLink>
                        </>}
```

- [ ] **Step 4: Type-check / build**

Run: `cd web && npm run build`
Expected: build succeeds with no TypeScript errors.

- [ ] **Step 5: Update web/src/features/AGENTS.md**

In `web/src/features/AGENTS.md`, note that `Login.tsx` is email/password with a sign-in/register toggle, and `Account.tsx` (`/account`) lets real accounts edit email + display name (guests see a notice). Mention it's linked from the lobby nav.

- [ ] **Step 6: Commit**

```bash
git add web/src/features/auth/Account.tsx web/src/App.tsx web/src/features/lobby/Lobby.tsx web/src/features/AGENTS.md
git commit -m "feat(web): account settings page to edit email + display name"
```

---

### Task 8: Manual end-to-end verification (local)

**Files:** none (manual verification before the prod cutover).

- [ ] **Step 1: Start backend + frontend**

Per project workflow: kill anything on ports 8080/3000, then run the backend (`go run cmd/server/main.go`) against a local Postgres, and `cd web && npm run dev`. (If no local DB, the backend runs with `DB == nil` and auth returns 503 — use a local Postgres for this check, or rely on the automated tests + prod smoke in Task 9.)

- [ ] **Step 2: Exercise the flows**

In the browser at `http://localhost:3000/login`:
1. Create account (email + password + display name) → should land on `/play` already signed in.
2. Open `/account` → email + display name prefilled; change display name → Save → see "Saved."
3. Sign out (clear `localStorage.fh_token` via devtools) → Sign in with the same email/password → lands on `/play`.
4. Confirm a duplicate email registration shows the "Email already registered" error.

Expected: all four behave as described; no console errors.

- [ ] **Step 3: Commit (if any doc tweaks)**

No code change expected. If you adjusted copy, commit it.

---

### Task 9: Zeabur deploy + verification

**Files:** none (operational). Uses the deployed `fhmj` project Postgres.

> The schema cutover is now **automated** in `storage.AutoMigrate` (adversarial-review round 2): it migrates an empty legacy table in place, drops the stale `idx_users_username` unique index, and **fails closed** (server aborts at startup with a diagnostic) if the legacy table unexpectedly holds rows. There is no manual `DROP TABLE` step.

- [ ] **Step 1: Merge the PR to main**

Merge the PR (`gh pr merge <n> --merge`) so Zeabur builds the new backend from `main`. On boot, `cmd/server/main.go` calls `storage.AutoMigrate`, which performs the cutover automatically. Wait for the `fh-mahjong` service to reach RUNNING (if it fails closed, the logs will show the `refusing to migrate` diagnostic — investigate the DB state rather than forcing).

- [ ] **Step 2: Verify the rebuilt schema**

Inspect the prod DB (a throwaway `cmd/dbcheck/main.go` with `Raw` queries, like the one used during brainstorming) to confirm:
- `users` columns include `email` (NOT NULL) and `username` (NOT NULL).
- There is a UNIQUE index on `email` and **no** `idx_users_username` unique index.

Delete the throwaway program afterward; confirm `git status` is clean.

- [ ] **Step 3: Production smoke test**

Against the deployed frontend: register a new account, edit it on `/account`, sign out, sign back in. Confirm success. Done.

---

## Self-Review Notes

- **Spec coverage:** data model (Task 1), random sparse id (Task 1), normalize/issueToken (Task 2), email Register + auto-login + 409 (Task 3), email Login + 401 generic (Task 4), PATCH /users/me + token re-issue + 409 (Task 5), frontend login (Task 6), account page + route + guest-notice + nav (Task 7), glebarez/sqlite test dep (Task 3), helper/validation/normalization tests (Tasks 1–5), fresh-start cutover incl. dropping stale username index + id sequence (Task 9). Guest login unchanged (Task 2 refactor preserves behavior).
- **Type consistency:** `AuthResponse{Token, User}`, `issueToken(uint,string,time.Duration)`, `normalizeEmail(string)`, `User.BeforeCreate`, `UpdateMe`, `RegisterRequest{Email,Password,DisplayName}`, `UpdateProfileRequest{*Email,*DisplayName}` are used identically across tasks and tests.
- **Task 3 ↔ Task 5 ordering:** the shared `newAuthTestRouter` harness registers only register+login in Task 3 (so the package compiles), and Task 5 adds the PATCH route to it — no comment-out dance.
