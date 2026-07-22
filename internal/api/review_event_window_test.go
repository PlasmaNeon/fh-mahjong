package api

import (
	"fmt"
	"testing"

	"github.com/plasma/fh-mahjong/internal/rl"
)

// clearReviewEventWindowEnv resets every env var reviewEventWindow consults so
// tests don't leak state across each other (t.Setenv can't unset, only set to
// "", which every one of these vars treats as unset).
func clearReviewEventWindowEnv(t *testing.T) {
	t.Helper()
	t.Setenv("REVIEW_EVENT_WINDOW", "")
	t.Setenv("RL_AGENT_EVENT_WINDOW", "")
	t.Setenv("RL_AGENT_POLICY_URL", "")
	t.Setenv("AI_BOT_POLICY_URL", "")
}

// TestReviewEventWindow covers reviewEventWindow's fallback to
// RL_AGENT_EVENT_WINDOW when REVIEW_EVENT_WINDOW is unset and POLICY_SERVER_URL
// is unset/empty (the common single-server case), including the upper bound
// shared with internal/rl.MaxEventHistoryWindow (internal/rl/env.go,
// internal/rl/searchpool.go). Values above the bound are rejected (fall back
// to 0), matching the non-numeric fallback — never silently clamped.
func TestReviewEventWindow(t *testing.T) {
	tests := []struct {
		name string
		env  string // not set when name == "unset"
		set  bool
		want uint32
	}{
		{name: "unset", set: false, want: 0},
		{name: "empty string", set: true, env: "", want: 0},
		{name: "valid value", set: true, env: "8", want: 8},
		{name: "non-numeric", set: true, env: "banana", want: 0},
		{name: "negative", set: true, env: "-1", want: 0},
		{name: "at max bound", set: true, env: fmt.Sprintf("%d", rl.MaxEventHistoryWindow), want: rl.MaxEventHistoryWindow},
		{name: "over max bound", set: true, env: fmt.Sprintf("%d", rl.MaxEventHistoryWindow+1), want: 0},
		{name: "far over max bound", set: true, env: "999999", want: 0},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			clearReviewEventWindowEnv(t)
			if tc.set {
				t.Setenv("RL_AGENT_EVENT_WINDOW", tc.env)
			}
			// POLICY_SERVER_URL unset -> fallback to RL_AGENT_EVENT_WINDOW is
			// always eligible regardless of RL_AGENT_POLICY_URL/AI_BOT_POLICY_URL.
			if got := reviewEventWindow(""); got != tc.want {
				t.Fatalf("reviewEventWindow(\"\") with RL_AGENT_EVENT_WINDOW=%q = %d, want %d", tc.env, got, tc.want)
			}
		})
	}
}

// TestReviewEventWindow_ExplicitEnvWins pins adversarial round 7, Finding 2:
// REVIEW_EVENT_WINDOW, when set, governs the review client's window
// regardless of RL_AGENT_EVENT_WINDOW — the review policy client talks to
// POLICY_SERVER_URL, which may be a different server/checkpoint than the
// RL_AGENT_POLICY_URL/AI_BOT_POLICY_URL endpoint RL_AGENT_EVENT_WINDOW
// describes.
func TestReviewEventWindow_ExplicitEnvWins(t *testing.T) {
	clearReviewEventWindowEnv(t)
	t.Setenv("REVIEW_EVENT_WINDOW", "8")
	t.Setenv("RL_AGENT_EVENT_WINDOW", "128")
	t.Setenv("POLICY_SERVER_URL", "http://policy.example/evaluate")
	t.Setenv("RL_AGENT_POLICY_URL", "http://rl.example/act")

	if got := reviewEventWindow("http://policy.example/evaluate"); got != 8 {
		t.Fatalf("reviewEventWindow with REVIEW_EVENT_WINDOW=8 = %d, want 8 (must not inherit RL_AGENT_EVENT_WINDOW)", got)
	}
}

// TestReviewEventWindow_ExplicitEnvBoundsEnforced pins that REVIEW_EVENT_WINDOW
// is subject to the same rl.MaxEventHistoryWindow bound as every other
// event-window env var in this codebase — an out-of-bound value is rejected
// outright (falls back to 0), never silently clamped, and never falls through
// to RL_AGENT_EVENT_WINDOW instead.
func TestReviewEventWindow_ExplicitEnvBoundsEnforced(t *testing.T) {
	clearReviewEventWindowEnv(t)
	t.Setenv("REVIEW_EVENT_WINDOW", fmt.Sprintf("%d", rl.MaxEventHistoryWindow+1))
	t.Setenv("RL_AGENT_EVENT_WINDOW", "64")

	if got := reviewEventWindow(""); got != 0 {
		t.Fatalf("reviewEventWindow with out-of-bound REVIEW_EVENT_WINDOW = %d, want 0 (rejected, not clamped, not falling back to RL_AGENT_EVENT_WINDOW)", got)
	}
}

