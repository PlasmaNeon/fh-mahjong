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
// Value bootstrapping is IN-DISTRIBUTION by construction. The champion value
// head was trained on per-seat GAE where V is only ever evaluated at states
// where THAT seat has a genuine decision. So every bootstrap row this pool emits
// is a REAL root-seat decision state with its REAL action mask — never the root
// seat's view frozen at another seat's turn (which would be out-of-distribution,
// and candidate-dependent under Chongci dealer succession → ranking corruption).
//
// Response contract (documented deviations from EnvPool / FHEnvPool, all within
// the same SlotState messages):
//   - RoundOutcome != nil && !Terminated ⇒ a ROUND ended earlier in this clone's
//     rollout and the clone has now reached the ROOT seat's next GENUINE
//     decision; HasObservation=true carries THAT row (root's real decision state,
//     real mask) as the VALUE-BOOTSTRAP row with the captured round outcome
//     attached. Python scores step_rewards[root] + V(this row) and skips the
//     clone. Between the round boundary and this row the clone surfaces ORDINARY
//     live-decision rows (other seats act in the next hand; Python steps them
//     with the champion as usual) — no outcome attached, no bootstrap.
//   - Terminated=true ⇒ the match ended; HasObservation=false. If the match ends
//     while still awaiting a bootstrap (root never got another decision), the
//     latest captured outcome is attached as metadata (rewards already telescoped
//     — no bootstrap, per the GAE terminal convention).
//   - Truncated=true (per-clone decision cap) ⇒ HasObservation=true: the cap is
//     checked ONLY at a root-seat decision, so the truncation row is always a
//     genuine root decision state (in-distribution) with its real mask. This is
//     the deliberate deviation from EnvPool, whose assembler drops the obs on
//     truncation.
//   - reset_seed command ⇒ per-slot error ("search pool has no reset"); the
//     pool keeps working.
//   - A hard safety stop (total decisions ≥ 2*maxRolloutDecisions+16 with no root
//     decision reached) ⇒ per-slot error, so a pathological no-root-decision loop
//     cannot spin (Python fail-open drops the clone).
//
// Root-action pinning. The FIRST action command sent to each clone is the ROOT
// CANDIDATE — the move being searched for rootSeat. It is always decoded and
// executed for rootSeat (searchClone.rootApplied gates this), NOT for whatever
// currentActionSeat() reports. At a WAIT_DISCARDS root, RedealUnseen recomputes
// interrupt eligibility for every opponent, so a clone's first
// currentActionSeat() can be a newly-eligible lower-numbered seat rather than
// rootSeat; ProcessPlayerAction accepts interrupt responses from any window seat
// asynchronously, so pinning plays the candidate as rootSeat's move. At a
// PLAYER_TURN root currentActionSeat() == rootSeat, so pinning is a no-op there.
// Every subsequent command uses currentActionSeat().
type SearchPool struct {
	clones   []*searchClone
	config   *pb.EnvConfig
	maxDec   uint64
	rootSeat uint32
}

type searchClone struct {
	env       *Env
	decisions uint64
	done      bool
	// rootApplied records whether this clone has consumed its ROOT CANDIDATE
	// action yet. The FIRST action command a clone receives is always the root
	// candidate — the move being searched for p.rootSeat. It MUST be executed
	// for p.rootSeat, not for whatever currentActionSeat() reports.
	//
	// At a WAIT_DISCARDS root, RedealUnseen recomputes interrupt eligibility for
	// every opponent, so a clone's first currentActionSeat() can be a
	// LOWER-numbered seat that became newly eligible — never the root seat. Since
	// ProcessPlayerAction in WAIT_DISCARDS accepts interrupt responses from any
	// window seat asynchronously (handleInterruptAction dispatch), pinning the
	// first step to p.rootSeat plays the searched candidate as the root player's
	// move. At a PLAYER_TURN root currentActionSeat() == p.rootSeat anyway, so
	// pinning is a no-op there. Subsequent commands (the other window seats'
	// responses, later turns) use currentActionSeat() as usual.
	rootApplied bool
	// awaitingBootstrap records that a ROUND ended in this clone's rollout and we
	// have not yet reached the root seat's next genuine decision to emit as the
	// value-bootstrap row. While it is set, the clone keeps surfacing ordinary
	// live-decision rows (other seats acting in the next hand) until a root
	// decision arrives (→ bootstrap emitted with pendingOutcome attached) or the
	// match ends (→ terminated, latest pendingOutcome attached as metadata). It
	// persists ACROSS Step calls because the bootstrap decision usually lands
	// several steps after the boundary.
	awaitingBootstrap bool
	// pendingOutcome is the round outcome captured at the most recent PHASE_ROUND_END
	// (before readyAllPlayersForNextRound clears State.RoundResult). If a second
	// round ends while still awaiting (root never acted between them — rare), it is
	// overwritten with the LATEST outcome. Cleared once the bootstrap row is emitted.
	pendingOutcome *pb.RoundOutcome
}

