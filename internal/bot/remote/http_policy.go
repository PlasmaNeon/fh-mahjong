package remote

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"sync"
	"sync/atomic"
	"time"

	"github.com/plasma/fh-mahjong/internal/bot"
	"github.com/plasma/fh-mahjong/internal/rl"
	pb "github.com/plasma/fh-mahjong/proto"
)

const defaultTimeout = 750 * time.Millisecond

const (
	FallbackReasonConfig        = "config"
	FallbackReasonEncode        = "encode"
	FallbackReasonRequest       = "request"
	FallbackReasonStatus        = "status"
	FallbackReasonBadJSON       = "bad_json"
	FallbackReasonRemoteError   = "remote_error"
	FallbackReasonIllegalAction = "illegal_action"
	FallbackReasonDecode        = "decode"
	FallbackReasonUnknown       = "unknown"
)

type HTTPPolicy struct {
	endpoint      string
	client        *http.Client
	fallback      bot.Policy
	decisionIndex uint64
	logger        Logger
	statsLogEvery uint64

	remoteCalls     atomic.Uint64
	remoteSuccesses atomic.Uint64
	fallbacks       atomic.Uint64
	noFallback      atomic.Uint64

	fallbackConfig        atomic.Uint64
	fallbackEncode        atomic.Uint64
	fallbackRequest       atomic.Uint64
	fallbackStatus        atomic.Uint64
	fallbackBadJSON       atomic.Uint64
	fallbackRemoteError   atomic.Uint64
	fallbackIllegalAction atomic.Uint64
	fallbackDecode        atomic.Uint64
	fallbackUnknown       atomic.Uint64

	// observedPolicyIDs records the distinct checkpoint identities
	// ("<path>@step<N>") that actually served /act responses, in serving
	// order. A policy hot reload mid-match adds a second entry, keeping
	// dataset attribution honest (see Room.persistMatch reconciliation).
	observedMu        sync.Mutex
	observedPolicyIDs []string
}

type Option func(*HTTPPolicy)

type Logger func(format string, args ...any)

type HTTPPolicyStats struct {
	RemoteCalls     uint64
	RemoteSuccesses uint64
	Fallbacks       uint64
	NoFallback      uint64
	FallbackReasons map[string]uint64
}

func WithHTTPClient(client *http.Client) Option {
	return func(policy *HTTPPolicy) {
		if client != nil {
			policy.client = client
		}
	}
}

func WithFallback(fallback bot.Policy) Option {
	return func(policy *HTTPPolicy) {
		policy.fallback = fallback
	}
}

func WithLogger(logger Logger) Option {
	return func(policy *HTTPPolicy) {
		policy.logger = logger
	}
}

func WithStatsLogEvery(decisions uint64) Option {
	return func(policy *HTTPPolicy) {
		policy.statsLogEvery = decisions
	}
}

func NewHTTPPolicy(endpoint string, opts ...Option) *HTTPPolicy {
	policy := &HTTPPolicy{
		endpoint: endpoint,
		client: &http.Client{
			Timeout: defaultTimeout,
		},
		fallback:      bot.NewHeuristicPolicy(),
		logger:        log.Printf,
		statsLogEvery: 100,
	}
	for _, opt := range opts {
		opt(policy)
	}
	return policy
}

func (p *HTTPPolicy) ChooseAction(state *pb.GameState, seat uint32) *pb.PlayerAction {
	if p == nil {
		return nil
	}
	callCount := p.remoteCalls.Add(1)
	action, err := p.chooseRemote(state, seat)
	if err == nil && action != nil {
		p.remoteSuccesses.Add(1)
		p.logStatsIfDue(callCount)
		return action
	}
	reason := fallbackReason(err)
	p.recordFallback(reason, err, seat)
	p.logStatsIfDue(callCount)
	if p.fallback == nil {
		p.noFallback.Add(1)
		return nil
	}
	return p.fallback.ChooseAction(state, seat)
}

