package bot

import (
	"github.com/plasma/fh-mahjong/internal/engine"
	pb "github.com/plasma/fh-mahjong/proto"
)

// DecisionContext is an atomic snapshot of everything a policy needs to make
// one decision: the current engine state, which seat is deciding, a
// room-owned monotonically increasing decision counter, and a copy of the
// round's public event log at the moment of the decision. Events is a
// snapshot COPY (RAW, unwindowed) — callers may hold onto it after the
// room's lock is released.
type DecisionContext struct {
	State         *pb.GameState
	Seat          uint32
	DecisionIndex uint64
	Events        []engine.PublicEvent
}

// ContextPolicy is an additive capability: policies that need more than the
// legacy (state, seat) pair — e.g. the public event log or a stable
// decision index for correlating with an external policy server — implement
// this alongside (or instead of) Policy. Room dispatch prefers
// ChooseActionCtx when a policy implements it; Policy.ChooseAction is
// unchanged and must keep working for policies that don't.
type ContextPolicy interface {
	ChooseActionCtx(ctx *DecisionContext) *pb.PlayerAction
}

// DecisionProvenance identifies where ONE decision's action actually came
// from: the remote policy server (with the serving checkpoint's identity),
// a local fallback (with the reason the remote path was not used), or a
// purely local heuristic policy that never had remote provenance to report.
// It travels only via return values — never as mutable state on a policy —
// so a hot reload between two decisions can never cross-attribute.
type DecisionProvenance struct {
	Source         string // "remote" | "fallback" | "heuristic"
	FallbackReason string // set only when Source == "fallback"
	CheckpointName string // set only when Source == "remote"
	CheckpointStep int64
	CheckpointSha  string // may be empty (legacy server)
}

// ProvenanceContextPolicy is the additive capability: same decision flow as
// ChooseActionCtx but the provenance of THIS decision travels back with the
// action (never via mutable policy state).
type ProvenanceContextPolicy interface {
	ContextPolicy
	ChooseActionCtxProv(ctx *DecisionContext) (*pb.PlayerAction, DecisionProvenance)
}
