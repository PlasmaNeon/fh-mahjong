package rl

import (
	"fmt"
	"sort"
	"sync"

	pb "github.com/plasma/fh-mahjong/proto"
)

// SearchPool holds K determinized clones of one live Env decision point for
// test-time search (e.g. a Python MCTS/rollout loop). Each clone is a
// CloneForBranch copy whose unseen state (opponents' hands + undrawn wall) has
// been re-dealt with a per-clone seed via engine.Game.RedealUnseen, while
// everything the acting seat can see stays fixed. Clones are stepped in
// lockstep rounds through Step, reusing the EnvPool proto messages.
//
// Response contract (documented deviations from EnvPool / FHEnvPool, all within
// the same SlotState messages):
//   - RoundOutcome != nil && !Terminated ⇒ the clone's current ROUND ended;
//     HasObservation=true carries the FIRST decision of the NEXT hand (the
//     value-bootstrap state). Python then stops stepping that clone.
//   - Terminated=true ⇒ the match ended; HasObservation=false.
//   - Truncated=true (per-clone decision cap) ⇒ HasObservation=true: the
//     cap-state observation IS returned for value bootstrapping. This is the
//     deliberate deviation from EnvPool, whose assembler drops the observation
//     on truncation.
//   - reset_seed command ⇒ per-slot error ("search pool has no reset"); the
//     pool keeps working.
type SearchPool struct {
	clones []*searchClone
	config *pb.EnvConfig
	maxDec uint64
}

type searchClone struct {
	env       *Env
	decisions uint64
	done      bool
}

// NewSearchPool builds `clones` determinized copies of e's current decision
// point. It fails on a nil env, an oracle-configured env (search must never see
// oracle channels), or an env that is not at a decision point.
func NewSearchPool(e *Env, clones int, seed uint64, maxRolloutDecisions uint64) (*SearchPool, error) {
	if e == nil || e.game == nil || e.game.State == nil {
		return nil, fmt.Errorf("search pool: nil env")
	}
	cfg := normalizeConfig(e.config)
	if cfg.OracleObservation {
		return nil, fmt.Errorf("search pool: oracle observation is forbidden in search")
	}
	seat, ok := e.currentActionSeat()
	if !ok {
		return nil, fmt.Errorf("search pool: env is not at a decision point")
	}
	if clones < 1 {
		clones = 1
	}

	p := &SearchPool{config: cfg, maxDec: maxRolloutDecisions}
	for i := 0; i < clones; i++ {
		g := e.game.CloneForBranch()
		if g == nil {
			return nil, fmt.Errorf("search pool: clone %d failed", i)
		}
		if err := g.RedealUnseen(seat, seed*1000003+uint64(i)); err != nil {
			return nil, err
		}
		p.clones = append(p.clones, &searchClone{env: &Env{
			config:        cfg,
			game:          g,
			learningSeats: map[uint32]bool{0: true, 1: true, 2: true, 3: true},
			decisionCount: e.decisionCount,
			baseSeed:      e.baseSeed,
			// The clone must carry the visible score snapshot so its dense
			// per-step reward (scoreDeltaReward) measures the change SINCE the
			// branch point, not since zero. The skeleton omitted this; it is
			// required for correct Chongci rewards.
			lastScores: snapshotScores(g.State),
		}})
	}
	return p, nil
}

// Step applies at most one command per commanded slot: an action_id steps that
// clone, skip idles it, reset_seed is a per-slot error. Commanded slots run
// concurrently (each clone is touched by its own goroutine).
func (p *SearchPool) Step(request *pb.EnvPoolStepRequest) (*pb.EnvPoolStepResponse, error) {
	commands := request.GetCommands()
	seen := make(map[uint32]bool, len(commands))
	for _, cmd := range commands {
		if int(cmd.GetSlot()) >= len(p.clones) {
			return nil, fmt.Errorf("slot %d out of range (pool has %d clones)", cmd.GetSlot(), len(p.clones))
		}
		if seen[cmd.GetSlot()] {
			return nil, fmt.Errorf("duplicate command for slot %d", cmd.GetSlot())
		}
		seen[cmd.GetSlot()] = true
	}

	results := make([]slotResult, len(commands))
	var wg sync.WaitGroup
	for i, cmd := range commands {
		wg.Add(1)
		go func(i int, cmd *pb.SlotCommand) {
			defer wg.Done()
			results[i] = p.stepOne(cmd)
		}(i, cmd)
	}
	wg.Wait()

	sort.Slice(results, func(a, b int) bool { return results[a].slot < results[b].slot })
	return assembleSearchResponse(results)
}

func (p *SearchPool) stepOne(cmd *pb.SlotCommand) slotResult {
	slot := cmd.GetSlot()
	clone := p.clones[slot]
	switch c := cmd.GetCmd().(type) {
	case *pb.SlotCommand_ResetSeed:
		return slotResult{slot: slot, err: fmt.Errorf("search pool has no reset")}
	case *pb.SlotCommand_ActionId:
		if clone.done {
			// The clone already ended its rollout; Python should have skipped
			// it. Idle defensively rather than stepping a terminal game.
			return slotResult{slot: slot, skipped: true}
		}
		res := p.stepClone(clone, c.ActionId)
		res.slot = slot
		return res
	default: // skip (or unset oneof): no-op
		return slotResult{slot: slot, skipped: true}
	}
}

