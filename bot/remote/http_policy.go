package remote

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"

	"github.com/plasma/fh-mahjong/bot"
	pb "github.com/plasma/fh-mahjong/proto"
	"github.com/plasma/fh-mahjong/rlenv"
)

const defaultTimeout = 750 * time.Millisecond

type HTTPPolicy struct {
	endpoint      string
	client        *http.Client
	fallback      bot.Policy
	decisionIndex uint64
}

type Option func(*HTTPPolicy)

func WithHTTPClient(client *http.Client) Option {
	return func(policy *HTTPPolicy) {
		if client != nil {
			policy.client = client
		}
	}
}

func WithFallback(fallback bot.Policy) Option {
	return func(policy *HTTPPolicy) {
		if fallback != nil {
			policy.fallback = fallback
		}
	}
}

func NewHTTPPolicy(endpoint string, opts ...Option) *HTTPPolicy {
	policy := &HTTPPolicy{
		endpoint: endpoint,
		client: &http.Client{
			Timeout: defaultTimeout,
		},
		fallback: bot.NewHeuristicPolicy(),
	}
	for _, opt := range opts {
		opt(policy)
	}
	return policy
}

func (p *HTTPPolicy) ChooseAction(state *pb.GameState, seat uint32) *pb.PlayerAction {
	action, err := p.chooseRemote(state, seat)
	if err == nil && action != nil {
		return action
	}
	if p.fallback == nil {
		return nil
	}
	return p.fallback.ChooseAction(state, seat)
}

func (p *HTTPPolicy) chooseRemote(state *pb.GameState, seat uint32) (*pb.PlayerAction, error) {
	if p == nil {
		return nil, fmt.Errorf("nil remote policy")
	}
	if state == nil {
		return nil, fmt.Errorf("nil game state")
	}
	if p.endpoint == "" {
		return nil, fmt.Errorf("remote policy endpoint is empty")
	}

	observation, err := rlenv.EncodeObservation(state, seat, p.decisionIndex)
	if err != nil {
		return nil, err
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
		return nil, err
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
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	payload, err := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
	if err != nil {
		return nil, err
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, fmt.Errorf("remote policy status %d: %s", resp.StatusCode, string(payload))
	}

	var response actResponse
	if err := json.Unmarshal(payload, &response); err != nil {
		return nil, err
	}
	if response.Error != "" {
		return nil, fmt.Errorf("remote policy error: %s", response.Error)
	}
	if response.ActionID < 0 || response.ActionID >= rlenv.ActionSpaceSize {
		return nil, fmt.Errorf("remote policy returned action id %d outside action space", response.ActionID)
	}

	return rlenv.DecodeActionID(state, seat, response.ActionID)
}

type actRequest struct {
	Seat       uint32         `json:"seat"`
	Planes     []float32      `json:"planes"`
	Scalars    []float32      `json:"scalars"`
	ActionMask []int          `json:"action_mask"`
	Metadata   map[string]any `json:"metadata,omitempty"`
}

type actResponse struct {
	ActionID int     `json:"action_id"`
	Value    float64 `json:"value,omitempty"`
	Error    string  `json:"error,omitempty"`
}

func actionMaskJSON(mask []byte) []int {
	out := make([]int, len(mask))
	for index, value := range mask {
		out[index] = int(value)
	}
	return out
}