// TestReviewEventWindow_FallbackGatedByPolicyURL pins the other half of
// Finding 2: when REVIEW_EVENT_WINDOW is unset, inheriting RL_AGENT_EVENT_WINDOW
// is only safe when POLICY_SERVER_URL is unset/empty OR equals the resolved RL
// agent endpoint (RL_AGENT_POLICY_URL, else AI_BOT_POLICY_URL) — i.e. review
// traffic and RL traffic actually hit the same service. When POLICY_SERVER_URL
// points at a genuinely different server, the fallback must NOT inherit
// RL_AGENT_EVENT_WINDOW (defaults to 0 instead), matching the fail-closed
// contract resolveAIBotEventWindow already established in cmd/server.
func TestReviewEventWindow_FallbackGatedByPolicyURL(t *testing.T) {
	tests := []struct {
		name          string
		policyURL     string
		rlOverride    string
		aiBotURL      string
		rlEventWindow string
		want          uint32
	}{
		{
			name:          "policy URL unset -> inherits RL window",
			policyURL:     "",
			rlOverride:    "http://rl.example/act",
			rlEventWindow: "128",
			want:          128,
		},
		{
			name:          "policy URL equals RL_AGENT_POLICY_URL literally -> inherits RL window",
			policyURL:     "http://shared.example",
			rlOverride:    "http://shared.example",
			rlEventWindow: "128",
			want:          128,
		},
		{
			name:          "policy URL equals AI_BOT_POLICY_URL fallback (no RL override) -> inherits RL window",
			policyURL:     "http://shared.example",
			aiBotURL:      "http://shared.example",
			rlEventWindow: "128",
			want:          128,
		},
		{
			name:          "policy URL differs from resolved RL endpoint -> fails closed to 0",
			policyURL:     "http://review-only.example/evaluate",
			rlOverride:    "http://rl.example/act",
			rlEventWindow: "128",
			want:          0,
		},
		{
			// Production-shaped same-service config: POLICY_SERVER_URL is a
			// BASE URL (HTTPPolicyClient appends "/evaluate"), while
			// RL_AGENT_POLICY_URL ends in "/act". Round 8 finding: comparing
			// these literally treats them as different services and forces
			// the window to 0. They must be recognized as the same service.
			name:          "base policy URL vs RL /act endpoint, same host -> inherits RL window",
			policyURL:     "http://policy:8765",
			rlOverride:    "http://policy:8765/act",
			rlEventWindow: "128",
			want:          128,
		},
		{
			name:          "base policy URL with trailing slash vs RL /act endpoint -> inherits RL window",
			policyURL:     "http://policy:8765/",
			rlOverride:    "http://policy:8765/act",
			rlEventWindow: "128",
			want:          128,
		},
		{
			name:          "base policy URL vs RL /act/ endpoint with trailing slash -> inherits RL window",
			policyURL:     "http://policy:8765",
			rlOverride:    "http://policy:8765/act/",
			rlEventWindow: "128",
			want:          128,
		},
		{
			name:          "same path shape but different host -> fails closed to 0",
			policyURL:     "http://policy-a:8765",
			rlOverride:    "http://policy-b:8765/act",
			rlEventWindow: "128",
			want:          0,
		},
		{
			name:          "unparseable policy URL -> fails closed to 0",
			policyURL:     "http://policy:8765\x7f",
			rlOverride:    "http://policy:8765/act",
			rlEventWindow: "128",
			want:          0,
		},
		{
			name:          "unparseable RL endpoint -> fails closed to 0",
			policyURL:     "http://policy:8765",
			rlOverride:    "http://policy:8765/act\x7f",
			rlEventWindow: "128",
			want:          0,
		},
		{
			// Adversarial round 11: with RL_AGENT_POLICY_URL and
			// AI_BOT_POLICY_URL both unset, cmd/server still resolves the RL
			// endpoint to the local default (remote.DefaultRLPolicyURL,
			// http://127.0.0.1:8765/act) rather than "no RL endpoint at
			// all". A POLICY_SERVER_URL pointed at a genuinely different
			// service during a staggered rollout must still fail closed to
			// 0, not inherit RL_AGENT_EVENT_WINDOW just because both
			// overrides happened to be unset.
			name:          "both RL overrides unset, POLICY_SERVER_URL is a different service -> fails closed to 0",
			policyURL:     "http://other:9999",
			rlEventWindow: "128",
			want:          0,
		},
		{
			// Same round-11 gap, other side: both RL overrides unset means
			// the resolved RL endpoint is the local default
			// (http://127.0.0.1:8765/act); POLICY_SERVER_URL naming that
			// same local default must still inherit RL_AGENT_EVENT_WINDOW.
			name:          "both RL overrides unset, POLICY_SERVER_URL matches the local default -> inherits RL window",
			policyURL:     "http://127.0.0.1:8765",
			rlEventWindow: "128",
			want:          128,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			clearReviewEventWindowEnv(t)
			t.Setenv("RL_AGENT_EVENT_WINDOW", tc.rlEventWindow)
			t.Setenv("RL_AGENT_POLICY_URL", tc.rlOverride)
			t.Setenv("AI_BOT_POLICY_URL", tc.aiBotURL)

			if got := reviewEventWindow(tc.policyURL); got != tc.want {
				t.Fatalf("reviewEventWindow(%q) = %d, want %d", tc.policyURL, got, tc.want)
			}
		})
	}
}
