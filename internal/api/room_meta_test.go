package api

import (
	"encoding/json"
	"testing"

	"github.com/plasma/fh-mahjong/internal/engine"
	"github.com/plasma/fh-mahjong/internal/rl"
	pb "github.com/plasma/fh-mahjong/proto"
)

// TestPersistMatchStampsV2Meta drives a full chongci match (capped at one
// hand) to its natural PHASE_MATCH_END and asserts the persisted paipu
// carries the complete v2 header: status/reason, placements, match mode +
// chongci config, and the version/provenance constants pinned by earlier
// tasks.
func TestPersistMatchStampsV2Meta(t *testing.T) {
	var captured string
	cfg := &pb.ChongciConfig{
		StartingScore: 3000,
		BustThreshold: -500,
		MaxHands:      1,
	}
	room := NewRoom("meta-match", nil, nil, WithMatchOptions(engine.MatchOptions{
		Mode:          pb.MatchMode_MATCH_MODE_CHONGCI,
		ChongciConfig: cfg,
	}))
	room.PaipuStore = func(matchID, paipuJSON string) {
		captured = paipuJSON
	}
	room.registerPaipuPlayers()

	phase := runBotOnlyRoomUntilTerminal(t, room, 200_000)
	if phase != pb.GamePhase_PHASE_MATCH_END {
		t.Fatalf("phase = %v, want PHASE_MATCH_END (handNum=%d)", phase, room.Engine.State.HandNum)
	}

	if err := room.persistMatch(); err != nil {
		t.Fatalf("persistMatch: %v", err)
	}
	if captured == "" {
		t.Fatal("expected paipu to be captured via PaipuStore")
	}

	var paipu engine.Paipu
	if err := json.Unmarshal([]byte(captured), &paipu); err != nil {
		t.Fatalf("parse paipu: %v", err)
	}

	if paipu.Status != "completed" {
		t.Fatalf("Status = %q, want completed", paipu.Status)
	}
	if paipu.CompletionReason != "match_end" {
		t.Fatalf("CompletionReason = %q, want match_end", paipu.CompletionReason)
	}
	if paipu.Placements == nil {
		t.Fatal("expected Placements to be set")
	}
	if paipu.MatchMode != "chongci" {
		t.Fatalf("MatchMode = %q, want chongci", paipu.MatchMode)
	}
	if paipu.Chongci == nil {
		t.Fatal("expected Chongci config to be set")
	}
	if paipu.Chongci.StartingScore != 3000 || paipu.Chongci.BustThreshold != -500 || paipu.Chongci.MaxHands != 1 {
		t.Fatalf("Chongci = %+v, want the engine's config values", paipu.Chongci)
	}
	if paipu.RulesetVersion != "fenghua-v1" {
		t.Fatalf("RulesetVersion = %q, want fenghua-v1", paipu.RulesetVersion)
	}
	if paipu.EventContractVersion != rl.EventContractV1 {
		t.Fatalf("EventContractVersion = %d, want %d", paipu.EventContractVersion, rl.EventContractV1)
	}
	if paipu.ActionCatalogVersion != rl.ActionCatalogVersion {
		t.Fatalf("ActionCatalogVersion = %d, want %d", paipu.ActionCatalogVersion, rl.ActionCatalogVersion)
	}
	if paipu.ProtoEnumsRevision != engine.ProtoEnumsRevision {
		t.Fatalf("ProtoEnumsRevision = %d, want %d", paipu.ProtoEnumsRevision, engine.ProtoEnumsRevision)
	}
	if paipu.ServerCommit != "unknown" {
		t.Fatalf("ServerCommit = %q, want unknown (test binary has no ldflags)", paipu.ServerCommit)
	}
}

// TestPersistMatchAbortReason asserts the abort reason distinguishes a
// server-initiated drain from an ordinary abandoned match: markDrained()
// must flip the persisted CompletionReason from "abandoned" to "drained".
func TestPersistMatchAbortReason(t *testing.T) {
	t.Run("abandoned without drain", func(t *testing.T) {
		var captured string
		room := NewRoom("meta-abandon", nil, nil)
		room.PaipuStore = func(matchID, paipuJSON string) { captured = paipuJSON }
		room.registerPaipuPlayers()
		if err := room.Engine.Start(); err != nil {
			t.Fatalf("engine start: %v", err)
		}
		if room.Engine.State.Phase == pb.GamePhase_PHASE_MATCH_END {
			t.Fatal("test premise broken: match already ended")
		}

		if err := room.persistMatch(); err != nil {
			t.Fatalf("persistMatch: %v", err)
		}
		var paipu engine.Paipu
		if err := json.Unmarshal([]byte(captured), &paipu); err != nil {
			t.Fatalf("parse paipu: %v", err)
		}
		if paipu.Status != "aborted" {
			t.Fatalf("Status = %q, want aborted", paipu.Status)
		}
		if paipu.CompletionReason != "abandoned" {
			t.Fatalf("CompletionReason = %q, want abandoned", paipu.CompletionReason)
		}
	})

	t.Run("drained via markDrained", func(t *testing.T) {
		var captured string
		room := NewRoom("meta-drain", nil, nil)
		room.PaipuStore = func(matchID, paipuJSON string) { captured = paipuJSON }
		room.registerPaipuPlayers()
		if err := room.Engine.Start(); err != nil {
			t.Fatalf("engine start: %v", err)
		}
		if room.Engine.State.Phase == pb.GamePhase_PHASE_MATCH_END {
			t.Fatal("test premise broken: match already ended")
		}
		room.markDrained()

		if err := room.persistMatch(); err != nil {
			t.Fatalf("persistMatch: %v", err)
		}
		var paipu engine.Paipu
		if err := json.Unmarshal([]byte(captured), &paipu); err != nil {
			t.Fatalf("parse paipu: %v", err)
		}
		if paipu.Status != "aborted" {
			t.Fatalf("Status = %q, want aborted", paipu.Status)
		}
		if paipu.CompletionReason != "drained" {
			t.Fatalf("CompletionReason = %q, want drained", paipu.CompletionReason)
		}
	})
}