func (p *HTTPPolicy) Stats() HTTPPolicyStats {
	if p == nil {
		return HTTPPolicyStats{FallbackReasons: map[string]uint64{}}
	}
	return HTTPPolicyStats{
		RemoteCalls:     p.remoteCalls.Load(),
		RemoteSuccesses: p.remoteSuccesses.Load(),
		Fallbacks:       p.fallbacks.Load(),
		NoFallback:      p.noFallback.Load(),
		FallbackReasons: map[string]uint64{
			FallbackReasonConfig:        p.fallbackConfig.Load(),
			FallbackReasonEncode:        p.fallbackEncode.Load(),
			FallbackReasonRequest:       p.fallbackRequest.Load(),
			FallbackReasonStatus:        p.fallbackStatus.Load(),
			FallbackReasonBadJSON:       p.fallbackBadJSON.Load(),
			FallbackReasonRemoteError:   p.fallbackRemoteError.Load(),
			FallbackReasonIllegalAction: p.fallbackIllegalAction.Load(),
			FallbackReasonDecode:        p.fallbackDecode.Load(),
			FallbackReasonUnknown:       p.fallbackUnknown.Load(),
		},
	}
}

func (p *HTTPPolicy) chooseRemote(state *pb.GameState, seat uint32) (*pb.PlayerAction, error) {
	if p == nil {
		return nil, policyError{reason: FallbackReasonConfig, err: fmt.Errorf("nil remote policy")}
	}
	if state == nil {
		return nil, policyError{reason: FallbackReasonConfig, err: fmt.Errorf("nil game state")}
	}
	if p.endpoint == "" {
		return nil, policyError{reason: FallbackReasonConfig, err: fmt.Errorf("remote policy endpoint is empty")}
	}

	observation, err := rl.EncodeObservation(state, seat, p.decisionIndex)
	if err != nil {
		return nil, policyError{reason: FallbackReasonEncode, err: err}
	}
	p.decisionIndex++

	requestPayload := actRequest{
		Seat:       observation.Seat,
		Planes:     observation.Planes,
		Scalars:    observation.Scalars,
		ActionMask: actionMaskJSON(observation.ActionMask),
		Metadata: map[string]any{
			"decision_index": observation.DecisionIndex,
			"phase":          observation.Phase.String(),
			"active_player":  observation.ActivePlayer,
		},
	}
	body, err := json.Marshal(requestPayload)
	if err != nil {
		return nil, policyError{reason: FallbackReasonRequest, err: err}
	}

	client := p.client
	if client == nil {
		client = &http.Client{Timeout: defaultTimeout}
	}
	timeout := client.Timeout
	if timeout <= 0 {
		timeout = defaultTimeout
	}
	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, p.endpoint, bytes.NewReader(body))
	if err != nil {
		return nil, policyError{reason: FallbackReasonRequest, err: err}
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := client.Do(req)
	if err != nil {
		return nil, policyError{reason: FallbackReasonRequest, err: err}
	}
	defer resp.Body.Close()

	payload, err := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
	if err != nil {
		return nil, policyError{reason: FallbackReasonRequest, err: err}
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, policyError{
			reason: FallbackReasonStatus,
			err:    fmt.Errorf("remote policy status %d: %s", resp.StatusCode, string(payload)),
		}
	}

	var response actResponse
	if err := json.Unmarshal(payload, &response); err != nil {
		return nil, policyError{reason: FallbackReasonBadJSON, err: err}
	}
	if response.Error != "" {
		return nil, policyError{
			reason: FallbackReasonRemoteError,
			err:    fmt.Errorf("remote policy error: %s", response.Error),
		}
	}
	if response.ActionID < 0 || response.ActionID >= rl.ActionSpaceSize {
		return nil, policyError{
			reason: FallbackReasonIllegalAction,
			err:    fmt.Errorf("remote policy returned action id %d outside action space", response.ActionID),
		}
	}

	action, err := rl.DecodeActionID(state, seat, response.ActionID)
	if err != nil {
		return nil, policyError{reason: FallbackReasonIllegalAction, err: err}
	}
	// Attribute the checkpoint only now that its action passed validation
	// and will actually be played (a rejected response falls back to the
	// heuristic, which must not be credited to the remote checkpoint).
	if response.CheckpointPath != "" {
		p.recordObservedPolicyID(checkpointIdentity(response.CheckpointPath, response.CheckpointStep))
	}
	return action, nil
}

type actRequest struct {
	Seat       uint32         `json:"seat"`
	Planes     []float32      `json:"planes"`
	Scalars    []float32      `json:"scalars"`
	ActionMask []int          `json:"action_mask"`
	Metadata   map[string]any `json:"metadata,omitempty"`
}

