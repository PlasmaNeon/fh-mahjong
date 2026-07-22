package review

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/plasma/fh-mahjong/internal/engine"
	pb "github.com/plasma/fh-mahjong/proto"
)

func TestBuildReportAgainstStubServer(t *testing.T) {
	paipu := generateHeuristicPaipu(t, 7, engine.MatchOptions{})

	var gotBatches [][]map[string]any
	stub := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/evaluate" {
			http.NotFound(w, r)
			return
		}
		var req struct {
			Observations []map[string]any `json:"observations"`
		}
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			t.Errorf("decode: %v", err)
		}
		gotBatches = append(gotBatches, req.Observations)
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
					probs[j] = 1.0 / float64(legal) // uniform over legal
				}
			}
			results[i] = map[string]any{"probs": probs, "value": 0.25}
		}
		json.NewEncoder(w).Encode(map[string]any{
			"results": results, "checkpoint_path": "stub.pt", "checkpoint_step": 42,
			"checkpoint_sha256": "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
		})
	}))
	defer stub.Close()

	report, err := BuildReport(context.Background(), paipu, NewHTTPPolicyClient(stub.URL, 0), 0)
	if err != nil {
		t.Fatalf("BuildReport: %v", err)
	}
	if report.SchemaVersion != 1 || report.CheckpointPath != "stub.pt" || report.CheckpointStep != 42 {
		t.Fatalf("bad header: %+v", report)
	}
	// Round 17, Finding 2: the report must carry the checkpoint sha256 the
	// server evaluated it with.
	if want := "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"; report.CheckpointSha256 != want {
		t.Fatalf("report.CheckpointSha256 = %q, want %q", report.CheckpointSha256, want)
	}
	if len(report.Seats) != 4 {
		t.Fatalf("expected 4 seat summaries, got %d", len(report.Seats))
	}
	for i, d := range report.Decisions {
		if len(d.Actions) == 0 {
			t.Fatalf("decision %d: no legal actions", i)
		}
		var sum float32
		for j, a := range d.Actions {
			sum += a.Prob
			if j > 0 && d.Actions[j-1].Prob < a.Prob {
				t.Fatalf("decision %d: actions not sorted desc", i)
			}
		}
		if sum < 0.99 || sum > 1.01 {
			t.Fatalf("decision %d: legal probs sum %f", i, sum)
		}
		// Uniform stub → chosen prob == 1/len(actions).
		want := 1.0 / float32(len(d.Actions))
		if diff := d.ChosenProb - want; diff < -1e-4 || diff > 1e-4 {
			t.Fatalf("decision %d: chosen prob %f want %f", i, d.ChosenProb, want)
		}
	}
	for _, s := range report.Seats {
		if s.Decisions > 5 && len(s.TopGaps) != 5 {
			t.Fatalf("seat %d: expected 5 top gaps, got %d", s.Seat, len(s.TopGaps))
		}
	}
	if len(gotBatches) == 0 {
		t.Fatal("expected at least one batch to reach the stub server")
	}
}

func TestBuildReportServerErrorReturnsNoPartialReport(t *testing.T) {
	paipu := generateHeuristicPaipu(t, 7, engine.MatchOptions{})
	stub := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, `{"error":"boom"}`, http.StatusInternalServerError)
	}))
	defer stub.Close()
	if _, err := BuildReport(context.Background(), paipu, NewHTTPPolicyClient(stub.URL, 0), 0); err == nil {
		t.Fatal("expected error")
	}
}

// TestBuildReportEventWindowZeroPayloadUnchanged is the client-side
// regression bar for Task 6: with eventWindow==0, no observation in the
// batched /evaluate request carries any of the compact event-history keys
// (they must be entirely absent from the JSON, not merely zero-valued).
func TestBuildReportEventWindowZeroPayloadUnchanged(t *testing.T) {
	paipu := generateHeuristicPaipu(t, 7, engine.MatchOptions{})

	var gotBatches [][]map[string]any
	stub := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var req struct {
			Observations []map[string]any `json:"observations"`
		}
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			t.Errorf("decode: %v", err)
		}
		gotBatches = append(gotBatches, req.Observations)
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
			results[i] = map[string]any{"probs": probs, "value": 0.0}
		}
		json.NewEncoder(w).Encode(map[string]any{
			"results": results, "checkpoint_path": "stub.pt", "checkpoint_step": 1,
		})
	}))
	defer stub.Close()

	if _, err := BuildReport(context.Background(), paipu, NewHTTPPolicyClient(stub.URL, 0), 0); err != nil {
		t.Fatalf("BuildReport: %v", err)
	}
	if len(gotBatches) == 0 {
		t.Fatal("expected at least one batch")
	}
	for _, batch := range gotBatches {
		for i, o := range batch {
			for _, key := range []string{"event_history", "event_count", "event_window", "contract_version"} {
				if _, present := o[key]; present {
					t.Fatalf("observation %d: unexpected key %q in window-0 payload: %+v", i, key, o)
				}
			}
		}
	}
}

