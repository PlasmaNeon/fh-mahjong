package api

import (
	"encoding/base64"
	"encoding/json"
	"fmt"
	"log"
	"math/rand"
	"os"
	"strings"
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

// defaultDisconnectGrace is how long a dropped seat is held before a bot takes
// over, giving a refresh or brief network blip time to reconnect without
// losing turns. Override per-room with WithDisconnectGrace (0 = immediate).
const defaultDisconnectGrace = 20 * time.Second

// Shutdown-persistence retry policy: transient DB hiccups (connection blips,
// lock contention) get a few quick attempts before the room gives up and
// leaves the match row in_progress.
const (
	persistAttempts     = 3
	persistRetryBackoff = 250 * time.Millisecond
)

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
	// SeatInfos records each seat's composition for the whole match (human
	// vs bot, bot difficulty, RL policy identity), captured by the matchmaker
	// at match start. It labels the paipu players so stored games are usable
	// as a labelled dataset. Seats absent from the map fall back to
	// SeatOwners/SeatPolicies-based classification (legacy paths and tests).
	SeatInfos map[uint32]SeatInfo
	Seats     map[uint32]*Client // maps 0-3 to active WS connections
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

	ActionQueue chan ClientAction
	Shutdown    chan bool
	// Done is closed once the shutdown case has finished persisting the
	// match, so a server drain can wait for persistence to complete.
	Done             chan struct{}
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

	// replayBytes accumulates every serialized broadcast for the whole match;
	// persisted on shutdown. Owned by the room goroutine (Start's loop).
	replayBytes []byte

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
		SeatInfos:          make(map[uint32]SeatInfo),
		Seats:              make(map[uint32]*Client),
		SeatOwners:         make(map[uint32]uint),
		ActionQueue:        make(chan ClientAction),
		Shutdown:           make(chan bool),
		Done:               make(chan struct{}),
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

// Start begins the event loop for the room. Every case body runs on this
// goroutine, which exclusively owns the engine, Seats, and the replay buffer.
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

	r.appendReplay(r.advanceAutomatedSeats())
	r.maybeScheduleBotTick()

	for {
		select {
		case <-r.Shutdown:
			log.Printf("Room %s shutting down", r.ID)
			// Persist BEFORE unregistering (OnShutdown): if SIGTERM lands
			// in between, DrainActiveRooms must still see this room so the
			// process can't exit mid-write. Transient DB failures get a few
			// retries; a persistent failure leaves the row in_progress (a
			// consistent state a backfill can find) and is logged loudly.
			var persistErr error
			for attempt := 1; attempt <= persistAttempts; attempt++ {
				if persistErr = r.persistMatch(); persistErr == nil {
					break
				}
				log.Printf("Room %s persist attempt %d/%d failed: %v", r.ID, attempt, persistAttempts, persistErr)
				if attempt < persistAttempts {
					time.Sleep(persistRetryBackoff)
				}
			}
			if persistErr != nil {
				log.Printf("Room %s GAVE UP persisting match after %d attempts; row remains in_progress", r.ID, persistAttempts)
			}
			if r.OnShutdown != nil {
				r.OnShutdown()
			}
			close(r.Done)
			return

		case <-r.TimerResolveChan:
			r.resolveInterruptsFromTimer()

		case client := <-r.DisconnectedClient:
			r.handleSeatDisconnect(client)

		case client := <-r.seatReleaseChan:
			r.releaseSeatAfterGrace(client)

		case client := <-r.ReconnectedClient:
			r.handleSeatReconnect(client)

		case <-r.botTick:
			r.stepBotTick()

		case clientAction := <-r.ActionQueue:
			r.dispatchClientAction(clientAction)
		}
	}
}

// appendReplay accumulates broadcast payloads into the room's replay buffer.
// Room-goroutine only.
func (r *Room) appendReplay(payloads [][]byte) {
	r.replayBytes = appendReplayPayloads(r.replayBytes, payloads)
}

