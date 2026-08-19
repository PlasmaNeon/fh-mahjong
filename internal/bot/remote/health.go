package remote

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"sync"
	"time"

	"github.com/plasma/fh-mahjong/internal/rl"
)

const (
	defaultHealthTimeout = 500 * time.Millisecond
	defaultHealthTTL     = 5 * time.Second
)

// HealthChecker reports whether a serve_policy.py policy endpoint is currently
// reachable by probing its GET /healthz route. Results are cached for a short
// TTL so callers (the /config capability check and seat-assignment gate) can
// ask freely without hammering the model server. A zero-value or nil checker
// reports unhealthy.
type HealthChecker struct {
	healthURL           string
	client              *http.Client
	ttl                 time.Duration
	expectedEventWindow uint32

	mu        sync.Mutex
	checkedAt time.Time
	healthy   bool
	primed    bool
	identity  string
}

// HealthCheckerOption configures optional HealthChecker behavior beyond bare
// reachability.
type HealthCheckerOption func(*HealthChecker)

// WithExpectedEventWindow makes the recurring health check also validate the
// serving contract: a reachable endpoint whose /healthz reports a different
// event_window (or a contract_version other than rl.EventContractV1) than
// window is reported UNHEALTHY, not just anonymous. This is what lets
// RLAgentAvailable catch a reachable-but-contract-mismatched server (the
// one-shot boot probe, validatePolicyContractAsync, only ever runs once at
// startup — often before a locally-managed policy server is even up — so it
// can miss a contract drift that only appears later). window <= 0 keeps the
// default reachability-only behavior.
func WithExpectedEventWindow(window uint32) HealthCheckerOption {
	return func(h *HealthChecker) {
		h.expectedEventWindow = window
	}
}

// NewHealthChecker builds a checker for the given /act endpoint. The /healthz
// URL is derived from it (same scheme+host, path "/healthz").
func NewHealthChecker(actEndpoint string, opts ...HealthCheckerOption) *HealthChecker {
	h := &HealthChecker{
		healthURL: deriveHealthURL(actEndpoint),
		client:    &http.Client{Timeout: defaultHealthTimeout},
		ttl:       defaultHealthTTL,
	}
	for _, opt := range opts {
		opt(h)
	}
	return h
}

// siblingRoute maps an /act endpoint to another serve_policy.py route on the
// same host, dropping any query or fragment. Returns "" when the endpoint is
// not a usable absolute URL.
func siblingRoute(actEndpoint, route string) string {
	u, err := url.Parse(actEndpoint)
	if err != nil || u.Scheme == "" || u.Host == "" {
		return ""
	}
	u.Path = route
	u.RawQuery = ""
	u.Fragment = ""
	return u.String()
}

// deriveHealthURL maps an /act endpoint to the serve_policy.py /healthz route.
func deriveHealthURL(actEndpoint string) string { return siblingRoute(actEndpoint, "/healthz") }

// Healthy reports whether the endpoint responded to its last (cached) probe.
// It is safe to call concurrently and from a nil receiver.
func (h *HealthChecker) Healthy() bool {
	if h == nil || h.healthURL == "" {
		return false
	}
	h.mu.Lock()
	defer h.mu.Unlock()
	h.refreshLocked()
	return h.healthy
}

// Identity reports the serving policy's checkpoint identity as
// "<checkpoint>@step<N>", extracted from the /healthz JSON payload. Empty when
// the endpoint is unreachable or its healthz body carries no checkpoint info
// (e.g. an older policy server). Shares the Healthy() probe cache.
func (h *HealthChecker) Identity() string {
	if h == nil || h.healthURL == "" {
		return ""
	}
	h.mu.Lock()
	defer h.mu.Unlock()
	h.refreshLocked()
	return h.identity
}

// refreshLocked re-probes the endpoint when the cached result expired.
// Caller must hold h.mu.
func (h *HealthChecker) refreshLocked() {
	if h.primed && time.Since(h.checkedAt) < h.ttl {
		return
	}
	h.healthy, h.identity = h.probe()
	h.checkedAt = time.Now()
	h.primed = true
}

// healthzPayload mirrors the identity and event-contract fields of
// serve_policy.py's GET /healthz response. Extra fields are ignored.
// EventWindow/ContractVersion are pointers so ABSENT (a legacy server that
// predates the event contract, decodes as nil) can be told apart from
// EXPLICITLY PUBLISHED zero values — a server that publishes event_window:0
// is making a claim that must still match what this checker expects, unlike
// a legacy server that says nothing at all.
type healthzPayload struct {
	Ok              *bool   `json:"ok"`
	Checkpoint      string  `json:"checkpoint"`
	CheckpointStep  int64   `json:"checkpoint_step"`
	EventWindow     *uint32 `json:"event_window"`
	ContractVersion *uint32 `json:"contract_version"`
}

