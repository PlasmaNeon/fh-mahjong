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
	"golang.org/x/crypto/bcrypt"
	"gorm.io/gorm"
)

// The unknown-email login path must perform one bcrypt comparison against a
// fixed dummy hash so it cannot be distinguished from the wrong-password path by
// timing. This anchors that the equalizer hash is a real bcrypt hash at the same
// cost as stored passwords; a no-op or wrong-cost value would reopen the oracle.
func TestLoginDummyHashEqualizesTiming(t *testing.T) {
	cost, err := bcrypt.Cost(dummyPasswordHash)
	if err != nil {
		t.Fatalf("dummyPasswordHash is not a valid bcrypt hash: %v", err)
	}
	if cost != bcrypt.DefaultCost {
		t.Fatalf("dummyPasswordHash cost = %d, want DefaultCost %d", cost, bcrypt.DefaultCost)
	}
}

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
	r.PATCH("/api/v1/users/me", AuthMiddleware(), h.UpdateMe)
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
	var errBody struct {
		Error string `json:"error"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &errBody); err != nil {
		t.Fatalf("decode error body: %v (body=%s)", err, rec.Body.String())
	}
	const wantMsg = "Invalid email or password"
	if errBody.Error != wantMsg {
		t.Fatalf("error message = %q, want %q (anti-enumeration)", errBody.Error, wantMsg)
	}
}

func TestLoginUnknownEmail(t *testing.T) {
	r, _ := newAuthTestRouter(t)
	rec := doJSON(t, r, http.MethodPost, "/api/v1/auth/login", "",
		map[string]string{"email": "nobody@example.com", "password": "hunter2pw"})
	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401, got %d", rec.Code)
	}
	var errBody struct {
		Error string `json:"error"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &errBody); err != nil {
		t.Fatalf("decode error body: %v (body=%s)", err, rec.Body.String())
	}
	const wantMsg = "Invalid email or password"
	if errBody.Error != wantMsg {
		t.Fatalf("error message = %q, want %q (anti-enumeration)", errBody.Error, wantMsg)
	}
}

func registerAndToken(t *testing.T, r http.Handler, email, password, name string) string {
	t.Helper()
	rec := doJSON(t, r, http.MethodPost, "/api/v1/auth/register", "",
		map[string]string{"email": email, "password": password, "displayName": name})
	if rec.Code != http.StatusCreated {
		t.Fatalf("register %s: got %d", email, rec.Code)
	}
	return decodeAuth(t, rec).Token
}

// Changing both email and name with the correct current password succeeds; the
// name change means a fresh token is issued.
func TestUpdateMeChangesEmailAndName(t *testing.T) {
	r, _ := newAuthTestRouter(t)
	token := registerAndToken(t, r, "dave@example.com", "hunter2pw", "Dave")

	rec := doJSON(t, r, http.MethodPatch, "/api/v1/users/me", token,
		map[string]string{"email": "DAVE2@example.com", "displayName": "Dave Two", "currentPassword": "hunter2pw"})
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
		t.Fatal("expected a fresh token after a display-name change")
	}
}

// Changing the login email requires the current password (anti-takeover): a
// bearer token alone is not enough.
func TestUpdateMeEmailChangeRequiresCurrentPassword(t *testing.T) {
	r, _ := newAuthTestRouter(t)
	token := registerAndToken(t, r, "erin@example.com", "hunter2pw", "Erin")

	rec := doJSON(t, r, http.MethodPatch, "/api/v1/users/me", token,
		map[string]string{"email": "erin-new@example.com"})
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 without current password, got %d (%s)", rec.Code, rec.Body.String())
	}
}

func TestUpdateMeEmailChangeWrongPassword(t *testing.T) {
	r, _ := newAuthTestRouter(t)
	token := registerAndToken(t, r, "fred@example.com", "hunter2pw", "Fred")

	rec := doJSON(t, r, http.MethodPatch, "/api/v1/users/me", token,
		map[string]string{"email": "fred-new@example.com", "currentPassword": "wrongpass"})
	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401 with wrong current password, got %d", rec.Code)
	}
}

// An email-only change must NOT mint a fresh token: this endpoint can't be used
// as an unrestricted token-refresh to indefinitely renew a stolen token.
func TestUpdateMeEmailOnlyChangeDoesNotRenewToken(t *testing.T) {
	r, _ := newAuthTestRouter(t)
	token := registerAndToken(t, r, "gail@example.com", "hunter2pw", "Gail")

	rec := doJSON(t, r, http.MethodPatch, "/api/v1/users/me", token,
		map[string]string{"email": "gail-new@example.com", "currentPassword": "hunter2pw"})
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d (%s)", rec.Code, rec.Body.String())
	}
	out := decodeAuth(t, rec)
	if out.User.Email != "gail-new@example.com" {
		t.Fatalf("email = %q, want gail-new@example.com", out.User.Email)
	}
	if out.Token != "" {
		t.Fatal("email-only change must not issue a fresh token (no token renewal)")
	}
}

// A no-op PATCH is rejected, so it can't serve as a token-refresh either.
func TestUpdateMeNoOpRejected(t *testing.T) {
	r, _ := newAuthTestRouter(t)
	token := registerAndToken(t, r, "hank@example.com", "hunter2pw", "Hank")

	// Empty body: no changes.
	rec := doJSON(t, r, http.MethodPatch, "/api/v1/users/me", token, map[string]string{})
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 for empty no-op PATCH, got %d", rec.Code)
	}
	// Same values as current: still a no-op.
	rec = doJSON(t, r, http.MethodPatch, "/api/v1/users/me", token,
		map[string]string{"displayName": "Hank"})
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 for same-value no-op PATCH, got %d", rec.Code)
	}
}

// A display-name-only change needs no password and re-issues the token.
func TestUpdateMeDisplayNameChangeReissuesToken(t *testing.T) {
	r, _ := newAuthTestRouter(t)
	token := registerAndToken(t, r, "ivan@example.com", "hunter2pw", "Ivan")

	rec := doJSON(t, r, http.MethodPatch, "/api/v1/users/me", token,
		map[string]string{"displayName": "Ivan The Great"})
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d (%s)", rec.Code, rec.Body.String())
	}
	out := decodeAuth(t, rec)
	if out.User.Username != "Ivan The Great" {
		t.Fatalf("name = %q, want Ivan The Great", out.User.Username)
	}
	if out.Token == "" {
		t.Fatal("expected a fresh token after a display-name change")
	}
}

func TestUpdateMeEmailCollision(t *testing.T) {
	r, _ := newAuthTestRouter(t)
	registerAndToken(t, r, "taken@example.com", "hunter2pw", "Taken")
	token := registerAndToken(t, r, "mover@example.com", "hunter2pw", "Mover")

	rec := doJSON(t, r, http.MethodPatch, "/api/v1/users/me", token,
		map[string]string{"email": "taken@example.com", "currentPassword": "hunter2pw"})
	if rec.Code != http.StatusConflict {
		t.Fatalf("expected 409, got %d (%s)", rec.Code, rec.Body.String())
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
