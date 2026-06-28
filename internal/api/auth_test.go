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
}

func TestLoginUnknownEmail(t *testing.T) {
	r, _ := newAuthTestRouter(t)
	rec := doJSON(t, r, http.MethodPost, "/api/v1/auth/login", "",
		map[string]string{"email": "nobody@example.com", "password": "hunter2pw"})
	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401, got %d", rec.Code)
	}
}

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
