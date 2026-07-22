package review

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"

	"github.com/plasma/fh-mahjong/internal/rl"
	pb "github.com/plasma/fh-mahjong/proto"
)

// evaluateChunkSize caps how many observations are sent in a single
// /evaluate request, mirroring the RPC-size discipline of
// internal/bot/remote's per-decision /act calls.
const evaluateChunkSize = 256

// PolicyResult is one observation's evaluation from the served policy.
// Probs is dense over the full 204-action catalog.
//
// Value is a pointer, not a plain float32 (adversarial round 15, Finding 4):
// a privileged-critic checkpoint's value head is out-of-distribution against
// serving's public-only planes, so the Python /evaluate endpoint sends JSON
// `null` for Value on those checkpoints rather than a misleading number. A
// plain float32 field would silently decode a JSON `null` as an
// indistinguishable 0.0 (encoding/json leaves non-pointer fields at their
// zero value on a null); the pointer preserves "absent" as nil instead of
// coercing it into a fake real value. Probs/action ranking are unaffected
// either way — only the value head is uncalibrated for these checkpoints.
type PolicyResult struct {
	Probs []float32
	Value *float32
}

// CheckpointInfo identifies which policy checkpoint produced a batch of
// PolicyResults, plus whether the values in that batch mean anything
// (ValuesCalibrated — see PolicyResult's doc).
//
// Sha256 is the served checkpoint's content hash (round 17, Finding 2):
// unlike Path/Step, a same-path hot reload changes it, so it is what lets
// Evaluate's cross-chunk consistency check (below) catch two chunks of one
// review that were actually served by two different checkpoint BYTES at the
// same path — Path/Step alone couldn't tell them apart. Empty when the
// server predates this field (a legacy serve_policy.py /evaluate response),
// meaning "unknown" rather than "no checkpoint" — see the mixed
// absent/present handling in Evaluate.
type CheckpointInfo struct {
	Path             string
	Step             int
	ValuesCalibrated bool
	Sha256           string
}

// PolicyClient evaluates a batch of observations against a served policy.
type PolicyClient interface {
	Evaluate(obs []*pb.SeatObservation) ([]PolicyResult, CheckpointInfo, error)
}

// HTTPPolicyClient is a PolicyClient backed by an HTTP /evaluate endpoint.
// It mirrors the request encoding of internal/bot/remote.HTTPPolicy's /act
// calls but batches many observations per request instead of one.
type HTTPPolicyClient struct {
	baseURL     string
	client      *http.Client
	eventWindow uint32
	token       string
}

// NewHTTPPolicyClient returns an HTTPPolicyClient that POSTs to
// {baseURL}/evaluate. eventWindow must match the served model's configured
// event_window (0 for a model with no event history): with eventWindow==0,
// batched requests are byte-identical to the pre-event-history wire format;
// with eventWindow>0, every observation in the request gains the compact
// event fields the Python /evaluate endpoint requires for an event-aware
// model (see evaluateChunk).
//
// No token is attached to requests (see evaluateChunk) — equivalent to
// NewHTTPPolicyClientWithToken(baseURL, eventWindow, ""). Production
// deployments MUST use NewHTTPPolicyClientWithToken instead (adversarial
// round 19): as of serve_policy.py's /evaluate auth gate, an unauthenticated
// request gets HTTP 403 from a properly configured server, so this
// constructor is retained mainly for tests exercising an unauthenticated
// (legacy/local) policy stub.
func NewHTTPPolicyClient(baseURL string, eventWindow uint32) *HTTPPolicyClient {
	return NewHTTPPolicyClientWithToken(baseURL, eventWindow, "")
}

// NewHTTPPolicyClientWithToken is NewHTTPPolicyClient plus a shared-secret
// token attached to every /evaluate request as an `Authorization: Bearer
// <token>` header (adversarial round 19): serve_policy.py's /evaluate now
// refuses every request with HTTP 403 unless one is configured server-side
// AND the caller presents a matching bearer token — mirroring the
// admin-token gate already required for POST /reload. An empty token
// attaches no header at all (see evaluateChunk), which only works against a
// serve_policy instance that likewise has no --evaluate-token/
// FH_MJ_EVALUATE_TOKEN configured.
func NewHTTPPolicyClientWithToken(baseURL string, eventWindow uint32, token string) *HTTPPolicyClient {
	return &HTTPPolicyClient{
		baseURL:     baseURL,
		client:      &http.Client{Timeout: 120 * time.Second},
		eventWindow: eventWindow,
		token:       token,
	}
}

type evaluateObservation struct {
	Seat       uint32    `json:"seat"`
	Planes     []float32 `json:"planes"`
	Scalars    []float32 `json:"scalars"`
	ActionMask []int     `json:"action_mask"`

	// Compact event-history fields, set only when the client is configured
	// with eventWindow > 0 (see evaluateChunk). Pointer types so a nil value
	// is dropped by omitempty regardless of the pointee's zero-ness — this
	// is what keeps the eventWindow==0 payload byte-identical to before.
	EventHistory    []uint32 `json:"event_history,omitempty"`
	EventCount      *int     `json:"event_count,omitempty"`
	EventWindow     *uint32  `json:"event_window,omitempty"`
	ContractVersion *int     `json:"contract_version,omitempty"`
}

