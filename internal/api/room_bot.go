package api

import (
	"log"
	"time"

	"github.com/plasma/fh-mahjong/internal/bot"
	"github.com/plasma/fh-mahjong/internal/engine"
	pb "github.com/plasma/fh-mahjong/proto"
)

// This file holds the automated-seat ("bot") driving logic for a Room:
// deciding when a seat has no connected human, scheduling paced bot steps,
// and advancing the engine through bot turns. The Room struct, its lifecycle
// (Start/BroadcastState), and seat/client bookkeeping live in room.go.

// fallbackHeuristicPolicy is a stateless package-level instance used by
// policyForSeat when a configured policy is missing for an automated seat.
// HeuristicPolicy carries no state, so a single shared instance is safe.
var fallbackHeuristicPolicy bot.Policy = bot.NewHeuristicPolicy()

const maxAutomatedSeatIterations = 200

func (r *Room) advanceAutomatedSeats() [][]byte {
	return r.advanceAutomatedSeatsN(maxAutomatedSeatIterations)
}

// advanceAutomatedSeatsN drives automated seats for at most maxIters steps.
// Pass 1 to take a single bot step (used by the bot pump to stay responsive);
// pass maxAutomatedSeatIterations to drain consecutive bot turns in one go.
func (r *Room) advanceAutomatedSeatsN(maxIters int) [][]byte {
	var payloads [][]byte

	for iteration := 0; iteration < maxIters; iteration++ {
		switch r.Engine.State.Phase {
		case pb.GamePhase_PHASE_PLAYER_TURN:
			seat := r.Engine.State.ActivePlayer
			if !r.isAutomatedSeat(seat) {
				return payloads
			}

			action, prov := r.chooseSeatAction(seat)
			if action == nil {
				log.Printf("bot policy produced no action for active seat %d in room %s", seat, r.ID)
				return payloads
			}

			r.sleepBotThink(action.Type)

			// Snapshot the decision context on the PRE-action state.
			var snap decisionSnapshot
			if r.Engine.Recorder != nil {
				snap = r.snapshotDecision(seat, action)
			}

			if err := r.Engine.ProcessPlayerAction(seat, action); err != nil {
				log.Printf("bot action failed for seat %d in room %s: %v", seat, r.ID, err)
				return payloads
			}
			if r.Engine.Recorder != nil {
				r.recordDecision(seat, snap, prov)
			}
			r.automatedDecisions[seat]++

			payloads = append(payloads, r.BroadcastState())

		case pb.GamePhase_PHASE_WAIT_DISCARDS:
			submitted := false

			for seatIndex, player := range r.Engine.State.Players {
				seat := uint32(seatIndex)
				if len(player.ValidActions) == 0 || !r.isAutomatedSeat(seat) {
					continue
				}

				action, prov := r.chooseSeatAction(seat)
				if action == nil {
					// A policy that declines to act still decided to pass.
					action = &pb.PlayerAction{Type: pb.ActionType_ACTION_PASS}
				}

				r.sleepBotThink(action.Type)

				var snap decisionSnapshot
				if r.Engine.Recorder != nil {
					snap = r.snapshotDecision(seat, action)
				}

				if err := r.Engine.ProcessPlayerAction(seat, action); err != nil {
					log.Printf("bot interrupt failed for seat %d in room %s: %v", seat, r.ID, err)
					if action.Type != pb.ActionType_ACTION_PASS {
						// Error recovery: the seat still ends up passing, and
						// that pass IS a processed decision — snapshot it
						// afresh (the claim's snapshot describes a different
						// action) and record it only if it succeeded.
						pass := &pb.PlayerAction{Type: pb.ActionType_ACTION_PASS}
						var passSnap decisionSnapshot
						if r.Engine.Recorder != nil {
							passSnap = r.snapshotDecision(seat, pass)
						}
						if passErr := r.Engine.ProcessPlayerAction(seat, pass); passErr != nil {
							log.Printf("bot fallback pass failed for seat %d in room %s: %v", seat, r.ID, passErr)
						} else if r.Engine.Recorder != nil {
							// The engine rejected the policy's claim; this pass is
							// recovery, not the model's decision, so stamp it with
							// its own provenance instead of the failed claim's
							// (which could carry source:"remote" + a checkpoint).
							// "engine_reject" is room-layer-only -- it is not one of
							// remote's 9 HTTP fallback reasons.
							fallbackProv := bot.DecisionProvenance{Source: "fallback", FallbackReason: "engine_reject"}
							r.recordDecision(seat, passSnap, fallbackProv)
						}
					}
				} else if r.Engine.Recorder != nil {
					r.recordDecision(seat, snap, prov)
				}
				r.automatedDecisions[seat]++

				submitted = true
			}

			if r.Engine.State.Phase != pb.GamePhase_PHASE_WAIT_DISCARDS {
				payloads = append(payloads, r.BroadcastState())
				continue
			}

			if !submitted || r.hasConnectedInterruptSeat() {
				return payloads
			}

			r.Engine.ResolveInterrupts()
			payloads = append(payloads, r.BroadcastState())

		case pb.GamePhase_PHASE_ROUND_END:
			submitted := false

			for seatIndex := range r.Engine.State.Players {
				seat := uint32(seatIndex)
				if !r.isAutomatedSeat(seat) || r.isSeatReady(seatIndex) {
					continue
				}

				if err := r.Engine.ProcessPlayerAction(seat, &pb.PlayerAction{Type: pb.ActionType_ACTION_READY}); err != nil {
					log.Printf("bot ready failed for seat %d in room %s: %v", seat, r.ID, err)
					return payloads
				}
				submitted = true
			}

			if !submitted {
				return payloads
			}

			payloads = append(payloads, r.BroadcastState())
			if r.Engine.State.Phase == pb.GamePhase_PHASE_ROUND_END {
				return payloads
			}

		default:
			return payloads
		}
	}

	if maxIters > 1 {
		log.Printf(
			"stopped automated advancement for room %s after %d iterations at phase %v",
			r.ID,
			maxIters,
			r.Engine.State.Phase,
		)
	}
	return payloads
}

