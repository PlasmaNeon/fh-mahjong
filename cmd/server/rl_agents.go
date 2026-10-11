package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"regexp"
	"strings"

	"github.com/plasma/fh-mahjong/internal/rl"
)

// rlAgentConfig is one private-room RL agent from RL_AGENTS: an id the seat
// stores, the label players see, the policy server's /act URL and the event
// window that server speaks.
type rlAgentConfig struct {
	ID          string
	Label       string
	URL         string
	EventWindow uint32
}

var rlAgentIDPattern = regexp.MustCompile(`^[a-z0-9-]{1,32}$`)

// parseRLAgents parses RL_AGENTS (a JSON array, menu order, first = default).
// Empty means unset (nil, nil). Any invalid entry is an error: a registry that
// silently dropped a model would offer players fewer opponents than configured.
func parseRLAgents(raw string) ([]rlAgentConfig, error) {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return nil, nil
	}
	var entries []struct {
		ID          string `json:"id"`
		Label       string `json:"label"`
		URL         string `json:"url"`
		EventWindow uint32 `json:"eventWindow"`
	}
	dec := json.NewDecoder(bytes.NewReader([]byte(raw)))
	dec.DisallowUnknownFields()
	if err := dec.Decode(&entries); err != nil {
		return nil, fmt.Errorf("RL_AGENTS: %w", err)
	}
	if len(entries) == 0 {
		return nil, fmt.Errorf("RL_AGENTS: empty list")
	}
	seen := make(map[string]bool, len(entries))
	agents := make([]rlAgentConfig, 0, len(entries))
	for i, e := range entries {
		switch {
		case !rlAgentIDPattern.MatchString(e.ID):
			return nil, fmt.Errorf("RL_AGENTS[%d]: id %q must match %s", i, e.ID, rlAgentIDPattern)
		case seen[e.ID]:
			return nil, fmt.Errorf("RL_AGENTS[%d]: duplicate id %q", i, e.ID)
		case strings.TrimSpace(e.Label) == "":
			return nil, fmt.Errorf("RL_AGENTS[%d]: empty label", i)
		case strings.TrimSpace(e.URL) == "":
			return nil, fmt.Errorf("RL_AGENTS[%d]: empty url", i)
		case e.EventWindow > rl.MaxEventHistoryWindow:
			return nil, fmt.Errorf("RL_AGENTS[%d]: eventWindow %d exceeds %d", i, e.EventWindow, rl.MaxEventHistoryWindow)
		}
		seen[e.ID] = true
		agents = append(agents, rlAgentConfig{ID: e.ID, Label: strings.TrimSpace(e.Label),
			URL: strings.TrimSpace(e.URL), EventWindow: e.EventWindow})
	}
	return agents, nil
}

// legacyRLAgent is the single agent used when RL_AGENTS is unset, built from
// the pre-registry env chain (RL_AGENT_POLICY_URL → AI_BOT_POLICY_URL → local
// default, RL_AGENT_EVENT_WINDOW).
func legacyRLAgent(url string, window uint32) rlAgentConfig {
	return rlAgentConfig{ID: "rl", Label: "AI", URL: url, EventWindow: window}
}
