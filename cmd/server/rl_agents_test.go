package main

import (
	"strings"
	"testing"
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
