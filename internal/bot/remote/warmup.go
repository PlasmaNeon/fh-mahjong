package remote

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"time"
)

// defaultWarmupTimeout is the per-attempt budget for POST /warmup. It is
// deliberately much larger than the 750ms /act budget: /warmup exists to pay
// the cold-start cost (first CPU forward pass, lazy torch kernel init) ONCE,
// up front, so no real decision ever has to. Warming is off the critical path
// of any in-match decision — it only gates room admission.
const defaultWarmupTimeout = 10 * time.Second

// warmupLogPrefix marks every warmup telemetry line so the rollout gate can
// grep for them ("policy warmup:").
const warmupLogPrefix = "policy warmup:"

// WarmupManager drives serve_policy.py's POST /warmup endpoint, ENDPOINT-SCOPED
// and ONCE PER PROCESS: an endpoint that has been warmed successfully is not
// warmed again (unless a TTL is configured and has expired), no matter how many
// rooms or seats later ask. Concurrent Warm calls for the same endpoint
// coalesce into a single HTTP request whose result every caller receives. A
// FAILED warmup leaves the endpoint cold, so the next admission attempt retries
// it — failure is never latched.
//
// The zero value is not usable; construct with NewWarmupManager. A nil manager
// fails closed (Warm returns an error) rather than silently reporting warm.
type WarmupManager struct {
	client *http.Client
	logger Logger
	ttl    time.Duration

	mu    sync.Mutex
	state map[string]*warmupState
}

// warmupState is the per-endpoint record: whether it is currently considered
// warm (and since when), plus the in-flight call other callers coalesce onto.
type warmupState struct {
	warm     bool
	warmedAt time.Time
	inflight *warmupCall
}

// warmupCall is one in-flight HTTP warmup that concurrent callers share.
type warmupCall struct {
	done chan struct{}
	err  error
}

// NewWarmupManager builds a manager. A nil client gets a dedicated client with
// the 10-second warmup timeout — deliberately NOT the shared 750ms /act client,
// whose budget a cold forward pass would blow every time.
func NewWarmupManager(client *http.Client) *WarmupManager {
	if client == nil {
		client = &http.Client{Timeout: defaultWarmupTimeout}
	}
	return &WarmupManager{
		client: client,
		state:  make(map[string]*warmupState),
	}
}

// WithWarmupTTL makes a warmed endpoint go cold again after d, so a long-lived
// backend re-warms a policy service that may itself have gone idle. The
// default, 0, means warm exactly once per process. Returns the receiver so it
// can be chained onto NewWarmupManager. Not safe to call concurrently with
// Warm (call it at construction time).
func (m *WarmupManager) WithWarmupTTL(d time.Duration) *WarmupManager {
	if m == nil {
		return m
	}
	if d < 0 {
		d = 0
	}
	m.ttl = d
	return m
}

// WithWarmupLogger installs the telemetry sink for warmup attempts. Nil (the
// default) disables logging. Returns the receiver for chaining. Not safe to
// call concurrently with Warm.
func (m *WarmupManager) WithWarmupLogger(logger Logger) *WarmupManager {
	if m == nil {
		return m
	}
	m.logger = logger
	return m
}

// Warm ensures the policy service behind the given /act endpoint has taken a
// real forward pass. token, when non-empty, is sent as
// "Authorization: Bearer <token>" — the same scheme serve_policy.py's
// /evaluate uses and that /warmup piggybacks on when the service is configured
// with an evaluate token (internal/review's client speaks the identical
// scheme). The PRIMARY production service runs tokenless, in which case
// /warmup is open and token must be empty.
//
// Returns nil when the endpoint is already warm (fast path, no HTTP at all).
func (m *WarmupManager) Warm(ctx context.Context, endpoint, token string) error {
	if m == nil {
		return fmt.Errorf("nil warmup manager")
	}
	if strings.TrimSpace(endpoint) == "" {
		return fmt.Errorf("warmup endpoint is empty")
	}
	warmupURL := deriveWarmupURL(endpoint)
	if warmupURL == "" {
		return fmt.Errorf("remote policy endpoint %q has no derivable /warmup URL", endpoint)
	}

	m.mu.Lock()
	entry := m.state[endpoint]
	if entry == nil {
		entry = &warmupState{}
		m.state[endpoint] = entry
	}
	if entry.warm && (m.ttl == 0 || time.Since(entry.warmedAt) < m.ttl) {
		m.mu.Unlock()
		return nil
	}
	if call := entry.inflight; call != nil {
		// Another caller is already warming this endpoint: share its result
		// rather than issuing a second cold forward pass.
		m.mu.Unlock()
		select {
		case <-call.done:
			return call.err
		case <-ctx.Done():
			return ctx.Err()
		}
	}
	call := &warmupCall{done: make(chan struct{})}
	entry.inflight = call
	m.mu.Unlock()

	err := m.doWarmup(ctx, warmupURL, endpoint, token)

	m.mu.Lock()
	entry.inflight = nil
	if err == nil {
		entry.warm = true
		entry.warmedAt = time.Now()
	} else {
		// Failure is never latched: leaving the endpoint cold means the next
		// admission attempt retries it.
		entry.warm = false
	}
	m.mu.Unlock()

	call.err = err
	close(call.done)
	return err
}

