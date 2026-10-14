package main

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/plasma/fh-mahjong/internal/bot/remote"
	pb "github.com/plasma/fh-mahjong/proto"
)

func TestParseRLAgentsValidList(t *testing.T) {
	got, err := parseRLAgents(`[{"id":"v4","label":"AI v4","url":"http://a:8765/act","eventWindow":128},
		{"id":"v3","label":"AI v3","url":"http://b:8765/act","eventWindow":128}]`)
	if err != nil {
		t.Fatalf("parseRLAgents: %v", err)
	}
	want := []rlAgentConfig{{"v4", "AI v4", "http://a:8765/act", 128}, {"v3", "AI v3", "http://b:8765/act", 128}}
	if len(got) != len(want) || got[0] != want[0] || got[1] != want[1] {
		t.Fatalf("got %+v, want %+v", got, want)
	}
}

func TestParseRLAgentsEmptyMeansUnset(t *testing.T) {
	got, err := parseRLAgents("  ")
	if err != nil || got != nil {
		t.Fatalf("got %+v, %v; want nil, nil", got, err)
	}
}

func TestParseRLAgentsRejectsInvalidEntries(t *testing.T) {
	cases := map[string]string{
		"malformed json": `[{"id":"v4"`,
		"empty list":     `[]`,
		"bad id":         `[{"id":"V4!","label":"x","url":"http://a/act","eventWindow":0}]`,
		"duplicate id":   `[{"id":"v4","label":"a","url":"http://a/act","eventWindow":0},{"id":"v4","label":"b","url":"http://b/act","eventWindow":0}]`,
		"missing url":    `[{"id":"v4","label":"a","url":"","eventWindow":0}]`,
		"missing label":  `[{"id":"v4","label":"","url":"http://a/act","eventWindow":0}]`,
		"window too big": `[{"id":"v4","label":"a","url":"http://a/act","eventWindow":513}]`,
		"unknown field":  `[{"id":"v4","label":"a","url":"http://a/act","eventWindow":0,"extra":1}]`,
	}
	for name, raw := range cases {
		if _, err := parseRLAgents(raw); err == nil {
			t.Errorf("%s: parseRLAgents(%s) succeeded, want error", name, raw)
		} else if !strings.Contains(err.Error(), "RL_AGENTS") {
			t.Errorf("%s: error %q does not name RL_AGENTS", name, err)
		}
	}
}

func TestLegacyRLAgent(t *testing.T) {
	got := legacyRLAgent("http://127.0.0.1:8765/act", 0)
	if got != (rlAgentConfig{ID: "rl", Label: "AI", URL: "http://127.0.0.1:8765/act", EventWindow: 0}) {
		t.Fatalf("legacyRLAgent = %+v", got)
	}
}

func TestRLAgentSetResolverBuildsFreshPolicyPerSeatForTheAgent(t *testing.T) {
	set := newRLAgentSet([]rlAgentConfig{
		{ID: "v4", Label: "AI v4", URL: "http://a:8765/act", EventWindow: 128},
		{ID: "v3", Label: "AI v3", URL: "http://b:8765/act", EventWindow: 64},
	}, &http.Client{}, nil, "")
	resolve := set.Resolver()
	p1, err := resolve(pb.Difficulty_DIFFICULTY_RL, "v3", "room", 1)
	if err != nil {
		t.Fatal(err)
	}
	p2, _ := resolve(pb.Difficulty_DIFFICULTY_RL, "v3", "room", 2)
	h1, ok := p1.(*remote.HTTPPolicy)
	if !ok || p1 == p2 {
		t.Fatalf("want two distinct *remote.HTTPPolicy, got %T %T same=%v", p1, p2, p1 == p2)
	}
	if h1.Endpoint() != "http://b:8765/act" || h1.EventWindow() != 64 {
		t.Fatalf("policy endpoint=%s window=%d, want agent v3's", h1.Endpoint(), h1.EventWindow())
	}
	if _, err := resolve(pb.Difficulty_DIFFICULTY_RL, "v9", "room", 1); err == nil {
		t.Fatal("unknown agent resolved")
	}
	if _, err := resolve(pb.Difficulty_DIFFICULTY_HEURISTIC, "", "room", 1); err != nil {
		t.Fatalf("heuristic seat: %v", err)
	}
}

func TestRLAgentSetWarmHookWarmsEachListedAgentOnce(t *testing.T) {
	// /warmup sits at the endpoint's host root, so each agent gets its own server.
	newServer := func(hits *int) *httptest.Server {
		return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.URL.Path == "/warmup" {
				*hits++
			}
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(`{"warmed":true,"event_window":0}`))
		}))
	}
	var v4Hits, v3Hits int
	v4, v3 := newServer(&v4Hits), newServer(&v3Hits)
	defer v4.Close()
	defer v3.Close()
	set := newRLAgentSet([]rlAgentConfig{
		{ID: "v4", Label: "AI v4", URL: v4.URL + "/act"},
		{ID: "v3", Label: "AI v3", URL: v3.URL + "/act"},
	}, &http.Client{}, nil, "")
	warm := set.WarmHook(remote.NewWarmupManager(nil), "", "")
	if err := warm(context.Background(), []string{"v3"}); err != nil {
		t.Fatal(err)
	}
	if v3Hits != 1 || v4Hits != 0 {
		t.Fatalf("warmup hits v3=%d v4=%d, want v3=1 v4=0", v3Hits, v4Hits)
	}
	if err := warm(context.Background(), []string{"v9"}); err == nil {
		t.Fatal("warming an unknown agent succeeded")
	}
}

func TestRLAgentSetIdentityFallsBackToAgentID(t *testing.T) {
	set := newRLAgentSet([]rlAgentConfig{{ID: "v4", Label: "AI v4", URL: "http://127.0.0.1:1/act"}}, &http.Client{}, nil, "")
	if got := set.Identity("v4"); got != "v4" {
		t.Fatalf("identity = %q, want agent id when /healthz reports nothing", got)
	}
	legacy := newRLAgentSet([]rlAgentConfig{legacyRLAgent("http://127.0.0.1:1/act", 0)}, &http.Client{}, nil, "deep4@275")
	if got := legacy.Identity("rl"); got != "deep4@275" {
		t.Fatalf("legacy identity = %q, want RL_AGENT_CHECKPOINT_ID", got)
	}
}
