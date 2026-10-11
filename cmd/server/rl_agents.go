package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"regexp"
	"strings"

	"github.com/plasma/fh-mahjong/internal/api"
	"github.com/plasma/fh-mahjong/internal/bot"
	"github.com/plasma/fh-mahjong/internal/bot/remote"
	"github.com/plasma/fh-mahjong/internal/rl"
	pb "github.com/plasma/fh-mahjong/proto"
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

// rlAgent is one configured agent with its live health checker.
type rlAgent struct {
	cfg    rlAgentConfig
	health *remote.HealthChecker
}

// rlAgentSet owns the private-room RL agents: one health checker per agent
// (availability + served identity), the per-seat policy resolver, and the
// warmup hook. The shadow policy (RL_AGENT_SHADOW_*) mirrors the default
// (first) agent only.
type rlAgentSet struct {
	agents      []*rlAgent
	byID        map[string]*rlAgent
	client      *http.Client
	shadow      bot.ContextPolicy
	legacyLabel string // RL_AGENT_CHECKPOINT_ID, used for the legacy "rl" agent only
}

func newRLAgentSet(cfgs []rlAgentConfig, client *http.Client, shadow bot.ContextPolicy, legacyCheckpointLabel string) *rlAgentSet {
	s := &rlAgentSet{byID: make(map[string]*rlAgent, len(cfgs)), client: client, shadow: shadow,
		legacyLabel: strings.TrimSpace(legacyCheckpointLabel)}
	for _, cfg := range cfgs {
		a := &rlAgent{cfg: cfg, health: remote.NewHealthChecker(cfg.URL, remote.WithExpectedEventWindow(cfg.EventWindow))}
		s.agents = append(s.agents, a)
		s.byID[cfg.ID] = a
	}
	return s
}

// Infos lists the agents in menu order with live availability
// (api.Matchmaker.RLAgents). Availability re-validates the event-window
// contract on every poll, so a reachable server speaking the wrong window is
// never offered.
func (s *rlAgentSet) Infos() []api.RLAgentInfo {
	out := make([]api.RLAgentInfo, 0, len(s.agents))
	for _, a := range s.agents {
		out = append(out, api.RLAgentInfo{ID: a.cfg.ID, Label: a.cfg.Label, Available: a.health.Healthy()})
	}
	return out
}

// Identity is the serving checkpoint identity recorded in the paipu for an RL
// seat: the agent's /healthz identity (basename@step), else (legacy agent
// only) RL_AGENT_CHECKPOINT_ID, else the agent id. Paipu are public, so never
// a URL or filesystem path.
func (s *rlAgentSet) Identity(agentID string) string {
	a, ok := s.byID[agentID]
	if !ok {
		return ""
	}
	if id := a.health.Identity(); id != "" {
		return id
	}
	if a.cfg.ID == "rl" && s.legacyLabel != "" {
		return s.legacyLabel
	}
	return a.cfg.ID
}

// Resolver builds the api.Matchmaker.SeatPolicyResolver: a fresh HTTPPolicy
// per RL seat (per-instance paipu counters must never be shared across seats —
// see newRLPrimaryPolicy), shadow-wrapped for the default agent when shadow
// mode is configured, labeled with roomID/seat so concurrent rooms are
// distinguishable in logs; bot.NewPolicy for every other difficulty.
func (s *rlAgentSet) Resolver() func(pb.Difficulty, string, string, uint32) (bot.Policy, error) {
	return func(d pb.Difficulty, agentID, roomID string, seat uint32) (bot.Policy, error) {
		if d != pb.Difficulty_DIFFICULTY_RL {
			return bot.NewPolicy(d)
		}
		a, ok := s.byID[agentID]
		if !ok {
			return nil, fmt.Errorf("unknown RL agent %q", agentID)
		}
		primary := newRLPrimaryPolicy(a.cfg.URL, s.client, a.cfg.EventWindow)
		if s.shadow != nil && a == s.agents[0] {
			label := fmt.Sprintf("room=%s seat=%d agent=%s", roomID, seat, agentID)
			return bot.NewShadowPolicyWithLabel(primary, s.shadow, 64, label), nil
		}
		return primary, nil
	}
}

// WarmHook builds api.Matchmaker.WarmRLEndpoints: warm each listed agent's
// endpoint (tokenless — production policy services run without an evaluate
// token, which leaves /warmup open), and the shadow candidate (with
// shadowToken) when the default agent is listed and shadow mode is
// configured — a cold shadow candidate would time out on its first mirrored
// decision and pollute the shadow-error count. An unknown id fails the warmup,
// so the room never starts.
func (s *rlAgentSet) WarmHook(manager *remote.WarmupManager, shadowURL, shadowToken string) func(context.Context, []string) error {
	return func(ctx context.Context, agentIDs []string) error {
		for _, id := range agentIDs {
			a, ok := s.byID[id]
			if !ok {
				return fmt.Errorf("unknown RL agent %q", id)
			}
			if err := manager.Warm(ctx, a.cfg.URL, ""); err != nil {
				return fmt.Errorf("RL agent %s endpoint: %w", id, err)
			}
			if shadowURL != "" && a == s.agents[0] {
				if err := manager.Warm(ctx, shadowURL, shadowToken); err != nil {
					return fmt.Errorf("shadow policy endpoint: %w", err)
				}
			}
		}
		return nil
	}
}
