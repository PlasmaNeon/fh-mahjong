package api

import (
	"context"
	"errors"
	"fmt"
	"log"
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
	ErrPrivateTableAlreadyStarted = errors.New("table already started")
	ErrPrivateTableHostOnly       = errors.New("only the host can start the match")
	ErrPrivateTablePersistFailed  = errors.New("persist match failed")
	ErrServerDraining             = errors.New("server is shutting down")
)

// InMemoryQueue is a mutex-guarded in-process FIFO queue with Redis-list-style
// semantics (RPush/LRange/LPopCount). Matchmaking is in-memory by design while
// the server is single-process; a Redis-backed implementation would only be
// needed if the server ever runs multi-instance.
type InMemoryQueue struct {
	mu    sync.Mutex
	lists map[string][]string
}

func NewInMemoryQueue() *InMemoryQueue {
	return &InMemoryQueue{
		lists: make(map[string][]string),
	}
}

func (q *InMemoryQueue) RPush(key string, val string) {
	q.mu.Lock()
	defer q.mu.Unlock()
	q.lists[key] = append(q.lists[key], val)
}

func (q *InMemoryQueue) LRange(key string) []string {
	q.mu.Lock()
	defer q.mu.Unlock()

	// Return a copy to avoid race conditions
	if lst, ok := q.lists[key]; ok {
		copied := make([]string, len(lst))
		copy(copied, lst)
		return copied
	}
	return nil
}

func (q *InMemoryQueue) LLen(key string) int {
	q.mu.Lock()
	defer q.mu.Unlock()
	return len(q.lists[key])
}

func (q *InMemoryQueue) LPopCount(key string, count int) []string {
	q.mu.Lock()
	defer q.mu.Unlock()

	lst, ok := q.lists[key]
	if !ok || len(lst) < count {
		return nil
	}

	popped := lst[:count]
	q.lists[key] = lst[count:]

	return popped
}

func (q *InMemoryQueue) Keys(pattern string) []string {
	q.mu.Lock()
	defer q.mu.Unlock()

	var prefix string
	if len(pattern) > 2 && pattern[len(pattern)-2:] == ":*" {
		prefix = pattern[:len(pattern)-1]
	}

	var matched []string
	for k := range q.lists {
		if prefix == "" || (len(k) >= len(prefix) && k[:len(prefix)] == prefix) {
			matched = append(matched, k)
		}
	}
	return matched
}

type Matchmaker struct {
	Queue *InMemoryQueue
	DB    *gorm.DB
	Hub   *Hub

	BotPolicyFactory func() bot.Policy
	PaipuStore       func(matchID, paipuJSON string) // in-memory fallback when DB is nil

	// SeatPolicyResolver builds the bot.Policy for a private-room seat of the
	// given difficulty. When nil, resolveSeatPolicy falls back to
	// bot.NewPolicy (heuristic-only). cmd/server installs a resolver that maps
	// DIFFICULTY_RL to the remote HTTP policy.
	SeatPolicyResolver func(pb.Difficulty) (bot.Policy, error)

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
func (m *Matchmaker) resolveSeatPolicy(d pb.Difficulty) (bot.Policy, error) {
	if m.SeatPolicyResolver != nil {
		return m.SeatPolicyResolver(d)
	}
	return bot.NewPolicy(d)
}

// rlAgentAvailable reports whether the trained RL agent can currently be
// offered. It is nil-safe (both for the receiver and the probe) and consults
// the health-checked RLAgentAvailable function installed by cmd/server.
func (m *Matchmaker) rlAgentAvailable() bool {
	return m != nil && m.RLAgentAvailable != nil && m.RLAgentAvailable()
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

	// Add user to the in-memory queue
	m.Queue.RPush(queueKey, fmt.Sprintf("%d", userID))

	log.Printf("User %d joined queue '%s'", userID, ruleset)
	return nil
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
		length := m.Queue.LLen(queueKey)
		if length >= 4 {
			// Pop exactly 4 players
			players := m.Queue.LPopCount(queueKey, 4)
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

// JoinOrCreatePrivateTable claims a seat for the given user. If the table
// does not exist, the user becomes the host at seat 0. If the user is
// already seated, this is a no-op.
//
// Returns a snapshot of the table state for the caller. The caller is
// expected to broadcast a lobby_update afterward.
func (m *Matchmaker) JoinOrCreatePrivateTable(tableID string, userID uint, username string) (*PrivateTable, error) {
	m.configuringMu.Lock()
	defer m.configuringMu.Unlock()

	table, ok := m.configuringTables[tableID]
	if !ok {
		table = newConfiguringTable(tableID, userID)
		m.configuringTables[tableID] = table
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

	err := func() error {
		table.mu.Lock()
		defer table.mu.Unlock()

		if table.State != "configuring" {
			return ErrPrivateTableAlreadyStarted
		}
		if requesterUserID != table.HostUserID {
			return ErrPrivateTableHostOnly
		}
		if err := table.canStart(); err != nil {
			return err
		}

		seatPolicies := make(map[uint32]bot.Policy)
		seatInfos := make(map[uint32]SeatInfo)
		humanSeats = make(map[uint32]uint)
		for i, s := range table.Seats {
			seat := uint32(i)
			switch s.Kind {
			case "human":
				humanSeats[seat] = s.UserID
				seatInfos[seat] = SeatInfo{Kind: "human", Name: s.Username, UserID: s.UserID}
			case "bot":
				policy, perr := m.resolveSeatPolicy(s.Difficulty)
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
		if table.MatchMode == pb.MatchMode_MATCH_MODE_CHONGCI && table.ChongciConfig != nil {
			roomOptions = append(roomOptions, WithMatchOptions(engine.MatchOptions{
				Mode:          pb.MatchMode_MATCH_MODE_CHONGCI,
				ChongciConfig: engine.CloneChongciConfig(table.ChongciConfig),
			}))
		}
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
	// holding table.mu (lock-order inversion with JoinOrCreatePrivateTable).
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
			Mode: pb.MatchMode_MATCH_MODE_CHONGCI,
			ChongciConfig: &pb.ChongciConfig{
				StartingScore: 2000,
				BustThreshold: 0,
				MaxHands:      50,
			},
		}, true
	default:
		return engine.MatchOptions{}, false
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
