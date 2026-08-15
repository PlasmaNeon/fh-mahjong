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

// SuppressedSender accepts a code and deliberately drops it, recording only
// that an attempt happened. Production wires this while no real provider is
// configured: LogSender's plaintext code in an application log would be a
// standing account-takeover path for anyone who can read logs, and with no
// provider the code could never reach the recipient regardless.
type SuppressedSender struct{}

// SendPasswordResetCode discards the code and records only that one was
// requested. The recipient is omitted too — it is the account identity.
func (SuppressedSender) SendPasswordResetCode(_ context.Context, _, _ string) error {
	log.Printf("mail: password reset code requested but no provider is configured; code suppressed")
	return nil
}
