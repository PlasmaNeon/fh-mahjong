package api

import (
	"encoding/base64"
	"encoding/json"
	"fmt"
	"log"
	"math/rand"
	"os"
	"time"

	"github.com/plasma/fh-mahjong/internal/bot"
	"github.com/plasma/fh-mahjong/internal/engine"
	"github.com/plasma/fh-mahjong/internal/rules"
	"github.com/plasma/fh-mahjong/internal/rules/shanten"
	"github.com/plasma/fh-mahjong/internal/storage"
	pb "github.com/plasma/fh-mahjong/proto"
	"google.golang.org/protobuf/proto"
	"gorm.io/gorm"
)

// fallbackHeuristicPolicy is a stateless package-level instance used by
// policyForSeat when a configured policy is missing for an automated seat.
// HeuristicPolicy carries no state, so a single shared instance is safe.
var fallbackHeuristicPolicy bot.Policy = bot.NewHeuristicPolicy()

const maxAutomatedSeatIterations = 200

// defaultDisconnectGrace is how long a dropped seat is held before a bot takes
// over, giving a refresh or brief network blip time to reconnect without
// losing turns. Override per-room with WithDisconnectGrace (0 = immediate).
const defaultDisconnectGrace = 20 * time.Second

// Room represents a single active match, orchestrating 4 clients and 1 core engine
type Room struct {
	ID             string
	PrivateTableID string
	Hub            *Hub
	DB             *gorm.DB
	MatchRecord    *storage.Match
	OnShutdown     func()

	Engine *engine.Game
	// BotPolicy is the room-wide default automated-seat policy. Server-side
	// injection via WithBotPolicy() lets ops swap in a remote AI policy
	// without per-seat configuration. When unset, the package-level
	// heuristic baseline is used.
	BotPolicy bot.Policy
	// SeatPolicies maps a seat index (0-3) to a per-seat override that
	// supersedes BotPolicy for that seat. Populated by the matchmaker from
	// the host's PrivateTable seat config. Seats not present in this map
	// fall through to BotPolicy / the heuristic baseline (defensive only).
	SeatPolicies map[uint32]bot.Policy
	Seats        map[uint32]*Client // maps 0-3 to active WS connections
	// SeatOwners maps a seat (0-3) to the user ID that owns it for the whole
	// match. Unlike Seats it is never cleared on disconnect, so a player can
	// reclaim their seat after a bot took it over. Populated at BindRoom.
	SeatOwners      map[uint32]uint
	PaipuStore      func(matchID, paipuJSON string) // in-memory fallback when DB is nil
	lastStoredRound uint32

	// matchOptions seeds engine.NewGame with match-mode + Chongci config.
	// Populated by WithMatchOptions; defaults to MatchOptions{} (classic).
	matchOptions engine.MatchOptions

	// botActionDelay is how long the room waits before each bot move in
	// PHASE_PLAYER_TURN and PHASE_WAIT_DISCARDS so the game has a human
	// pace. Zero means no delay (used by tests). ACTION_READY between
	// hands is unaffected.
	botActionDelay time.Duration

	ActionQueue      chan ClientAction
	Shutdown         chan bool
	InterruptChan    chan bool
	TimerResolveChan chan bool // timer goroutine signals main loop to resolve interrupts
	interruptTmr     *time.Timer
	interruptEpoch   uint64 // incremented each interrupt cycle to prevent stale goroutines

	// Seat lifecycle is owned by the room goroutine (Start's select loop) so
	// Seats is only ever mutated from one place after the match begins. The hub
	// hands disconnects and reconnects over these channels instead of touching
	// Seats directly, which would race the room goroutine.
	DisconnectedClient chan *Client  // hub -> room: a seat's socket dropped
	ReconnectedClient  chan *Client  // hub -> room: an owner's socket returned
	seatReleaseChan    chan *Client  // grace timer -> room: free the seat now
	disconnectGrace    time.Duration // wait before a bot takes over a dropped seat

	// botTick drives bot-only play one step at a time so the room loop stays
	// responsive (e.g. to a reconnect) instead of running a whole bot-only
	// game synchronously. botTickPending guards against stacking timers and is
	// only touched on the room goroutine.
	botTick        chan struct{}
	botTickPending bool

	// matchEndScheduled tracks whether the grace-shutdown timer has been
	// armed for PHASE_MATCH_END. Idempotency guard so repeated broadcasts
	// of the terminal phase don't spawn multiple timer goroutines.
	matchEndScheduled bool
}

