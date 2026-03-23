package api

import (
	"context"
	"fmt"
	"log"
	"strings"
	"sync"
	"time"

	"github.com/google/uuid"
	"github.com/plasma/fh-mahjong/models"
	"gorm.io/gorm"
)

var ctx = context.Background()

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

	privateTablesMu     sync.RWMutex
	activePrivateTables map[string]ActivePrivateTable
}

type ActivePrivateTable struct {
	TableID        string
	MatchID        string
	ParticipantIDs map[uint]bool
}

func NewMatchmaker(queue *InMemoryQueue, db *gorm.DB, hub *Hub) *Matchmaker {
	return &Matchmaker{
		Queue: queue,
		DB:    db,
		Hub:   hub,
		activePrivateTables: make(map[string]ActivePrivateTable),
	}
}

// JoinQueue adds a user to the matchmaking queue
func (m *Matchmaker) JoinQueue(userID uint, ruleset string) error {
	queueKey := "queue:" + ruleset

	// Add user to the in-memory queue
	m.Queue.RPush(queueKey, fmt.Sprintf("%d", userID))


	log.Printf("User %d joined queue '%s'", userID, ruleset)
	return nil
}

// JoinPrivateTable adds a user to a specific private table queue
func (m *Matchmaker) JoinPrivateTable(userID uint, username string, tableID string) error {
	queueKey := "table:" + tableID

	// Check if this user is already in the queue to prevent double-joins
	existing := m.Queue.LRange(queueKey)
	for _, id := range existing {
		if id == fmt.Sprintf("%d", userID) {
			return nil // User is already queued, silently succeed
		}
	}

	// Add user to the in-memory queue
	m.Queue.RPush(queueKey, fmt.Sprintf("%d", userID))

	length := m.Queue.LLen(queueKey)

	log.Printf("User %d (%s) joined private table queue '%s'", userID, username, tableID)

	// Broadcast alert
	msg := fmt.Sprintf(`{"type":"lobby_update", "table":"%s", "message":"Player %s is ready! (%d/4)"}`, tableID, username, length)
	go func() {
		m.Hub.LobbyBroadcast <- []byte(msg)
	}()

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

func (m *Matchmaker) registerActivePrivateTable(tableID string, matchID string, userIDs []uint) {
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

func (m *Matchmaker) StartPrivateTableWatcher() {
	log.Printf("Matchmaker polling for any private tables...")

	for {
		// Find all keys starting with table:
		keys := m.Queue.Keys("table:*")
		for _, key := range keys {
			length := m.Queue.LLen(key)
			if length >= 4 {
				players := m.Queue.LPopCount(key, 4)
				if len(players) == 4 {
					log.Printf("Matchmaker found 4 players for private %s: %v", key, players)
					// For simplicity, default to hometown rules for private tables
					go m.createMatch(players, "hometown", strings.TrimPrefix(key, "table:"))
				}
			}
		}

		time.Sleep(2 * time.Second)
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
	room := NewRoom(matchID, m.Hub, m.DB)
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
		m.registerActivePrivateTable(tableID, matchID, userIDs)
	}

	m.Hub.BindRoom <- RoomBind{
		UserIDs: userIDs,
		Room:    room,
	}
}
