package api

import (
	"fmt"
	"log"
	"net/http"

	"github.com/gin-gonic/gin"
	"github.com/gorilla/websocket"
	pb "github.com/plasma/fh-mahjong/proto"
	"gorm.io/gorm"
)

var upgrader = websocket.Upgrader{
	ReadBufferSize:  1024,
	WriteBufferSize: 1024,
	CheckOrigin: func(r *http.Request) bool {
		return originAllowed(r)
	},
}

// ClientAction pairs a network action with the origin client
type ClientAction struct {
	Client *Client
	Action *pb.PlayerAction
}

// RoomBind maps a group of users to a specific match Room. Seats holds
// the explicit seat→userID assignment so the Hub binds each connected
// client to the seat the matchmaker chose (mixed human+AI tables can
// have non-contiguous human seats).
type RoomBind struct {
	Seats map[uint32]uint
	Room  *Room
}

// Hub maintains the set of active clients and broadcasts messages to the match rooms.
type Hub struct {
	// Registered clients.
	Clients map[*Client]bool

	// Inbound messages from the clients.
	ActionStream chan ClientAction

	// Register requests from the clients.
	Register chan *Client

	// Unregister requests from clients.
	Unregister chan *Client

	// Room binding requests
	BindRoom chan RoomBind
	// Room shutdown notifications. The hub owns UserRooms, so room goroutines
	// hand cleanup back here instead of mutating that map concurrently.
	UnbindRoom chan *Room

	// Lobby announcements
	LobbyBroadcast chan []byte

	// Map user IDs to their current Room
	UserRooms map[uint]*Room
}

func NewHub() *Hub {
	return &Hub{
		ActionStream: make(chan ClientAction),
		Register:     make(chan *Client),
		Unregister:   make(chan *Client),
		BindRoom:     make(chan RoomBind),
		// Buffered so a room can finish and close Done even when the hub is
		// momentarily routing that room's final in-flight action.
		UnbindRoom:     make(chan *Room, 256),
		LobbyBroadcast: make(chan []byte),
		Clients:        make(map[*Client]bool),
		UserRooms:      make(map[uint]*Room),
	}
}

func (h *Hub) Run() {
	for {
		select {
		case client := <-h.Register:
			h.Clients[client] = true
			log.Printf("User %d connected via WS", client.UserID)

			// Reconnection: if they're already assigned to an active room, hand
			// the socket to that room's goroutine, which owns Seats and will
			// rebind the seat (reclaiming it from a bot if needed) and replay
			// the board. Mutating Seats here would race the room goroutine.
			if room, exists := h.UserRooms[client.UserID]; exists {
				log.Printf("User %d reconnecting to active room %s", client.UserID, room.ID)
				select {
				case room.ReconnectedClient <- client:
				default:
					log.Printf("reconnect channel full for room %s, dropping", room.ID)
				}
			}
		case client := <-h.Unregister:
			if _, ok := h.Clients[client]; ok {
				delete(h.Clients, client)
				log.Printf("User %d disconnected", client.UserID)
				if room, inRoom := h.UserRooms[client.UserID]; inRoom {
					// Hand off to the room goroutine: it frees the seat (after a
					// grace window) so a bot takes over, and closes Send itself
					// to avoid racing BroadcastState against a closed channel.
					select {
					case room.DisconnectedClient <- client:
					default:
						safeClose(client.Send)
					}
				} else {
					close(client.Send)
				}
			}
		case payload := <-h.ActionStream:
			// Route standard action to the specific match room
			if room, exists := h.UserRooms[payload.Client.UserID]; exists {
				select {
				case room.ActionQueue <- payload:
				case <-room.Done:
					log.Printf("User %d submitted action as room %s shut down", payload.Client.UserID, room.ID)
				}
			} else {
				log.Printf("User %d submitted action but is not in a room", payload.Client.UserID)
			}
		case bind := <-h.BindRoom:
			for seat, uid := range bind.Seats {
				h.UserRooms[uid] = bind.Room
				bind.Room.SeatOwners[seat] = uid // stable seat ownership for reconnect

				for client := range h.Clients {
					if client.UserID == uid {
						bind.Room.Seats[seat] = client
						msg := []byte(fmt.Sprintf(`{"type":"seat_assignment","seat":%d}`, seat))
						select {
						case client.Send <- msg:
						default:
							close(client.Send)
							delete(h.Clients, client)
						}
						break
					}
				}
			}
			// Engine and web sockets are wired, start the room loop
			go bind.Room.Start()
		case room := <-h.UnbindRoom:
			h.unbindRoom(room)
		case msg := <-h.LobbyBroadcast:
			// Broadcast JSON text message to all clients not currently in a room
			for client := range h.Clients {
				if _, inRoom := h.UserRooms[client.UserID]; !inRoom {
					select {
					case client.Send <- msg:
					default:
						close(client.Send)
						delete(h.Clients, client)
					}
				}
			}
		}
	}
}

func (h *Hub) unbindRoom(room *Room) {
	for userID, currentRoom := range h.UserRooms {
		// A late shutdown from an old room must not erase a newer assignment.
		if currentRoom == room {
			delete(h.UserRooms, userID)
		}
	}
}

// ServeWs handles websocket requests from the peer.
func ServeWs(hub *Hub, db *gorm.DB, c *gin.Context) {
	if !originAllowed(c.Request) {
		abortError(c, http.StatusForbidden, "Origin not allowed")
		return
	}
	user, _, _, authErr := authenticateSessionRequest(db, c.Request)
	if authErr != nil {
		abortError(c, http.StatusUnauthorized, "Authentication required")
		return
	}

	conn, err := upgrader.Upgrade(c.Writer, c.Request, nil)
	if err != nil {
		log.Println(err)
		return
	}

	client := &Client{
		Hub:      hub,
		Conn:     conn,
		Send:     make(chan []byte, 256),
		UserID:   user.ID,
		Username: user.Username,
	}

	client.Hub.Register <- client

	// Allow collection of memory referenced by the caller by doing all work in
	// new goroutines.
	go client.writePump()
	go client.readPump()
}
