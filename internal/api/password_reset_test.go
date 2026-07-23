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
