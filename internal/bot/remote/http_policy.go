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

var _ bot.ContextPolicy = (*HTTPPolicy)(nil)

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
	decisionIndex atomic.Uint64
	logger        Logger
	statsLogEvery uint64
	eventWindow   uint32

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

// WithEventWindow enables the event-history wire contract: ChooseActionCtx
// encodes via rl.EncodeObservationWithEvents with this tail window and the
// three event scalar fields are populated accordingly. The default, 0, is
// event-free legacy behavior (event_window:0, event_count:0, no history).
func WithEventWindow(window uint32) Option {
	return func(policy *HTTPPolicy) {
		policy.eventWindow = window
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

// ChooseActionCtx is the ContextPolicy entry point: it speaks the compact
// event-history wire form, encoding via rl.EncodeObservationWithEvents with
// the DECISION INDEX FROM THE CONTEXT (not the internal p.decisionIndex
// counter, which is only used by the legacy ChooseAction path). Fallback
// semantics (heuristic + counters) are unchanged.
func (p *HTTPPolicy) ChooseActionCtx(decisionCtx *bot.DecisionContext) *pb.PlayerAction {
	if p == nil {
		return nil
	}
	callCount := p.remoteCalls.Add(1)
	var state *pb.GameState
	var seat uint32
	if decisionCtx != nil {
		state = decisionCtx.State
		seat = decisionCtx.Seat
	}
	action, err := p.chooseRemoteCtx(decisionCtx)
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

	observation, err := rl.EncodeObservation(state, seat, p.decisionIndex.Load())
	if err != nil {
		return nil, policyError{reason: FallbackReasonEncode, err: err}
	}
	p.decisionIndex.Add(1)

	requestPayload := actRequest{
		Seat:            observation.Seat,
		Planes:          observation.Planes,
		Scalars:         observation.Scalars,
		ActionMask:      actionMaskJSON(observation.ActionMask),
		EventCount:      0,
		EventWindow:     0,
		ContractVersion: rl.EventContractV1,
		Metadata: map[string]any{
			"decision_index": observation.DecisionIndex,
			"phase":          observation.Phase.String(),
			"active_player":  observation.ActivePlayer,
		},
	}
	return p.doAct(state, seat, requestPayload)
}

// chooseRemoteCtx mirrors chooseRemote's request/response/validation flow but
// encodes the observation with the context's raw event log and the policy's
// configured event window, and takes the decision index from the context
// rather than the internal p.decisionIndex counter.
func (p *HTTPPolicy) chooseRemoteCtx(decisionCtx *bot.DecisionContext) (*pb.PlayerAction, error) {
	if p == nil {
		return nil, policyError{reason: FallbackReasonConfig, err: fmt.Errorf("nil remote policy")}
	}
	if decisionCtx == nil || decisionCtx.State == nil {
		return nil, policyError{reason: FallbackReasonConfig, err: fmt.Errorf("nil game state")}
	}
	if p.endpoint == "" {
		return nil, policyError{reason: FallbackReasonConfig, err: fmt.Errorf("remote policy endpoint is empty")}
	}

	state := decisionCtx.State
	seat := decisionCtx.Seat

	observation, err := rl.EncodeObservationWithEvents(state, seat, decisionCtx.DecisionIndex, decisionCtx.Events, p.eventWindow)
	if err != nil {
		return nil, policyError{reason: FallbackReasonEncode, err: err}
	}

	requestPayload := actRequest{
		Seat:            observation.Seat,
		Planes:          observation.Planes,
		Scalars:         observation.Scalars,
		ActionMask:      actionMaskJSON(observation.ActionMask),
		EventHistory:    observation.EventHistory,
		EventCount:      len(observation.EventHistory),
		EventWindow:     p.eventWindow,
		ContractVersion: rl.EventContractV1,
		Metadata: map[string]any{
			"decision_index": observation.DecisionIndex,
			"phase":          observation.Phase.String(),
			"active_player":  observation.ActivePlayer,
		},
	}
	return p.doAct(state, seat, requestPayload)
}

// doAct is the shared HTTP/request logic for both the legacy and
// context-aware serving paths: marshal the request, POST it, validate and
// decode the response, and attribute the serving checkpoint on success.
func (p *HTTPPolicy) doAct(state *pb.GameState, seat uint32, requestPayload actRequest) (*pb.PlayerAction, error) {
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

// eventContractHealthz mirrors the event-contract handshake fields of
// serve_policy.py's GET /healthz response. Extra fields are ignored.
// EventWindow/ContractVersion are pointers so an ABSENT field (a legacy
// server that predates the event contract, decodes as nil) can be told apart
// from an EXPLICITLY PUBLISHED value — a server that publishes
// event_window:0 is making a claim that must still match what this policy
// expects, unlike a legacy server that says nothing at all.
type eventContractHealthz struct {
	EventWindow     *uint32 `json:"event_window"`
	ContractVersion *uint32 `json:"contract_version"`
}

// ValidateServer probes the policy endpoint's GET /healthz route and checks
// that the serving contract matches this policy's configuration. A server
// that PUBLISHES the event contract (event_window present in its /healthz
// body) is making an explicit claim that must match p.eventWindow AND
// contract_version == rl.EventContractV1 regardless of whether p is itself
// event-enabled — this is what catches a window-0 policy left pointed at a
// server that is actually serving an event checkpoint (e.g.
// RL_AGENT_EVENT_WINDOW=0 against a policy service serving iter_075 at
// window 128): every /act call would otherwise 400 and silently fall back to
// the heuristic. A legacy healthz that omits the field entirely (nil) keeps
// today's behavior: passes for a window-0 policy, fails for an event-enabled
// one (cannot verify a match, fail closed).
func (p *HTTPPolicy) ValidateServer(ctx context.Context) error {
	if p == nil {
		return fmt.Errorf("nil remote policy")
	}
	healthURL := deriveHealthURL(p.endpoint)
	if healthURL == "" {
		return fmt.Errorf("remote policy endpoint %q has no derivable /healthz URL", p.endpoint)
	}

	client := p.client
	if client == nil {
		client = &http.Client{Timeout: defaultTimeout}
	}
	timeout := client.Timeout
	if timeout <= 0 {
		timeout = defaultTimeout
	}
	reqCtx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()
	req, err := http.NewRequestWithContext(reqCtx, http.MethodGet, healthURL, nil)
	if err != nil {
		return err
	}
	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return fmt.Errorf("healthz status %d", resp.StatusCode)
	}

	payload, err := io.ReadAll(io.LimitReader(resp.Body, 1<<16))
	if err != nil {
		return err
	}
	var body eventContractHealthz
	if err := json.Unmarshal(payload, &body); err != nil {
		// A non-JSON/undecodable body means the event contract (if this
		// policy expects one) cannot be verified — fail closed rather than
		// assume a match. A window-0 policy keeps the legacy
		// reachability-only behavior (mirrors HealthChecker.probe in
		// health.go: window-0 + undecodable body => acceptable legacy
		// reachability, window>0 stays strict in both).
		if p.eventWindow == 0 {
			return nil
		}
		return fmt.Errorf("healthz body is not valid JSON: %w", err)
	}

	if body.EventWindow == nil {
		// Legacy server: no contract published at all. Fine for a window-0
		// policy (nothing to check); fails closed for an event-enabled one,
		// since a match can't be verified.
		if p.eventWindow == 0 {
			return nil
		}
		return fmt.Errorf("healthz reports no event_window (legacy server), want event_window %d", p.eventWindow)
	}

	var contractVersion uint32
	if body.ContractVersion != nil {
		contractVersion = *body.ContractVersion
	}
	if contractVersion != rl.EventContractV1 {
		return fmt.Errorf("healthz contract_version = %d, want %d", contractVersion, rl.EventContractV1)
	}
	if *body.EventWindow != p.eventWindow {
		return fmt.Errorf("healthz event_window = %d, want %d", *body.EventWindow, p.eventWindow)
	}
	return nil
}

type actRequest struct {
	Seat       uint32         `json:"seat"`
	Planes     []float32      `json:"planes"`
	Scalars    []float32      `json:"scalars"`
	ActionMask []int          `json:"action_mask"`
	Metadata   map[string]any `json:"metadata,omitempty"`

	// Event-history fields. EventHistory carries the compact, already
	// tail-windowed wire form (rl.EncodeObservationWithEvents' output — no
	// separate padding/truncation happens here). The three scalars are
	// ALWAYS sent, even by the legacy (window==0) path, so the server can
	// distinguish "legacy Go caller" (event_window:0, contract_version:1,
	// no history) from "event caller with an empty history".
	EventHistory    []uint32 `json:"event_history,omitempty"`
	EventCount      int      `json:"event_count"`
	EventWindow     uint32   `json:"event_window"`
	ContractVersion uint32   `json:"contract_version"`
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