// validHealthzBody reports whether raw is a genuine, non-vacuous healthz
// response (round 17, Finding 1). serve_policy.py's GET /healthz ALWAYS
// emits "ok": true on success (see ai/src/fh_mahjong_ai/scripts/serve_policy.py
// do_GET, and the pre-B2c legacy server it descends from) — so {}, a bare
// JSON `null`, or an explicit "ok": false are never legitimate. Those all
// decode without error into healthzPayload's zero value, which is why the
// old code fell through to "Checkpoint=="" -> healthy, anonymous" and
// silently treated an empty/negative body as legacy reachability. raw must
// also be a JSON *object* (not an array/string/number/bool masquerading as
// one).
func validHealthzBody(raw []byte) bool {
	trimmed := bytes.TrimSpace(raw)
	if len(trimmed) == 0 || string(trimmed) == "null" {
		return false
	}
	var asObject map[string]json.RawMessage
	if err := json.Unmarshal(raw, &asObject); err != nil {
		// Valid JSON that isn't an object (e.g. `42`, `"ok"`, `[]`) is never
		// a legitimate healthz body.
		return false
	}
	var envelope struct {
		Ok *bool `json:"ok"`
	}
	if err := json.Unmarshal(raw, &envelope); err != nil {
		return false
	}
	return envelope.Ok != nil && *envelope.Ok
}

// fetchHealthzBody performs the GET /healthz round-trip shared by
// HealthChecker.probe and HTTPPolicy.ValidateServer: apply the timeout, read a
// bounded body, and reject anything that is not a genuine healthz response.
//
// The vacuity check is part of this helper deliberately. A 2xx body that is not
// the healthz contract -- a misrouted URL, a reverse-proxy error page, an SPA
// fallback, {} , JSON null, or "ok": false -- once let a misrouted endpoint
// advertise itself as a healthy RL agent while every /act silently fell back to
// the heuristic (rounds 16 and 17). Keeping the rule here means a third caller
// cannot forget it.
func fetchHealthzBody(ctx context.Context, client *http.Client, healthURL string, timeout time.Duration) ([]byte, error) {
	if timeout <= 0 {
		timeout = defaultHealthTimeout
	}
	reqCtx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()
	req, err := http.NewRequestWithContext(reqCtx, http.MethodGet, healthURL, nil)
	if err != nil {
		return nil, err
	}
	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, fmt.Errorf("healthz status %d", resp.StatusCode)
	}
	raw, err := io.ReadAll(io.LimitReader(resp.Body, 1<<16))
	if err != nil {
		return nil, err
	}
	if !validHealthzBody(raw) {
		return nil, fmt.Errorf("healthz body is not a valid healthz response")
	}
	return raw, nil
}

func (h *HealthChecker) probe() (healthy bool, identity string) {
	raw, err := fetchHealthzBody(context.Background(), h.client, h.healthURL, h.client.Timeout)
	if err != nil {
		return false, ""
	}

	var payload healthzPayload
	if err := json.Unmarshal(raw, &payload); err != nil {
		return false, ""
	}

	// A server that PUBLISHES the event contract (event_window present in
	// its /healthz body) is making an explicit claim about its wire form —
	// that claim must match this checker's expectation regardless of
	// whether the checker itself expects events (window > 0) or not
	// (window == 0, e.g. expected 0 vs published 128). A server that omits
	// the field entirely (nil) is legacy and keeps today's behavior: healthy
	// for window-0 checkers, unhealthy for event checkers (handled below).
	if payload.EventWindow != nil {
		var contractVersion uint32
		if payload.ContractVersion != nil {
			contractVersion = *payload.ContractVersion
		}
		if contractVersion != rl.EventContractV1 || *payload.EventWindow != h.expectedEventWindow {
			// Reachable but speaking the wrong wire contract: every /act
			// against this endpoint would be rejected or mis-decoded, so it
			// must not be offered as available.
			return false, ""
		}
	} else if h.expectedEventWindow > 0 {
		// Event checker talking to a legacy server that never mentions the
		// contract at all: cannot verify a match, fail closed.
		return false, ""
	}

	// Identity is best-effort: a healthz body without checkpoint info still
	// counts as healthy, just anonymous.
	if payload.Checkpoint == "" {
		return true, ""
	}
	return true, checkpointIdentity(payload.Checkpoint, payload.CheckpointStep)
}
