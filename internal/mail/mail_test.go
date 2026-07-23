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
// into later. This is a compile-time assertion — a runtime nil check would
// assert nothing, because a non-pointer value assigned to an interface is
// never nil.
var _ Sender = LogSender{}