func (p *SearchPool) stepClone(clone *searchClone, actionID uint32) slotResult {
	env := clone.env
	seat, ok := env.currentActionSeat()
	if !ok {
		return slotResult{err: fmt.Errorf("search: clone is not at a decision point")}
	}
	action, err := decodeActionID(env.game.State, seat, int(actionID))
	if err != nil {
		return slotResult{err: err}
	}

	env.decisionCount++
	clone.decisions++
	if err := env.game.ProcessPlayerAction(seat, action); err != nil {
		return slotResult{err: err}
	}

	res := p.advanceClone(clone)
	if res.terminated || res.truncated || res.outcome != nil {
		clone.done = true
	}
	return res
}

// advanceClone drives one clone from just after a ProcessPlayerAction to its
// next decision, mirroring Env.advanceToDecision but with two search-specific
// behaviours it cannot delegate:
//
//  1. Round-end detection. In Chongci, advanceToDecision auto-acks the ROUND_END
//     ready gate and continues; startNextRound() then NILS State.RoundResult, so
//     the just-ended outcome would be unrecoverable afterwards. HandNum-change is
//     a robust boundary signal but carries no payout data. We therefore capture
//     the RoundOutcome HERE, before readying up, and attach it to the surfaced
//     next-hand decision — realising "RoundOutcome + next-hand obs".
//  2. Decision cap. The per-clone maxRolloutDecisions cap truncates WITH the
//     cap-state observation (value bootstrap), unlike Env's MaxDecisions cap.
func (p *SearchPool) advanceClone(clone *searchClone) slotResult {
	env := clone.env
	var pendingOutcome *pb.RoundOutcome
	for {
		state := env.game.State

		if state.Phase == pb.GamePhase_PHASE_MATCH_END {
			// Terminal: dense per-step rewards already telescoped the outcome.
			// Attach any final-round outcome so callers still get payout metadata
			// (symmetric with the classic-terminal path below). Prefer a
			// pendingOutcome captured this advance; fall back to the current
			// state's outcome (nil-safe).
			outcome := pendingOutcome
			if outcome == nil {
				outcome = roundOutcome(state)
			}
			return slotResult{terminated: true, rewards: env.scoreDeltaReward(), outcome: outcome}
		}

		if state.Phase == pb.GamePhase_PHASE_ROUND_END {
			if state.MatchMode == pb.MatchMode_MATCH_MODE_CHONGCI {
				// Capture before readying up: startNextRound() clears RoundResult.
				pendingOutcome = roundOutcome(state)
				if err := env.readyAllPlayersForNextRound(); err != nil {
					return slotResult{err: err}
				}
				continue
			}
			// Classic: a round end is the match's terminal state for search.
			return slotResult{terminated: true, rewards: roundRewards(state), outcome: roundOutcome(state)}
		}

		if p.maxDec > 0 && clone.decisions >= p.maxDec {
			obs := p.capStateObservation(env)
			return slotResult{truncated: true, rewards: env.scoreDeltaReward(), observation: obs, outcome: pendingOutcome}
		}

		if seat, ok := env.currentActionSeat(); ok {
			obs, err := encodeObservation(state, seat, env.decisionCount, false)
			if err != nil {
				return slotResult{err: err}
			}
			return slotResult{observation: obs, rewards: env.scoreDeltaReward(), outcome: pendingOutcome}
		}

		if state.Phase == pb.GamePhase_PHASE_WAIT_DISCARDS {
			// All interrupt-window seats have queued (or been re-asked); resolve.
			if err := env.assertInterruptsReadyToResolve(); err != nil {
				return slotResult{err: err}
			}
			env.game.ResolveInterrupts()
			continue
		}

		return slotResult{err: fmt.Errorf("search: no actionable seat found: %s", env.decisionStateSummary())}
	}
}

// capStateObservation returns the acting seat's observation at the cap point, or
// an empty (zero-plane) observation if the game is mid-transition with no seat
// currently on the clock.
func (p *SearchPool) capStateObservation(env *Env) *pb.SeatObservation {
	if seat, ok := env.currentActionSeat(); ok {
		if obs, err := encodeObservation(env.game.State, seat, env.decisionCount, false); err == nil {
			return obs
		}
	}
	return emptyObservation(env.game.State, env.decisionCount, false)
}

// cloneObservationForTest is an unexported test hook returning EncodeObservation
// of clone i for the given seat.
func (p *SearchPool) cloneObservationForTest(i int, seat uint32) *pb.SeatObservation {
	if i < 0 || i >= len(p.clones) {
		return nil
	}
	clone := p.clones[i]
	obs, err := encodeObservation(clone.env.game.State, seat, clone.env.decisionCount, false)
	if err != nil {
		return nil
	}
	return obs
}

// Close releases the pool's clones.
func (p *SearchPool) Close() {
	p.clones = nil
}

// assembleSearchResponse packs slot results into an EnvPoolStepResponse using
// the SearchPool observation-inclusion contract: an observation is carried
// whenever the slot is not skipped, not terminated, and an observation exists —
// including the truncated cap state and the round-end next-hand state (both of
// which EnvPool's assembler would drop).
func assembleSearchResponse(results []slotResult) (*pb.EnvPoolStepResponse, error) {
	response := &pb.EnvPoolStepResponse{}
	for _, r := range results {
		state := &pb.SlotState{Slot: r.slot, Terminated: r.terminated, Truncated: r.truncated,
			StepRewards: r.rewards, RoundOutcome: r.outcome}
		if r.err != nil {
			state.Error = r.err.Error()
			response.Slots = append(response.Slots, state)
			continue
		}
		hasObs := !r.skipped && !r.terminated && r.observation != nil
		state.HasObservation = hasObs
		if hasObs {
			state.Seat = r.observation.Seat
			appendObservationRow(response, r.observation)
		}
		response.Slots = append(response.Slots, state)
	}
	return response, nil
}
