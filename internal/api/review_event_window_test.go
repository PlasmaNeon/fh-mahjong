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
			name:          "policy URL equals RL_AGENT_POLICY_URL -> inherits RL window",
			policyURL:     "http://shared.example/act",
			rlOverride:    "http://shared.example/act",
			rlEventWindow: "128",
			want:          128,
		},
		{
			name:          "policy URL equals AI_BOT_POLICY_URL fallback (no RL override) -> inherits RL window",
			policyURL:     "http://shared.example/act",
			aiBotURL:      "http://shared.example/act",
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