type actResponse struct {
	ActionID       int     `json:"action_id"`
	Value          float64 `json:"value,omitempty"`
	Error          string  `json:"error,omitempty"`
	CheckpointPath string  `json:"checkpoint_path,omitempty"`
	CheckpointStep int64   `json:"checkpoint_step,omitempty"`
}

// Bounds on remote-reported checkpoint identities: the values come from an
// external response and end up in a varchar(512) column that shares a
// transaction with the match write, so a hostile/misconfigured server must
// not be able to bloat them.
const (
	maxObservedPolicyIDs   = 8
	maxObservedPolicyIDLen = 256
)

// recordObservedPolicyID appends a checkpoint identity the first time it is
// seen. The list stays tiny (one entry per hot reload), so a linear scan is
// fine.
func (p *HTTPPolicy) recordObservedPolicyID(id string) {
	if len(id) > maxObservedPolicyIDLen {
		id = id[:maxObservedPolicyIDLen]
	}
	p.observedMu.Lock()
	defer p.observedMu.Unlock()
	for _, existing := range p.observedPolicyIDs {
		if existing == id {
			return
		}
	}
	if len(p.observedPolicyIDs) >= maxObservedPolicyIDs {
		return
	}
	p.observedPolicyIDs = append(p.observedPolicyIDs, id)
}

// DecisionCounts reports how many decisions the remote endpoint actually
// served vs how many fell back to the local heuristic. Persisted per seat so
// datasets can select pure-RL play (fallback == 0).
func (p *HTTPPolicy) DecisionCounts() (remote, fallback uint64) {
	if p == nil {
		return 0, 0
	}
	return p.remoteSuccesses.Load(), p.fallbacks.Load()
}

// ObservedPolicyIDs returns the distinct checkpoint identities that served
// this policy's /act responses, in first-seen order. Empty when the server
// does not report checkpoint info.
func (p *HTTPPolicy) ObservedPolicyIDs() []string {
	if p == nil {
		return nil
	}
	p.observedMu.Lock()
	defer p.observedMu.Unlock()
	out := make([]string, len(p.observedPolicyIDs))
	copy(out, p.observedPolicyIDs)
	return out
}

func actionMaskJSON(mask []byte) []int {
	out := make([]int, len(mask))
	for index, value := range mask {
		out[index] = int(value)
	}
	return out
}

type policyError struct {
	reason string
	err    error
}

func (e policyError) Error() string {
	return e.err.Error()
}

func (e policyError) Unwrap() error {
	return e.err
}

func fallbackReason(err error) string {
	if err == nil {
		return FallbackReasonUnknown
	}
	if typed, ok := err.(policyError); ok {
		return typed.reason
	}
	return FallbackReasonUnknown
}

func (p *HTTPPolicy) recordFallback(reason string, err error, seat uint32) {
	p.fallbacks.Add(1)
	switch reason {
	case FallbackReasonConfig:
		p.fallbackConfig.Add(1)
	case FallbackReasonEncode:
		p.fallbackEncode.Add(1)
	case FallbackReasonRequest:
		p.fallbackRequest.Add(1)
	case FallbackReasonStatus:
		p.fallbackStatus.Add(1)
	case FallbackReasonBadJSON:
		p.fallbackBadJSON.Add(1)
	case FallbackReasonRemoteError:
		p.fallbackRemoteError.Add(1)
	case FallbackReasonIllegalAction:
		p.fallbackIllegalAction.Add(1)
	case FallbackReasonDecode:
		p.fallbackDecode.Add(1)
	default:
		p.fallbackUnknown.Add(1)
		reason = FallbackReasonUnknown
	}

	if p.logger != nil {
		p.logger("remote policy fallback endpoint=%q seat=%d reason=%s err=%v", p.endpoint, seat, reason, err)
	}
}

func (p *HTTPPolicy) logStatsIfDue(callCount uint64) {
	if p.logger == nil || p.statsLogEvery == 0 || callCount%p.statsLogEvery != 0 {
		return
	}
	stats := p.Stats()
	p.logger(
		"remote policy stats endpoint=%q calls=%d successes=%d fallbacks=%d no_fallback=%d reasons=%v",
		p.endpoint,
		stats.RemoteCalls,
		stats.RemoteSuccesses,
		stats.Fallbacks,
		stats.NoFallback,
		stats.FallbackReasons,
	)
}
