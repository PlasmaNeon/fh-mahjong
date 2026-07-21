package remote

import (
	"os"
	"strings"
)

// DefaultRLPolicyURL is the local serve_policy.py endpoint used for the
// private-room RL agent when no override is configured (RL_AGENT_POLICY_URL
// and AI_BOT_POLICY_URL both unset). Shared by cmd/server (which autostarts a
// managed child process for this exact endpoint — see policy_autostart.go)
// and internal/api's review path (adversarial round 11): before this both
// sides resolved the effective RL endpoint differently, so "both overrides
// unset" looked like "no RL endpoint" to internal/api even though cmd/server
// was already serving RL traffic on this local default.
const DefaultRLPolicyURL = "http://127.0.0.1:8765/act"

// EffectiveRLEndpointURL resolves the effective private-room RL endpoint
// using the single fallback chain cmd/server's main() applies: an explicit
// RL_AGENT_POLICY_URL override (rlOverride) wins, then AI_BOT_POLICY_URL
// (botPolicyURL), then DefaultRLPolicyURL. isLocalDefault reports whether
// neither override was set — the only case eligible for local-default-only
// behavior (e.g. cmd/server's child-process autostart).
//
// This is the single shared resolution behind cmd/server's rlEndpointURL
// (cmd/server/policy_autostart.go, now a thin wrapper around this) and
// internal/api's reviewEventWindow (internal/api/review.go), so both packages
// always agree on which endpoint the private-room RL agent actually is.
func EffectiveRLEndpointURL(rlOverride, botPolicyURL string) (endpoint string, isLocalDefault bool) {
	if rlOverride != "" {
		return rlOverride, false
	}
	if botPolicyURL != "" {
		return botPolicyURL, false
	}
	return DefaultRLPolicyURL, true
}

// EffectiveRLEndpointURLFromEnv is the env-reading convenience wrapper around
// EffectiveRLEndpointURL, reading RL_AGENT_POLICY_URL and AI_BOT_POLICY_URL
// directly (trimmed, same as cmd/server's main() and internal/api's
// reviewEventWindow already did before resolving the fallback chain).
func EffectiveRLEndpointURLFromEnv() (endpoint string, isLocalDefault bool) {
	rlOverride := strings.TrimSpace(os.Getenv("RL_AGENT_POLICY_URL"))
	botPolicyURL := strings.TrimSpace(os.Getenv("AI_BOT_POLICY_URL"))
	return EffectiveRLEndpointURL(rlOverride, botPolicyURL)
}
