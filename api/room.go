package api

import (
	"encoding/base64"
	"log"
	"time"

	"github.com/plasma/fh-mahjong/core"
	"github.com/plasma/fh-mahjong/models"
	pb "github.com/plasma/fh-mahjong/proto"
	"github.com/plasma/fh-mahjong/rules"
	"google.golang.org/protobuf/proto"
	"gorm.io/gorm"
)

// Room represents a single active match, orchestrating 4 clients and 1 core engine
type Room struct {
	ID          string
	Hub         *Hub
	DB          *gorm.DB
	MatchRecord *models.Match

	Engine *core.Game
	Seats  map[uint32]*Client // maps 0-3 to active WS connections

	ActionQueue      chan ClientAction
	Shutdown         chan bool
	InterruptChan    chan bool
	TimerResolveChan chan bool // timer goroutine signals main loop to resolve interrupts
	interruptTmr     *time.Timer
	interruptEpoch   uint64 // incremented each interrupt cycle to prevent stale goroutines
}

// NewRoom creates a new match
func NewRoom(matchID string, hub *Hub, db *gorm.DB) *Room {
	ruleset := &rules.HometownRuleset{}

	room := &Room{
		ID:            matchID,
		Hub:           hub,
		DB:            db,
		Engine:        core.NewGame(matchID, ruleset),
		Seats:         make(map[uint32]*Client),
		ActionQueue:      make(chan ClientAction),
		Shutdown:         make(chan bool),
		InterruptChan:    make(chan bool, 1),
		TimerResolveChan: make(chan bool, 1),
	}

	return room
}

