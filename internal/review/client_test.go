package review

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"

	"github.com/plasma/fh-mahjong/internal/engine"
	pb "github.com/plasma/fh-mahjong/proto"
)

// shaObservations builds n trivial single-legal-action observations, enough
// to force Evaluate to split into multiple /evaluate chunks (see
// evaluateChunkSize) so cross-chunk checkpoint-identity checks can be
// exercised.
func shaObservations(n int) []*pb.SeatObservation {
	obs := make([]*pb.SeatObservation, n)
	for i := range obs {
		obs[i] = &pb.SeatObservation{Seat: 0, Planes: []float32{0}, Scalars: []float32{0}, ActionMask: []byte{1, 0}}
	}
	return obs
}

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
	results, info, err := client.Evaluate(context.Background(), obs)
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
	results, info, err := client.Evaluate(context.Background(), obs)
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

// TestHTTPClientEvaluateShaMismatchAcrossChunksErrors pins round 17, Finding
// 2: a same-path hot reload mid-review must not silently mix two different
// checkpoints' bytes into one report. Each chunk here reports the SAME path
// but a DIFFERENT checkpoint_sha256 (as a same-path hot reload would produce
// on the server side between two /evaluate calls) — Evaluate must error
// rather than merge them.
func TestHTTPClientEvaluateShaMismatchAcrossChunksErrors(t *testing.T) {
	var requestCount int64
	stub := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var req struct {
			Observations []map[string]any `json:"observations"`
		}
		_ = json.NewDecoder(r.Body).Decode(&req)
		sha := "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
		if atomic.AddInt64(&requestCount, 1) > 1 {
			sha = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
		}
		results := make([]map[string]any, len(req.Observations))
		for i := range results {
			results[i] = map[string]any{"probs": []float64{1, 0}, "value": 0.1}
		}
		_ = json.NewEncoder(w).Encode(map[string]any{
			"results": results, "checkpoint_path": "hotswap.pt", "checkpoint_step": 1,
			"checkpoint_sha256": sha, "values_calibrated": true,
		})
	}))
	defer stub.Close()

	client := NewHTTPPolicyClient(stub.URL, 0)
	_, _, err := client.Evaluate(context.Background(), shaObservations(evaluateChunkSize + 1))
	if err == nil {
		t.Fatal("expected error: chunks reported different checkpoint_sha256 for the same path")
	}
}

// The all-equal-sha counterpart: every chunk reports the same
// checkpoint_sha256, so Evaluate succeeds and CheckpointInfo carries it.
func TestHTTPClientEvaluateShaAllEqualCarriesSha(t *testing.T) {
	const sha = "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
	stub := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var req struct {
			Observations []map[string]any `json:"observations"`
		}
		_ = json.NewDecoder(r.Body).Decode(&req)
		results := make([]map[string]any, len(req.Observations))
		for i := range results {
			results[i] = map[string]any{"probs": []float64{1, 0}, "value": 0.1}
		}
		_ = json.NewEncoder(w).Encode(map[string]any{
			"results": results, "checkpoint_path": "steady.pt", "checkpoint_step": 1,
			"checkpoint_sha256": sha, "values_calibrated": true,
		})
	}))
	defer stub.Close()

	client := NewHTTPPolicyClient(stub.URL, 0)
	results, info, err := client.Evaluate(context.Background(), shaObservations(evaluateChunkSize + 1))
	if err != nil {
		t.Fatalf("Evaluate: %v", err)
	}
	if len(results) != evaluateChunkSize+1 {
		t.Fatalf("expected %d results, got %d", evaluateChunkSize+1, len(results))
	}
	if info.Sha256 != sha {
		t.Fatalf("info.Sha256 = %q, want %q", info.Sha256, sha)
	}
}

// A legacy server that never emits checkpoint_sha256 at all must keep
// working exactly as before: absent sha on every chunk is "unknown", not an
// error.
func TestHTTPClientEvaluateAbsentShaLegacyStillWorks(t *testing.T) {
	stub := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var req struct {
			Observations []map[string]any `json:"observations"`
		}
		_ = json.NewDecoder(r.Body).Decode(&req)
		results := make([]map[string]any, len(req.Observations))
		for i := range results {
			results[i] = map[string]any{"probs": []float64{1, 0}, "value": 0.1}
		}
		_ = json.NewEncoder(w).Encode(map[string]any{
			"results": results, "checkpoint_path": "legacy.pt", "checkpoint_step": 1,
			"values_calibrated": true,
		})
	}))
	defer stub.Close()

	client := NewHTTPPolicyClient(stub.URL, 0)
	results, info, err := client.Evaluate(context.Background(), shaObservations(evaluateChunkSize + 1))
	if err != nil {
		t.Fatalf("Evaluate: %v", err)
	}
	if len(results) != evaluateChunkSize+1 {
		t.Fatalf("expected %d results, got %d", evaluateChunkSize+1, len(results))
	}
	if info.Sha256 != "" {
		t.Fatalf("info.Sha256 = %q, want empty (unknown) for a legacy server", info.Sha256)
	}
}

