package review

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/plasma/fh-mahjong/internal/engine"
	pb "github.com/plasma/fh-mahjong/proto"
)

// TestHTTPClientTolerateNullValues pins adversarial round 15, Finding 4's Go
// side: a privileged-critic checkpoint's served /evaluate response carries
// JSON `null` for every result's "value" field (out-of-distribution value
// head — see PolicyResult's doc) plus a top-level "values_calibrated":
// false. The client must decode this canned response WITHOUT error, surface
// nil Values (never a silently-coerced 0.0), and propagate
// ValuesCalibrated=false via CheckpointInfo.
func TestHTTPClientTolerateNullValues(t *testing.T) {
	stub := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{
			"results": [
				{"probs": [1, 0], "value": null},
				{"probs": [0, 1], "value": null}
			],
			"checkpoint_path": "privileged.pt",
			"checkpoint_step": 7,
			"values_calibrated": false
		}`))
	}))
	defer stub.Close()

	obs := []*pb.SeatObservation{
		{Seat: 0, Planes: []float32{0}, Scalars: []float32{0}, ActionMask: []byte{1, 0}},
		{Seat: 1, Planes: []float32{0}, Scalars: []float32{0}, ActionMask: []byte{0, 1}},
	}

	client := NewHTTPPolicyClient(stub.URL, 0)
	results, info, err := client.Evaluate(obs)
	if err != nil {
		t.Fatalf("Evaluate: %v", err)
	}
	if len(results) != 2 {
		t.Fatalf("expected 2 results, got %d", len(results))
	}
	for i, res := range results {
		if res.Value != nil {
			t.Fatalf("result %d: expected nil Value, got %v", i, *res.Value)
		}
	}
	if info.ValuesCalibrated {
		t.Fatal("expected ValuesCalibrated=false")
	}
	if info.Path != "privileged.pt" || info.Step != 7 {
		t.Fatalf("bad checkpoint info: %+v", info)
	}
}

// TestHTTPClientCalibratedValuesUnaffected is the positive counterpart: a
// server that DOES send real numeric values and values_calibrated=true
// (window-0/old-champion-style checkpoint) round-trips unchanged.
func TestHTTPClientCalibratedValuesUnaffected(t *testing.T) {
	stub := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{
			"results": [{"probs": [1, 0], "value": 0.5}],
			"checkpoint_path": "champion.pt",
			"checkpoint_step": 42,
			"values_calibrated": true
		}`))
	}))
	defer stub.Close()

	obs := []*pb.SeatObservation{
		{Seat: 0, Planes: []float32{0}, Scalars: []float32{0}, ActionMask: []byte{1, 0}},
	}

	client := NewHTTPPolicyClient(stub.URL, 0)
	results, info, err := client.Evaluate(obs)
	if err != nil {
		t.Fatalf("Evaluate: %v", err)
	}
	if len(results) != 1 || results[0].Value == nil {
		t.Fatalf("expected 1 calibrated result, got %+v", results)
	}
	if *results[0].Value != 0.5 {
		t.Fatalf("expected value 0.5, got %f", *results[0].Value)
	}
	if !info.ValuesCalibrated {
		t.Fatal("expected ValuesCalibrated=true")
	}
}

// TestBuildReportPrivilegedCriticOmitsValuesButKeepsRanking exercises
// BuildReport end to end against a stub that mirrors a real privileged-
// critic serve_policy.py response: nil values, values_calibrated=false. The
// resulting Report must propagate ValuesCalibrated=false, every
// ReportDecision.Value must be nil (and therefore omitted from JSON, per its
// omitempty tag), and the probability-based ranking (Actions/ChosenProb)
// must be completely unaffected.
func TestBuildReportPrivilegedCriticOmitsValuesButKeepsRanking(t *testing.T) {
	paipu := generateHeuristicPaipu(t, 11, engine.MatchOptions{})

	stub := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var req struct {
			Observations []map[string]any `json:"observations"`
		}
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			t.Errorf("decode: %v", err)
			return
		}
		results := make([]map[string]any, len(req.Observations))
		for i, o := range req.Observations {
			mask := o["action_mask"].([]any)
			probs := make([]float64, len(mask))
			legal := 0
			for _, m := range mask {
				if m.(float64) == 1 {
					legal++
				}
			}
			for j, m := range mask {
				if m.(float64) == 1 {
					probs[j] = 1.0 / float64(legal)
				}
			}
			results[i] = map[string]any{"probs": probs, "value": nil}
		}
		_ = json.NewEncoder(w).Encode(map[string]any{
			"results": results, "checkpoint_path": "privileged.pt", "checkpoint_step": 9,
			"values_calibrated": false,
		})
	}))
	defer stub.Close()

	report, err := BuildReport(paipu, NewHTTPPolicyClient(stub.URL, 0), 0)
	if err != nil {
		t.Fatalf("BuildReport: %v", err)
	}
	if report.ValuesCalibrated {
		t.Fatal("expected Report.ValuesCalibrated=false")
	}
	if len(report.Decisions) == 0 {
		t.Fatal("expected at least one decision")
	}
	for i, d := range report.Decisions {
		if d.Value != nil {
			t.Fatalf("decision %d: expected nil Value, got %v", i, *d.Value)
		}
		if len(d.Actions) == 0 {
			t.Fatalf("decision %d: action ranking must still be present", i)
		}
	}
}