// Start begins the event loop for the room
func (r *Room) Start() {
	log.Printf("Match Room %s initialized", r.ID)

	err := r.Engine.Start()
	if err != nil {
		log.Printf("Failed to start engine for room %s: %v", r.ID, err)
		return
	}

	// Initial State Broadcast
	r.BroadcastState()

	// 1. In-memory buffer to record the full serialized replay of the match
	var replayBytes []byte

	for {
		select {
		case <-r.Shutdown:
			log.Printf("Room %s shutting down", r.ID)

			// 2. Persist replay to database
			// (For production, we might upload `replayBytes` to AWS S3 and save the URL.
			// Since we're keeping it simple, we'll store the raw bytes directly in the DB as text via base64)
			encodedReplay := base64.StdEncoding.EncodeToString(replayBytes)

			now := time.Now()
			if r.DB != nil {
				r.DB.Model(&models.Match{}).Where("id = ?", r.ID).Updates(models.Match{
					Status:    "completed",
					EndTime:   &now,
					ReplayURL: encodedReplay,
					WallSeed:  r.Engine.State.WallSeed,
				})
			} else {
				log.Printf("Database disabled, skipping replay persistence for room %s", r.ID)
			}
			return

		case <-r.TimerResolveChan:
			// Timer goroutine signaled that we should resolve interrupts.
			// All engine mutations happen here on the main goroutine, preventing races.
			if r.Engine.State.Phase == pb.GamePhase_PHASE_WAIT_DISCARDS {
				r.Engine.ResolveInterrupts()
				resolvePayload := r.BroadcastState()
				replayBytes = append(replayBytes, resolvePayload...)
				log.Printf("Resolved interrupts for room %s, next active player: %d", r.ID, r.Engine.State.ActivePlayer)
			}

		case clientAction := <-r.ActionQueue:
			// 1. Identify which seat this client belongs to
			var originSeat uint32
			found := false
			for seat, client := range r.Seats {
				if client.UserID == clientAction.Client.UserID {
					originSeat = seat
					found = true
					break
				}
			}

			if !found {
				log.Printf("Unauthorized action by user %d in room %s", clientAction.Client.UserID, r.ID)
				continue
			}

			// 2. Feed action securely to the Core Game Engine
			err := r.Engine.ProcessPlayerAction(originSeat, clientAction.Action)

			if err != nil {
				// We don't crash, we just log and ignore illegal moves
				log.Printf("Illegal move by seat %d: %v", originSeat, err)
			} else {
				// 3. The state has successfully mutated! Broadcast the new state to all 4 players
				log.Printf("Seat %d executed %v", originSeat, clientAction.Action.Type)

				// 3. Serialize the StateDelta
				statePayload := r.BroadcastState()

				// Keep appending the state into the giant binary blob
				replayBytes = append(replayBytes, statePayload...)

				// 4. Handle Phase Transitions
				currentPhase := r.Engine.State.Phase

				// Did we just resolve the wait phase early?
				if clientAction.Action.Type != pb.ActionType_ACTION_DISCARD && currentPhase != pb.GamePhase_PHASE_WAIT_DISCARDS {
					select {
					case r.InterruptChan <- true: // signal early cancel
					default:
					}
				}

				// If we just entered wait phase, start the timer
				if currentPhase == pb.GamePhase_PHASE_WAIT_DISCARDS && clientAction.Action.Type == pb.ActionType_ACTION_DISCARD {
					// Auto-PASS for any seat that has valid actions but no connected client (bot/absent player)
					for seat, p := range r.Engine.State.Players {
						if len(p.ValidActions) > 0 {
							if _, connected := r.Seats[uint32(seat)]; !connected {
								r.Engine.ProcessPlayerAction(uint32(seat), &pb.PlayerAction{Type: pb.ActionType_ACTION_PASS})
							}
						}
					}

					// If auto-pass resolved everything, no need for a timer
					if r.Engine.State.Phase != pb.GamePhase_PHASE_WAIT_DISCARDS {
						statePayload = r.BroadcastState()
						replayBytes = append(replayBytes, statePayload...)
						log.Printf("Auto-resolved interrupts (all bots) for room %s", r.ID)
					} else {
						if r.interruptTmr != nil {
							r.interruptTmr.Stop()
						}
						// Drain any stale signal from previous cycle
						select {
						case <-r.InterruptChan:
						default:
						}

						r.interruptEpoch++
						epoch := r.interruptEpoch

						// 5 seconds to decide if they want to Pong/Chi/Ron
						r.interruptTmr = time.NewTimer(1 * time.Hour) // Temporarily disabled for UI testing

						go func(timer *time.Timer, myEpoch uint64) {
							select {
							case <-timer.C:
								// Time expired, auto-resolve
							case <-r.InterruptChan:
								// Someone claimed it early or everyone skipped!
								if !timer.Stop() {
									select {
									case <-timer.C:
									default:
									}
								}
							}

							// Only signal the main loop if this goroutine's epoch is still current.
							// Prevents stale goroutines from resolving a newer interrupt cycle.
							if myEpoch == r.interruptEpoch {
								select {
								case r.TimerResolveChan <- true:
								default:
								}
							}
						}(r.interruptTmr, epoch)
					}
				}
			}
		}
	}
}

// BroadcastState serializes the master GameState Protobuf and sends it to all connected players
func (r *Room) BroadcastState() []byte { // Modified function signature
	// In a real production system, you would send a `StateDelta` or filter the `GameState`
	// so that you aren't sending Player 2's ClosedHand to Player 1.
	// For now, we serialize the entire raw state.

	masterState := r.Engine.State

	payload, err := proto.Marshal(masterState)
	if err != nil {
		log.Printf("Failed to marshal GameState for room %s: %v", r.ID, err)
		return nil // Modified return
	}

	for seatId, client := range r.Seats {
		select {
		case client.Send <- payload:
			// successfully written to channel
		default:
			log.Printf("Failed to broadcast state to seat %d (offline or buffer full)", seatId)
			// don't remove them from seats here, just gracefully ignore so they can reconnect later
		}
	}

	return payload // Added return
}

// SendStateToClient sends the serialized GameState Protobuf strictly to one single connected player (used for reconnects)
func (r *Room) SendStateToClient(client *Client) {
	masterState := r.Engine.State

	payload, err := proto.Marshal(masterState)
	if err != nil {
		log.Printf("Failed to marshal GameState for room %s: %v", r.ID, err)
		return
	}

	select {
	case client.Send <- payload:
		// success
	default:
		log.Printf("Failed to send state directly to client %d (offline or buffer full)", client.UserID)
	}
}