type RoomOption func(*Room)

func WithBotPolicy(policy bot.Policy) RoomOption {
	return func(room *Room) {
		if policy != nil {
			room.BotPolicy = policy
		}
	}
}

// WithDisconnectGrace sets how long a dropped seat is held before a bot takes
// it over. Zero means the bot takes over immediately (used by tests). When the
// option is omitted the room uses defaultDisconnectGrace.
func WithDisconnectGrace(d time.Duration) RoomOption {
	return func(r *Room) {
		if d >= 0 {
			r.disconnectGrace = d
		}
	}
}

// WithMatchOptions configures the engine constructed by NewRoom with a
// match-mode + Chongci config. Default is MatchOptions{} (classic).
func WithMatchOptions(opts engine.MatchOptions) RoomOption {
	return func(r *Room) {
		r.matchOptions = opts
	}
}

// WithBotActionDelay sets the per-action think-time pause for automated
// seats. Applied before discard, chii, pon, kan, ron, and tsumo. Zero
// (the default) disables the pause.
func WithBotActionDelay(d time.Duration) RoomOption {
	return func(r *Room) {
		if d > 0 {
			r.botActionDelay = d
		}
	}
}

// NewRoom creates a new match
func NewRoom(matchID string, hub *Hub, db *gorm.DB, opts ...RoomOption) *Room {
	ruleset := &rules.FenghuaRuleset{}

	room := &Room{
		ID:                 matchID,
		Hub:                hub,
		DB:                 db,
		SeatPolicies:       make(map[uint32]bot.Policy),
		Seats:              make(map[uint32]*Client),
		SeatOwners:         make(map[uint32]uint),
		ActionQueue:        make(chan ClientAction),
		Shutdown:           make(chan bool),
		InterruptChan:      make(chan bool, 1),
		TimerResolveChan:   make(chan bool, 1),
		DisconnectedClient: make(chan *Client, 4),
		ReconnectedClient:  make(chan *Client, 4),
		seatReleaseChan:    make(chan *Client, 4),
		disconnectGrace:    defaultDisconnectGrace,
		botTick:            make(chan struct{}, 1),
	}
	for _, opt := range opts {
		opt(room)
	}

	room.Engine = engine.NewGame(matchID, ruleset, room.matchOptions)
	room.Engine.Recorder = engine.NewPaipuRecorder(matchID, "fenghua")

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
	r.maybeScheduleBotTick()

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
				r.DB.Model(&storage.Match{}).Where("id = ?", r.ID).Updates(storage.Match{
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
				if r.Engine.State.Phase == pb.GamePhase_PHASE_ROUND_END {
					r.storePaipuSnapshot()
				}
				replayBytes = appendReplayPayloads(replayBytes, r.advanceAutomatedSeats())
				if r.Engine.State.Phase == pb.GamePhase_PHASE_ROUND_END {
					r.storePaipuSnapshot()
				}
				r.maybeScheduleBotTick()
				log.Printf("Resolved interrupts for room %s, next active player: %d", r.ID, r.Engine.State.ActivePlayer)
			}

		case client := <-r.DisconnectedClient:
			// A seat's socket dropped. Hold the seat for a grace window so a
			// refresh or brief blip can reconnect without losing turns; after
			// that a bot takes over. All matching is by pointer identity.
			seat, found := r.seatForClient(client)
			if !found {
				// Never seated, or already superseded by a reconnect.
				safeClose(client.Send)
				continue
			}
			if r.disconnectGrace <= 0 {
				r.freeSeatForClient(client)
				safeClose(client.Send)
				log.Printf("Seat %d disconnected in room %s; bot taking over", seat, r.ID)
				r.maybeScheduleBotTick()
			} else {
				log.Printf("Seat %d disconnected in room %s; bot takes over in %s unless they return", seat, r.ID, r.disconnectGrace)
				grace := r.disconnectGrace
				dropped := client
				go func() {
					time.Sleep(grace)
					select {
					case r.seatReleaseChan <- dropped:
					default:
					}
				}()
			}

		case client := <-r.seatReleaseChan:
			// Grace window elapsed. Free the seat only if this same connection
			// still holds it (a reconnect would have replaced the pointer).
			seat, found := r.freeSeatForClient(client)
			safeClose(client.Send)
			if found {
				log.Printf("Seat %d grace window elapsed in room %s; bot taking over", seat, r.ID)
				r.maybeScheduleBotTick()
			}

		case client := <-r.ReconnectedClient:
			// An owner's socket returned. Rebind their seat (reclaiming it from
			// a bot if needed), then replay the current board to just them.
			seat, owned := r.seatForOwner(client.UserID)
			if !owned {
				log.Printf("Reconnect from user %d but no owned seat in room %s", client.UserID, r.ID)
				safeClose(client.Send)
				continue
			}
			if old, exists := r.Seats[seat]; exists && old != client {
				safeClose(old.Send)
			}
			r.Seats[seat] = client
			seatMsg := []byte(fmt.Sprintf(`{"type":"seat_assignment","seat":%d}`, seat))
			select {
			case client.Send <- seatMsg:
			default:
			}
			r.SendStateToClient(client)
			log.Printf("User %d reconnected to seat %d in room %s", client.UserID, seat, r.ID)
			// If they returned while a bot is mid-turn, keep the bots moving up
			// to their seat instead of stalling until they happen to act.
			r.maybeScheduleBotTick()

		case <-r.botTick:
			// One step of bot-only play, then re-arm if more remains. Yielding
			// between steps keeps the loop responsive to reconnects.
			r.botTickPending = false
			replayBytes = appendReplayPayloads(replayBytes, r.advanceAutomatedSeatsN(1))
			if r.Engine.State.Phase == pb.GamePhase_PHASE_ROUND_END {
				r.storePaipuSnapshot()
			}
			r.maybeScheduleBotTick()

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
				if r.Engine.State.Phase == pb.GamePhase_PHASE_ROUND_END {
					r.storePaipuSnapshot()
				}
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

			action := r.policyForSeat(seat).ChooseAction(r.Engine.State, seat)
			if action == nil {
				log.Printf("bot policy produced no action for active seat %d in room %s", seat, r.ID)
				return payloads
			}

			r.sleepBotThink(action.Type)

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

				action := r.policyForSeat(seat).ChooseAction(r.Engine.State, seat)
				if action == nil {
					action = &pb.PlayerAction{Type: pb.ActionType_ACTION_PASS}
				}

				r.sleepBotThink(action.Type)

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

// seatForClient returns the seat currently held by the given client, matched by
// pointer identity. Called only from the room goroutine.
func (r *Room) seatForClient(client *Client) (uint32, bool) {
	for seat, c := range r.Seats {
		if c == client {
			return seat, true
		}
	}
	return 0, false
}

// freeSeatForClient removes the seat held by the given client so the seat
// becomes bot-controlled (isAutomatedSeat true). Matched by pointer identity so
// a client that already reconnected (a new *Client at the same seat) is never
// displaced by a stale release. Called only from the room goroutine.
func (r *Room) freeSeatForClient(client *Client) (uint32, bool) {
	seat, ok := r.seatForClient(client)
	if ok {
		delete(r.Seats, seat)
	}
	return seat, ok
}

// seatForOwner returns the seat owned by the given user ID for this match,
// independent of whether a socket is currently connected. Lets a returning
// player reclaim a seat a bot has been playing. Called only from the room
// goroutine.
func (r *Room) seatForOwner(userID uint) (uint32, bool) {
	for seat, uid := range r.SeatOwners {
		if uid == userID {
			return seat, true
		}
	}
	return 0, false
}

// safeClose closes a client send channel, tolerating a double close (e.g. a
// reconnect superseded a seat and a late grace-release also fires for the old
// connection). Sends on the closed channel are guarded by select/default at
// the call sites, and the channel is no longer referenced by any seat once
// closed here.
func safeClose(ch chan []byte) {
	defer func() { _ = recover() }()
	close(ch)
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

	// Avoid redundant snapshots for the same round
	if handNum <= r.lastStoredRound {
		return
	}

	paipuID := fmt.Sprintf("%s-%d", r.ID, handNum)

	single := engine.Paipu{
		Version:     cumulative.Version,
		MatchID:     paipuID,
		Ruleset:     cumulative.Ruleset,
		Players:     cumulative.Players,
		Rounds:      []engine.PaipuRound{latestRound},
		FinalScores: scores,
	}

	data, err := json.Marshal(single)
	if err != nil {
		log.Printf("Failed to marshal paipu for room %s hand %d: %v", r.ID, handNum, err)
		return
	}
	r.PaipuStore(paipuID, string(data))
	r.lastStoredRound = handNum
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

		name := fmt.Sprintf("Bot %d", seat+1)
		if _, configured := r.SeatPolicies[seat]; configured {
			name = fmt.Sprintf("Bot %d (Heuristic)", seat+1)
		}
		r.Engine.Recorder.AddPlayer(seat, name, 0)
	}
}

func appendReplayPayloads(dst []byte, payloads [][]byte) []byte {
	for _, payload := range payloads {
		dst = append(dst, payload...)
	}
	return dst
}

// invalidRecipientSeat is a seat value no real player ever holds (seats are
// 0-3). Passing it to redactedStateForSeat hides every player's concealed hand,
// the safe default for a viewer we can't map to a seat.
const invalidRecipientSeat = ^uint32(0)

// revealAllHandsEnv is the ONLY switch that disables client-state redaction.
// Redaction is fail-closed: on for every broadcast unless an operator explicitly
// opts into the all-hands debug god-view. Never set this in a deployed
// environment — it exposes every concealed hand, opponents' pending-call tiles,
// and the deal seed to all clients. `make dev`/docker-compose set it locally;
// Zeabur deploys via the Dockerfile, which never sets it.
const revealAllHandsEnv = "MAHJONG_DEV_REVEAL_HANDS"

// revealAllHands reports whether the local debug god-view is explicitly enabled.
// Anything other than the exact opt-in keeps redaction on, so a missing or
// misconfigured env var fails safe (redacted) rather than open.
func revealAllHands() bool {
	return os.Getenv(revealAllHandsEnv) == "1"
}

// newTileObfuscation returns a fresh random real-tile-id -> fake-id mapping for
// a single broadcast. Fake IDs are offset by 1000 so they never collide with a
// real tile id (0-143); that keeps a revealed discard (real id) from matching
// any in-hand fake id.
//
// A NEW permutation is generated on every broadcast, on purpose. A map fixed for
// the whole hand let an inspecting opponent client (1) track a concealed tile
// across turns by its stable fake id, and (2) de-anonymize the map by
// correlating each revealed discard with the fake id that left an opponent's
// hand. Re-randomizing per broadcast removes any stable handle to track or
// correlate. Opponent hands render as anonymous backs keyed by hand slot, so the
// frontend tolerates the volatile id (see web/src/table/seat/ClosedHand.tsx).
func newTileObfuscation() map[uint32]uint32 {
	obf := make(map[uint32]uint32, 144)
	fakeIDs := rand.Perm(144)
	for realID := 0; realID < 144; realID++ {
		obf[uint32(realID)] = uint32(fakeIDs[realID]) + 1000
	}
	return obf
}

// handsRevealed reports whether every player's closed hand should be shown to
// everyone. Once a round (or the whole match) has ended, opponents' hands are
// revealed so players can see the result; during play they stay obfuscated.
func handsRevealed(phase pb.GamePhase) bool {
	return phase == pb.GamePhase_PHASE_ROUND_END || phase == pb.GamePhase_PHASE_MATCH_END
}

// redactedStateForSeat returns a deep clone of master that hides what the seat
// at viewerSeat must not see (production anti-cheat). It generates a fresh
// obfuscation map per call, so calling it once per recipient per broadcast means
// no fake id persists across broadcasts — defeating cross-turn tracking of a
// concealed tile and de-anonymizing the map from revealed discards.
//
// For every seat other than viewerSeat: valid_actions is dropped (its meld tiles
// would expose the concealed tiles backing a pon/chii/kan), and when concealHands
// is true (during play) the closed hand + drawn tile are obfuscated
// (SUIT_UNKNOWN/value 0 + a fake id) and shanten cleared. At round/match end the
// caller passes concealHands=false to reveal hands. Discards keep their REAL ids
// and faces (public the moment made); per-broadcast rotation means a real discard
// id can't be correlated to any concealed fake id, so the client animates an
// opponent discard from a random hand slot (tedashi) or the drawn slot
// (tsumogiri) via the public last_discard_from_drawn flag, not the real tile.
//
// The top-level wall_seed is cleared for everyone: it deterministically
// reconstructs the entire deal and would defeat redaction outright. The master is
// never mutated, so the caller can reuse it across recipients and the replay log.
func redactedStateForSeat(master *pb.GameState, viewerSeat uint32, concealHands bool) *pb.GameState {
	obf := newTileObfuscation()
	redacted := proto.Clone(master).(*pb.GameState)
	redacted.WallSeed = ""
	for _, p := range redacted.Players {
		if uint32(p.Seat) == viewerSeat {
			continue
		}
		// Only the recipient needs its own valid_actions (to render buttons);
		// another seat's call options embed its real concealed tiles.
		p.ValidActions = nil
		if !concealHands {
			continue
		}
		for j, t := range p.ClosedHand {
			p.ClosedHand[j] = &pb.Tile{
				Id:    obf[t.Id],
				Suit:  pb.Suit_SUIT_UNKNOWN,
				Value: 0,
			}
		}
		if p.DrawnTileId != nil {
			fakeID := int32(obf[uint32(*p.DrawnTileId)])
			p.DrawnTileId = &fakeID
		}
		p.Shanten = 0
	}
	return redacted
}

// BroadcastState serializes the master GameState Protobuf and sends it to all connected players
func (r *Room) BroadcastState() []byte {
	masterState := r.Engine.State
	// Fail closed: redact unless the debug god-view is explicitly opted into.
	redactHands := !revealAllHands()

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

	// Reveal all hands once the round/match has ended so players see the result;
	// during play opponents' hands stay obfuscated. A fresh obfuscation map is
	// generated per recipient inside redactedStateForSeat (per-broadcast rotation).
	revealAll := handsRevealed(masterState.Phase)

	for seatId, client := range r.Seats {
		var payload []byte

		if redactHands {
			payload, _ = proto.Marshal(redactedStateForSeat(masterState, seatId, !revealAll))
		} else {
			payload = rawPayload
		}

		select {
		case client.Send <- payload:
		default:
			log.Printf("Failed to broadcast state to seat %d (offline or buffer full)", seatId)
		}
	}

	r.checkMatchEndShutdown()

	return rawPayload
}

// checkMatchEndShutdown arms a 30-second timer the first time the engine
// reports PHASE_MATCH_END. When the timer fires, it sends on the Shutdown
// channel so the main loop runs its usual teardown (paipu persistence,
// hub deregister, etc.). Players see the final state during the grace
// window so client overlays render before any reconnect attempt 404s.
//
// The send is non-blocking: if no one is reading from Shutdown (e.g.
// synchronous tests that never started Room.Start), the timer signal is
// silently dropped. Production rooms always have a Shutdown receiver.
func (r *Room) checkMatchEndShutdown() {
	if r.matchEndScheduled {
		return
	}
	if r.Engine.State.Phase != pb.GamePhase_PHASE_MATCH_END {
		return
	}
	r.matchEndScheduled = true
	go func() {
		time.Sleep(30 * time.Second)
		select {
		case r.Shutdown <- true:
		default:
		}
	}()
}

// MatchEndScheduledForTest exposes the matchEndScheduled flag to tests.
func (r *Room) MatchEndScheduledForTest() bool { return r.matchEndScheduled }

// CheckMatchEndShutdownForTest exposes checkMatchEndShutdown to tests.
func (r *Room) CheckMatchEndShutdownForTest() { r.checkMatchEndShutdown() }

// SendStateToClient sends the serialized GameState Protobuf strictly to one single connected player (used for reconnects)
func (r *Room) SendStateToClient(client *Client) {
	masterState := r.Engine.State
	// Fail closed: redact unless the debug god-view is explicitly opted into.
	redactHands := !revealAllHands()

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

	if redactHands {
		// Default to a seat no player holds so an unmappable viewer (e.g. a
		// spectator) sees every hand hidden rather than the full state.
		clientSeat := invalidRecipientSeat
		for seat, c := range r.Seats {
			if c.UserID == client.UserID {
				clientSeat = seat
				break
			}
		}

		// Reveal hands at round/match end; obfuscation is freshly rotated per call.
		payload, err = proto.Marshal(redactedStateForSeat(masterState, clientSeat, !handsRevealed(masterState.Phase)))
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
