package main

import (
	"bytes"
	"fmt"
	"log"
	"net/http"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/plasma/fh-mahjong/internal/bot"
	"github.com/plasma/fh-mahjong/internal/bot/remote"
	"github.com/plasma/fh-mahjong/internal/rl"
	pb "github.com/plasma/fh-mahjong/proto"
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

// TestResolveAIBotEventWindow pins adversarial round 6, Finding 1:
// AI_BOT_POLICY_URL (matchmaking bots) and RL_AGENT_POLICY_URL (private-room
// RL agent) can point at DIFFERENT services during a staggered rollout, so
// AI_BOT_EVENT_WINDOW must be resolvable independently of
// RL_AGENT_EVENT_WINDOW rather than always inheriting it. When
// AI_BOT_EVENT_WINDOW is unset, the only safe default is to inherit
// rlEventWindow when both URLs are the literal same non-empty string (single
// shared service); anything else (different services, or only one of the two
// configured) must fail closed to 0 rather than guess a contract the
// matchmaking bot policy might not actually speak.
func TestResolveAIBotEventWindow(t *testing.T) {
	tests := []struct {
		name                string
		aiBotPolicyURL      string
		rlPolicyURLOverride string
		rlEventWindow       uint32
		envAIBotWindow      string // "" means unset
		want                uint32
	}{
		{
			name:                "distinct URLs, AI_BOT_EVENT_WINDOW unset -> bot window 0",
			aiBotPolicyURL:      "http://bots.example/act",
			rlPolicyURLOverride: "http://rl.example/act",
			rlEventWindow:       128,
			want:                0,
		},
		{
			name:                "same URL, AI_BOT_EVENT_WINDOW unset -> inherits RL window",
			aiBotPolicyURL:      "http://shared.example/act",
			rlPolicyURLOverride: "http://shared.example/act",
			rlEventWindow:       128,
			want:                128,
		},
		{
			name:                "AI_BOT_POLICY_URL set, RL_AGENT_POLICY_URL not set -> bot window 0",
			aiBotPolicyURL:      "http://bots.example/act",
			rlPolicyURLOverride: "",
			rlEventWindow:       128,
			want:                0,
		},
		{
			name:                "explicit AI_BOT_EVENT_WINDOW honored even when URLs differ",
			aiBotPolicyURL:      "http://bots.example/act",
			rlPolicyURLOverride: "http://rl.example/act",
			rlEventWindow:       128,
			envAIBotWindow:      "128",
			want:                128,
		},
		{
			name:                "explicit AI_BOT_EVENT_WINDOW honored even when URLs equal",
			aiBotPolicyURL:      "http://shared.example/act",
			rlPolicyURLOverride: "http://shared.example/act",
			rlEventWindow:       64,
			envAIBotWindow:      "0",
			want:                0,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Setenv("AI_BOT_EVENT_WINDOW", tc.envAIBotWindow)
			got := resolveAIBotEventWindow(tc.aiBotPolicyURL, tc.rlPolicyURLOverride, tc.rlEventWindow)
			if got != tc.want {
				t.Fatalf("resolveAIBotEventWindow(%q, %q, %d) with AI_BOT_EVENT_WINDOW=%q = %d, want %d",
					tc.aiBotPolicyURL, tc.rlPolicyURLOverride, tc.rlEventWindow, tc.envAIBotWindow, got, tc.want)
			}
		})
	}
}

// TestValidatePolicyContractAsync_NilPolicyDoesNotPanic covers the guard
// clause: a nil *remote.HTTPPolicy (e.g. shadow disabled) must be a no-op,
// never a nil-pointer panic at startup.
func TestValidatePolicyContractAsync_NilPolicyDoesNotPanic(t *testing.T) {
	validatePolicyContractAsync("nil policy", nil)
}

// syncBuffer is a mutex-guarded bytes.Buffer: the validation goroutine
// spawned by validatePolicyContractAsync writes to the log output while the
// test goroutine polls it, so an unsynchronized bytes.Buffer is a data race
// under -race even though the test's assertions would still pass.
type syncBuffer struct {
	mu  sync.Mutex
	buf bytes.Buffer
}

func (b *syncBuffer) Write(p []byte) (int, error) {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.buf.Write(p)
}

func (b *syncBuffer) String() string {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.buf.String()
}

