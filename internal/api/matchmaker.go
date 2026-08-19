package api

import (
	"context"
	"errors"
	"fmt"
	"log"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/google/uuid"
	"github.com/plasma/fh-mahjong/internal/bot"
	"github.com/plasma/fh-mahjong/internal/engine"
	"github.com/plasma/fh-mahjong/internal/storage"
	pb "github.com/plasma/fh-mahjong/proto"
	"gorm.io/gorm"
)

var ctx = context.Background()

// defaultBotActionDelay paces automated seats during PHASE_PLAYER_TURN and
// PHASE_WAIT_DISCARDS so the game has a human rhythm (discard, chii, pon,
// kan, ron, tsumo). Applied by the matchmaker when constructing rooms for
// real matches; tests construct Room directly and inherit zero delay.
const defaultBotActionDelay = 800 * time.Millisecond

// Private-table lifecycle sentinels. Used by handlers (via errors.Is) to map
// internal errors to HTTP status codes without string-matching.
var (
	ErrPrivateTableNotFound       = errors.New("table not found")
	ErrPrivateTableExists         = errors.New("table already exists")
	ErrPrivateTableFull           = errors.New("table is full")
	ErrPrivateTableAlreadyStarted = errors.New("table already started")
	ErrPrivateTableHostOnly       = errors.New("only the host can start the match")
	ErrPrivateTablePersistFailed  = errors.New("persist match failed")
	ErrServerDraining             = errors.New("server is shutting down")
	ErrRLWarmupFailed             = errors.New("RL agent is not ready")
	// ErrPrivateTableChangedDuringStart is returned when the table was
	// reconfigured while StartPrivateTable had released table.mu to warm the
	// policy endpoints. Retryable: the host simply starts again, against the
	// new configuration.
	ErrPrivateTableChangedDuringStart = errors.New("table configuration changed during start; try again")
)

// rlWarmupBudget bounds how long StartPrivateTable will block waiting for the
// RL policy endpoints to warm. It covers BOTH endpoints (primary + shadow) and,
// after the first RL room, only elapses again once the warmup TTL has expired —
// warmup is endpoint-scoped (see internal/bot/remote/warmup.go).
const rlWarmupBudget = 25 * time.Second

type Matchmaker struct {
	Queue *InMemoryQueue
	DB    *gorm.DB
	Hub   *Hub

	BotPolicyFactory func() bot.Policy
	PaipuStore       func(matchID, paipuJSON string) // in-memory fallback when DB is nil

	// SeatPolicyResolver builds the bot.Policy for a private-room seat of the
	// given difficulty. When nil, resolveSeatPolicy falls back to
	// bot.NewPolicy (heuristic-only). cmd/server installs a resolver that maps
	// DIFFICULTY_RL to the remote HTTP policy. roomID and seat identify the
	// private table and seat index this resolution is for — cmd/server uses
	// them (adversarial round 3, Finding 2) to label any bot.ShadowPolicy it
	// wraps the primary in, so concurrent rooms/seats are distinguishable in
	// shared server logs; callers that don't need this may ignore both.
	SeatPolicyResolver func(d pb.Difficulty, roomID string, seat uint32) (bot.Policy, error)

	// RLAgentAvailable reports whether the trained RL agent can currently be
	// offered as a seat option. cmd/server wires this to a health-checked
	// probe of the policy endpoint, so the option only appears when a model
	// server is actually reachable. Nil means unavailable.
	RLAgentAvailable func() bool

	// RLPolicyIdentity reports the identity of the policy currently served at
	// the RL endpoint (e.g. "<checkpoint>@step<N>" from its /healthz payload,
	// falling back to the endpoint URL). Captured per RL seat at match start
	// and recorded in the paipu so the dataset knows which model played. Nil
	// or empty means unknown.
	RLPolicyIdentity func() string

	// WarmRLEndpoints, when set, must leave every configured policy endpoint
	// (primary and, when configured, shadow) warm — i.e. each has taken a real
	// forward pass — before an RL private room is admitted. cmd/server wires it
	// to a remote.WarmupManager, so it is warm-once per process and a no-op on
	// every table after the first. A non-nil error FAILS the table start: a
	// room the host explicitly asked to be played by the RL agent must never
	// silently degrade to the heuristic because the model server was still
	// cold. Failures are retryable — the next start attempt warms again.
	WarmRLEndpoints func(ctx context.Context) error

	privateTablesMu     sync.RWMutex
	activePrivateTables map[string]ActivePrivateTable

	// activeRooms tracks every live match room (queue and private) keyed by
	// matchID so a server drain can persist them before the process exits.
	activeRoomsMu sync.Mutex
	activeRooms   map[string]*Room

	// draining is set by DrainActiveRooms: once the server is shutting down,
	// no new match may start (it would miss the drain snapshot and be
	// orphaned when the process exits).
	draining atomic.Bool

	configuringMu     sync.Mutex
	configuringTables map[string]*PrivateTable
}

