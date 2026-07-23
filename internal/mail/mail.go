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
