package api

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/glebarez/sqlite"
	"github.com/plasma/fh-mahjong/internal/storage"
	"golang.org/x/crypto/bcrypt"
	"gorm.io/gorm"
)

type authSessionFixture struct {
	router *gin.Engine
	db     *gorm.DB
}

func TestLoginDummyHashEqualizesTiming(t *testing.T) {
	cost, err := bcrypt.Cost(dummyPasswordHash)
	if err != nil || cost != bcrypt.DefaultCost {
		t.Fatalf("dummy bcrypt cost = %d, err=%v", cost, err)
	}
}

func newAuthSessionFixture(t *testing.T) authSessionFixture {
	t.Helper()
	gin.SetMode(gin.TestMode)
	db, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	if err := storage.AutoMigrate(db); err != nil {
		t.Fatalf("migrate: %v", err)
	}
	h := &AuthHandler{DB: db}
	r := gin.New()
	r.POST("/api/v1/auth/register", h.Register)
	r.POST("/api/v1/auth/login", h.Login)
	r.GET("/api/v1/auth/session", AuthMiddleware(db), h.Session)
	r.DELETE("/api/v1/auth/session", AuthMiddleware(db), h.Logout)
	r.PATCH("/api/v1/users/me", AuthMiddleware(db), h.UpdateMe)
	return authSessionFixture{router: r, db: db}
}