type ActivePrivateTable struct {
	TableID        string
	MatchID        string
	ParticipantIDs map[uint]bool
	Room           *Room
}

func NewMatchmaker(queue *InMemoryQueue, db *gorm.DB, hub *Hub) *Matchmaker {
	return &Matchmaker{
		Queue:               queue,
		DB:                  db,
		Hub:                 hub,
		activePrivateTables: make(map[string]ActivePrivateTable),
		activeRooms:         make(map[string]*Room),
		configuringTables:   make(map[string]*PrivateTable),
	}
}

// registerActiveRoom tracks a live room for server-drain persistence.
// Registration is atomic with the draining flag (same mutex): either the room
// is visible to the drain's first snapshot, or the caller is told the server
// is draining and must abort the start. Returns false when draining.
func (m *Matchmaker) registerActiveRoom(room *Room) bool {
	m.activeRoomsMu.Lock()
	defer m.activeRoomsMu.Unlock()
	if m.draining.Load() {
		return false
	}
	m.activeRooms[room.ID] = room
	return true
}

// unregisterActiveRoom drops a room from the drain registry (normal shutdown).
func (m *Matchmaker) unregisterActiveRoom(matchID string) {
	m.activeRoomsMu.Lock()
	defer m.activeRoomsMu.Unlock()
	delete(m.activeRooms, matchID)
}

// DrainActiveRooms stops new matches from starting, then asks every live room
// to shut down and waits (up to timeout) for each to finish persisting.
// Called on SIGINT/SIGTERM so a redeploy marks in-flight matches "aborted"
// with their partial paipu instead of orphaning in_progress rows with empty
// PaipuJSON. It re-snapshots until the registry is empty so a room that
// started just before the draining flag flipped is still covered. Rooms whose
// loop never started (or that are wedged) are skipped once the timeout
// elapses.
func (m *Matchmaker) DrainActiveRooms(timeout time.Duration) {
	// Set the flag under the registry mutex so it serializes with
	// registerActiveRoom: every successful registration is visible to the
	// first snapshot below, and everything later is refused.
	m.activeRoomsMu.Lock()
	m.draining.Store(true)
	m.activeRoomsMu.Unlock()

	// A closed channel (unlike time.After's one-shot send) releases every
	// waiting goroutine at the deadline.
	deadline := make(chan struct{})
	timer := time.AfterFunc(timeout, func() { close(deadline) })
	defer timer.Stop()

	for {
		m.activeRoomsMu.Lock()
		rooms := make([]*Room, 0, len(m.activeRooms))
		for _, room := range m.activeRooms {
			rooms = append(rooms, room)
		}
		m.activeRoomsMu.Unlock()

		if len(rooms) == 0 {
			return
		}
		select {
		case <-deadline:
			log.Printf("Drain deadline reached with %d room(s) still registered", len(rooms))
			return
		default:
		}
		log.Printf("Draining %d active room(s) before shutdown...", len(rooms))

		var wg sync.WaitGroup
		for _, room := range rooms {
			wg.Add(1)
			go func(r *Room) {
				defer wg.Done()
				r.markDrained()
				select {
				case r.Shutdown <- true:
				case <-r.Done: // already shutting down on its own
				case <-deadline:
					log.Printf("Drain timed out signalling room %s", r.ID)
					return
				}
				select {
				case <-r.Done:
				case <-deadline:
					log.Printf("Drain timed out waiting for room %s to persist", r.ID)
				}
			}(room)
		}
		wg.Wait()

		// Rooms that hit the deadline (wedged/never-started) stay registered;
		// exit rather than spinning on them forever.
		select {
		case <-deadline:
			return
		default:
		}
	}
}

