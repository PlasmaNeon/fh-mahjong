package api

import (
	"encoding/base64"
	"encoding/json"
	"fmt"
	"log"
	"math/rand"
	"os"
	"time"

	"github.com/plasma/fh-mahjong/bot"
	"github.com/plasma/fh-mahjong/core"
	"github.com/plasma/fh-mahjong/models"
	pb "github.com/plasma/fh-mahjong/proto"
	"github.com/plasma/fh-mahjong/rules"
	"github.com/plasma/fh-mahjong/rules/shanten"
	"google.golang.org/protobuf/proto"
	"gorm.io/gorm"
)

const maxAutomatedSeatIterations = 200

// Room represents a single active match, orchestrating 4 clients and 1 core engine
type Room struct {
	ID             string
	PrivateTableID string
	Hub            *Hub
	DB             *gorm.DB
	MatchRecord    *models.Match
	OnShutdown     func()

	Engine     *core.Game
	BotPolicy  bot.Policy
	Seats      map[uint32]*Client // maps 0-3 to active WS connections
	PaipuStore func(matchID, paipuJSON string) // in-memory fallback when DB is nil

	TileObfuscationMap map[uint32]uint32 // maps real tile IDs to fake IDs for redacting closed hands

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

	obfMap := make(map[uint32]uint32)
	fakeIDs := rand.Perm(144)
	for i := 0; i < 144; i++ {
		obfMap[uint32(i)] = uint32(fakeIDs[i]) + 1000
	}

	room := &Room{
		ID:                 matchID,
		Hub:                hub,
		DB:                 db,
		Engine:             core.NewGame(matchID, ruleset),
		BotPolicy:          bot.NewHeuristicPolicy(),
		Seats:              make(map[uint32]*Client),
		TileObfuscationMap: obfMap,
		ActionQueue:        make(chan ClientAction),
		Shutdown:           make(chan bool),
		InterruptChan:      make(chan bool, 1),
		TimerResolveChan:   make(chan bool, 1),
	}

	room.Engine.Recorder = core.NewPaipuRecorder(matchID, "hometown")

	return room
}

// Start begins the event loop for the room
func (r *Room) Start() {
	log.Printf("Match Room %s initialized", r.ID)

	r.registerPaipuPlayers()

	err := r.Engine.Start()
	if err != nil {
		log.Printf("Failed to start engine for room %s: %v", r.ID, err)
		return
	}

	// Initial State Broadcast
	r.BroadcastState()

	// 1. In-memory buffer to record the full serialized replay of the match
	var replayBytes []byte
	replayBytes = appendReplayPayloads(replayBytes, r.advanceAutomatedSeats())

	for {
		select {
		case <-r.Shutdown:
			log.Printf("Room %s shutting down", r.ID)
			if r.OnShutdown != nil {
				r.OnShutdown()
			}

			// 2. Persist replay to database
			// (For production, we might upload `replayBytes` to AWS S3 and save the URL.
			// Since we're keeping it simple, we'll store the raw bytes directly in the DB as text via base64)
			encodedReplay := base64.StdEncoding.EncodeToString(replayBytes)

			// Finalize paipu recording
			var paipuJSON string
			if r.Engine.Recorder != nil {
				var finalScores [4]int32
				for i, p := range r.Engine.State.Players {
					finalScores[i] = p.Score
				}
				paipu := r.Engine.Recorder.Finalize(finalScores)
				paipuBytes, err := json.Marshal(paipu)
				if err != nil {
					log.Printf("Failed to marshal paipu: %v", err)
				} else {
					paipuJSON = string(paipuBytes)
				}
			}

			now := time.Now()
			if r.DB != nil {
				r.DB.Model(&models.Match{}).Where("id = ?", r.ID).Updates(models.Match{
					Status:    "completed",
					EndTime:   &now,
					ReplayURL: encodedReplay,
					WallSeed:  r.Engine.State.WallSeed,
					PaipuJSON: paipuJSON,
				})
			} else if paipuJSON != "" && r.PaipuStore != nil {
				r.PaipuStore(r.ID, paipuJSON)
				log.Printf("Stored paipu in-memory for room %s", r.ID)
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
				replayBytes = appendReplayPayloads(replayBytes, r.advanceAutomatedSeats())
				if r.Engine.State.Phase == pb.GamePhase_PHASE_ROUND_END {
					r.storePaipuSnapshot()
				}
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
				replayBytes = appendReplayPayloads(replayBytes, r.advanceAutomatedSeats())

				if r.Engine.State.Phase == pb.GamePhase_PHASE_ROUND_END {
					r.storePaipuSnapshot()
				}

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
					if r.Engine.State.Phase == pb.GamePhase_PHASE_WAIT_DISCARDS {
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
					} else {
						log.Printf("Auto-resolved interrupts for room %s", r.ID)
					}
				}
			}
		}
	}
}