// botWorkPending reports whether the engine is waiting on an automated seat
// that no connected human will drive — i.e. the bot pump should take a step.
func (r *Room) botWorkPending() bool {
	switch r.Engine.State.Phase {
	case pb.GamePhase_PHASE_PLAYER_TURN:
		return r.isAutomatedSeat(r.Engine.State.ActivePlayer)
	case pb.GamePhase_PHASE_WAIT_DISCARDS:
		// Bots resolve interrupts only once no connected human still has a
		// pending call to make.
		return !r.hasConnectedInterruptSeat()
	case pb.GamePhase_PHASE_ROUND_END:
		for seat := range r.Engine.State.Players {
			if r.isAutomatedSeat(uint32(seat)) && !r.isSeatReady(seat) {
				return true
			}
		}
		return false
	default:
		return false
	}
}

// maybeScheduleBotTick arms a single delayed bot step when bot work is pending.
// Driving one step per tick (rather than the whole bot-only game synchronously)
// keeps the room loop responsive to reconnects. No-op if a tick is already
// pending or no bot work remains. Called only from the room goroutine.
func (r *Room) maybeScheduleBotTick() {
	if r.botTickPending || !r.botWorkPending() {
		return
	}
	r.botTickPending = true
	delay := r.botActionDelay
	go func() {
		if delay > 0 {
			time.Sleep(delay)
		}
		select {
		case r.botTick <- struct{}{}:
		default:
		}
	}()
}

func (r *Room) isAutomatedSeat(seat uint32) bool {
	_, connected := r.Seats[seat]
	return !connected
}

// sleepBotThink pauses for r.botActionDelay before a bot action so the
// game has a human pace. Skipped when the delay is 0 (tests / RL env) or
// when the action is a between-hands READY ack (which has no animation
// to wait for; the round-end overlay already has its own client-side
// duration).
func (r *Room) sleepBotThink(actionType pb.ActionType) {
	if r.botActionDelay <= 0 {
		return
	}
	if actionType == pb.ActionType_ACTION_READY {
		return
	}
	time.Sleep(r.botActionDelay)
}

// policyForSeat returns the bot policy for an automated seat. The lookup
// order is: per-seat override in SeatPolicies (set by the matchmaker from
// the host's PrivateTable seat config) → room-wide default BotPolicy (set
// by WithBotPolicy, e.g. server-side remote AI injection) → the heuristic
// baseline so the engine never stalls due to a config bug.
func (r *Room) policyForSeat(seat uint32) bot.Policy {
	if p, ok := r.SeatPolicies[seat]; ok && p != nil {
		return p
	}
	if r.BotPolicy != nil {
		return r.BotPolicy
	}
	return fallbackHeuristicPolicy
}

// buildDecisionContext snapshots the decision atomically. Called with the
// room lock held (the callers already are). The events slice is COPIED —
// policies may consume it after the lock is released.
func (r *Room) buildDecisionContext(seat uint32) *bot.DecisionContext {
	events := r.Engine.PublicEvents()
	snapshot := make([]engine.PublicEvent, len(events))
	copy(snapshot, events)
	r.policyDecisionIndex++
	return &bot.DecisionContext{
		State:         r.Engine.State,
		Seat:          seat,
		DecisionIndex: r.policyDecisionIndex,
		Events:        snapshot,
	}
}