// resolveSeatPolicy builds the bot.Policy for a private-room seat of the given
// difficulty. It uses the injected SeatPolicyResolver when present (so a
// DIFFICULTY_RL seat can route to the trained endpoint) and otherwise the
// heuristic-only bot.NewPolicy. It is the single point used by both seat
// validation and the match-start loop, so an unsupported difficulty (e.g.
// DIFFICULTY_RL when no resolver is installed) is rejected consistently.
func (m *Matchmaker) resolveSeatPolicy(d pb.Difficulty, roomID string, seat uint32) (bot.Policy, error) {
	if m.SeatPolicyResolver != nil {
		return m.SeatPolicyResolver(d, roomID, seat)
	}
	return bot.NewPolicy(d)
}

// ValidateSeatDifficulty reports whether d is an assignable bot-seat
// difficulty, WITHOUT constructing a policy for it. This is the validate-only
// counterpart to resolveSeatPolicy, used by handlePrivateTableSeat when a
// host merely picks a difficulty for a seat (no match has started, no Room
// exists yet to ever own or close a constructed policy).
//
// It deliberately never calls SeatPolicyResolver: cmd/server's resolver is
// where a real DIFFICULTY_RL seat gets wrapped in a bot.NewShadowPolicy when
// shadow mode is configured, and constructing a ShadowPolicy starts its
// background worker goroutine immediately. Calling the resolver purely to
// validate and discarding the result (adversarial round 4, Finding 1) leaked
// one goroutine+queue per seat-assignment request — an authenticated host
// repeating the request could exhaust the server. Validation instead mirrors
// resolveSeatPolicy's rejection rules using only side-effect-free checks:
// DIFFICULTY_RL is acceptable iff the RL agent is currently available (the
// same knowledge cmd/server's resolver closure would otherwise need to
// consult before constructing anything), and every other difficulty is
// acceptable iff bot.NewPolicy recognizes it (NewPolicy itself has no side
// effects — it either errors or returns a plain, non-closeable
// HeuristicPolicy). StartPrivateTable still calls resolveSeatPolicy to build
// the real per-seat policy at match start, once a Room exists to own it.
func (m *Matchmaker) ValidateSeatDifficulty(d pb.Difficulty) error {
	if d == pb.Difficulty_DIFFICULTY_RL {
		if !m.rlAgentAvailable() {
			return errRLAgentUnavailable
		}
		return nil
	}
	_, err := bot.NewPolicy(d)
	return err
}

// rlAgentAvailable reports whether the trained RL agent can currently be
// offered. It is nil-safe (both for the receiver and the probe) and consults
// the health-checked RLAgentAvailable function installed by cmd/server.
func (m *Matchmaker) rlAgentAvailable() bool {
	return m != nil && m.RLAgentAvailable != nil && m.RLAgentAvailable()
}

// tableHasRLSeat reports whether any seat of the table is a DIFFICULTY_RL bot.
// Caller must hold table.mu.
func tableHasRLSeat(table *PrivateTable) bool {
	if table == nil {
		return false
	}
	for _, s := range table.Seats {
		if s.Kind == "bot" && s.Difficulty == pb.Difficulty_DIFFICULTY_RL {
			return true
		}
	}
	return false
}

// seatSignature renders the seat configuration as a comparable string, used to
// detect a table being reconfigured while StartPrivateTable had released
// table.mu for the warmup. Caller must hold table.mu.
func seatSignature(table *PrivateTable) string {
	if table == nil {
		return ""
	}
	var b strings.Builder
	for _, s := range table.Seats {
		fmt.Fprintf(&b, "%s/%d/%d|", s.Kind, s.UserID, int32(s.Difficulty))
	}
	return b.String()
}

// validateStartLocked runs the cheap, purely-in-memory start validation:
// the table is still configuring, the requester is the host, and all four
// seats are filled. Caller must hold table.mu. Run BEFORE the warmup (to
// avoid warming for a start that would be refused anyway) and again AFTER it
// (the lock is released while warming, so any of these can have changed).
func validateStartLocked(table *PrivateTable, requesterUserID uint) error {
	if table.State != "configuring" {
		return ErrPrivateTableAlreadyStarted
	}
	if requesterUserID != table.HostUserID {
		return ErrPrivateTableHostOnly
	}
	return table.canStart()
}

