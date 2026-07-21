package remote

import "testing"

// TestEffectiveRLEndpointURL pins the fallback chain shared by cmd/server's
// rlEndpointURL and internal/api's reviewEventWindow (adversarial round 11):
// RL_AGENT_POLICY_URL wins, then AI_BOT_POLICY_URL, then DefaultRLPolicyURL
// (the local serve_policy.py default) when both overrides are unset.
func TestEffectiveRLEndpointURL(t *testing.T) {
	cases := []struct {
		name          string
		rlOverride    string
		botPolicyURL  string
		wantEndpoint  string
		wantLocalDflt bool
	}{
		{"local default", "", "", DefaultRLPolicyURL, true},
		{"follows bot policy url", "", "http://bot:9/act", "http://bot:9/act", false},
		{"rl override wins", "http://policy:8765/act", "http://bot:9/act", "http://policy:8765/act", false},
		{"rl override without bot url", "http://policy:8765/act", "", "http://policy:8765/act", false},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			ep, local := EffectiveRLEndpointURL(c.rlOverride, c.botPolicyURL)
			if ep != c.wantEndpoint || local != c.wantLocalDflt {
				t.Fatalf("EffectiveRLEndpointURL(%q,%q) = (%q,%v), want (%q,%v)",
					c.rlOverride, c.botPolicyURL, ep, local, c.wantEndpoint, c.wantLocalDflt)
			}
		})
	}
}

// TestEffectiveRLEndpointURLFromEnv pins the env-reading convenience wrapper
// used by internal/api's reviewEventWindow: it must resolve to
// DefaultRLPolicyURL (not empty) when both RL_AGENT_POLICY_URL and
// AI_BOT_POLICY_URL are unset, matching cmd/server's own resolution so a
// same-service comparison against POLICY_SERVER_URL is possible even in the
// all-unset case.
func TestEffectiveRLEndpointURLFromEnv(t *testing.T) {
	t.Setenv("RL_AGENT_POLICY_URL", "")
	t.Setenv("AI_BOT_POLICY_URL", "")
	ep, local := EffectiveRLEndpointURLFromEnv()
	if ep != DefaultRLPolicyURL || !local {
		t.Fatalf("EffectiveRLEndpointURLFromEnv() with both env vars unset = (%q,%v), want (%q,true)", ep, local, DefaultRLPolicyURL)
	}

	t.Setenv("RL_AGENT_POLICY_URL", "http://rl.example/act")
	ep, local = EffectiveRLEndpointURLFromEnv()
	if ep != "http://rl.example/act" || local {
		t.Fatalf("EffectiveRLEndpointURLFromEnv() with RL_AGENT_POLICY_URL set = (%q,%v), want (\"http://rl.example/act\",false)", ep, local)
	}
}