// persistMatch finalizes the paipu and writes the replay + result to the DB
// (or the in-memory paipu store when the DB is absent). Called once, on
// shutdown. A room persisted before natural MATCH_END (server drain, abort)
// records status "aborted" but still keeps every completed round.
//
// The Match update and MatchPlayer insert run in one transaction, and a
// failure is returned (and logged by the caller): a failed write leaves the
// row in_progress with no seat rows, a consistent state a backfill can find,
// rather than a silently half-persisted match.
func (r *Room) persistMatch() error {
	// (For production, we might upload the replay to AWS S3 and save the URL.
	// Since we're keeping it simple, we store the raw bytes directly in the DB
	// as base64 text.)
	encodedReplay := base64.StdEncoding.EncodeToString(r.replayBytes)

	// Finalize paipu recording
	var paipuJSON string
	var paipu *engine.Paipu
	var finalScores [4]int32
	for i, p := range r.Engine.State.Players {
		finalScores[i] = p.Score
	}
	if r.Engine.Recorder != nil {
		r.reconcileRLPolicyIDs()
		// Snapshot (not Finalize) so an abort mid-hand keeps the active
		// hand's deals/actions as a result-less round. At natural MATCH_END
		// the current round is already closed and this equals Finalize.
		paipu = r.Engine.Recorder.Snapshot(finalScores)
		paipuBytes, err := json.Marshal(paipu)
		if err != nil {
			log.Printf("Failed to marshal paipu: %v", err)
		} else {
			paipuJSON = string(paipuBytes)
		}
	}

	status := "completed"
	if r.Engine.State.Phase != pb.GamePhase_PHASE_MATCH_END {
		status = "aborted"
	}

	now := time.Now()
	if r.DB != nil {
		err := r.DB.Transaction(func(tx *gorm.DB) error {
			if err := tx.Model(&storage.Match{}).Where("id = ?", r.ID).Updates(storage.Match{
				Status:    status,
				EndTime:   &now,
				ReplayURL: encodedReplay,
				WallSeed:  r.Engine.State.WallSeed,
				PaipuJSON: paipuJSON,
			}).Error; err != nil {
				return err
			}
			return persistMatchPlayers(tx, r.ID, paipu, finalScores)
		})
		if err != nil {
			return fmt.Errorf("persist match %s: %w", r.ID, err)
		}
	} else if paipuJSON != "" && r.PaipuStore != nil {
		r.PaipuStore(r.ID, paipuJSON)
		log.Printf("Stored paipu in-memory for room %s", r.ID)
	} else {
		log.Printf("Database disabled, skipping replay persistence for room %s", r.ID)
	}
	return nil
}

// policyIdentityReporter is implemented by remote policies that know which
// checkpoints actually served their /act responses (remote.HTTPPolicy).
type policyIdentityReporter interface {
	ObservedPolicyIDs() []string
}

// reconcileRLPolicyIDs replaces each RL seat's match-start policy label with
// the checkpoints that actually served its actions, comma-joined in serving
// order — so a policy hot reload mid-match stays attributable instead of
// silently mislabeling the dataset. Seats whose endpoint reports no
// checkpoint info keep the match-start label.
func (r *Room) reconcileRLPolicyIDs() {
	for seat, info := range r.SeatInfos {
		if info.Difficulty != pb.Difficulty_DIFFICULTY_RL {
			continue
		}
		reporter, ok := r.SeatPolicies[seat].(policyIdentityReporter)
		if !ok {
			continue
		}
		observed := reporter.ObservedPolicyIDs()
		if len(observed) == 0 {
			continue
		}
		r.Engine.Recorder.SetPlayerPolicyID(seat, strings.Join(observed, ","))
	}
}

// persistMatchPlayers mirrors the paipu's seat entries into relational
// MatchPlayer rows (seat, user, bot labels, final score, placement) so the
// dataset can be filtered in SQL without parsing PaipuJSON. Ties share the
// best placement (competition ranking). Runs inside persistMatch's
// transaction. No-op without a paipu.
func persistMatchPlayers(tx *gorm.DB, matchID string, paipu *engine.Paipu, finalScores [4]int32) error {
	if paipu == nil || len(paipu.Players) == 0 {
		return nil
	}
	rows := make([]storage.MatchPlayer, 0, len(paipu.Players))
	for _, p := range paipu.Players {
		if p.Seat >= uint32(len(finalScores)) {
			continue
		}
		score := finalScores[p.Seat]
		placement := uint(1)
		for _, other := range finalScores {
			if other > score {
				placement++
			}
		}
		// PolicyID is varchar(512); truncate rather than let an oversized
		// label fail the insert and roll back the whole match write.
		policyID := p.PolicyID
		if len(policyID) > 512 {
			policyID = policyID[:512]
		}
		rows = append(rows, storage.MatchPlayer{
			MatchID:    matchID,
			UserID:     p.UserID,
			Seat:       uint(p.Seat),
			FinalScore: score,
			Placement:  placement,
			IsBot:      p.Kind == "bot",
			Difficulty: p.Difficulty,
			PolicyID:   policyID,
		})
	}
	if len(rows) == 0 {
		return nil
	}
	return tx.Create(&rows).Error
}