// warmRLEndpoints blocks (up to rlWarmupBudget) until every configured policy
// endpoint is warm. It must be called WITHOUT holding table.mu: a cold warm
// costs seconds, and holding the table lock across it would stall every
// join/seat/state handler for that table (and serialize N impatient Start
// clicks into N sequential waits). tableID is for telemetry only.
//
// A warmup error is wrapped in ErrRLWarmupFailed so the handler can map it to
// a 503 instead of starting a room whose "RL" seats would fall back to the
// heuristic. The wrapped detail (which can name the internal policy endpoint)
// is for logs — the HTTP layer sanitizes it, see handlePrivateTableStart.
func (m *Matchmaker) warmRLEndpoints(tableID string) error {
	if m == nil || m.WarmRLEndpoints == nil {
		return nil
	}
	warmCtx, cancel := context.WithTimeout(context.Background(), rlWarmupBudget)
	defer cancel()
	if err := m.WarmRLEndpoints(warmCtx); err != nil {
		log.Printf("policy warmup: refusing RL table %s start: %v", tableID, err)
		return fmt.Errorf("%w: %w", ErrRLWarmupFailed, err)
	}
	return nil
}

// prepareStartUnderLock does the cheap start validation under table.mu and
// reports whether the table needs an RL warmup, along with the seat signature
// observed while the lock was held. The caller warms with the lock RELEASED
// and then re-validates against this signature.
func (m *Matchmaker) prepareStartUnderLock(table *PrivateTable, requesterUserID uint) (needWarm bool, signature string, err error) {
	table.mu.Lock()
	defer table.mu.Unlock()
	if verr := validateStartLocked(table, requesterUserID); verr != nil {
		return false, "", verr
	}
	// Tables with no RL seat never touch the policy service at all, so they
	// must neither pay for — nor fail on — a warmup.
	needWarm = m != nil && m.WarmRLEndpoints != nil && tableHasRLSeat(table)
	return needWarm, seatSignature(table), nil
}

// legacyRulesetAliases maps deprecated ruleset queue keys to their current
// canonical name, so clients that still send an old key match into the right
// queue. "hometown" was renamed to "fenghua" in 2026-06.
var legacyRulesetAliases = map[string]string{
	"hometown": "fenghua",
}

// canonicalRuleset resolves a possibly-legacy ruleset key to its current name.
func canonicalRuleset(ruleset string) string {
	if canonical, ok := legacyRulesetAliases[ruleset]; ok {
		return canonical
	}
	return ruleset
}

// JoinQueue adds a user to the matchmaking queue
func (m *Matchmaker) JoinQueue(userID uint, ruleset string) error {
	ruleset = canonicalRuleset(ruleset)
	queueKey := "queue:" + ruleset

	// Duplicate network requests are harmless: one user occupies one queue slot.
	m.Queue.PushUnique(queueKey, fmt.Sprintf("%d", userID))

	log.Printf("User %d joined queue '%s'", userID, ruleset)
	return nil
}

// LeaveQueue removes a waiting user from a single ruleset queue. False means
// the player is no longer waiting and may already be assigned to a match.
func (m *Matchmaker) LeaveQueue(userID uint, ruleset string) bool {
	ruleset = canonicalRuleset(ruleset)
	return m.Queue.Remove("queue:"+ruleset, fmt.Sprintf("%d", userID))
}

func (m *Matchmaker) GetActivePrivateTable(tableID string) (ActivePrivateTable, bool) {
	m.privateTablesMu.RLock()
	defer m.privateTablesMu.RUnlock()

	table, ok := m.activePrivateTables[tableID]
	if !ok {
		return ActivePrivateTable{}, false
	}

	copiedParticipants := make(map[uint]bool, len(table.ParticipantIDs))
	for userID, present := range table.ParticipantIDs {
		copiedParticipants[userID] = present
	}
	table.ParticipantIDs = copiedParticipants

	return table, true
}

func (m *Matchmaker) IsPrivateTableParticipant(tableID string, userID uint) (ActivePrivateTable, bool, bool) {
	table, ok := m.GetActivePrivateTable(tableID)
	if !ok {
		return ActivePrivateTable{}, false, false
	}

	return table, true, table.ParticipantIDs[userID]
}

