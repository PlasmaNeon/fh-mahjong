package api

import (
	"log"
	"sort"

	"github.com/plasma/fh-mahjong/internal/bot"
	"github.com/plasma/fh-mahjong/internal/engine"
	"github.com/plasma/fh-mahjong/internal/rl"
	pb "github.com/plasma/fh-mahjong/proto"
)

// This file captures the paipu v2 supervision trace (spec:
// docs/superpowers/specs/2026-08-09-paipu-v2-provenance-design.md §2-3).
// The room layer is the single choke point where every explicit decision
// passes AND provenance is known; the engine stays provenance-blind.

// decisionSnapshot holds the pre-action context of one decision: the legal
// catalog IDs and the chosen action's catalog id, both computed against the
// PRE-action state (encoding after mutation would be wrong).
type decisionSnapshot struct {
	legalIDs []int
	chosenID int
	snapErr  bool // legal-set enumeration or encoding failed (never blocks play)
}

// snapshotDecision computes the legal-set + chosen-id context for seat's
// pending action. Call BEFORE Engine.ProcessPlayerAction.
func (r *Room) snapshotDecision(seat uint32, action *pb.PlayerAction) decisionSnapshot {
	snap := decisionSnapshot{chosenID: -1}
	legal, err := rl.LegalActions(r.Engine.State, seat)
	if err != nil {
		log.Printf("paipu decision snapshot: legal-set enumeration failed for seat %d in room %s: %v", seat, r.ID, err)
		snap.snapErr = true
	} else {
		snap.legalIDs = make([]int, 0, len(legal))
		for id := range legal {
			snap.legalIDs = append(snap.legalIDs, id)
		}
		sort.Ints(snap.legalIDs)
	}
	if id, ok := rl.EncodeAction(r.Engine.State, seat, action); ok {
		snap.chosenID = id
	} else {
		log.Printf("paipu decision snapshot: EncodeAction failed for seat %d action %v in room %s", seat, action.Type, r.ID)
		snap.snapErr = true
	}
	return snap
}

// recordDecision appends the supervision-trace row for a decision that has
// just been SUCCESSFULLY processed. prov describes who produced the action.
func (r *Room) recordDecision(seat uint32, snap decisionSnapshot, prov bot.DecisionProvenance) {
	if r.Engine.Recorder == nil {
		return
	}
	d := engine.PaipuDecision{
		Seat:           seat,
		ChosenID:       snap.chosenID,
		LegalIDs:       snap.legalIDs,
		LegalIDsError:  snap.snapErr,
		Source:         prov.Source,
		FallbackReason: prov.FallbackReason,
	}
	if prov.Source == "remote" {
		d.Checkpoint = &engine.PaipuCheckpoint{
			Name:   prov.CheckpointName,
			Step:   prov.CheckpointStep,
			Sha256: prov.CheckpointSha,
		}
	}
	r.Engine.Recorder.RecordDecision(d)
}

// humanProvenance / heuristicProvenance are the fixed labels for
// non-remote decision sources.
func humanProvenance() bot.DecisionProvenance     { return bot.DecisionProvenance{Source: "human"} }
func heuristicProvenance() bot.DecisionProvenance { return bot.DecisionProvenance{Source: "heuristic"} }

// chooseSeatAction asks the seat's policy for an action, preferring the
// richest capability it implements, and returns the decision's provenance
// alongside it (heuristic unless the policy reports otherwise).
func (r *Room) chooseSeatAction(seat uint32) (*pb.PlayerAction, bot.DecisionProvenance) {
	policy := r.policyForSeat(seat)
	prov := heuristicProvenance()
	switch p := policy.(type) {
	case bot.ProvenanceContextPolicy:
		action, provOut := p.ChooseActionCtxProv(r.buildDecisionContext(seat))
		return action, provOut
	case bot.ContextPolicy:
		return p.ChooseActionCtx(r.buildDecisionContext(seat)), prov
	default:
		return policy.ChooseAction(r.Engine.State, seat), prov
	}
}
