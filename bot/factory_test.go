package bot

import (
	"testing"

	pb "github.com/plasma/fh-mahjong/proto"
)

func TestNewPolicyHeuristic(t *testing.T) {
	policy, err := NewPolicy(pb.Difficulty_DIFFICULTY_HEURISTIC)
	if err != nil {
		t.Fatalf("NewPolicy(HEURISTIC) returned error: %v", err)
	}
	if policy == nil {
		t.Fatal("NewPolicy(HEURISTIC) returned nil policy")
	}
	if _, ok := policy.(*HeuristicPolicy); !ok {
		t.Fatalf("expected *HeuristicPolicy, got %T", policy)
	}
}

func TestNewPolicyUnspecifiedRejected(t *testing.T) {
	if _, err := NewPolicy(pb.Difficulty_DIFFICULTY_UNSPECIFIED); err == nil {
		t.Fatal("expected error for DIFFICULTY_UNSPECIFIED")
	}
}

func TestNewPolicyUnknownRejected(t *testing.T) {
	if _, err := NewPolicy(pb.Difficulty(99)); err == nil {
		t.Fatal("expected error for unknown difficulty value")
	}
}