func (m *Matchmaker) registerActivePrivateTable(tableID string, matchID string, userIDs []uint, room *Room) {
	participants := make(map[uint]bool, len(userIDs))
	for _, userID := range userIDs {
		participants[userID] = true
	}

	m.privateTablesMu.Lock()
	defer m.privateTablesMu.Unlock()
	m.activePrivateTables[tableID] = ActivePrivateTable{
		TableID:        tableID,
		MatchID:        matchID,
		ParticipantIDs: participants,
		Room:           room,
	}
}

func (m *Matchmaker) unregisterActivePrivateTable(tableID string) {
	if tableID == "" {
		return
	}

	m.privateTablesMu.Lock()
	defer m.privateTablesMu.Unlock()
	delete(m.activePrivateTables, tableID)
}

// StartQueueWatcher starts a background goroutine to poll the queue for 4 players
func (m *Matchmaker) StartQueueWatcher(ruleset string) {
	queueKey := "queue:" + ruleset
	log.Printf("Matchmaker polling queue '%s'...", queueKey)

	for {
		// Attempt to atomically pop 4 players from the list
		// (In production, use Lua scripts or ZSETs with ELO tracking.
		// Here we use LPop with count for simplicity)

		// Check length first
		length := m.Queue.Len(queueKey)
		if length >= 4 {
			// Pop exactly 4 players
			players := m.Queue.PopN(queueKey, 4)
			if len(players) == 4 {
				log.Printf("Matchmaker found 4 players: %v", players)
				go m.createMatch(players, ruleset, "")
			}
		}

		time.Sleep(1 * time.Second)
	}
}

func (m *Matchmaker) createMatch(playerIDs []string, ruleset string, tableID string) {
	ruleset = canonicalRuleset(ruleset)
	matchID := uuid.New().String()

	// 1. Persist the match explicitly to Postgres
	match := storage.Match{
		ID:        matchID,
		Status:    "in_progress",
		StartTime: time.Now(),
		Ruleset:   ruleset,
	}

	if m.DB != nil {
		if err := m.DB.Create(&match).Error; err != nil {
			log.Printf("Failed to create match %s in DB: %v", matchID, err)
			return
		}
	} else {
		log.Printf("Database disabled, skipping match persistence for %s", matchID)
	}

	// 2. MatchPlayer rows are inserted by Room.persistMatch at shutdown, once
	// final scores and placements are known.

	// 3. Create the Room Goroutine explicitly
	roomOptions := []RoomOption{WithBotActionDelay(defaultBotActionDelay)}
	if m.BotPolicyFactory != nil {
		roomOptions = append(roomOptions, WithBotPolicy(m.BotPolicyFactory()))
	}
	if matchOpts, ok := defaultMatchOptionsFor(ruleset); ok {
		roomOptions = append(roomOptions, WithMatchOptions(matchOpts))
	}
	room := NewRoom(matchID, m.Hub, m.DB, roomOptions...)
	room.PaipuStore = m.PaipuStore
	room.PrivateTableID = tableID
	room.OnShutdown = func() {
		m.unregisterActivePrivateTable(tableID)
		m.unregisterActiveRoom(matchID)
	}
	// Atomic with the draining flag: refuse to start a queue match that
	// would miss the shutdown drain.
	if !m.registerActiveRoom(room) {
		log.Printf("Refusing to start match during shutdown drain (players %v)", playerIDs)
		if m.DB != nil {
			if derr := m.DB.Delete(&storage.Match{}, "id = ?", matchID).Error; derr != nil {
				log.Printf("Failed to clean up draining-refused match %s: %v", matchID, derr)
			}
		}
		return
	}

	// 4. Parse user IDs and dispatch to Hub for exact WS binding
	var userIDs []uint
	for _, idStr := range playerIDs {
		var uid uint
		// Simple conversion, assuming IDs are pure numeric strings or standard uints in the queue
		// If these were Postgres UUIDs, we'd handle it differently, but our IDs are uint representations
		fmt.Sscanf(idStr, "%d", &uid)
		userIDs = append(userIDs, uid)
	}

	if tableID != "" {
		m.registerActivePrivateTable(tableID, matchID, userIDs, room)
	}

	seats := make(map[uint32]uint, len(userIDs))
	seatInfos := make(map[uint32]SeatInfo, len(userIDs))
	for i, uid := range userIDs {
		seats[uint32(i)] = uid
		// Queue matches seat four humans; usernames are resolved from the
		// live socket (or a userID placeholder) when the paipu registers.
		seatInfos[uint32(i)] = SeatInfo{Kind: "human", UserID: uid}
	}
	room.SeatInfos = seatInfos
	m.Hub.BindRoom <- RoomBind{
		Seats: seats,
		Room:  room,
	}
}

