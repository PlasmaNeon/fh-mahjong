package main

import (
	"context"
	"log"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/plasma/fh-mahjong/internal/api"
	"github.com/plasma/fh-mahjong/internal/bot"
	"github.com/plasma/fh-mahjong/internal/bot/remote"
	"github.com/plasma/fh-mahjong/internal/rl"
)

// defaultRLPolicyURL is the local serve_policy.py endpoint used for the
// private-room RL agent when AI_BOT_POLICY_URL is not set. The option is only
// offered when this endpoint passes its /healthz probe, so defaulting it is
// safe even when no model server is running.
//
// Alias for remote.DefaultRLPolicyURL (adversarial round 11): the constant now
// lives in internal/bot/remote so internal/api's reviewEventWindow can resolve
// the same effective RL endpoint cmd/server does, without internal/api
// importing package main.
const defaultRLPolicyURL = remote.DefaultRLPolicyURL

// defaultShadowEventWindow is used for RL_AGENT_SHADOW_EVENT_WINDOW when the
// env var is unset.
const defaultShadowEventWindow = 128

// configurePolicies wires matchmaking and private-room policies and returns
// cleanup for an optional locally managed policy server.
func configurePolicies(matchmaker *api.Matchmaker) func() {
	// RL_AGENT_EVENT_WINDOW declares the event-history wire contract every
	// PRIMARY remote policy speaks (matchmaking-queue bots AND the
	// private-room RL agent) — same env family as RL_AGENT_POLICY_URL /
	// RL_AGENT_CHECKPOINT_ID / RL_AGENT_SHADOW_EVENT_WINDOW, and the same
	// parsing semantics internal/api's reviewEventWindow uses for the review
	// path. Unset/invalid/out-of-bound values fail closed to 0 (event-free,
	// byte-identical to pre-event-contract behavior) rather than serving a
	// mismatched wire form.
	rlEventWindow := parseEventWindowEnv("RL_AGENT_EVENT_WINDOW", 0)
	log.Printf("Primary remote policy event window: %d (RL_AGENT_EVENT_WINDOW)", rlEventWindow)

	// An explicit AI_BOT_POLICY_URL routes ALL matchmaking-queue bots through
	// the remote policy (unchanged behavior). For the private-room RL agent we
	// fall back to a local default endpoint, so the option works out of the box
	// in local dev without any env var.
	explicitPolicyURL := strings.TrimSpace(os.Getenv("AI_BOT_POLICY_URL"))
	// RL_AGENT_POLICY_URL, read raw so it can feed rlEndpointURL below.
	rlOverride := strings.TrimSpace(os.Getenv("RL_AGENT_POLICY_URL"))
	// Resolve the EFFECTIVE RL endpoint URL (same fallback chain used to pick
	// rlPolicyURL further down: RL_AGENT_POLICY_URL, else AI_BOT_POLICY_URL,
	// else the local default) BEFORE computing aiBotEventWindow. Round 7,
	// Finding 1: resolveAIBotEventWindow previously compared AI_BOT_POLICY_URL
	// against the RAW rlOverride, so "AI_BOT_POLICY_URL set, RL_AGENT_POLICY_URL
	// unset" looked like "different services" even though rlEndpointURL's own
	// fallback resolves the RL side to that SAME AI_BOT_POLICY_URL — matchmaking
	// and the private-room RL agent then silently spoke different event-window
	// contracts to the identical service. Resolving once here and reusing the
	// result for both aiBotEventWindow and rlPolicyURL keeps the fallback logic
	// in exactly one place (rlEndpointURL).
	effectiveRLURL, rlIsLocalDefault := rlEndpointURL(rlOverride, explicitPolicyURL)
	// AI_BOT_POLICY_URL and the effective RL endpoint may still be DIFFERENT
	// services during a staggered rollout (adversarial round 6, Finding 1) —
	// applying rlEventWindow to both would make one of them silently speak the
	// wrong wire contract and degrade to heuristic per-decision. Resolve the AI
	// bot policy's own window independently.
	aiBotEventWindow := resolveAIBotEventWindow(explicitPolicyURL, effectiveRLURL, rlEventWindow)
	log.Printf("Matchmaking bot policy event window: %d (AI_BOT_EVENT_WINDOW)", aiBotEventWindow)
	if explicitPolicyURL != "" {
		log.Printf("Using remote AI bot policy endpoint for matchmaking seats: %s", explicitPolicyURL)
		// Shared instance (HTTPPolicy is safe for concurrent use — atomic
		// stats counters, no other mutable state) rather than a fresh policy
		// per bot: lets one startup healthz validation cover every
		// matchmaking-queue bot this factory ever hands out.
		botPolicy := remote.NewHTTPPolicy(explicitPolicyURL, remote.WithEventWindow(aiBotEventWindow))
		matchmaker.BotPolicyFactory = func() bot.Policy {
			return botPolicy
		}
		validatePolicyContractAsync("matchmaking bot policy (AI_BOT_POLICY_URL)", botPolicy)
	}

	// RL endpoint for the private-room agent. RL_AGENT_POLICY_URL points it at a
	// dedicated policy server (e.g. the docker-compose `policy` service) without
	// routing matchmaking bots through it; otherwise it follows AI_BOT_POLICY_URL,
	// and finally the local default that the Go server can autostart. Already
	// resolved above (effectiveRLURL) so aiBotEventWindow can compare against it;
	// reuse rather than re-deriving.
	rlPolicyURL := effectiveRLURL
	// Share one HTTP client (and its connection pool) across every RL seat the
	// resolver creates, rather than letting each NewHTTPPolicy spin up its own.
	// Reusing connections avoids socket churn/exhaustion when many RL seats or
	// rooms start. 750ms matches the remote package's default per-call timeout.
	rlHTTPClient := &http.Client{Timeout: 750 * time.Millisecond}
	// RL_AGENT_SHADOW_POLICY_URL, if set, wraps the RESOLVED RL primary policy
	// (the currently-deployed champion serving real seats) with a
	// bot.ShadowPolicy that silently mirrors each decision to a second,
	// candidate event-aware HTTPPolicy for comparison. Shadow mode never
	// affects what actually gets played — the primary always answers, the
	// shadow's evaluation runs on a background worker — so a candidate policy
	// can be evaluated against live traffic before it is ever promoted to
	// serve directly.
	shadowPolicyURL := strings.TrimSpace(os.Getenv("RL_AGENT_SHADOW_POLICY_URL"))
	var shadowPolicy bot.ContextPolicy
	if shadowPolicyURL != "" {
		window := shadowEventWindow(defaultShadowEventWindow)
		shadowHTTPPolicy := newShadowHTTPPolicy(shadowPolicyURL, rlHTTPClient, window)
		shadowPolicy = shadowHTTPPolicy
		log.Printf(
			"RL agent shadow policy enabled: endpoint=%s event_window=%d (mirrors private-room RL decisions only; never serves them)",
			shadowPolicyURL, window,
		)
		validatePolicyContractAsync("RL shadow policy", shadowHTTPPolicy)
	}

	// Private-room RL agents. RL_AGENTS (JSON, menu order, first = default)
	// configures several, each a separate policy service; unset keeps the
	// single legacy agent at the endpoint resolved above. A malformed registry
	// is fatal: silently running with fewer agents would hide a misconfigured
	// model from every host. Each RL seat plays its agent through a fresh
	// remote HTTP policy that falls back to the heuristic per-decision, so a
	// transient outage mid-match degrades gracefully rather than stalling.
	agentCfgs, err := parseRLAgents(os.Getenv("RL_AGENTS"))
	if err != nil {
		log.Fatalf("invalid RL agent registry: %v", err)
	}
	usingRegistry := agentCfgs != nil
	if !usingRegistry {
		agentCfgs = []rlAgentConfig{legacyRLAgent(rlPolicyURL, rlEventWindow)}
	} else if rlOverride != "" || strings.TrimSpace(os.Getenv("RL_AGENT_EVENT_WINDOW")) != "" {
		log.Printf("RL_AGENTS is set: ignoring RL_AGENT_POLICY_URL / RL_AGENT_EVENT_WINDOW for private-room agents")
	}
	// Each agent gets one health checker: it gates the agent's availability
	// (reachable AND serving the event-window contract this server expects —
	// a mismatch would otherwise fall back on every /act while still showing
	// as available) and reports the served checkpoint identity for the paipu.
	// RL_AGENT_CHECKPOINT_ID labels the legacy agent when /healthz reports
	// nothing.
	agents := newRLAgentSet(agentCfgs, rlHTTPClient, shadowPolicy, os.Getenv("RL_AGENT_CHECKPOINT_ID"))
	for _, cfg := range agentCfgs {
		// One startup contract probe per agent (one goroutine at boot, not one per seat).
		validatePolicyContractAsync("RL agent "+cfg.ID, newRLPrimaryPolicy(cfg.URL, rlHTTPClient, cfg.EventWindow))
		log.Printf("Private-room RL agent %s (%q): %s window=%d (offered when reachable)", cfg.ID, cfg.Label, cfg.URL, cfg.EventWindow)
	}
	matchmaker.SeatPolicyResolver = agents.Resolver()
	matchmaker.RLAgents = agents.Infos
	matchmaker.RLPolicyIdentity = agents.Identity

	// Cold-start gate: warm every agent a table seats (plus the shadow
	// candidate when it mirrors a seated default agent) with a real forward
	// pass BEFORE the RL private room is admitted, so no in-match /act ever
	// pays the cold-start cost and silently falls back to the heuristic.
	// Warmup is endpoint-scoped and refreshed after the configured TTL (see
	// internal/bot/remote/warmup.go), with its own budget rather than the
	// 750ms /act budget a cold forward pass would blow.
	//
	// RL_AGENT_SHADOW_POLICY_TOKEN carries the candidate service's evaluate
	// token: serve_policy.py token-gates /warmup with its FH_MJ_EVALUATE_TOKEN
	// whenever one is configured, so the backend must be given the SAME value
	// here (empty = the service runs tokenless and /warmup is open, which is
	// the production agents' posture).
	shadowPolicyToken := strings.TrimSpace(os.Getenv("RL_AGENT_SHADOW_POLICY_TOKEN"))
	warmupManager := remote.NewWarmupManager(nil).
		WithWarmupTTL(warmupTTL()).
		WithWarmupLogger(log.Printf)
	matchmaker.WarmRLEndpoints = agents.WarmHook(warmupManager, shadowPolicyURL, shadowPolicyToken)

	// When using the local default endpoint, bring the policy server up as a
	// managed child process so the RL agent connects automatically on boot.
	// Skipped when an external endpoint is configured (AI_BOT_POLICY_URL or
	// RL_AGENT_POLICY_URL) — e.g. the docker-compose `policy` service.
	var policyCleanup func()
	if rlIsLocalDefault && !usingRegistry {
		policyCleanup = maybeStartPolicyServer(rlPolicyURL)
	}
	return policyCleanup
}