type evaluateRequest struct {
	Observations []evaluateObservation `json:"observations"`
}

type evaluateResult struct {
	Probs []float32 `json:"probs"`
	// Value is a pointer so a JSON `null` (sent for privileged-critic
	// checkpoints — see PolicyResult's doc) decodes to nil rather than being
	// silently coerced to 0.0.
	Value *float32 `json:"value"`
}

type evaluateResponse struct {
	Results        []evaluateResult `json:"results"`
	CheckpointPath string           `json:"checkpoint_path"`
	CheckpointStep int              `json:"checkpoint_step"`
	Error          string           `json:"error"`
	// ValuesCalibrated is false when the served checkpoint is a
	// privileged-critic model (adversarial round 15, Finding 4): every
	// result's Value in this response is nil in that case. Absent on
	// responses from a server that predates this field decodes to the Go
	// zero value (false) — the conservative default of "don't assume
	// calibrated" rather than silently trusting an unknown response.
	ValuesCalibrated bool `json:"values_calibrated"`
	// CheckpointSha256 is the served checkpoint's content hash, from the
	// SAME PolicyHolder snapshot serve_policy.py used for this batch (round
	// 17, Finding 2). Absent on a legacy server that predates this field
	// decodes to "" — treated as "unknown" (see CheckpointInfo.Sha256), not
	// coerced into a fake shared identity with any other response.
	CheckpointSha256 string `json:"checkpoint_sha256"`
}

// Evaluate sends obs to the /evaluate endpoint in chunks of at most
// evaluateChunkSize, preserving order across chunks. Every chunk must report
// the same checkpoint (a hot-swap mid-review is an error, never a
// mixed-champion report), and any non-200 response, "error" field, or
// result-count mismatch aborts the whole call — never a partial result.
func (c *HTTPPolicyClient) Evaluate(obs []*pb.SeatObservation) ([]PolicyResult, CheckpointInfo, error) {
	if c == nil {
		return nil, CheckpointInfo{}, fmt.Errorf("nil HTTPPolicyClient")
	}
	results := make([]PolicyResult, 0, len(obs))
	var info CheckpointInfo
	haveInfo := false

	for start := 0; start < len(obs); start += evaluateChunkSize {
		end := start + evaluateChunkSize
		if end > len(obs) {
			end = len(obs)
		}
		chunk := obs[start:end]
		chunkResults, chunkInfo, err := c.evaluateChunk(chunk)
		if err != nil {
			return nil, CheckpointInfo{}, fmt.Errorf("evaluate chunk [%d:%d): %w", start, end, err)
		}
		if len(chunkResults) != len(chunk) {
			return nil, CheckpointInfo{}, fmt.Errorf("evaluate chunk [%d:%d): expected %d results, got %d", start, end, len(chunk), len(chunkResults))
		}
		if !haveInfo {
			info = chunkInfo
			haveInfo = true
		} else if chunkInfo != info {
			return nil, CheckpointInfo{}, fmt.Errorf("checkpoint mismatch across chunks: chunk [%d:%d) reported %+v, earlier chunks reported %+v", start, end, chunkInfo, info)
		}
		results = append(results, chunkResults...)
	}
	return results, info, nil
}