// CreatePrivateTable creates a configuring room and seats its creator as host.
// It never reuses an existing id.
func (m *Matchmaker) CreatePrivateTable(tableID string, userID uint, username string) (*PrivateTable, error) {
	m.configuringMu.Lock()
	defer m.configuringMu.Unlock()
	if _, exists := m.configuringTables[tableID]; exists {
		return nil, ErrPrivateTableExists
	}
	table := newConfiguringTable(tableID, userID)
	if _, err := table.claimNextHumanSeat(userID, username); err != nil {
		return nil, err
	}
	table.normalize()
	m.configuringTables[tableID] = table
	return table, nil
}

// JoinPrivateTable claims a seat in an existing room. Missing room ids are
// rejected and never create state.
func (m *Matchmaker) JoinPrivateTable(tableID string, userID uint, username string) (*PrivateTable, error) {
	table := m.GetConfiguringPrivateTable(tableID)
	if table == nil {
		return nil, ErrPrivateTableNotFound
	}
	table.mu.Lock()
	defer table.mu.Unlock()

	if table.State != "configuring" {
		return nil, errors.New("table is no longer accepting players")
	}

	if _, err := table.claimNextHumanSeat(userID, username); err != nil {
		return nil, err
	}
	table.normalize()
	return table, nil
}

// GetConfiguringPrivateTable returns the live table struct (locked by
// caller via Mutate) or nil if no such table exists in the "configuring"
// state.
func (m *Matchmaker) GetConfiguringPrivateTable(tableID string) *PrivateTable {
	m.configuringMu.Lock()
	defer m.configuringMu.Unlock()
	return m.configuringTables[tableID]
}

// MutatePrivateTable runs fn under the table lock. Returns the table for
// snapshotting after fn returns successfully.
func (m *Matchmaker) MutatePrivateTable(tableID string, fn func(t *PrivateTable) error) (*PrivateTable, error) {
	table := m.GetConfiguringPrivateTable(tableID)
	if table == nil {
		return nil, ErrPrivateTableNotFound
	}
	table.mu.Lock()
	defer table.mu.Unlock()
	if err := fn(table); err != nil {
		return nil, err
	}
	return table, nil
}

// removeConfiguringTable drops the table from the configuring registry.
// Called after a successful start once the match has been dispatched.
func (m *Matchmaker) removeConfiguringTable(tableID string) {
	m.configuringMu.Lock()
	defer m.configuringMu.Unlock()
	delete(m.configuringTables, tableID)
}