// newRLPrimaryPolicy builds a fresh *remote.HTTPPolicy configured for the
// private-room RL primary. Every call returns a brand-new instance sharing
// only httpClient (and its connection pool) — never the counters. This
// matters because HTTPPolicy.DecisionCounts and ObservedPolicyIDs are
// per-instance counters that Room.reconcileRLPolicyIDs (internal/api/room.go)
// reads to attribute paipu per seat; a shared instance would let one seat's
// fallback/reload counters bleed into every other room's dataset, corrupting
// the pure-RL filter and checkpoint labeling across the server's whole
// lifetime. rlAgentSet.Resolver calls this once per RL seat resolution; the
// startup contract probe calls it once more for a throwaway validation-only
// instance.
func newRLPrimaryPolicy(rlPolicyURL string, httpClient *http.Client, eventWindow uint32) *remote.HTTPPolicy {
	return remote.NewHTTPPolicy(rlPolicyURL, remote.WithHTTPClient(httpClient), remote.WithEventWindow(eventWindow))
}

// newShadowHTTPPolicy builds the candidate policy that RL_AGENT_SHADOW_POLICY_URL
// wires into bot.NewShadowPolicy. Unlike the primary/matchmaking policies, its
// fallback is explicitly disabled (remote.WithFallback(nil)): the shadow
// candidate never serves a real decision, it only gets compared against the
// primary's action, so a dead or contract-rejecting candidate endpoint must
// surface as a ShadowPolicy shadow error, not silently succeed by returning
// the local heuristic's action. With the default heuristic fallback, a
// candidate that is completely down would still return a (heuristic) action
// on every decision, ChooseActionCtx would never see nil, and the runbook's
// zero-shadow-error gate would pass even though nothing candidate-side is
// actually being evaluated. configurePolicies uses this factory so the fallback
// wiring is directly testable.
func newShadowHTTPPolicy(shadowPolicyURL string, httpClient *http.Client, eventWindow uint32) *remote.HTTPPolicy {
	return remote.NewHTTPPolicy(
		shadowPolicyURL,
		remote.WithHTTPClient(httpClient),
		remote.WithEventWindow(eventWindow),
		remote.WithFallback(nil),
	)
}

