package api

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"
	"time"

	"github.com/plasma/fh-mahjong/internal/storage"
	"golang.org/x/crypto/bcrypt"
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

func newPasswordResetFixture(t *testing.T) *resetFixture {
	t.Helper()
	base := newAuthSessionFixture(t)
	sender := &captureSender{}
	base.handler.Mail = sender
	return &resetFixture{authSessionFixture: base, mail: sender}
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
	if err := bcrypt.CompareHashAndPassword([]byte(stored.CodeHash), []byte(sent[0].Code)); err != nil {
		t.Fatalf("stored hash does not verify against the sent code: %v", err)
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

// The one deliberate exception to the identical-failure rule: a new password
// that fails the length policy reports the binding error, because password
// policy feedback discloses nothing about the account.
func TestPasswordResetConfirmReportsShortPasswordDistinctly(t *testing.T) {
	fx := newPasswordResetFixture(t)
	registerWithEmail(t, fx, "Short Wind", "short@example.com")
	requestReset(t, fx, "Short Wind")
	code := fx.mail.messages()[0].Code

	rec := confirmReset(t, fx, "Short Wind", code, "short")
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("short password = %d, want 400: %s", rec.Code, rec.Body.String())
	}
	var payload map[string]string
	_ = json.Unmarshal(rec.Body.Bytes(), &payload)
	if payload["error"] == passwordResetGenericError {
		t.Fatalf("a short password must not be reported as an invalid code: %q", payload["error"])
	}
	if payload["error"] == "" {
		t.Fatalf("expected a binding error message, got %s", rec.Body.String())
	}

	var record storage.PasswordResetCode
	if err := fx.db.Order("id DESC").First(&record).Error; err != nil {
		t.Fatalf("load code: %v", err)
	}
	if record.Attempts != 0 {
		t.Fatalf("attempts = %d, want 0 — a malformed request must not spend a guess", record.Attempts)
	}

	// The rejection is a binding failure before any DB access, so the code
	// must still be live: a later confirm with a valid password succeeds.
	retry := confirmReset(t, fx, "Short Wind", code, "brand-new-pw")
	if retry.Code != http.StatusNoContent {
		t.Fatalf("confirm after short-password rejection = %d, want 204: %s", retry.Code, retry.Body.String())
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

// The 5-attempt cap must hold when guesses arrive together, not just in
// sequence: bcrypt sits inside the check-then-act window, so a stale read
// would let every concurrent request through a budget of five.
func TestPasswordResetConfirmCapHoldsUnderConcurrentGuesses(t *testing.T) {
	fx := newPasswordResetFixture(t)
	registerWithEmail(t, fx, "Swarm Wind", "swarm@example.com")
	requestReset(t, fx, "Swarm Wind")

	const guesses = 12
	var wg sync.WaitGroup
	for i := 0; i < guesses; i++ {
		wg.Add(1)
		go func(n int) {
			defer wg.Done()
			confirmReset(t, fx, "Swarm Wind", fmt.Sprintf("%06d", 900000+n), "brand-new-pw")
		}(i)
	}
	wg.Wait()

	var record storage.PasswordResetCode
	if err := fx.db.Order("id DESC").First(&record).Error; err != nil {
		t.Fatalf("load code: %v", err)
	}
	if record.Attempts != passwordResetMaxAttempts {
		t.Fatalf("attempts = %d, want exactly %d — the cap must be spent, and never exceeded",
			record.Attempts, passwordResetMaxAttempts)
	}
}

// Changing the address must retire a code already sent to the old one.
func TestChangingEmailRetiresOutstandingResetCodes(t *testing.T) {
	fx := newPasswordResetFixture(t)
	cookie, csrf := registerWithEmail(t, fx, "Moved Wind", "old@example.com")
	requestReset(t, fx, "Moved Wind")
	code := fx.mail.messages()[0].Code

	changed := authRequest(t, fx.router, http.MethodPatch, "/api/v1/users/me",
		`{"email":"new@example.com","currentPassword":"hunter2pw"}`, cookie, csrf)
	if changed.Code != http.StatusOK {
		t.Fatalf("change email = %d: %s", changed.Code, changed.Body.String())
	}

	if rec := confirmReset(t, fx, "Moved Wind", code, "brand-new-pw"); rec.Code != http.StatusBadRequest {
		t.Fatalf("code issued to the old address = %d, want 400", rec.Code)
	}
}

// Clearing the address is the case this retirement exists for: someone wipes
// an address precisely because they lost control of that inbox, and a code
// already sent there must stop working immediately.
func TestClearingEmailRetiresOutstandingResetCodes(t *testing.T) {
	fx := newPasswordResetFixture(t)
	cookie, csrf := registerWithEmail(t, fx, "Wiped Wind", "wiped@example.com")
	requestReset(t, fx, "Wiped Wind")
	code := fx.mail.messages()[0].Code

	cleared := authRequest(t, fx.router, http.MethodPatch, "/api/v1/users/me",
		`{"email":"","currentPassword":"hunter2pw"}`, cookie, csrf)
	if cleared.Code != http.StatusOK {
		t.Fatalf("clear email = %d: %s", cleared.Code, cleared.Body.String())
	}

	if rec := confirmReset(t, fx, "Wiped Wind", code, "brand-new-pw"); rec.Code != http.StatusBadRequest {
		t.Fatalf("code issued before the address was cleared = %d, want 400", rec.Code)
	}
}