// StartPrivateTable validates host + seat fullness, constructs the Room
// with per-seat bot policies, persists the match, and dispatches the room
// via the Hub. Returns the table snapshot (with State == "started" and
// MatchID populated) on success.
func (m *Matchmaker) StartPrivateTable(tableID string, requesterUserID uint) (*PrivateTable, error) {
	table := m.GetConfiguringPrivateTable(tableID)
	if table == nil {
		return nil, ErrPrivateTableNotFound
	}

	var room *Room
	var humanSeats map[uint32]uint
	var matchID string

	// Admission gate: an RL table only starts once the policy service is warm,
	// so the first in-match decision never eats the cold-start cost (which
	// would blow the 750ms /act budget and silently fall back to the
	// heuristic). The warm can take seconds, so it runs with table.mu
	// RELEASED: (1) cheap validation under the lock, (2) unlock, (3) warm,
	// (4) re-acquire and re-validate everything below. Holding the lock across
	// the warm would freeze that table's join/seat/state handlers for the full
	// budget and serialize repeated Start clicks into sequential waits.
	needWarm, startSignature, err := m.prepareStartUnderLock(table, requesterUserID)
	if err != nil {
		return nil, err
	}
	if needWarm {
		if werr := m.warmRLEndpoints(tableID); werr != nil {
			return nil, werr
		}
	}

	err = func() error {
		table.mu.Lock()
		defer table.mu.Unlock()

		// Re-validate: everything checked before the warm could have changed
		// while the lock was released (another start won the race, seats were
		// reconfigured, a human left). Any change is a normal validation
		// failure — in particular a seat change means the warm decision itself
		// was made against a configuration that no longer exists, so the host
		// must start again (and be re-gated).
		if verr := validateStartLocked(table, requesterUserID); verr != nil {
			return verr
		}
		if seatSignature(table) != startSignature {
			return ErrPrivateTableChangedDuringStart
		}

		seatPolicies := make(map[uint32]bot.Policy)
		seatInfos := make(map[uint32]SeatInfo)
		humanSeats = make(map[uint32]uint)

		// handedOff flips to true only once a Room has been constructed and
		// taken ownership of seatPolicies (it will close them itself at
		// shutdown, via closeSeatPolicies). Every return path before that
		// point — a later seat's resolveSeatPolicy failing, match persistence
		// failing, or registerActiveRoom refusing the room because the server
		// is draining — must close whatever was already constructed for
		// earlier seats itself, or a closeable policy (e.g. a ShadowPolicy's
		// worker goroutine) leaks for good (adversarial round 4, Finding 1b).
		handedOff := false
		defer func() {
			if !handedOff {
				policies := make([]bot.Policy, 0, len(seatPolicies))
				for _, p := range seatPolicies {
					policies = append(policies, p)
				}
				closeBotPolicies(policies...)
			}
		}()

		for i, s := range table.Seats {
			seat := uint32(i)
			switch s.Kind {
			case "human":
				humanSeats[seat] = s.UserID
				seatInfos[seat] = SeatInfo{Kind: "human", Name: s.Username, UserID: s.UserID}
			case "bot":
				policy, perr := m.resolveSeatPolicy(s.Difficulty, tableID, seat)
				if perr != nil {
					return fmt.Errorf("seat %d: %w", i, perr)
				}
				seatPolicies[seat] = policy
				info := SeatInfo{Kind: "bot", Difficulty: s.Difficulty}
				if s.Difficulty == pb.Difficulty_DIFFICULTY_RL && m.RLPolicyIdentity != nil {
					info.PolicyID = m.RLPolicyIdentity()
				}
				seatInfos[seat] = info
			default:
				return fmt.Errorf("seat %d is %s, expected human or bot", i, s.Kind)
			}
		}

		matchID = uuid.New().String()
		match := storage.Match{
			ID:        matchID,
			Status:    "in_progress",
			StartTime: time.Now(),
			Ruleset:   "fenghua",
		}
		if m.DB != nil {
			if dberr := m.DB.Create(&match).Error; dberr != nil {
				return fmt.Errorf("%w: %w", ErrPrivateTablePersistFailed, dberr)
			}
		} else {
			log.Printf("Database disabled, skipping match persistence for %s", matchID)
		}

		roomOptions := []RoomOption{WithBotActionDelay(defaultBotActionDelay)}
		if m.BotPolicyFactory != nil {
			roomOptions = append(roomOptions, WithBotPolicy(m.BotPolicyFactory()))
		}
		roomOptions = append(roomOptions, WithMatchOptions(matchOptionsForPrivateTable(table)))
		room = NewRoom(matchID, m.Hub, m.DB, roomOptions...)
		room.PaipuStore = m.PaipuStore
		room.PrivateTableID = tableID
		room.SeatPolicies = seatPolicies
		room.SeatInfos = seatInfos
		room.OnShutdown = func() {
			m.unregisterActivePrivateTable(tableID)
			m.unregisterActiveRoom(matchID)
		}
		// The drain-registry admission is the authoritative draining gate:
		// it is atomic with DrainActiveRooms' flag flip, so a start racing a
		// shutdown either lands in the drain snapshot or is refused here.
		if !m.registerActiveRoom(room) {
			if m.DB != nil {
				if derr := m.DB.Delete(&storage.Match{}, "id = ?", matchID).Error; derr != nil {
					log.Printf("Failed to clean up draining-refused match %s: %v", matchID, derr)
				}
			}
			return ErrServerDraining
		}

		m.registerActivePrivateTable(tableID, matchID, mapValues(humanSeats), room)

		// From here on, room (holding seatPolicies) is the durable owner: its
		// own closeSeatPolicies will run at shutdown, so the deferred cleanup
		// above must stand down.
		handedOff = true

		table.State = "started"
		table.MatchID = matchID

		return nil
	}()

	if err != nil {
		return nil, err
	}

	// BindRoom send happens AFTER table.mu is released so a slow Hub.Run
	// doesn't block concurrent readers. State is already "started", so
	// any incoming join request will be rejected cleanly.
	m.Hub.BindRoom <- RoomBind{
		Seats: humanSeats,
		Room:  room,
	}

	// Async to avoid acquiring configuringMu while we'd otherwise be
	// holding table.mu (lock-order inversion with JoinPrivateTable).
	// Even now (after the lock is released) the goroutine is harmless and
	// keeps the caller responsive.
	go m.removeConfiguringTable(tableID)

	// Return the live pointer; State is "started" so future readers can
	// still SnapshotProto() without seeing an inconsistent view.
	return table, nil
}