// defaultWarmupTTL is how long a successful warmup is trusted before the
// endpoint is warmed again. It is deliberately NOT "once per process": the
// policy service is a separate process (a Zeabur service that is redeployed,
// restarted, and evicted independently of this backend), so a warm-once
// manager would keep reporting "warm" against a service that has since gone
// cold — the exact failure the warmup gate exists to prevent, with the gate
// showing green. Re-warming costs one forward pass per 15 idle minutes.
const defaultWarmupTTL = 15 * time.Minute

// warmupTTL reads RL_AGENT_WARMUP_TTL (a time.ParseDuration string, e.g.
// "15m"). Unset -> defaultWarmupTTL. An EXPLICIT "0" (only when the env var is
// actually set) disables the TTL, i.e. warm exactly once per process — an
// opt-in for a fixed, never-restarted policy process. Unparseable or negative
// values fall back to the default rather than being silently reinterpreted as
// "disabled".
func warmupTTL() time.Duration {
	raw := strings.TrimSpace(os.Getenv("RL_AGENT_WARMUP_TTL"))
	if raw == "" {
		return defaultWarmupTTL
	}
	d, err := time.ParseDuration(raw)
	if err != nil || d < 0 {
		log.Printf("ignoring invalid RL_AGENT_WARMUP_TTL %q (using default %s)", raw, defaultWarmupTTL)
		return defaultWarmupTTL
	}
	return d
}