func (c *HTTPPolicyClient) evaluateChunk(obs []*pb.SeatObservation) ([]PolicyResult, CheckpointInfo, error) {
	payload := evaluateRequest{Observations: make([]evaluateObservation, len(obs))}
	for i, o := range obs {
		row := evaluateObservation{
			Seat:       o.Seat,
			Planes:     o.Planes,
			Scalars:    o.Scalars,
			ActionMask: actionMaskToInts(o.ActionMask),
		}
		if c.eventWindow > 0 {
			count := len(o.EventHistory)
			window := c.eventWindow
			version := rl.EventContractV1
			row.EventHistory = o.EventHistory
			row.EventCount = &count
			row.EventWindow = &window
			row.ContractVersion = &version
		}
		payload.Observations[i] = row
	}
	body, err := json.Marshal(payload)
	if err != nil {
		return nil, CheckpointInfo{}, fmt.Errorf("marshal request: %w", err)
	}

	client := c.client
	if client == nil {
		client = &http.Client{Timeout: 120 * time.Second}
	}
	timeout := client.Timeout
	if timeout <= 0 {
		timeout = 120 * time.Second
	}
	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+"/evaluate", bytes.NewReader(body))
	if err != nil {
		return nil, CheckpointInfo{}, fmt.Errorf("build request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	// Adversarial round 19: attach the shared-secret token as a bearer
	// header, mirroring /reload's admin-token auth. An empty c.token (the
	// zero value, e.g. via NewHTTPPolicyClient's no-token convenience
	// constructor) attaches no header at all, rather than sending
	// "Authorization: Bearer " with an empty token — a server with no token
	// configured rejects both identically, but omitting the header keeps
	// requests to such a server byte-identical to before this change.
	if c.token != "" {
		req.Header.Set("Authorization", "Bearer "+c.token)
	}

	resp, err := client.Do(req)
	if err != nil {
		return nil, CheckpointInfo{}, fmt.Errorf("request: %w", err)
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(io.LimitReader(resp.Body, 64<<20))
	if err != nil {
		return nil, CheckpointInfo{}, fmt.Errorf("read response: %w", err)
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, CheckpointInfo{}, fmt.Errorf("policy server status %d: %s", resp.StatusCode, string(respBody))
	}

	var decoded evaluateResponse
	if err := json.Unmarshal(respBody, &decoded); err != nil {
		return nil, CheckpointInfo{}, fmt.Errorf("decode response: %w", err)
	}
	if decoded.Error != "" {
		return nil, CheckpointInfo{}, fmt.Errorf("policy server error: %s", decoded.Error)
	}

	out := make([]PolicyResult, len(decoded.Results))
	for i, r := range decoded.Results {
		out[i] = PolicyResult{Probs: r.Probs, Value: r.Value}
	}
	info := CheckpointInfo{
		Path:             decoded.CheckpointPath,
		Step:             decoded.CheckpointStep,
		ValuesCalibrated: decoded.ValuesCalibrated,
		Sha256:           decoded.CheckpointSha256,
	}
	return out, info, nil
}

// reviewHealthzTimeout bounds CurrentCheckpointSha256's GET /healthz call.
// Deliberately short (independent of c.client's 120s /evaluate timeout):
// this is a cheap liveness probe, not a batch evaluation, and the caller
// (handlePostReview) treats a slow/unreachable healthz as "sha unknown" and
// falls back to serving the newest cached row rather than blocking the
// request on it.
const reviewHealthzTimeout = 5 * time.Second

// healthzEnvelope mirrors just the fields CurrentCheckpointSha256 needs from
// serve_policy.py's GET /healthz response (see ai/src/fh_mahjong_ai/scripts/
// serve_policy.py's do_GET and internal/bot/remote/health.go's
// healthzPayload for the fuller contract). Extra fields are ignored.
type healthzEnvelope struct {
	Ok               *bool  `json:"ok"`
	CheckpointSha256 string `json:"checkpoint_sha256"`
}

// CurrentCheckpointSha256 resolves the checkpoint content hash the policy
// server is CURRENTLY serving, via its GET /healthz route (round 21, Finding
// 2). This is what lets handlePostReview's cache lookup key on the
// checkpoint actually serving right now, instead of trusting the newest
// cached MatchReview row regardless of whether the server has since been
// promoted, hot-reloaded, or rolled back to a different checkpoint.
//
// Returns ("", err) when healthz is unreachable, returns a non-2xx status,
// or its body doesn't decode into a genuine "ok": true envelope — the
// caller's documented choice (round 21, Finding 2) is to treat this
// identically to "sha unknown" and fall back to serving the newest cached
// row for a read-mostly endpoint, rather than erroring the request over a
// healthz hiccup: a build that's actually needed will still hit the same
// unreachable server and surface its own 502 below.
//
// Returns ("", nil) — NOT an error — when healthz is reachable and reports
// "ok": true but simply omits checkpoint_sha256: a legacy serve_policy.py
// that predates the field. The caller folds this into the same "sha
// unknown" fallback as the error case, mirroring reviewCacheCheckpointID's
// own path-based fallback for legacy /evaluate responses.
func (c *HTTPPolicyClient) CurrentCheckpointSha256() (string, error) {
	if c == nil {
		return "", fmt.Errorf("nil HTTPPolicyClient")
	}

	ctx, cancel := context.WithTimeout(context.Background(), reviewHealthzTimeout)
	defer cancel()

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.baseURL+"/healthz", nil)
	if err != nil {
		return "", fmt.Errorf("build healthz request: %w", err)
	}
	// Same bearer-token convention as evaluateChunk: an empty c.token
	// attaches no header at all.
	if c.token != "" {
		req.Header.Set("Authorization", "Bearer "+c.token)
	}

	client := c.client
	if client == nil {
		client = &http.Client{Timeout: reviewHealthzTimeout}
	}

	resp, err := client.Do(req)
	if err != nil {
		return "", fmt.Errorf("healthz request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return "", fmt.Errorf("healthz status %d", resp.StatusCode)
	}

	body, err := io.ReadAll(io.LimitReader(resp.Body, 1<<16))
	if err != nil {
		return "", fmt.Errorf("read healthz response: %w", err)
	}

	var envelope healthzEnvelope
	if err := json.Unmarshal(body, &envelope); err != nil {
		return "", fmt.Errorf("decode healthz response: %w", err)
	}
	if envelope.Ok == nil || !*envelope.Ok {
		return "", fmt.Errorf("healthz did not report ok:true")
	}
	return envelope.CheckpointSha256, nil
}

func actionMaskToInts(mask []byte) []int {
	out := make([]int, len(mask))
	for i, v := range mask {
		out[i] = int(v)
	}
	return out
}
