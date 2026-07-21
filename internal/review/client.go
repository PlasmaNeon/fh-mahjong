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
type PolicyResult struct {
	Probs []float32
	Value float32
}

// CheckpointInfo identifies which policy checkpoint produced a batch of
// PolicyResults.
type CheckpointInfo struct {
	Path string
	Step int
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
}

// NewHTTPPolicyClient returns an HTTPPolicyClient that POSTs to
// {baseURL}/evaluate. eventWindow must match the served model's configured
// event_window (0 for a model with no event history): with eventWindow==0,
// batched requests are byte-identical to the pre-event-history wire format;
// with eventWindow>0, every observation in the request gains the compact
// event fields the Python /evaluate endpoint requires for an event-aware
// model (see evaluateChunk).
func NewHTTPPolicyClient(baseURL string, eventWindow uint32) *HTTPPolicyClient {
	return &HTTPPolicyClient{
		baseURL:     baseURL,
		client:      &http.Client{Timeout: 120 * time.Second},
		eventWindow: eventWindow,
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
	Value float32   `json:"value"`
}

type evaluateResponse struct {
	Results        []evaluateResult `json:"results"`
	CheckpointPath string           `json:"checkpoint_path"`
	CheckpointStep int              `json:"checkpoint_step"`
	Error          string           `json:"error"`
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
	return out, CheckpointInfo{Path: decoded.CheckpointPath, Step: decoded.CheckpointStep}, nil
}

func actionMaskToInts(mask []byte) []int {
	out := make([]int, len(mask))
	for i, v := range mask {
		out[i] = int(v)
	}
	return out
}
