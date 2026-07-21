package api

import (
	"fmt"
	"testing"

	"github.com/plasma/fh-mahjong/internal/rl"
)

// TestReviewEventWindow covers reviewEventWindow's parsing of
// RL_AGENT_EVENT_WINDOW, including the upper bound shared with
// internal/rl.MaxEventHistoryWindow (internal/rl/env.go, internal/rl/searchpool.go).
// Values above the bound are rejected (fall back to 0), matching the
// non-numeric fallback — never silently clamped.
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
			if tc.set {
				t.Setenv("RL_AGENT_EVENT_WINDOW", tc.env)
			} else {
				t.Setenv("RL_AGENT_EVENT_WINDOW", "")
				// t.Setenv can't unset; reviewEventWindow treats "" same as unset.
			}
			if got := reviewEventWindow(); got != tc.want {
				t.Fatalf("reviewEventWindow() with RL_AGENT_EVENT_WINDOW=%q = %d, want %d", tc.env, got, tc.want)
			}
		})
	}
}
