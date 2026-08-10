package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"

	"github.com/plasma/fh-mahjong/internal/engine"
	"github.com/plasma/fh-mahjong/internal/review"
)

// TestGeneratedPaipuPassesReview pins the contract this tool's output has to
// honor: the file it writes is a version-2 paipu, so it must carry a decision
// trace that internal/review's cross-check accepts. The generated JSON is
// round-tripped through disk exactly as `go run ./cmd/rlpaipu -output ...`
// would produce it, then fed to ExtractDecisions — the same call the real
// POST /api/v1/matches/<id>/review flow makes.
func TestGeneratedPaipuPassesReview(t *testing.T) {
	paipu, err := generateHeuristicPaipu("rlpaipu-test", 1, 512)
	if err != nil {
		t.Fatalf("generate paipu: %v", err)
	}
	if paipu.Version < 2 {
		t.Fatalf("expected a version-2 paipu, got version %d", paipu.Version)
	}

	payload, err := json.MarshalIndent(paipu, "", "  ")
	if err != nil {
		t.Fatalf("marshal paipu: %v", err)
	}
	path := filepath.Join(t.TempDir(), "paipu.json")
	if err := os.WriteFile(path, append(payload, '\n'), 0o644); err != nil {
		t.Fatalf("write paipu: %v", err)
	}

	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read paipu: %v", err)
	}
	var loaded engine.Paipu
	if err := json.Unmarshal(raw, &loaded); err != nil {
		t.Fatalf("unmarshal paipu: %v", err)
	}

	rows := 0
	for i := range loaded.Rounds {
		rows += len(loaded.Rounds[i].Decisions)
	}
	if rows == 0 {
		t.Fatal("generated paipu carries no decision rows")
	}

	decisions, err := review.ExtractDecisions(&loaded, 0)
	if err != nil {
		t.Fatalf("ExtractDecisions on generated paipu: %v", err)
	}
	if len(decisions) == 0 {
		t.Fatal("expected at least one reviewable decision")
	}
}
