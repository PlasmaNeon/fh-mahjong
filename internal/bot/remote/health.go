package remote

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"sync"
	"time"
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
	healthURL string
	client    *http.Client
	ttl       time.Duration

	mu        sync.Mutex
	checkedAt time.Time
	healthy   bool
	primed    bool
	identity  string
}

// NewHealthChecker builds a checker for the given /act endpoint. The /healthz
// URL is derived from it (same scheme+host, path "/healthz").
func NewHealthChecker(actEndpoint string) *HealthChecker {
	return &HealthChecker{
		healthURL: deriveHealthURL(actEndpoint),
		client:    &http.Client{Timeout: defaultHealthTimeout},
		ttl:       defaultHealthTTL,
	}
}

// deriveHealthURL maps an /act endpoint to the serve_policy.py /healthz route.
// Returns "" when the endpoint cannot be parsed, which makes the checker report
// unhealthy.
func deriveHealthURL(actEndpoint string) string {
	u, err := url.Parse(actEndpoint)
	if err != nil || u.Scheme == "" || u.Host == "" {
		return ""
	}
	u.Path = "/healthz"
	u.RawQuery = ""
	u.Fragment = ""
	return u.String()
}

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

// healthzPayload mirrors the identity fields of serve_policy.py's GET /healthz
// response. Extra fields are ignored.
type healthzPayload struct {
	Checkpoint     string `json:"checkpoint"`
	CheckpointStep int64  `json:"checkpoint_step"`
}

func (h *HealthChecker) probe() (healthy bool, identity string) {
	timeout := h.client.Timeout
	if timeout <= 0 {
		timeout = defaultHealthTimeout
	}
	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, h.healthURL, nil)
	if err != nil {
		return false, ""
	}
	resp, err := h.client.Do(req)
	if err != nil {
		return false, ""
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return false, ""
	}
	// Identity is best-effort: a healthz body without checkpoint info (or
	// that isn't JSON) still counts as healthy, just anonymous.
	var payload healthzPayload
	if err := json.NewDecoder(io.LimitReader(resp.Body, 1<<16)).Decode(&payload); err != nil || payload.Checkpoint == "" {
		return true, ""
	}
	return true, fmt.Sprintf("%s@step%d", payload.Checkpoint, payload.CheckpointStep)
}