func authRequest(t *testing.T, r http.Handler, method, path, body string, cookie *http.Cookie, csrf string) *httptest.ResponseRecorder {
	t.Helper()
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(method, path, strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	if cookie != nil {
		req.AddCookie(cookie)
	}
	if csrf != "" {
		req.Header.Set(csrfHeaderName, csrf)
	}
	r.ServeHTTP(rec, req)
	return rec
}

func sessionCookieFrom(t *testing.T, rec *httptest.ResponseRecorder) *http.Cookie {
	t.Helper()
	for _, cookie := range rec.Result().Cookies() {
		if cookie.Name == devSessionCookieName || cookie.Name == prodSessionCookieName {
			return cookie
		}
	}
	t.Fatalf("response did not set a session cookie: %v", rec.Header().Values("Set-Cookie"))
	return nil
}

func TestRegisterCreatesPersistentHttpOnlySessionWithoutReturningToken(t *testing.T) {
	fx := newAuthSessionFixture(t)
	rec := authRequest(t, fx.router, http.MethodPost, "/api/v1/auth/register",
		`{"username":"Rain Player","password":"hunter2pw"}`, nil, "")
	if rec.Code != http.StatusCreated {
		t.Fatalf("register = %d, body=%s", rec.Code, rec.Body.String())
	}
	if strings.Contains(rec.Body.String(), `"token"`) {
		t.Fatalf("auth response must not expose a credential: %s", rec.Body.String())
	}
	cookie := sessionCookieFrom(t, rec)
	if !cookie.HttpOnly || cookie.Path != "/" || cookie.MaxAge != int(sessionTTL.Seconds()) || cookie.SameSite != http.SameSiteLaxMode {
		t.Fatalf("unexpected cookie attributes: %#v", cookie)
	}
	if cookie.Value == "" {
		t.Fatal("session cookie value is empty")
	}

	var sessions []storage.UserSession
	if err := fx.db.Find(&sessions).Error; err != nil || len(sessions) != 1 {
		t.Fatalf("sessions = %d, err=%v", len(sessions), err)
	}
	hash := sha256.Sum256([]byte(cookie.Value))
	if sessions[0].TokenHash != hex.EncodeToString(hash[:]) {
		t.Fatal("database must store the session token hash, not the raw cookie")
	}
	if strings.Contains(sessions[0].TokenHash, cookie.Value) {
		t.Fatal("stored token hash contains the raw cookie")
	}
}

func TestProductionSessionUsesSecureHostCookie(t *testing.T) {
	t.Setenv("APP_ENV", "production")
	fx := newAuthSessionFixture(t)
	rec := authRequest(t, fx.router, http.MethodPost, "/api/v1/auth/register",
		`{"username":"Secure Wind","password":"hunter2pw"}`, nil, "")
	cookie := sessionCookieFrom(t, rec)
	if cookie.Name != prodSessionCookieName || !cookie.Secure || !cookie.HttpOnly {
		t.Fatalf("production cookie = %#v", cookie)
	}
}

func TestProductionDoesNotAuthenticateDevelopmentCookieName(t *testing.T) {
	fx := newAuthSessionFixture(t)
	registered := authRequest(t, fx.router, http.MethodPost, "/api/v1/auth/register",
		`{"username":"Cookie Wind","password":"hunter2pw"}`, nil, "")
	developmentCookie := sessionCookieFrom(t, registered)
	if developmentCookie.Name != devSessionCookieName {
		t.Fatalf("development cookie name = %q", developmentCookie.Name)
	}

	t.Setenv("APP_ENV", "production")
	bootstrap := authRequest(t, fx.router, http.MethodGet, "/api/v1/auth/session", "", developmentCookie, "")
	if bootstrap.Code != http.StatusUnauthorized {
		t.Fatalf("development cookie authenticated in production: %d", bootstrap.Code)
	}
}

func TestExpiredSessionIsDeleted(t *testing.T) {
	fx := newAuthSessionFixture(t)
	registered := authRequest(t, fx.router, http.MethodPost, "/api/v1/auth/register",
		`{"username":"Old Wind","password":"hunter2pw"}`, nil, "")
	cookie := sessionCookieFrom(t, registered)
	if err := fx.db.Model(&storage.UserSession{}).Where("token_hash = ?", hashSessionToken(cookie.Value)).Update("expires_at", time.Now().Add(-time.Minute)).Error; err != nil {
		t.Fatalf("expire session: %v", err)
	}
	bootstrap := authRequest(t, fx.router, http.MethodGet, "/api/v1/auth/session", "", cookie, "")
	if bootstrap.Code != http.StatusUnauthorized {
		t.Fatalf("expired session = %d, want 401", bootstrap.Code)
	}
	var count int64
	_ = fx.db.Model(&storage.UserSession{}).Where("token_hash = ?", hashSessionToken(cookie.Value)).Count(&count).Error
	if count != 0 {
		t.Fatal("expired session row was not deleted")
	}
}

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

func TestRegisterRejectsDuplicateUsernameCaseInsensitively(t *testing.T) {
	fx := newAuthSessionFixture(t)
	first := authRequest(t, fx.router, http.MethodPost, "/api/v1/auth/register",
		`{"username":"River Wind","password":"hunter2pw"}`, nil, "")
	if first.Code != http.StatusCreated {
		t.Fatalf("first registration = %d: %s", first.Code, first.Body.String())
	}
	second := authRequest(t, fx.router, http.MethodPost, "/api/v1/auth/register",
		`{"username":"RIVER WIND","password":"hunter2pw"}`, nil, "")
	if second.Code != http.StatusConflict {
		t.Fatalf("duplicate username = %d: %s", second.Code, second.Body.String())
	}
}

func TestRegisterAcceptsLegacyDisplayNameAndRejectsAtSign(t *testing.T) {
	fx := newAuthSessionFixture(t)
	legacy := authRequest(t, fx.router, http.MethodPost, "/api/v1/auth/register",
		`{"displayName":"Legacy Name","password":"hunter2pw"}`, nil, "")
	if legacy.Code != http.StatusCreated {
		t.Fatalf("legacy registration = %d: %s", legacy.Code, legacy.Body.String())
	}
	bad := authRequest(t, fx.router, http.MethodPost, "/api/v1/auth/register",
		`{"username":"bad@name","password":"hunter2pw"}`, nil, "")
	if bad.Code != http.StatusBadRequest {
		t.Fatalf("username containing @ = %d: %s", bad.Code, bad.Body.String())
	}
	disagree := authRequest(t, fx.router, http.MethodPost, "/api/v1/auth/register",
		`{"username":"Canonical","displayName":"Legacy","password":"hunter2pw"}`, nil, "")
	if disagree.Code != http.StatusBadRequest {
		t.Fatalf("disagreeing registration aliases = %d: %s", disagree.Code, disagree.Body.String())
	}
}

func TestLoginRejectsDisagreeingCanonicalAndLegacyIdentifiers(t *testing.T) {
	fx := newAuthSessionFixture(t)
	rec := authRequest(t, fx.router, http.MethodPost, "/api/v1/auth/login",
		`{"identifier":"one","email":"two@example.com","password":"hunter2pw"}`, nil, "")
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("disagreeing login aliases = %d: %s", rec.Code, rec.Body.String())
	}
}

