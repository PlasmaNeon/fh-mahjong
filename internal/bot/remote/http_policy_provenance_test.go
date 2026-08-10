package remote

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/plasma/fh-mahjong/internal/bot"
)

// Case 1: remote success reports the serving checkpoint's identity (base
// name only, per checkpointIdentity's convention) plus step and sha.
func TestHTTPPolicyChooseActionCtxProvRemoteSuccess(t *testing.T) {
	state := testDiscardState()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(actResponse{
			ActionID:         5,
			CheckpointPath:   "/models/ck.pt",
			CheckpointStep:   75,
			CheckpointSha256: "ff00",
		})
	}))
	defer server.Close()

	policy := NewHTTPPolicy(server.URL+"/act", WithLogger(nil))
	action, prov := policy.ChooseActionCtxProv(&bot.DecisionContext{State: state, Seat: 0, DecisionIndex: 1})

	if action == nil {
		t.Fatal("expected remote action")
	}
	if prov.Source != "remote" {
		t.Fatalf("Source = %q, want %q", prov.Source, "remote")
	}
	if prov.CheckpointName != "ck.pt" {
		t.Fatalf("CheckpointName = %q, want %q", prov.CheckpointName, "ck.pt")
	}
	if prov.CheckpointStep != 75 {
		t.Fatalf("CheckpointStep = %d, want 75", prov.CheckpointStep)
	}
	if prov.CheckpointSha != "ff00" {
		t.Fatalf("CheckpointSha = %q, want %q", prov.CheckpointSha, "ff00")
	}
}

// Case 2: server error -> fallback fires, action is the heuristic's,
// provenance reports the fallback reason and no checkpoint identity.
func TestHTTPPolicyChooseActionCtxProvFallback(t *testing.T) {
	state := testDiscardState()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "unavailable", http.StatusServiceUnavailable)
	}))
	defer server.Close()

	policy := NewHTTPPolicy(server.URL+"/act", WithLogger(nil))
	action, prov := policy.ChooseActionCtxProv(&bot.DecisionContext{State: state, Seat: 0, DecisionIndex: 1})

	assertFallbackDiscard(t, action)
	if prov.Source != "fallback" {
		t.Fatalf("Source = %q, want %q", prov.Source, "fallback")
	}
	if prov.FallbackReason != FallbackReasonStatus {
		t.Fatalf("FallbackReason = %q, want %q", prov.FallbackReason, FallbackReasonStatus)
	}
	if prov.CheckpointName != "" {
		t.Fatalf("CheckpointName = %q, want empty", prov.CheckpointName)
	}
}

// Case 3: sha absent from body (legacy server, Task 4 not yet shipped) ->
// still Source "remote", but CheckpointSha is empty rather than erroring.
func TestHTTPPolicyChooseActionCtxProvRemoteSuccessNoSha(t *testing.T) {
	state := testDiscardState()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(actResponse{
			ActionID:       5,
			CheckpointPath: "/models/ck.pt",
			CheckpointStep: 75,
		})
	}))
	defer server.Close()

	policy := NewHTTPPolicy(server.URL+"/act", WithLogger(nil))
	action, prov := policy.ChooseActionCtxProv(&bot.DecisionContext{State: state, Seat: 0, DecisionIndex: 1})

	if action == nil {
		t.Fatal("expected remote action")
	}
	if prov.Source != "remote" {
		t.Fatalf("Source = %q, want %q", prov.Source, "remote")
	}
	if prov.CheckpointSha != "" {
		t.Fatalf("CheckpointSha = %q, want empty", prov.CheckpointSha)
	}
}

var _ bot.ProvenanceContextPolicy = (*HTTPPolicy)(nil)
