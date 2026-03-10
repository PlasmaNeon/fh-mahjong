package api

import (
	"context"
	"fmt"
	"log"
	"time"

	"github.com/google/uuid"
	"github.com/plasma/fh-mahjong/models"
	"github.com/redis/go-redis/v9"
	"gorm.io/gorm"
)

var ctx = context.Background()

type Matchmaker struct {
	Redis *redis.Client
	DB    *gorm.DB
	Hub   *Hub
}

func NewMatchmaker(rdb *redis.Client, db *gorm.DB, hub *Hub) *Matchmaker {
	return &Matchmaker{
		Redis: rdb,
		DB:    db,
		Hub:   hub,
	}
}

// JoinQueue adds a user to the matchmaking queue
func (m *Matchmaker) JoinQueue(userID uint, ruleset string) error {
	queueKey := "queue:" + ruleset

	// Add user to a Redis List
	err := m.Redis.RPush(ctx, queueKey, userID).Err()
	if err != nil {
		return err
	}

	log.Printf("User %d joined queue '%s'", userID, ruleset)
	return nil
}

// JoinPrivateTable adds a user to a specific private table queue
func (m *Matchmaker) JoinPrivateTable(userID uint, username string, tableID string) error {
	queueKey := "table:" + tableID

	// Check if this user is already in the queue to prevent double-joins
	existing, err := m.Redis.LRange(ctx, queueKey, 0, -1).Result()
	if err == nil {
		for _, id := range existing {
			if id == fmt.Sprintf("%d", userID) {
				return nil // User is already queued, silently succeed
			}
		}
	}

	// Add user to a Redis List
	err = m.Redis.RPush(ctx, queueKey, userID).Err()
	if err != nil {
		return err
	}

	length, _ := m.Redis.LLen(ctx, queueKey).Result()

	log.Printf("User %d (%s) joined private table queue '%s'", userID, username, tableID)

	// Broadcast alert
	msg := fmt.Sprintf(`{"type":"lobby_update", "table":"%s", "message":"Player %s is ready! (%d/4)"}`, tableID, username, length)
	go func() {
		m.Hub.LobbyBroadcast <- []byte(msg)
	}()

	return nil
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
		length, err := m.Redis.LLen(ctx, queueKey).Result()
		if err != nil {
			time.Sleep(2 * time.Second)
			continue
		}

		if length >= 4 {
			// Pop exactly 4 players
			players, err := m.Redis.LPopCount(ctx, queueKey, 4).Result()
			if err == nil && len(players) == 4 {
				log.Printf("Matchmaker found 4 players: %v", players)
				go m.createMatch(players, ruleset)
			}
		}

		time.Sleep(1 * time.Second)
	}
}

func (m *Matchmaker) StartPrivateTableWatcher() {
	log.Printf("Matchmaker polling for any private tables...")

	for {
		// Find all keys starting with table:
		keys, err := m.Redis.Keys(ctx, "table:*").Result()
		if err == nil {
			for _, key := range keys {
				length, err := m.Redis.LLen(ctx, key).Result()
				if err == nil && length >= 4 {
					players, err := m.Redis.LPopCount(ctx, key, 4).Result()
					if err == nil && len(players) == 4 {
						log.Printf("Matchmaker found 4 players for private %s: %v", key, players)
						// For simplicity, default to hometown rules for private tables
						go m.createMatch(players, "hometown")
					}
				}
			}
		}

		time.Sleep(2 * time.Second)
	}
}

func (m *Matchmaker) createMatch(playerIDs []string, ruleset string) {
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

	// 4. Parse user IDs and dispatch to Hub for exact WS binding
	var userIDs []uint
	for _, idStr := range playerIDs {
		var uid uint
		// Simple conversion, assuming IDs are pure numeric strings or standard uints in redis
		// If these were Postgres UUIDs, we'd handle it differently, but our IDs are uint representations
		fmt.Sscanf(idStr, "%d", &uid)
		userIDs = append(userIDs, uid)
	}

	m.Hub.BindRoom <- RoomBind{
		UserIDs: userIDs,
		Room:    room,
	}
}