// Mixing an absent-sha chunk with a present-sha chunk must error rather than
// silently treat the absent one as "matches anything".
func TestHTTPClientEvaluateMixedAbsentPresentShaErrors(t *testing.T) {
	var requestCount int64
	stub := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var req struct {
			Observations []map[string]any `json:"observations"`
		}
		_ = json.NewDecoder(r.Body).Decode(&req)
		results := make([]map[string]any, len(req.Observations))
		for i := range results {
			results[i] = map[string]any{"probs": []float64{1, 0}, "value": 0.1}
		}
		resp := map[string]any{
			"results": results, "checkpoint_path": "mixed.pt", "checkpoint_step": 1,
			"values_calibrated": true,
		}
		if atomic.AddInt64(&requestCount, 1) > 1 {
			resp["checkpoint_sha256"] = "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"
		}
		_ = json.NewEncoder(w).Encode(resp)
	}))
	defer stub.Close()

	client := NewHTTPPolicyClient(stub.URL, 0)
	_, _, err := client.Evaluate(context.Background(), shaObservations(evaluateChunkSize + 1))
	if err == nil {
		t.Fatal("expected error: one chunk had no checkpoint_sha256, another chunk did")
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

	report, err := BuildReport(context.Background(), paipu, NewHTTPPolicyClient(stub.URL, 0), 0)
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

// TestHTTPClientAttachesBearerTokenWhenConfigured pins adversarial round
// 19's Go side: NewHTTPPolicyClientWithToken must send the configured token
// as an `Authorization: Bearer <token>` header on every /evaluate request —
// serve_policy.py now refuses unauthenticated /evaluate calls with HTTP 403.
func TestHTTPClientAttachesBearerTokenWhenConfigured(t *testing.T) {
	var gotAuth string
	stub := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotAuth = r.Header.Get("Authorization")
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"results": [{"probs": [1, 0], "value": 0.5}], "checkpoint_path": "p", "checkpoint_step": 1, "values_calibrated": true}`))
	}))
	defer stub.Close()

	obs := []*pb.SeatObservation{{Seat: 0, Planes: []float32{0}, Scalars: []float32{0}, ActionMask: []byte{1, 0}}}
	client := NewHTTPPolicyClientWithToken(stub.URL, 0, "s3cr3t-token")
	if _, _, err := client.Evaluate(context.Background(), obs); err != nil {
		t.Fatalf("Evaluate: %v", err)
	}
	if want := "Bearer s3cr3t-token"; gotAuth != want {
		t.Fatalf("Authorization header = %q, want %q", gotAuth, want)
	}
}

// TestHTTPClientOmitsAuthorizationHeaderWhenNoTokenConfigured pins the other
// half of adversarial round 19's Go side: NewHTTPPolicyClient (no token)
// must NOT send an Authorization header at all — never a header carrying an
// empty bearer value — keeping requests to an unauthenticated (legacy/local)
// policy stub byte-identical to before this change.
func TestHTTPClientOmitsAuthorizationHeaderWhenNoTokenConfigured(t *testing.T) {
	sawAuthHeader := false
	stub := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if _, ok := r.Header["Authorization"]; ok {
			sawAuthHeader = true
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"results": [{"probs": [1, 0], "value": 0.5}], "checkpoint_path": "p", "checkpoint_step": 1, "values_calibrated": true}`))
	}))
	defer stub.Close()

	obs := []*pb.SeatObservation{{Seat: 0, Planes: []float32{0}, Scalars: []float32{0}, ActionMask: []byte{1, 0}}}
	client := NewHTTPPolicyClient(stub.URL, 0)
	if _, _, err := client.Evaluate(context.Background(), obs); err != nil {
		t.Fatalf("Evaluate: %v", err)
	}
	if sawAuthHeader {
		t.Fatal("expected no Authorization header when no token is configured")
	}
}
