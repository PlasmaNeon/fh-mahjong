package api

import (
	"encoding/base64"
	"log"
	"time"

	"github.com/plasma/fh-mahjong/core"
	"github.com/plasma/fh-mahjong/models"
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

	ActionQueue chan ClientAction
	Shutdown    chan bool
}

// NewRoom creates a new match
func NewRoom(matchID string, hub *Hub, db *gorm.DB) *Room {
	ruleset := &rules.HometownRuleset{}

	room := &Room{
		ID:          matchID,
		Hub:         hub,
		DB:          db,
		Engine:      core.NewGame(matchID, ruleset),
		Seats:       make(map[uint32]*Client),
		ActionQueue: make(chan ClientAction),
		Shutdown:    make(chan bool),
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
			r.DB.Model(&models.Match{}).Where("id = ?", r.ID).Updates(models.Match{
				Status:    "completed",
				EndTime:   &now,
				ReplayURL: encodedReplay,
				WallSeed:  r.Engine.State.WallSeed,
			})
			return

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
				// (In real apps, use protobuf repeated `StateDelta` wrappers)
				replayBytes = append(replayBytes, statePayload...)
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

	for _, client := range r.Seats {
		client.Send <- payload
	}

	return payload // Added return
}