// resolveInterruptsFromTimer handles the timer goroutine's signal that the
// interrupt window elapsed. All engine mutations happen here on the room
// goroutine, preventing races.
func (r *Room) resolveInterruptsFromTimer() {
	if r.Engine.State.Phase != pb.GamePhase_PHASE_WAIT_DISCARDS {
		return
	}
	r.Engine.ResolveInterrupts()
	r.replayBytes = append(r.replayBytes, r.BroadcastState()...)
	if r.Engine.State.Phase == pb.GamePhase_PHASE_ROUND_END {
		r.storePaipuSnapshot()
	}
	r.appendReplay(r.advanceAutomatedSeats())
	if r.Engine.State.Phase == pb.GamePhase_PHASE_ROUND_END {
		r.storePaipuSnapshot()
	}
	r.maybeScheduleBotTick()
	log.Printf("Resolved interrupts for room %s, next active player: %d", r.ID, r.Engine.State.ActivePlayer)
}

// handleSeatDisconnect holds a dropped seat for the grace window so a refresh
// or brief blip can reconnect without losing turns; after that a bot takes
// over. All matching is by pointer identity.
func (r *Room) handleSeatDisconnect(client *Client) {
	seat, found := r.seatForClient(client)
	if !found {
		// Never seated, or already superseded by a reconnect.
		safeClose(client.Send)
		return
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
}

// releaseSeatAfterGrace frees a seat whose grace window elapsed, but only if
// the same connection still holds it (a reconnect replaces the pointer).
func (r *Room) releaseSeatAfterGrace(client *Client) {
	seat, found := r.freeSeatForClient(client)
	safeClose(client.Send)
	if found {
		log.Printf("Seat %d grace window elapsed in room %s; bot taking over", seat, r.ID)
		r.maybeScheduleBotTick()
	}
}

// handleSeatReconnect rebinds a returning owner's seat (reclaiming it from a
// bot if needed), then replays the current board to just them.
func (r *Room) handleSeatReconnect(client *Client) {
	seat, owned := r.seatForOwner(client.UserID)
	if !owned {
		log.Printf("Reconnect from user %d but no owned seat in room %s", client.UserID, r.ID)
		safeClose(client.Send)
		return
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
}

// stepBotTick advances bot-only play one step, then re-arms if more remains.
// Yielding between steps keeps the loop responsive to reconnects.
func (r *Room) stepBotTick() {
	r.botTickPending = false
	r.appendReplay(r.advanceAutomatedSeatsN(1))
	if r.Engine.State.Phase == pb.GamePhase_PHASE_ROUND_END {
		r.storePaipuSnapshot()
	}
	r.maybeScheduleBotTick()
}

// dispatchClientAction authorizes a client's action, feeds it to the engine,
// broadcasts the result, and manages the interrupt-window timer.
func (r *Room) dispatchClientAction(clientAction ClientAction) {
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
		return
	}

	// 2. Feed action securely to the Core Game Engine
	err := r.Engine.ProcessPlayerAction(originSeat, clientAction.Action)
	if err != nil {
		// We don't crash, we just log and ignore illegal moves
		log.Printf("Illegal move by seat %d: %v", originSeat, err)
		return
	}

	// 3. The state has successfully mutated! Broadcast the new state to all 4
	// players and keep appending the payloads into the replay buffer.
	log.Printf("Seat %d executed %v", originSeat, clientAction.Action.Type)
	r.replayBytes = append(r.replayBytes, r.BroadcastState()...)
	if r.Engine.State.Phase == pb.GamePhase_PHASE_ROUND_END {
		r.storePaipuSnapshot()
	}
	r.appendReplay(r.advanceAutomatedSeats())
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
		r.armInterruptTimer()
	}
}

