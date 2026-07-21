package main

import (
	"bytes"
	"fmt"
	"log"
	"strings"
	"testing"
	"time"

	"github.com/plasma/fh-mahjong/internal/bot/remote"
	"github.com/plasma/fh-mahjong/internal/rl"
)

// TestParseEventWindowEnv covers the shared event-window env-var parser used
// for both RL_AGENT_EVENT_WINDOW (the primary serving contract) and
// RL_AGENT_SHADOW_EVENT_WINDOW (via shadowEventWindow), including the upper
// bound shared with internal/rl.MaxEventHistoryWindow (internal/rl/env.go,
// internal/rl/searchpool.go) and internal/api's reviewEventWindow, which this
// mirrors. Values above the bound are rejected (fall back to defaultWindow),
// matching the non-numeric fallback — never silently clamped.
func TestParseEventWindowEnv(t *testing.T) {
	const envVar = "FH_TEST_EVENT_WINDOW"
	const defaultWindow = uint32(7)

	tests := []struct {
		name string
		env  string // not set when name == "unset"
		set  bool
		want uint32
	}{
		{name: "unset", set: false, want: defaultWindow},
		{name: "empty string", set: true, env: "", want: defaultWindow},
		{name: "valid value", set: true, env: "8", want: 8},
		{name: "zero", set: true, env: "0", want: 0},
		{name: "non-numeric", set: true, env: "banana", want: defaultWindow},
		{name: "negative", set: true, env: "-1", want: defaultWindow},
		{name: "at max bound", set: true, env: fmt.Sprintf("%d", rl.MaxEventHistoryWindow), want: rl.MaxEventHistoryWindow},
		{name: "over max bound", set: true, env: fmt.Sprintf("%d", rl.MaxEventHistoryWindow+1), want: defaultWindow},
		{name: "far over max bound", set: true, env: "999999", want: defaultWindow},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			if tc.set {
				t.Setenv(envVar, tc.env)
			} else {
				t.Setenv(envVar, "")
				// t.Setenv can't unset; parseEventWindowEnv treats "" same as unset.
			}
			if got := parseEventWindowEnv(envVar, defaultWindow); got != tc.want {
				t.Fatalf("parseEventWindowEnv(%q, %d) with env=%q = %d, want %d", envVar, defaultWindow, tc.env, got, tc.want)
			}
		})
	}
}

// TestRLAgentEventWindowDefaultsToZero pins that RL_AGENT_EVENT_WINDOW (the
// primary serving contract's window, read once in main()) defaults to 0 —
// event-free, byte-identical to pre-event-contract behavior — same as
// internal/api's reviewEventWindow, unlike RL_AGENT_SHADOW_EVENT_WINDOW which
// defaults to defaultShadowEventWindow (128).
func TestRLAgentEventWindowDefaultsToZero(t *testing.T) {
	t.Setenv("RL_AGENT_EVENT_WINDOW", "")
	if got := parseEventWindowEnv("RL_AGENT_EVENT_WINDOW", 0); got != 0 {
		t.Fatalf("parseEventWindowEnv(RL_AGENT_EVENT_WINDOW, 0) unset = %d, want 0", got)
	}
}

// TestValidatePolicyContractAsync_NilPolicyDoesNotPanic covers the guard
// clause: a nil *remote.HTTPPolicy (e.g. shadow disabled) must be a no-op,
// never a nil-pointer panic at startup.
func TestValidatePolicyContractAsync_NilPolicyDoesNotPanic(t *testing.T) {
	validatePolicyContractAsync("nil policy", nil)
}

// TestValidatePolicyContractAsync_UnreachableLogsLoudlyWithoutBlocking pins
// finding 2's contract: ValidateServer failure (here, an endpoint nothing is
// listening on) must be logged LOUDLY with the "POLICY CONTRACT MISMATCH"
// wording the on-call runbook greps for, but must never crash/panic the
// caller — startup continues regardless, since the policy server may simply
// not be up yet.
func TestValidatePolicyContractAsync_UnreachableLogsLoudlyWithoutBlocking(t *testing.T) {
	var buf bytes.Buffer
	origOutput := log.Writer()
	origFlags := log.Flags()
	log.SetOutput(&buf)
	log.SetFlags(0)
	defer func() {
		log.SetOutput(origOutput)
		log.SetFlags(origFlags)
	}()

	// Nothing listens on this endpoint; ValidateServer fails fast (connection
	// refused) well within its own internal timeout.
	policy := remote.NewHTTPPolicy("http://127.0.0.1:1/act")
	validatePolicyContractAsync("test policy", policy)

	deadline := time.Now().Add(5 * time.Second)
	for time.Now().Before(deadline) {
		if strings.Contains(buf.String(), "POLICY CONTRACT MISMATCH") {
			break
		}
		time.Sleep(10 * time.Millisecond)
	}

	got := buf.String()
	if !strings.Contains(got, "POLICY CONTRACT MISMATCH") {
		t.Fatalf("expected a loud POLICY CONTRACT MISMATCH log line, got: %q", got)
	}
	if !strings.Contains(got, "test policy") {
		t.Fatalf("expected the log line to carry the label %q, got: %q", "test policy", got)
	}
}