// shadowEventWindow reads RL_AGENT_SHADOW_EVENT_WINDOW, falling back to
// defaultWindow per parseEventWindowEnv's semantics.
func shadowEventWindow(defaultWindow uint32) uint32 {
	return parseEventWindowEnv("RL_AGENT_SHADOW_EVENT_WINDOW", defaultWindow)
}

// parseEventWindowEnv reads envVar as an event-history window: unset/empty
// falls back to defaultWindow; unparseable or exceeding
// rl.MaxEventHistoryWindow (512 — same bound internal/api's
// reviewEventWindow enforces) is rejected outright (logged, not clamped)
// rather than silently truncated, matching internal/rl's refusal semantics
// elsewhere (env.go, searchpool.go). Shared by every event-window env var in
// this package (RL_AGENT_EVENT_WINDOW, RL_AGENT_SHADOW_EVENT_WINDOW) so their
// parsing/rejection rules can never drift apart.
func parseEventWindowEnv(envVar string, defaultWindow uint32) uint32 {
	raw := strings.TrimSpace(os.Getenv(envVar))
	if raw == "" {
		return defaultWindow
	}
	n, err := strconv.ParseUint(raw, 10, 32)
	if err != nil {
		log.Printf("ignoring invalid %s %q: %v (using default %d)", envVar, raw, err, defaultWindow)
		return defaultWindow
	}
	if n > rl.MaxEventHistoryWindow {
		log.Printf("ignoring %s %q: exceeds maximum %d (using default %d)", envVar, raw, rl.MaxEventHistoryWindow, defaultWindow)
		return defaultWindow
	}
	return uint32(n)
}

