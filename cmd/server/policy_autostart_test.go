package main

import (
	"testing"
	"time"
)

func TestHostPortFromURL(t *testing.T) {
	cases := []struct {
		in         string
		host, port string
	}{
		{"http://127.0.0.1:8765/act", "127.0.0.1", "8765"},
		{"http://localhost:9000/act", "localhost", "9000"},
		{"https://policy.internal:443/act", "policy.internal", "443"},
		{"http://127.0.0.1/act", "127.0.0.1", "8765"}, // no port -> default
		{"", "127.0.0.1", "8765"},                     // unparseable -> defaults
	}
	for _, c := range cases {
		host, port := hostPortFromURL(c.in)
		if host != c.host || port != c.port {
			t.Errorf("hostPortFromURL(%q) = (%q,%q), want (%q,%q)", c.in, host, port, c.host, c.port)
		}
	}
}

func TestRLEndpointURL(t *testing.T) {
	cases := []struct {
		name          string
		rlOverride    string
		botPolicyURL  string
		wantEndpoint  string
		wantLocalDflt bool
	}{
		{"local default", "", "", defaultRLPolicyURL, true},
		{"follows bot policy url", "", "http://bot:9/act", "http://bot:9/act", false},
		{"rl override wins", "http://policy:8765/act", "http://bot:9/act", "http://policy:8765/act", false},
		{"rl override without bot url", "http://policy:8765/act", "", "http://policy:8765/act", false},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			ep, local := rlEndpointURL(c.rlOverride, c.botPolicyURL)
			if ep != c.wantEndpoint || local != c.wantLocalDflt {
				t.Fatalf("rlEndpointURL(%q,%q) = (%q,%v), want (%q,%v)",
					c.rlOverride, c.botPolicyURL, ep, local, c.wantEndpoint, c.wantLocalDflt)
			}
		})
	}
}

func TestEnvBool(t *testing.T) {
	cases := map[string]bool{
		"":      true, // unset -> fallback(true)
		"1":     true,
		"true":  true,
		"YES":   true,
		"0":     false,
		"false": false,
		"Off":   false,
		"no":    false,
	}
	for v, want := range cases {
		t.Setenv("RL_TEST_FLAG", v)
		if got := envBool("RL_TEST_FLAG", true); got != want {
			t.Errorf("envBool(%q) = %v, want %v", v, got, want)
		}
	}
}

func TestMaybeStartPolicyServer_DisabledReturnsNil(t *testing.T) {
	t.Setenv("RL_AGENT_AUTOSTART", "0")
	if stop := maybeStartPolicyServer("http://127.0.0.1:8765/act"); stop != nil {
		stop()
		t.Fatal("expected nil cleanup when autostart is disabled")
	}
}

func TestMaybeStartPolicyServer_MissingBinaryReturnsNil(t *testing.T) {
	t.Setenv("RL_AGENT_AUTOSTART", "1")
	t.Setenv("RL_AGENT_SERVE_CMD", "fh-definitely-not-a-real-binary-xyz serve")
	if stop := maybeStartPolicyServer("http://127.0.0.1:8765/act"); stop != nil {
		stop()
		t.Fatal("expected nil cleanup when launcher binary is missing")
	}
}

func TestMaybeStartPolicyServer_LaunchesAndCleansUp(t *testing.T) {
	// Exercise the real spawn + process-group teardown path using a portable
	// binary, without depending on uv/python. The process may exit immediately
	// (sleep rejects the appended --host/--port flags); the point is that
	// Start() succeeds and the cleanup is safe even if the child is already gone.
	t.Setenv("RL_AGENT_AUTOSTART", "1")
	t.Setenv("RL_AGENT_SERVE_CMD", "sleep")

	stop := maybeStartPolicyServer("http://127.0.0.1:8765/act")
	if stop == nil {
		t.Skip("sleep not available; skipping spawn assertion")
	}
	time.Sleep(20 * time.Millisecond)
	stop() // must not panic whether the child is alive or already exited
}
