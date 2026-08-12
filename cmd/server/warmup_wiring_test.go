package main

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/plasma/fh-mahjong/internal/bot/remote"
)

const warmupOKJSON = `{"warmed":true,"checkpoint_path":"/ckpt/iter_075.pt","checkpoint_step":75,` +
	`"checkpoint_sha256":"abc123","contract_version":1,"event_window":128,"latency_ms":12.5}`

// TestNewRLWarmupHook_WarmsPrimaryAndTokenedShadow pins the wiring contract:
// both endpoints are warmed before an RL room is admitted, the primary
// tokenless and the shadow with RL_AGENT_SHADOW_POLICY_TOKEN.
func TestNewRLWarmupHook_WarmsPrimaryAndTokenedShadow(t *testing.T) {
	var primaryHits, shadowHits atomic.Int64
	var primaryAuth, shadowAuth atomic.Value
	primaryAuth.Store("")
	shadowAuth.Store("")

	primary := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		primaryHits.Add(1)
		primaryAuth.Store(r.Header.Get("Authorization"))
		fmt.Fprint(w, warmupOKJSON)
	}))
	defer primary.Close()
	shadow := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		shadowHits.Add(1)
		shadowAuth.Store(r.Header.Get("Authorization"))
		fmt.Fprint(w, warmupOKJSON)
	}))
	defer shadow.Close()

	hook := newRLWarmupHook(remote.NewWarmupManager(nil), primary.URL+"/act", shadow.URL+"/act", "tok123")
	if err := hook(context.Background()); err != nil {
		t.Fatalf("warmup hook: %v", err)
	}
	// Warm-once: a second admission does no HTTP at all.
	if err := hook(context.Background()); err != nil {
		t.Fatalf("second warmup hook call: %v", err)
	}
	if got := primaryHits.Load(); got != 1 {
		t.Errorf("primary warmup hits = %d, want 1", got)
	}
	if got := shadowHits.Load(); got != 1 {
		t.Errorf("shadow warmup hits = %d, want 1", got)
	}
	if got := primaryAuth.Load(); got != "" {
		t.Errorf("primary Authorization = %q, want none", got)
	}
	if got := shadowAuth.Load(); got != "Bearer tok123" {
		t.Errorf("shadow Authorization = %q, want %q", got, "Bearer tok123")
	}
}

func TestNewRLWarmupHook_FailsOnShadowFailure(t *testing.T) {
	primary := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprint(w, warmupOKJSON)
	}))
	defer primary.Close()
	shadow := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusForbidden)
	}))
	defer shadow.Close()

	hook := newRLWarmupHook(remote.NewWarmupManager(nil), primary.URL+"/act", shadow.URL+"/act", "")
	err := hook(context.Background())
	if err == nil {
		t.Fatal("expected the hook to fail when the shadow endpoint refuses warmup")
	}
	if !strings.Contains(err.Error(), "shadow policy endpoint") {
		t.Errorf("error %v should identify the failing endpoint", err)
	}
}

func TestNewRLWarmupHook_NoShadowConfigured(t *testing.T) {
	var hits atomic.Int64
	primary := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		hits.Add(1)
		fmt.Fprint(w, warmupOKJSON)
	}))
	defer primary.Close()

	hook := newRLWarmupHook(remote.NewWarmupManager(nil), primary.URL+"/act", "", "")
	if err := hook(context.Background()); err != nil {
		t.Fatalf("warmup hook: %v", err)
	}
	if got := hits.Load(); got != 1 {
		t.Fatalf("primary warmup hits = %d, want 1", got)
	}
}

func TestWarmupTTLEnv(t *testing.T) {
	cases := map[string]time.Duration{
		"":      0,
		"15m":   15 * time.Minute,
		"bogus": 0,
		"-1m":   0,
	}
	for raw, want := range cases {
		t.Run("ttl="+raw, func(t *testing.T) {
			t.Setenv("RL_AGENT_WARMUP_TTL", raw)
			if got := warmupTTL(); got != want {
				t.Fatalf("warmupTTL() with %q = %v, want %v", raw, got, want)
			}
		})
	}
}