func (r *Room) advanceAutomatedSeats() [][]byte {
	var payloads [][]byte

	for iteration := 0; iteration < maxAutomatedSeatIterations; iteration++ {
		switch r.Engine.State.Phase {
		case pb.GamePhase_PHASE_PLAYER_TURN:
			seat := r.Engine.State.ActivePlayer
			if !r.isAutomatedSeat(seat) {
				return payloads
			}

			action := r.BotPolicy.ChooseAction(r.Engine.State, seat)
			if action == nil {
				log.Printf("bot policy produced no action for active seat %d in room %s", seat, r.ID)
				return payloads
			}

			if err := r.Engine.ProcessPlayerAction(seat, action); err != nil {
				log.Printf("bot action failed for seat %d in room %s: %v", seat, r.ID, err)
				return payloads
			}

			payloads = append(payloads, r.BroadcastState())

		case pb.GamePhase_PHASE_WAIT_DISCARDS:
			submitted := false

			for seatIndex, player := range r.Engine.State.Players {
				seat := uint32(seatIndex)
				if len(player.ValidActions) == 0 || !r.isAutomatedSeat(seat) {
					continue
				}

				action := r.BotPolicy.ChooseAction(r.Engine.State, seat)
				if action == nil {
					action = &pb.PlayerAction{Type: pb.ActionType_ACTION_PASS}
				}

				if err := r.Engine.ProcessPlayerAction(seat, action); err != nil {
					log.Printf("bot interrupt failed for seat %d in room %s: %v", seat, r.ID, err)
					if action.Type != pb.ActionType_ACTION_PASS {
						_ = r.Engine.ProcessPlayerAction(seat, &pb.PlayerAction{Type: pb.ActionType_ACTION_PASS})
					}
				}

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

	log.Printf(
		"stopped automated advancement for room %s after %d iterations at phase %v",
		r.ID,
		maxAutomatedSeatIterations,
		r.Engine.State.Phase,
	)
	return payloads
}

func (r *Room) isAutomatedSeat(seat uint32) bool {
	_, connected := r.Seats[seat]
	return !connected
}

func (r *Room) hasConnectedInterruptSeat() bool {
	for seat, player := range r.Engine.State.Players {
		if len(player.ValidActions) == 0 {
			continue
		}
		if !r.isAutomatedSeat(uint32(seat)) {
			return true
		}
	}
	return false
}

func (r *Room) isSeatReady(seatIndex int) bool {
	return seatIndex >= 0 && seatIndex < len(r.Engine.State.PlayerReady) && r.Engine.State.PlayerReady[seatIndex]
}

func (r *Room) storePaipuSnapshot() {
	if r.Engine.Recorder == nil || r.PaipuStore == nil {
		return
	}
	// Get the cumulative paipu with current scores
	var scores [4]int32
	for i, p := range r.Engine.State.Players {
		scores[i] = p.Score
	}
	cumulative := r.Engine.Recorder.Finalize(scores)
	if len(cumulative.Rounds) == 0 {
		return
	}

	// Extract only the latest round into a standalone paipu
	latestRound := cumulative.Rounds[len(cumulative.Rounds)-1]
	handNum := latestRound.Round
	paipuID := fmt.Sprintf("%s-%d", r.ID, handNum)

	single := core.Paipu{
		Version:     cumulative.Version,
		MatchID:     paipuID,
		Ruleset:     cumulative.Ruleset,
		Players:     cumulative.Players,
		Rounds:      []core.PaipuRound{latestRound},
		FinalScores: scores,
	}

	data, err := json.Marshal(single)
	if err != nil {
		log.Printf("Failed to marshal paipu for room %s hand %d: %v", r.ID, handNum, err)
		return
	}
	r.PaipuStore(paipuID, string(data))
	log.Printf("Saved paipu %s (hand %d)", paipuID, handNum)
}

func (r *Room) registerPaipuPlayers() {
	if r.Engine == nil || r.Engine.Recorder == nil {
		return
	}

	for seat := uint32(0); seat < 4; seat++ {
		if client, ok := r.Seats[seat]; ok && client != nil {
			r.Engine.Recorder.AddPlayer(seat, client.Username, client.UserID)
			continue
		}

		r.Engine.Recorder.AddPlayer(seat, fmt.Sprintf("Bot %d", seat+1), 0)
	}
}

func appendReplayPayloads(dst []byte, payloads [][]byte) []byte {
	for _, payload := range payloads {
		dst = append(dst, payload...)
	}
	return dst
}

// BroadcastState serializes the master GameState Protobuf and sends it to all connected players
func (r *Room) BroadcastState() []byte {
	masterState := r.Engine.State
	isProd := os.Getenv("ZEABUR") != ""

	// Compute shanten for each player
	for _, p := range masterState.Players {
		p.Shanten = int32(shanten.CalculateFromTiles(
			p.ClosedHand,
			len(p.OpenMelds),
			masterState.WildTiles,
		))
	}

	rawPayload, err := proto.Marshal(masterState)
	if err != nil {
		log.Printf("Failed to marshal GameState for room %s: %v", r.ID, err)
		return nil
	}

	for seatId, client := range r.Seats {
		var payload []byte

		if isProd {
			redactedState := proto.Clone(masterState).(*pb.GameState)
			for _, p := range redactedState.Players {
				if uint32(p.Seat) != seatId {
					for j, t := range p.ClosedHand {
						fakeID := r.TileObfuscationMap[t.Id]
						p.ClosedHand[j] = &pb.Tile{
							Id:    fakeID,
							Suit:  pb.Suit_SUIT_UNKNOWN,
							Value: 0,
						}
					}
					if p.DrawnTileId != nil {
						fakeID := int32(r.TileObfuscationMap[uint32(*p.DrawnTileId)])
						p.DrawnTileId = &fakeID
					}
					p.Shanten = 0
				}
			}
			payload, _ = proto.Marshal(redactedState)
		} else {
			payload = rawPayload
		}

		select {
		case client.Send <- payload:
		default:
			log.Printf("Failed to broadcast state to seat %d (offline or buffer full)", seatId)
		}
	}

	return rawPayload
}

// SendStateToClient sends the serialized GameState Protobuf strictly to one single connected player (used for reconnects)
func (r *Room) SendStateToClient(client *Client) {
	masterState := r.Engine.State
	isProd := os.Getenv("ZEABUR") != ""

	// Compute shanten for each player
	for _, p := range masterState.Players {
		p.Shanten = int32(shanten.CalculateFromTiles(
			p.ClosedHand,
			len(p.OpenMelds),
			masterState.WildTiles,
		))
	}

	var payload []byte
	var err error

	if isProd {
		redactedState := proto.Clone(masterState).(*pb.GameState)

		var clientSeat uint32
		var found bool
		for seat, c := range r.Seats {
			if c.UserID == client.UserID {
				clientSeat = seat
				found = true
				break
			}
		}

		if found {
			for _, p := range redactedState.Players {
				if uint32(p.Seat) != clientSeat {
					for j, t := range p.ClosedHand {
						fakeID := r.TileObfuscationMap[t.Id]
						p.ClosedHand[j] = &pb.Tile{
							Id:    fakeID,
							Suit:  pb.Suit_SUIT_UNKNOWN,
							Value: 0,
						}
					}
					if p.DrawnTileId != nil {
						fakeID := int32(r.TileObfuscationMap[uint32(*p.DrawnTileId)])
						p.DrawnTileId = &fakeID
					}
					p.Shanten = 0
				}
			}
		}
		payload, err = proto.Marshal(redactedState)
	} else {
		payload, err = proto.Marshal(masterState)
	}

	if err != nil {
		log.Printf("Failed to marshal GameState for room %s: %v", r.ID, err)
		return
	}

	select {
	case client.Send <- payload:
	default:
		log.Printf("Failed to send state directly to client %d (offline or buffer full)", client.UserID)
	}
}