// resolveAIBotEventWindow computes the event-history window for the
// matchmaking bot policy (AI_BOT_POLICY_URL), independently of rlEventWindow
// (RL_AGENT_EVENT_WINDOW, which governs the private-room RL primary). The two
// can point at DIFFERENT policy services during a staggered rollout
// (adversarial round 6, Finding 1); blindly sharing rlEventWindow across both
// would make one of them silently speak the wrong wire contract and degrade
// to heuristic on every /act call. AI_BOT_EVENT_WINDOW, parsed with the same
// parseEventWindowEnv helper as every other event-window env var in this
// package, lets operators set it independently.
//
// effectiveRLURL must be the RESOLVED RL endpoint (rlEndpointURL's return
// value — RL_AGENT_POLICY_URL, else AI_BOT_POLICY_URL, else the local
// default), never the raw RL_AGENT_POLICY_URL env var. Round 7, Finding 1:
// passing the raw override made "AI_BOT_POLICY_URL set, RL_AGENT_POLICY_URL
// unset" look like two different services, when rlEndpointURL's own fallback
// actually resolves the RL side onto AI_BOT_POLICY_URL itself — a single
// shared service whose window must be inherited, not zeroed. Resolving the
// fallback exactly once (in configurePolicies, via rlEndpointURL) and feeding the result
// in here keeps that logic from existing in two places.
//
// When AI_BOT_EVENT_WINDOW is unset: if aiBotPolicyURL and effectiveRLURL
// name the same backing service (per remote.SameServiceEndpoint — not just
// byte-for-byte equal; see adversarial round 9, Finding below), inherit
// rlEventWindow — the two clients speak the same server, so the same window
// is safe. Otherwise — genuinely different services, or neither URL
// configured — default to 0 (event-free) and fail closed rather than guess a
// contract the bot policy might not actually speak.
//
// Round 9: a bare == undercounts equivalent spellings of the same endpoint
// (e.g. "http://policy:8765/act" vs "http://policy:8765/act/", host case,
// an explicit default port like ":80"/":443") as different services, which
// zeroed the window and made the event server reject every /act call even
// though it was the correct service. remote.SameServiceEndpoint is the one
// shared normalization also used by internal/api's sameReviewService, so
// this logic exists in exactly one place.
func resolveAIBotEventWindow(aiBotPolicyURL, effectiveRLURL string, rlEventWindow uint32) uint32 {
	defaultWindow := uint32(0)
	if aiBotPolicyURL != "" && remote.SameServiceEndpoint(aiBotPolicyURL, effectiveRLURL) {
		defaultWindow = rlEventWindow
	}
	return parseEventWindowEnv("AI_BOT_EVENT_WINDOW", defaultWindow)
}

// validatePolicyContractAsync probes policy's /healthz in the background at
// startup (HTTPPolicy.ValidateServer — previously constructed but never
// invoked), confirming the served checkpoint's event-window/contract-version
// match what this Go server was configured to speak. Failures are logged
// LOUDLY but never fatal and never block boot: the policy server commonly
// isn't up yet when the backend starts (autostart launches it as a child
// process, and the RL option only surfaces once its own health check
// passes), and a genuine mismatch is still caught fail-closed at decision
// time by the heuristic fallback and serve_policy's own 400s. label
// identifies which policy in the logs (matchmaking bot / RL primary / RL
// shadow).
func validatePolicyContractAsync(label string, policy *remote.HTTPPolicy) {
	if policy == nil {
		return
	}
	go func() {
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		if err := policy.ValidateServer(ctx); err != nil {
			log.Printf("POLICY CONTRACT MISMATCH / server unreachable (%s): %v — serving falls back to heuristic per-decision until this is resolved", label, err)
			return
		}
		log.Printf("policy contract validated (%s)", label)
	}()
}