// armInterruptTimer (re)starts the interrupt-decision window and spawns the
// goroutine that signals the room loop when it expires or is cancelled early.
// The epoch counter prevents stale goroutines from resolving a newer cycle.
func (r *Room) armInterruptTimer() {
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

// SeatInfo describes who or what occupies a seat for the whole match. The
// matchmaker builds it from the private table's seat config (or the queue's
// user list) so the paipu can be labelled independently of which sockets
// happen to be connected when the room starts.
type SeatInfo struct {
	Kind       string // "human" | "bot"
	Name       string // human display name (bots are named by the room)
	UserID     uint   // humans only
	Difficulty pb.Difficulty
	PolicyID   string // RL seats: serving checkpoint identity
}

// difficultyLabel maps a proto difficulty to the stable string stored in the
// paipu. Unknown/unspecified difficulties record as "" (unknown).
func difficultyLabel(d pb.Difficulty) string {
	switch d {
	case pb.Difficulty_DIFFICULTY_HEURISTIC:
		return "heuristic"
	case pb.Difficulty_DIFFICULTY_RL:
		return "rl"
	default:
		return ""
	}
}

// botDisplayName renders the paipu display name for an automated seat, e.g.
// "Bot 2 (RL)". Difficulty-less bots stay plain "Bot 2".
func botDisplayName(seat uint32, d pb.Difficulty) string {
	name := fmt.Sprintf("Bot %d", seat+1)
	switch d {
	case pb.Difficulty_DIFFICULTY_HEURISTIC:
		return name + " (Heuristic)"
	case pb.Difficulty_DIFFICULTY_RL:
		return name + " (RL)"
	default:
		return name
	}
}

// registerPaipuPlayers records the four seat entries on the paipu. Seat
// composition comes from SeatInfos when the matchmaker provided it; otherwise
// classification falls back to SeatOwners (authoritative for the whole match
// — a reserved-but-not-yet-connected human is still a human), then the live
// socket map, then a bot placeholder.
func (r *Room) registerPaipuPlayers() {
	if r.Engine == nil || r.Engine.Recorder == nil {
		return
	}

	for seat := uint32(0); seat < 4; seat++ {
		if info, ok := r.SeatInfos[seat]; ok {
			r.Engine.Recorder.AddPlayerInfo(r.paipuPlayerForSeatInfo(seat, info))
			continue
		}
		if owner, owned := r.SeatOwners[seat]; owned {
			r.Engine.Recorder.AddPlayerInfo(r.humanPaipuPlayer(seat, "", owner))
			continue
		}
		if client, ok := r.Seats[seat]; ok && client != nil {
			r.Engine.Recorder.AddPlayerInfo(r.humanPaipuPlayer(seat, client.Username, client.UserID))
			continue
		}
		// No composition info at all: an automated seat of unknown difficulty.
		r.Engine.Recorder.AddPlayerInfo(engine.PaipuPlayer{
			Seat: seat,
			Name: botDisplayName(seat, pb.Difficulty_DIFFICULTY_UNSPECIFIED),
			Kind: "bot",
		})
	}
}

// paipuPlayerForSeatInfo converts a matchmaker SeatInfo into its paipu entry.
func (r *Room) paipuPlayerForSeatInfo(seat uint32, info SeatInfo) engine.PaipuPlayer {
	if info.Kind == "human" {
		return r.humanPaipuPlayer(seat, info.Name, info.UserID)
	}
	return engine.PaipuPlayer{
		Seat:       seat,
		Name:       botDisplayName(seat, info.Difficulty),
		Kind:       "bot",
		Difficulty: difficultyLabel(info.Difficulty),
		PolicyID:   info.PolicyID,
	}
}

// humanPaipuPlayer builds a human seat entry, preferring the live socket's
// username, then the provided fallback name, then a userID-derived
// placeholder (a reserved seat whose owner never connected).
func (r *Room) humanPaipuPlayer(seat uint32, name string, userID uint) engine.PaipuPlayer {
	if client, ok := r.Seats[seat]; ok && client != nil && client.Username != "" {
		name = client.Username
		if userID == 0 {
			userID = client.UserID
		}
	}
	if name == "" {
		name = fmt.Sprintf("Player %d", userID)
	}
	return engine.PaipuPlayer{Seat: seat, Name: name, UserID: userID, Kind: "human"}
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
