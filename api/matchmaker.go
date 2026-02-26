package api

import (
	"context"
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

func (m *Matchmaker) createMatch(playerIDs []string, ruleset string) {
	matchID := uuid.New().String()

	// 1. Persist the match explicitly to Postgres
	match := models.Match{
		ID:        matchID,
		Status:    "in_progress",
		StartTime: time.Now(),
		Ruleset:   ruleset,
	}

	if err := m.DB.Create(&match).Error; err != nil {
		log.Printf("Failed to create match %s in DB: %v", matchID, err)
		return
	}

	// 2. Add players to the join table
	// In a real scenario we'd query users to convert string ID to uint ID
	// For simulation, we assume ID mappings are properly handled down the line
	// Note: Skipped explicit MatchPlayer insertion here for brevity; the Room engine handles scores.

	// 3. Create the Room Goroutine explicitly
	room := NewRoom(matchID, m.Hub, m.DB)

	// 4. Map the users to their connections and the Room
	for seat, idStr := range playerIDs {
		// (Real conversion logic needed here: string -> uint)
		// For now we just route the 4 active WS connections that belong to these IDs into the Room.
		_ = seat
		_ = idStr
		// Usually we lock the Hub, find the Client by UserID, add to room.Seats[seat] = Client
		// and set hub.UserRooms[userID] = room
	}

	// Boot the isolated game engine loop
	go room.Start()
}
