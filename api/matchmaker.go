package api

import (
	"context"
	"errors"
	"fmt"
	"log"
	"sync"
	"time"

	"github.com/google/uuid"
	"github.com/plasma/fh-mahjong/bot"
	"github.com/plasma/fh-mahjong/core"
	"github.com/plasma/fh-mahjong/models"
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
)

// InMemoryQueue simulates Redis lists
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
	// DIFFICULTY_RL to the remote HTTP policy when AI_BOT_POLICY_URL is set.
	SeatPolicyResolver func(pb.Difficulty) (bot.Policy, error)

	// RLAgentAvailable reports whether the server can route a private-room seat
	// to a trained RL agent. Set together with SeatPolicyResolver by
	// cmd/server when AI_BOT_POLICY_URL is configured.
	RLAgentAvailable bool

	privateTablesMu     sync.RWMutex
	activePrivateTables map[string]ActivePrivateTable

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
		configuringTables:   make(map[string]*PrivateTable),
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

// JoinQueue adds a user to the matchmaking queue
func (m *Matchmaker) JoinQueue(userID uint, ruleset string) error {
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

// StartQueueWatcher starts a background goroutine to poll Redis for 4 players
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
	matchID := uuid.New().String()

	// 1. Persist the match explicitly to Postgres
	match := models.Match{
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

	// 2. Add players to the join table
	// In a real scenario we'd query users to convert string ID to uint ID
	// For simulation, we assume ID mappings are properly handled down the line
	// Note: Skipped explicit MatchPlayer insertion here for brevity; the Room engine handles scores.

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
	}

	// 4. Parse user IDs and dispatch to Hub for exact WS binding
	var userIDs []uint
	for _, idStr := range playerIDs {
		var uid uint
		// Simple conversion, assuming IDs are pure numeric strings or standard uints in redis
		// If these were Postgres UUIDs, we'd handle it differently, but our IDs are uint representations
		fmt.Sscanf(idStr, "%d", &uid)
		userIDs = append(userIDs, uid)
	}

	if tableID != "" {
		m.registerActivePrivateTable(tableID, matchID, userIDs, room)
	}

	seats := make(map[uint32]uint, len(userIDs))
	for i, uid := range userIDs {
		seats[uint32(i)] = uid
	}
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
		humanSeats = make(map[uint32]uint)
		for i, s := range table.Seats {
			seat := uint32(i)
			switch s.Kind {
			case "human":
				humanSeats[seat] = s.UserID
			case "bot":
				policy, perr := m.resolveSeatPolicy(s.Difficulty)
				if perr != nil {
					return fmt.Errorf("seat %d: %w", i, perr)
				}
				seatPolicies[seat] = policy
			default:
				return fmt.Errorf("seat %d is %s, expected human or bot", i, s.Kind)
			}
		}

		matchID = uuid.New().String()
		match := models.Match{
			ID:        matchID,
			Status:    "in_progress",
			StartTime: time.Now(),
			Ruleset:   "hometown",
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
			cfg := *table.ChongciConfig
			roomOptions = append(roomOptions, WithMatchOptions(core.MatchOptions{
				Mode:          pb.MatchMode_MATCH_MODE_CHONGCI,
				ChongciConfig: &cfg,
			}))
		}
		room = NewRoom(matchID, m.Hub, m.DB, roomOptions...)
		room.PaipuStore = m.PaipuStore
		room.PrivateTableID = tableID
		room.SeatPolicies = seatPolicies
		room.OnShutdown = func() {
			m.unregisterActivePrivateTable(tableID)
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
func defaultMatchOptionsFor(ruleset string) (core.MatchOptions, bool) {
	switch ruleset {
	case "chongci-fh":
		return core.MatchOptions{
			Mode: pb.MatchMode_MATCH_MODE_CHONGCI,
			ChongciConfig: &pb.ChongciConfig{
				StartingScore: 2000,
				BustThreshold: 0,
				MaxHands:      50,
			},
		}, true
	default:
		return core.MatchOptions{}, false
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