func TestProfileMapsUsernameConflictAndAcceptsLegacyAlias(t *testing.T) {
	fx := newAuthSessionFixture(t)
	first := authRequest(t, fx.router, http.MethodPost, "/api/v1/auth/register",
		`{"username":"First Wind","password":"hunter2pw"}`, nil, "")
	if first.Code != http.StatusCreated {
		t.Fatalf("first registration = %d: %s", first.Code, first.Body.String())
	}
	second := authRequest(t, fx.router, http.MethodPost, "/api/v1/auth/register",
		`{"username":"Second Wind","password":"hunter2pw"}`, nil, "")
	secondCookie := sessionCookieFrom(t, second)
	var session AuthResponse
	if err := decodeJSONBody(second.Body.Bytes(), &session); err != nil {
		t.Fatalf("decode second registration: %v", err)
	}

	conflict := authRequest(t, fx.router, http.MethodPatch, "/api/v1/users/me",
		`{"username":"FIRST WIND"}`, secondCookie, session.CSRFToken)
	if conflict.Code != http.StatusConflict {
		t.Fatalf("profile username conflict = %d: %s", conflict.Code, conflict.Body.String())
	}
	disagree := authRequest(t, fx.router, http.MethodPatch, "/api/v1/users/me",
		`{"username":"Third Wind","displayName":"Fourth Wind"}`, secondCookie, session.CSRFToken)
	if disagree.Code != http.StatusBadRequest {
		t.Fatalf("profile alias disagreement = %d: %s", disagree.Code, disagree.Body.String())
	}
	legacy := authRequest(t, fx.router, http.MethodPatch, "/api/v1/users/me",
		`{"displayName":"Third Wind"}`, secondCookie, session.CSRFToken)
	if legacy.Code != http.StatusOK || !strings.Contains(legacy.Body.String(), `"username":"Third Wind"`) {
		t.Fatalf("legacy profile alias = %d: %s", legacy.Code, legacy.Body.String())
	}
}

func TestProfileEmailChangeRequiresCurrentPassword(t *testing.T) {
	fx := newAuthSessionFixture(t)
	registered := authRequest(t, fx.router, http.MethodPost, "/api/v1/auth/register",
		`{"username":"Email Wind","password":"hunter2pw"}`, nil, "")
	cookie := sessionCookieFrom(t, registered)
	var session AuthResponse
	if err := decodeJSONBody(registered.Body.Bytes(), &session); err != nil {
		t.Fatalf("decode registration: %v", err)
	}
	missing := authRequest(t, fx.router, http.MethodPatch, "/api/v1/users/me",
		`{"email":"new-email@example.com"}`, cookie, session.CSRFToken)
	if missing.Code != http.StatusBadRequest {
		t.Fatalf("email change without password = %d: %s", missing.Code, missing.Body.String())
	}
	changed := authRequest(t, fx.router, http.MethodPatch, "/api/v1/users/me",
		`{"email":"new-email@example.com","currentPassword":"hunter2pw"}`, cookie, session.CSRFToken)
	if changed.Code != http.StatusOK || !strings.Contains(changed.Body.String(), `"email":"new-email@example.com"`) {
		t.Fatalf("email change = %d: %s", changed.Code, changed.Body.String())
	}
}

func TestUnknownAndWrongPasswordShareGenericError(t *testing.T) {
	fx := newAuthSessionFixture(t)
	authRequest(t, fx.router, http.MethodPost, "/api/v1/auth/register",
		`{"username":"Known","password":"hunter2pw"}`, nil, "")
	var messages []string
	for _, body := range []string{
		`{"identifier":"missing","password":"hunter2pw"}`,
		`{"identifier":"Known","password":"wrongpass"}`,
	} {
		rec := authRequest(t, fx.router, http.MethodPost, "/api/v1/auth/login", body, nil, "")
		if rec.Code != http.StatusUnauthorized {
			t.Fatalf("failed login = %d: %s", rec.Code, rec.Body.String())
		}
		var payload map[string]string
		_ = json.Unmarshal(rec.Body.Bytes(), &payload)
		messages = append(messages, payload["error"])
	}
	if messages[0] != "Invalid username/email or password" || messages[1] != messages[0] {
		t.Fatalf("generic errors = %#v", messages)
	}
}