// RoomForTableForTest returns the live *Room registered for the given
// private-table ID, or nil if no match is active. Test-only.
func (m *Matchmaker) RoomForTableForTest(tableID string) *Room {
	m.privateTablesMu.RLock()
	defer m.privateTablesMu.RUnlock()
	ap, ok := m.activePrivateTables[tableID]
	if !ok {
		return nil
	}
	return ap.Room
}

// defaultMatchOptionsFor returns the canonical MatchOptions for a public
// queue ruleset key. Returns false if the key has no match-mode mapping
// (i.e. classic queues fall through to MatchOptions{}).
func defaultMatchOptionsFor(ruleset string) (engine.MatchOptions, bool) {
	switch ruleset {
	case "chongci-fh":
		return engine.MatchOptions{
			Mode:          pb.MatchMode_MATCH_MODE_CHONGCI,
			ChongciConfig: defaultChongciConfig(),
		}, true
	default:
		return engine.MatchOptions{}, false
	}
}

// defaultChongciConfig is the canonical starting configuration shared by the
// public chongci queue and private tables: bust-at-zero from 2000 points,
// capped at 50 hands. Kept in one place so the two defaults cannot drift.
func defaultChongciConfig() *pb.ChongciConfig {
	return &pb.ChongciConfig{
		StartingScore: 2000,
		BustThreshold: 0,
		MaxHands:      50,
	}
}

// classicSingleHandConfig makes a private "classic" table a single-hand match
// ("a 1-hand chongci"): players start at 0 (the classic baseline) and the match
// ends after exactly one hand, so it reaches PHASE_MATCH_END, persists as
// completed, and appears in the paipu library. The bust threshold is set far
// below any reachable single-hand score so the match always ends on the hand
// cap (never a misleading "bust"). The engine keeps MatchMode == CLASSIC (random
// dealer), so the in-game chongci UI stays hidden.
func classicSingleHandConfig() *pb.ChongciConfig {
	return &pb.ChongciConfig{
		StartingScore: 0,
		BustThreshold: -1_000_000,
		MaxHands:      1,
	}
}

// matchOptionsForPrivateTable maps a configured private table to the engine
// MatchOptions its match should run with. Chongci tables carry their host
// config; every other table (classic, the default) runs the single-hand classic
// match so it can complete and be recorded.
func matchOptionsForPrivateTable(t *PrivateTable) engine.MatchOptions {
	if t.MatchMode == pb.MatchMode_MATCH_MODE_CHONGCI {
		return engine.MatchOptions{
			Mode:          pb.MatchMode_MATCH_MODE_CHONGCI,
			ChongciConfig: engine.CloneChongciConfig(t.ChongciConfig),
		}
	}
	return engine.MatchOptions{
		Mode:          pb.MatchMode_MATCH_MODE_CLASSIC,
		ChongciConfig: classicSingleHandConfig(),
	}
}

// mapValues returns the values of a uint32→uint map as a slice. Used to
// adapt the seat-keyed human map to the userID-list APIs.
func mapValues(m map[uint32]uint) []uint {
	out := make([]uint, 0, len(m))
	for _, v := range m {
		out = append(out, v)
	}
	return out
}