// TestValidatePolicyContractAsync_UnreachableLogsLoudlyWithoutBlocking pins
// finding 2's contract: ValidateServer failure (here, an endpoint nothing is
// listening on) must be logged LOUDLY with the "POLICY CONTRACT MISMATCH"
// wording the on-call runbook greps for, but must never crash/panic the
// caller — startup continues regardless, since the policy server may simply
// not be up yet.
func TestValidatePolicyContractAsync_UnreachableLogsLoudlyWithoutBlocking(t *testing.T) {
	var buf syncBuffer
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

// FINDING 2: the shadow candidate policy must be built with its fallback
// disabled — otherwise an unreachable/contract-rejecting candidate still
// returns a (heuristic) action on every decision, and ShadowPolicy's worker
// never sees the nil that would count it as a shadow error, masking the
// candidate being down from the runbook's zero-shadow-error gate.
func TestNewShadowHTTPPolicy_FallbackDisabled(t *testing.T) {
	policy := newShadowHTTPPolicy("http://127.0.0.1:1/act", &http.Client{}, 64)

	action := policy.ChooseAction(nil, 0) // nil state -> config-error fallback path
	if action != nil {
		t.Fatalf("expected nil action with fallback disabled, got %+v", action)
	}
	stats := policy.Stats()
	if stats.NoFallback != 1 {
		t.Fatalf("expected NoFallback=1 (fallback disabled), got %+v", stats)
	}
}

// TestNewSeatPolicyResolver_RLSeatsGetDistinctPrimaryInstances pins the
// regression fix: in a no-shadow config, two DIFFICULTY_RL resolutions from
// the SAME resolver must return two DISTINCT *remote.HTTPPolicy instances,
// never a shared one. Room.reconcileRLPolicyIDs (internal/api/room.go) reads
// each seat's policy's DecisionCounts/ObservedPolicyIDs to attribute paipu
// per seat; if the resolver ever went back to handing out one shared
// instance (as commit 2c45bed regressed to), one seat's fallback/reload
// counters would bleed into every other room's dataset, corrupting the
// pure-RL filter and checkpoint labeling server-lifetime-wide.
func TestNewSeatPolicyResolver_RLSeatsGetDistinctPrimaryInstances(t *testing.T) {
	resolver := newSeatPolicyResolver("http://127.0.0.1:1/act", &http.Client{}, 0, nil)

	first, err := resolver(pb.Difficulty_DIFFICULTY_RL, "room-1", 0)
	if err != nil {
		t.Fatalf("resolver first call: %v", err)
	}
	second, err := resolver(pb.Difficulty_DIFFICULTY_RL, "room-2", 1)
	if err != nil {
		t.Fatalf("resolver second call: %v", err)
	}

	firstPolicy, ok := first.(*remote.HTTPPolicy)
	if !ok {
		t.Fatalf("first resolved policy is %T, want *remote.HTTPPolicy", first)
	}
	secondPolicy, ok := second.(*remote.HTTPPolicy)
	if !ok {
		t.Fatalf("second resolved policy is %T, want *remote.HTTPPolicy", second)
	}
	if firstPolicy == secondPolicy {
		t.Fatalf("two RL seat resolutions returned the SAME *remote.HTTPPolicy instance %p — per-seat paipu attribution (DecisionCounts/ObservedPolicyIDs) would be corrupted across seats/rooms", firstPolicy)
	}

	// Independence check: mutating one instance's counters must not affect
	// the other's — the concrete symptom the shared-instance regression
	// produced (Room.reconcileRLPolicyIDs reading cross-contaminated counts).
	firstPolicy.ChooseAction(nil, 0) // nil state -> config-error fallback path, bumps fallback counters only
	_, firstFallback := firstPolicy.DecisionCounts()
	secondRemote, secondFallback := secondPolicy.DecisionCounts()
	if firstFallback == 0 {
		t.Fatalf("expected first policy's fallback counter to be nonzero after ChooseAction")
	}
	if secondRemote != 0 || secondFallback != 0 {
		t.Fatalf("second policy's counters were affected by the first instance's activity: remote=%d fallback=%d, want 0/0", secondRemote, secondFallback)
	}
}

// TestNewSeatPolicyResolver_ShadowPolicyIsLabeledWithRoomAndSeat pins the
// adversarial round 3, Finding 2 fix: when a shadow candidate is configured,
// the resolver must wrap the primary in a bot.NewShadowPolicyWithLabel whose
// label identifies the room and seat this resolution was called for, so
// concurrent private tables' shadow-mode log lines are distinguishable.
func TestNewSeatPolicyResolver_ShadowPolicyIsLabeledWithRoomAndSeat(t *testing.T) {
	var buf bytes.Buffer
	prevOutput := log.Writer()
	log.SetOutput(&buf)
	defer log.SetOutput(prevOutput)

	shadowCandidate := newShadowHTTPPolicy("http://127.0.0.1:1/act", &http.Client{}, 0)
	resolver := newSeatPolicyResolver("http://127.0.0.1:1/act", &http.Client{}, 0, shadowCandidate)

	policy, err := resolver(pb.Difficulty_DIFFICULTY_RL, "table-42", 3)
	if err != nil {
		t.Fatalf("resolver call: %v", err)
	}
	shadowPolicy, ok := policy.(*bot.ShadowPolicy)
	if !ok {
		t.Fatalf("resolved policy is %T, want *bot.ShadowPolicy", policy)
	}

	shadowPolicy.ChooseActionCtx(&bot.DecisionContext{State: &pb.GameState{}, Seat: 3, DecisionIndex: 0})
	shadowPolicy.Close()

	out := buf.String()
	if !strings.Contains(out, "room=table-42 seat=3") {
		t.Fatalf("expected shadow policy log output to contain the room/seat label, got: %s", out)
	}
}