// TestBuildReportEventWindowEightEnrichesPayload is the positive-window
// counterpart: every batched observation must carry event_count, event_window,
// and contract_version, with event_history present iff event_count > 0 and,
// when present, len(event_history) == event_count <= window.
func TestBuildReportEventWindowEightEnrichesPayload(t *testing.T) {
	const window = 8
	paipu := generateHeuristicPaipu(t, 7, engine.MatchOptions{})

	var gotBatches [][]map[string]any
	stub := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var req struct {
			Observations []map[string]any `json:"observations"`
		}
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			t.Errorf("decode: %v", err)
		}
		gotBatches = append(gotBatches, req.Observations)
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
			results[i] = map[string]any{"probs": probs, "value": 0.0}
		}
		json.NewEncoder(w).Encode(map[string]any{
			"results": results, "checkpoint_path": "stub.pt", "checkpoint_step": 1,
		})
	}))
	defer stub.Close()

	if _, err := BuildReport(context.Background(), paipu, NewHTTPPolicyClient(stub.URL, window), window); err != nil {
		t.Fatalf("BuildReport: %v", err)
	}
	if len(gotBatches) == 0 {
		t.Fatal("expected at least one batch")
	}
	sawNonEmptyHistory := false
	for _, batch := range gotBatches {
		for i, o := range batch {
			ver, ok := o["contract_version"].(float64)
			if !ok || int(ver) != 1 {
				t.Fatalf("observation %d: contract_version = %v, want 1", i, o["contract_version"])
			}
			win, ok := o["event_window"].(float64)
			if !ok || uint32(win) != window {
				t.Fatalf("observation %d: event_window = %v, want %d", i, o["event_window"], window)
			}
			countRaw, ok := o["event_count"].(float64)
			if !ok {
				t.Fatalf("observation %d: missing event_count", i)
			}
			count := int(countRaw)
			if count > window {
				t.Fatalf("observation %d: event_count %d exceeds window %d", i, count, window)
			}
			hist, present := o["event_history"]
			if count == 0 {
				if present {
					t.Fatalf("observation %d: event_history present with event_count 0: %v", i, hist)
				}
				continue
			}
			histSlice, ok := hist.([]any)
			if !ok {
				t.Fatalf("observation %d: event_history not a list: %v", i, hist)
			}
			if len(histSlice) != count {
				t.Fatalf("observation %d: len(event_history)=%d != event_count=%d", i, len(histSlice), count)
			}
			sawNonEmptyHistory = true
		}
	}
	if !sawNonEmptyHistory {
		t.Fatal("expected at least one observation with non-empty event history")
	}
}

// TestHTTPClientChunksBatches calls Evaluate directly with 600 synthetic
// observations (tiny slices, distinct seats are fine — the client doesn't
// interpret payload contents). The stub echoes back a result whose Value
// equals the observation's index within the whole request (via a
// per-request counter), so we can verify chunk boundaries and that order is
// preserved end to end. It also counts requests and expects
// ceil(600/256)=3.
func TestHTTPClientChunksBatches(t *testing.T) {
	const total = 600
	const chunkSize = 256

	var requestCount int
	var seenCount int
	stub := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		requestCount++
		var req struct {
			Observations []map[string]any `json:"observations"`
		}
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			t.Errorf("decode: %v", err)
			return
		}
		results := make([]map[string]any, len(req.Observations))
		for i, o := range req.Observations {
			seat := o["seat"].(float64)
			// Echo back the global index (tracked via seenCount) as Value so
			// the caller can verify order was preserved across chunks.
			results[i] = map[string]any{
				"probs": []float64{1},
				"value": float64(seenCount),
			}
			_ = seat
			seenCount++
		}
		json.NewEncoder(w).Encode(map[string]any{
			"results": results, "checkpoint_path": "stub.pt", "checkpoint_step": 1,
		})
	}))
	defer stub.Close()

	obs := make([]*pb.SeatObservation, total)
	for i := range obs {
		obs[i] = &pb.SeatObservation{
			Seat:       uint32(i % 4),
			Planes:     []float32{float32(i)},
			Scalars:    []float32{float32(i)},
			ActionMask: []byte{1},
		}
	}

	client := NewHTTPPolicyClient(stub.URL, 0)
	results, info, err := client.Evaluate(context.Background(), obs)
	if err != nil {
		t.Fatalf("Evaluate: %v", err)
	}

	wantRequests := (total + chunkSize - 1) / chunkSize
	if requestCount != wantRequests {
		t.Fatalf("expected %d requests, got %d", wantRequests, requestCount)
	}
	if len(results) != total {
		t.Fatalf("expected %d results, got %d", total, len(results))
	}
	for i, res := range results {
		if res.Value == nil {
			t.Fatalf("result %d: expected non-nil value", i)
		}
		if int(*res.Value) != i {
			t.Fatalf("result %d: expected order-preserving value %d, got %f", i, i, *res.Value)
		}
	}
	if info.Path != "stub.pt" || info.Step != 1 {
		t.Fatalf("bad checkpoint info: %+v", info)
	}
}