// NewSearchPool builds `clones` determinized copies of e's current decision
// point. It fails on a nil env, an oracle-configured env (search must never see
// oracle channels), or an env that is not at a decision point.
//
// Root seat selection. The variadic rootSeat makes the search root EXPLICIT
// end-to-end. When one value is supplied it is validated against the env's
// pending-decision set (seatHasPendingDecision) and used as the pool root; when
// omitted the pool falls back to e.currentActionSeat() (the all-four-learning
// self-play default; existing Go tests rely on this back-compat). The explicit
// form is REQUIRED for duplicate-seat evaluation (auto_play_heuristics=true, one
// learning seat): at a WAIT_DISCARDS window a lower-numbered heuristic opponent
// can hold an unqueued interrupt at the same time as the learning seat, so
// currentActionSeat() would return the opponent and the pool would root on — and
// RedealUnseen would protect — the WRONG hand, and pinning would apply the
// learning seat's candidate id as that opponent's move. Passing the learning
// seat explicitly roots the pool correctly.
//
// Common-random-numbers pairing (honesty guarantee against a live-seed future
// leak). Clone i belongs to determinization group k = i % determinizations
// (K; the clone count is M candidates x K). BOTH per-clone seeds are derived
// from (pool seed, k) ALONE:
//
//   - redealSeed  = seed*1_000_003 + k  → the hidden world (opponents' hands +
//     undrawn wall) RedealUnseen deals.
//   - cloneBaseSeed = seed*7_919 + k + 1 → the clone Env's baseSeed, which
//     drives readyAllPlayersForNextRound's next-hand wall at a Chongci round
//     boundary (deriveHandSeed(baseSeed, handNum)).
//
// NEITHER is ever derived from e.baseSeed. Copying the live env's baseSeed (the
// pre-fix behaviour) let a rollout that crosses a round boundary deal the live
// simulator's ACTUAL future hand — information unavailable at the root decision,
// and the root-seat next-hand bootstrap observation would contain the player's
// real future tiles. Deriving from (seed, k) instead means clones (c,k) and
// (c',k) in different candidate groups share the identical determinized world
// AND the identical sampled future, so candidates are compared on paired worlds
// (variance-reducing) and the live env's future is never consulted.
func NewSearchPool(e *Env, clones int, seed uint64, maxRolloutDecisions uint64, determinizations uint32, rootSeat ...uint32) (*SearchPool, error) {
	if e == nil || e.game == nil || e.game.State == nil {
		return nil, fmt.Errorf("search pool: nil env")
	}
	if len(rootSeat) > 1 {
		return nil, fmt.Errorf("search pool: at most one root seat may be supplied, got %d", len(rootSeat))
	}
	cfg := normalizeConfig(e.config)
	if cfg.OracleObservation {
		return nil, fmt.Errorf("search pool: oracle observation is forbidden in search")
	}
	var seat uint32
	if len(rootSeat) == 1 {
		// Explicit root: validate the caller-chosen seat is genuinely actionable
		// right now. This is the seat whose hand RedealUnseen preserves and whose
		// candidate the first apply pins, so an unactionable choice must error
		// rather than mis-score or fail open at an interrupt decision.
		seat = rootSeat[0]
		if !e.seatHasPendingDecision(seat) {
			return nil, fmt.Errorf("search pool: root seat %d has no pending decision", seat)
		}
	} else {
		s, ok := e.currentActionSeat()
		if !ok {
			return nil, fmt.Errorf("search pool: env is not at a decision point")
		}
		seat = s
	}
	if clones < 1 {
		clones = 1
	}
	// determinizations==0 means "each clone its own world" (K = clone count), so
	// k = i % clones == i and every clone is independent — the honest default
	// when the caller does not pair.
	if determinizations < 1 {
		determinizations = uint32(clones)
	}

	p := &SearchPool{config: cfg, maxDec: maxRolloutDecisions, rootSeat: seat}
	for i := 0; i < clones; i++ {
		k := uint64(uint32(i) % determinizations)
		g := e.game.CloneForBranch()
		if g == nil {
			return nil, fmt.Errorf("search pool: clone %d failed", i)
		}
		if err := g.RedealUnseen(seat, seed*1000003+k); err != nil {
			return nil, err
		}
		p.clones = append(p.clones, &searchClone{env: &Env{
			config:        cfg,
			game:          g,
			learningSeats: map[uint32]bool{0: true, 1: true, 2: true, 3: true},
			decisionCount: e.decisionCount,
			// Derive the clone's baseSeed from (pool seed, k) — NEVER from
			// e.baseSeed — so a boundary-crossing rollout's next-hand wall is a
			// sampled future paired by k, not the live env's actual future.
			baseSeed: seed*7919 + k + 1,
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
	// Root-action pinning: the FIRST command a clone receives is the root
	// candidate, which must be decoded/executed for p.rootSeat regardless of
	// currentActionSeat(). After a WAIT_DISCARDS redeal, currentActionSeat() may
	// surface a newly-eligible lower-numbered seat; applying the candidate there
	// would either fail-open or, worse, play it as the wrong seat's move. Every
	// subsequent command uses currentActionSeat().
	var seat uint32
	if clone.rootApplied {
		s, ok := env.currentActionSeat()
		if !ok {
			return slotResult{err: fmt.Errorf("search: clone is not at a decision point")}
		}
		seat = s
	} else {
		seat = p.rootSeat
	}
	action, err := decodeActionID(env.game.State, seat, int(actionID))
	if err != nil {
		return slotResult{err: err}
	}
	clone.rootApplied = true

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

// advanceClone drives one clone from just after a ProcessPlayerAction to the
// next row it surfaces, mirroring Env.advanceToDecision but with search-specific
// behaviours it cannot delegate. The bootstrap contract keeps every value row
// IN-DISTRIBUTION for the champion value head (a real root-seat decision state):
//
//  1. Round-end detection + deferred bootstrap. In Chongci, advanceToDecision
//     auto-acks the ROUND_END ready gate and continues; startNextRound() then
//     NILS State.RoundResult, so the just-ended outcome would be unrecoverable
//     afterwards. We therefore capture the RoundOutcome HERE, before readying up,
//     into clone.pendingOutcome and set clone.awaitingBootstrap — but we do NOT
//     stop the clone. It keeps surfacing ordinary live-decision rows (other seats
//     act in the next hand) until the ROOT seat's next genuine decision, which we
//     emit as the bootstrap row with the outcome attached.
//  2. Decision cap. The per-clone maxRolloutDecisions cap is checked ONLY at a
//     root-seat decision, so a truncation row is always a genuine root decision
//     state; it truncates WITH that observation (value bootstrap), unlike Env's
//     MaxDecisions cap.
//  3. Hard safety stop. A pathological rollout that never reaches a root decision
//     is broken with a per-slot error once total decisions exceed a hard bound.
func (p *SearchPool) advanceClone(clone *searchClone) slotResult {
	env := clone.env
	for {
		state := env.game.State

		if state.Phase == pb.GamePhase_PHASE_MATCH_END {
			// Terminal: dense per-step rewards already telescoped the outcome, so
			// there is NO bootstrap (GAE terminal convention) even if we were still
			// awaiting one — the root simply never got another decision. Attach the
			// latest captured outcome (or the current state's, nil-safe) so callers
			// still get final-round payout metadata.
			outcome := clone.pendingOutcome
			if outcome == nil {
				outcome = roundOutcome(state)
			}
			return slotResult{terminated: true, rewards: env.scoreDeltaReward(), outcome: outcome}
		}

		if state.Phase == pb.GamePhase_PHASE_ROUND_END {
			if state.MatchMode == pb.MatchMode_MATCH_MODE_CHONGCI {
				// Capture before readying up (startNextRound() clears RoundResult),
				// arm the bootstrap, and keep going — the clone continues surfacing
				// ordinary rows until the root's next decision. A second boundary
				// while still awaiting overwrites with the LATEST outcome.
				clone.pendingOutcome = roundOutcome(state)
				clone.awaitingBootstrap = true
				if err := env.readyAllPlayersForNextRound(); err != nil {
					return slotResult{err: err}
				}
				continue
			}
			// Classic: a round end is the match's terminal state for search.
			return slotResult{terminated: true, rewards: roundRewards(state), outcome: roundOutcome(state)}
		}

		// Hard safety stop: never let a clone that fails to reach another root
		// decision spin forever. Python fail-open drops the errored clone.
		if p.maxDec > 0 && clone.decisions >= 2*p.maxDec+16 {
			return slotResult{err: fmt.Errorf("search: hard decision cap %d exceeded without a root decision", clone.decisions)}
		}

		if seat, ok := env.currentActionSeat(); ok {
			isRoot := seat == p.rootSeat
			// Bootstrap emission: the root's next GENUINE decision after a round
			// boundary. Emit THIS row (real decision state + real mask) with the
			// captured outcome attached; Python scores and skips the clone.
			if isRoot && clone.awaitingBootstrap {
				obs, err := encodeObservation(state, seat, env.decisionCount, false)
				if err != nil {
					return slotResult{err: err}
				}
				outcome := clone.pendingOutcome
				clone.awaitingBootstrap = false
				clone.pendingOutcome = nil
				return slotResult{observation: obs, rewards: env.scoreDeltaReward(), outcome: outcome}
			}
			// Decision cap, checked ONLY at a root decision so the truncation row is
			// an in-distribution root decision state with a real mask.
			if isRoot && p.maxDec > 0 && clone.decisions >= p.maxDec {
				obs, err := encodeObservation(state, seat, env.decisionCount, false)
				if err != nil {
					return slotResult{err: err}
				}
				return slotResult{truncated: true, rewards: env.scoreDeltaReward(), observation: obs}
			}
			// Ordinary live-decision row: encode the acting seat to drive rollout.
			obs, err := encodeObservation(state, seat, env.decisionCount, false)
			if err != nil {
				return slotResult{err: err}
			}
			return slotResult{observation: obs, rewards: env.scoreDeltaReward()}
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