func TestSessionBootstrapAndMutationsRequireCSRF(t *testing.T) {
	fx := newAuthSessionFixture(t)
	register := authRequest(t, fx.router, http.MethodPost, "/api/v1/auth/register",
		`{"username":"Jade","password":"hunter2pw"}`, nil, "")
	cookie := sessionCookieFrom(t, register)

	bootstrap := authRequest(t, fx.router, http.MethodGet, "/api/v1/auth/session", "", cookie, "")
	if bootstrap.Code != http.StatusOK || !strings.Contains(bootstrap.Body.String(), `"csrfToken"`) {
		t.Fatalf("session bootstrap = %d: %s", bootstrap.Code, bootstrap.Body.String())
	}
	var payload AuthResponse
	if err := decodeJSONBody(bootstrap.Body.Bytes(), &payload); err != nil {
		t.Fatalf("decode session: %v", err)
	}
	if payload.CSRFToken == "" {
		t.Fatal("session response missing CSRF token")
	}

	missing := authRequest(t, fx.router, http.MethodPatch, "/api/v1/users/me", `{"username":"Jade Rain"}`, cookie, "")
	if missing.Code != http.StatusForbidden {
		t.Fatalf("mutation without CSRF = %d, want 403", missing.Code)
	}
	good := authRequest(t, fx.router, http.MethodPatch, "/api/v1/users/me", `{"username":"Jade Rain"}`, cookie, payload.CSRFToken)
	if good.Code != http.StatusOK {
		t.Fatalf("mutation with CSRF = %d: %s", good.Code, good.Body.String())
	}
}

func TestLogoutRevokesCurrentSession(t *testing.T) {
	fx := newAuthSessionFixture(t)
	register := authRequest(t, fx.router, http.MethodPost, "/api/v1/auth/register",
		`{"username":"East Wind","password":"hunter2pw"}`, nil, "")
	cookie := sessionCookieFrom(t, register)
	var payload AuthResponse
	if err := decodeJSONBody(register.Body.Bytes(), &payload); err != nil {
		t.Fatalf("decode register: %v", err)
	}
	logout := authRequest(t, fx.router, http.MethodDelete, "/api/v1/auth/session", "", cookie, payload.CSRFToken)
	if logout.Code != http.StatusNoContent {
		t.Fatalf("logout = %d: %s", logout.Code, logout.Body.String())
	}
	bootstrap := authRequest(t, fx.router, http.MethodGet, "/api/v1/auth/session", "", cookie, "")
	if bootstrap.Code != http.StatusUnauthorized {
		t.Fatalf("revoked session bootstrap = %d, want 401", bootstrap.Code)
	}
	var count int64
	if err := fx.db.Model(&storage.UserSession{}).Count(&count).Error; err != nil || count != 0 {
		t.Fatalf("session count = %d, err=%v", count, err)
	}
}

func TestLogoutKeepsOtherDeviceSessionActive(t *testing.T) {
	fx := newAuthSessionFixture(t)
	first := authRequest(t, fx.router, http.MethodPost, "/api/v1/auth/register",
		`{"username":"Many Devices","password":"hunter2pw"}`, nil, "")
	firstCookie := sessionCookieFrom(t, first)
	var firstSession AuthResponse
	if err := decodeJSONBody(first.Body.Bytes(), &firstSession); err != nil {
		t.Fatalf("decode first session: %v", err)
	}
	second := authRequest(t, fx.router, http.MethodPost, "/api/v1/auth/login",
		`{"identifier":"Many Devices","password":"hunter2pw"}`, nil, "")
	secondCookie := sessionCookieFrom(t, second)

	logout := authRequest(t, fx.router, http.MethodDelete, "/api/v1/auth/session", "", firstCookie, firstSession.CSRFToken)
	if logout.Code != http.StatusNoContent {
		t.Fatalf("logout first device = %d: %s", logout.Code, logout.Body.String())
	}
	if got := authRequest(t, fx.router, http.MethodGet, "/api/v1/auth/session", "", firstCookie, ""); got.Code != http.StatusUnauthorized {
		t.Fatalf("first device after logout = %d", got.Code)
	}
	if got := authRequest(t, fx.router, http.MethodGet, "/api/v1/auth/session", "", secondCookie, ""); got.Code != http.StatusOK {
		t.Fatalf("second device after first logout = %d: %s", got.Code, got.Body.String())
	}
}

func decodeJSONBody(data []byte, target any) error {
	return json.Unmarshal(data, target)
}

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
