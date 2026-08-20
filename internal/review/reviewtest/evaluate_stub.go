// Package reviewtest provides the shared /evaluate policy-server stub used by
// both internal/api and internal/review tests.
//
// It is a normal (non-_test) package on purpose: a _test.go helper cannot be
// imported across package boundaries, and the same stub was previously written
// out 26 times across 9 test files.
package reviewtest

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
)

// Options configures the stub. The zero value is the common case: a healthy
// server that answers /healthz with {"ok":true} and /evaluate with a uniform
// distribution over the legal actions.
type Options struct {
	// Sha, when non-nil, is called per request to supply checkpoint_sha256 on
	// both /healthz and /evaluate. A func rather than a string so a test can
	// swap the value mid-run (checkpoint hot-swap cases).
	Sha func() string

	// HealthzUnavailable makes /healthz return 503 instead of {"ok":true}.
	HealthzUnavailable bool

	// Value is the per-observation value emitted by /evaluate. Defaults to 0.25.
	Value *float64

	// ValuesCalibrated, when non-nil, sets the values_calibrated flag.
	ValuesCalibrated *bool

	// CheckpointPath and CheckpointStep default to "stub.pt" and 42 — several
	// tests assert on exactly those.
	CheckpointPath string
	CheckpointStep int

	// Block, when non-nil, holds every /evaluate request until it is closed.
	// Used by the concurrency/singleflight cases.
	Block <-chan struct{}

	// OnEvaluate, when non-nil, is called once per /evaluate request. It exists
	// so callers holding a plain counter can keep their existing shape; prefer
	// Ctl.EvalCount, which is race-free.
	OnEvaluate func()

	// OnBatch, when non-nil, receives each decoded observations batch, for
	// tests that assert on what the client actually sent (batch sizes, event
	// history payloads, seat ordering).
	OnBatch func(observations []map[string]any)
}

// Ctl exposes what a test can observe about the stub after the fact.
type Ctl struct {
	evalCount    atomic.Int64
	healthzCount atomic.Int64
	inFlight     atomic.Int64
	maxInFlight  atomic.Int64
}

// EvalCount is the number of /evaluate requests served.
func (c *Ctl) EvalCount() int { return int(c.evalCount.Load()) }

// HealthzCount is the number of /healthz requests served.
func (c *Ctl) HealthzCount() int { return int(c.healthzCount.Load()) }

// MaxInFlight is the highest number of /evaluate requests handled concurrently,
// which is how the singleflight cases prove de-duplication.
func (c *Ctl) MaxInFlight() int { return int(c.maxInFlight.Load()) }

// NewEvaluateStub starts a stub policy server. It is closed via t.Cleanup.
func NewEvaluateStub(t testing.TB, o Options) (*httptest.Server, *Ctl) {
	t.Helper()
	ctl := &Ctl{}

	checkpointPath := o.CheckpointPath
	if checkpointPath == "" {
		checkpointPath = "stub.pt"
	}
	checkpointStep := o.CheckpointStep
	if checkpointStep == 0 {
		checkpointStep = 42
	}
	value := 0.25
	if o.Value != nil {
		value = *o.Value
	}

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/healthz":
			ctl.healthzCount.Add(1)
			if o.HealthzUnavailable {
				w.WriteHeader(http.StatusServiceUnavailable)
				return
			}
			w.Header().Set("Content-Type", "application/json")
			body := map[string]any{"ok": true}
			if o.Sha != nil {
				body["checkpoint_sha256"] = o.Sha()
			}
			_ = json.NewEncoder(w).Encode(body)
			return
		case "/evaluate":
		default:
			// Only /evaluate is counted: it is the call that costs the policy
			// server RL-serving capacity.
			http.NotFound(w, r)
			return
		}

		ctl.evalCount.Add(1)
		if o.OnEvaluate != nil {
			o.OnEvaluate()
		}
		cur := ctl.inFlight.Add(1)
		for {
			max := ctl.maxInFlight.Load()
			if cur <= max || ctl.maxInFlight.CompareAndSwap(max, cur) {
				break
			}
		}
		defer ctl.inFlight.Add(-1)

		if o.Block != nil {
			<-o.Block
		}

		var req struct {
			Observations []map[string]any `json:"observations"`
		}
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			t.Errorf("reviewtest: decode /evaluate request: %v", err)
			return
		}

		if o.OnBatch != nil {
			o.OnBatch(req.Observations)
		}

		results := make([]map[string]any, len(req.Observations))
		for i, o := range req.Observations {
			results[i] = map[string]any{"probs": UniformOverLegal(o["action_mask"]), "value": value}
		}
		body := map[string]any{
			"results":         results,
			"checkpoint_path": checkpointPath,
			"checkpoint_step": checkpointStep,
		}
		if o.Sha != nil {
			body["checkpoint_sha256"] = o.Sha()
		}
		if o.ValuesCalibrated != nil {
			body["values_calibrated"] = *o.ValuesCalibrated
		}
		_ = json.NewEncoder(w).Encode(body)
	}))
	t.Cleanup(server.Close)
	return server, ctl
}

// UniformOverLegal spreads probability evenly across the legal entries of a
// decoded action_mask, matching what a policy server returns for an untrained
// checkpoint. Illegal entries get 0.
func UniformOverLegal(rawMask any) []float64 {
	mask, _ := rawMask.([]any)
	probs := make([]float64, len(mask))
	legal := 0
	for _, m := range mask {
		if v, ok := m.(float64); ok && v == 1 {
			legal++
		}
	}
	if legal == 0 {
		return probs
	}
	for j, m := range mask {
		if v, ok := m.(float64); ok && v == 1 {
			probs[j] = 1.0 / float64(legal)
		}
	}
	return probs
}