// Warmed reports whether the endpoint is currently considered warm (honoring
// any configured TTL). Intended for tests and diagnostics.
func (m *WarmupManager) Warmed(endpoint string) bool {
	if m == nil {
		return false
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	entry := m.state[endpoint]
	if entry == nil || !entry.warm {
		return false
	}
	return m.ttl == 0 || time.Since(entry.warmedAt) < m.ttl
}

// warmupResponse mirrors serve_policy.py's POST /warmup body. Extra fields are
// ignored.
type warmupResponse struct {
	Warmed           bool    `json:"warmed"`
	CheckpointPath   string  `json:"checkpoint_path"`
	CheckpointStep   int64   `json:"checkpoint_step"`
	CheckpointSha256 string  `json:"checkpoint_sha256"`
	ContractVersion  uint32  `json:"contract_version"`
	EventWindow      uint32  `json:"event_window"`
	LatencyMS        float64 `json:"latency_ms"`
}

// doWarmup performs one POST /warmup and logs the attempt. endpoint is passed
// alongside warmupURL purely for telemetry (operators configure the /act URL).
func (m *WarmupManager) doWarmup(ctx context.Context, warmupURL, endpoint, token string) error {
	client := m.client
	if client == nil {
		client = &http.Client{Timeout: defaultWarmupTimeout}
	}
	timeout := client.Timeout
	if timeout <= 0 {
		timeout = defaultWarmupTimeout
	}
	// Warmup gets its own budget, separate from the /act timeout, but never
	// outlives the caller's context (room admission gives up with it).
	reqCtx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()

	started := time.Now()
	resp, body, err := m.postWarmup(reqCtx, warmupURL, token)
	elapsed := time.Since(started)
	if err != nil {
		m.logAttempt(endpoint, elapsed, warmupResponse{}, err)
		return err
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		err := fmt.Errorf("warmup status %d: %s", resp.StatusCode, strings.TrimSpace(string(body)))
		m.logAttempt(endpoint, elapsed, warmupResponse{}, err)
		return err
	}

	var payload warmupResponse
	if jerr := json.Unmarshal(body, &payload); jerr != nil {
		err := fmt.Errorf("warmup body is not valid JSON: %w", jerr)
		m.logAttempt(endpoint, elapsed, warmupResponse{}, err)
		return err
	}
	if !payload.Warmed {
		err := fmt.Errorf("warmup response reports warmed=false")
		m.logAttempt(endpoint, elapsed, payload, err)
		return err
	}
	m.logAttempt(endpoint, elapsed, payload, nil)
	return nil
}

// postWarmup issues the request and reads a capped response body. The body is
// an empty JSON object: /warmup ignores it, but sending "{}" (with an explicit
// Content-Length) keeps the request well-formed for proxies.
func (m *WarmupManager) postWarmup(ctx context.Context, warmupURL, token string) (*http.Response, []byte, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, warmupURL, strings.NewReader("{}"))
	if err != nil {
		return nil, nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	if token != "" {
		// Same scheme serve_policy.py checks for /evaluate; /warmup reuses that
		// token when the service is configured with one, and is open otherwise.
		req.Header.Set("Authorization", "Bearer "+token)
	}
	resp, err := m.client.Do(req)
	if err != nil {
		return nil, nil, err
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(io.LimitReader(resp.Body, 1<<16))
	if err != nil {
		return nil, nil, err
	}
	return resp, body, nil
}

// logAttempt emits the grep-able telemetry line that the rollout gate reads:
// one per warmup ATTEMPT (not per admission), with endpoint, observed
// round-trip latency, the server-reported forward-pass latency, the serving
// checkpoint sha, and success/failure.
func (m *WarmupManager) logAttempt(endpoint string, elapsed time.Duration, payload warmupResponse, err error) {
	if m.logger == nil {
		return
	}
	if err != nil {
		m.logger(
			"%s endpoint=%q ok=false latency_ms=%.1f err=%v",
			warmupLogPrefix, endpoint, float64(elapsed.Microseconds())/1000.0, err,
		)
		return
	}
	m.logger(
		"%s endpoint=%q ok=true latency_ms=%.1f server_latency_ms=%.1f checkpoint_sha=%s checkpoint_step=%d event_window=%d",
		warmupLogPrefix,
		endpoint,
		float64(elapsed.Microseconds())/1000.0,
		payload.LatencyMS,
		payload.CheckpointSha256,
		payload.CheckpointStep,
		payload.EventWindow,
	)
}

// deriveWarmupURL maps an /act endpoint to the serve_policy.py /warmup route,
// exactly as deriveHealthURL maps it to /healthz. Returns "" when the endpoint
// cannot be parsed.
func deriveWarmupURL(actEndpoint string) string {
	u, err := url.Parse(actEndpoint)
	if err != nil || u.Scheme == "" || u.Host == "" {
		return ""
	}
	u.Path = "/warmup"
	u.RawQuery = ""
	u.Fragment = ""
	return u.String()
}
