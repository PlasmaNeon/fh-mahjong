package api

import (
	"fmt"
	"log"
	"net/http"

	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v5"
	"github.com/gorilla/websocket"
	pb "github.com/plasma/fh-mahjong/proto"
)

var upgrader = websocket.Upgrader{
	ReadBufferSize:  1024,
	WriteBufferSize: 1024,
	// Open up CORS for local web testing
	CheckOrigin: func(r *http.Request) bool {
		return true
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

	// Lobby announcements
	LobbyBroadcast chan []byte

	// Map user IDs to their current Room
	UserRooms map[uint]*Room
}

func NewHub() *Hub {
	return &Hub{
		ActionStream:   make(chan ClientAction),
		Register:       make(chan *Client),
		Unregister:     make(chan *Client),
		BindRoom:       make(chan RoomBind),
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

			// Reconnection logic: if they are already legally assigned to an active room
			if room, exists := h.UserRooms[client.UserID]; exists {
				log.Printf("User %d reconnected to active room %s", client.UserID, room.ID)

				// Find their assigned seat and update the active socket pointer
				var assignedSeat uint32
				for seat, c := range room.Seats {
					if c != nil && c.UserID == client.UserID {
						assignedSeat = seat
						break
					}
				}
				room.Seats[assignedSeat] = client

				// Send them their seat assignment immediately
				msg := []byte(fmt.Sprintf(`{"type":"seat_assignment","seat":%d}`, assignedSeat))
				client.Send <- msg

				// Send them the current master state of the board
				room.SendStateToClient(client)
			}
		case client := <-h.Unregister:
			if _, ok := h.Clients[client]; ok {
				delete(h.Clients, client)
				close(client.Send)
				log.Printf("User %d disconnected", client.UserID)
			}
		case payload := <-h.ActionStream:
			// Route standard action to the specific match room
			if room, exists := h.UserRooms[payload.Client.UserID]; exists {
				room.ActionQueue <- payload
			} else {
				log.Printf("User %d submitted action but is not in a room", payload.Client.UserID)
			}
		case bind := <-h.BindRoom:
			for seat, uid := range bind.Seats {
				h.UserRooms[uid] = bind.Room

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

// ServeWs handles websocket requests from the peer.
func ServeWs(hub *Hub, c *gin.Context) {
	// Since this is a websocket connection, the standard Gin Header middleware
	// for JWT often fails because browsers can't set headers on WebSocket(url) connections easily.
	// Normally we pass token as a query param `?token=XYZ`
	token := c.Query("token")

	if token == "" {
		log.Println("WebSocket connection failed: Missing token")
		return // Return without upgrading
	}

	parsedToken, err := jwt.Parse(token, func(t *jwt.Token) (interface{}, error) {
		if _, ok := t.Method.(*jwt.SigningMethodHMAC); !ok {
			return nil, fmt.Errorf("unexpected signing method: %v", t.Header["alg"])
		}
		return jwtSecret, nil
	})

	if err != nil || !parsedToken.Valid {
		log.Println("WebSocket connection failed: Invalid or expired token")
		return
	}

	claims, ok := parsedToken.Claims.(jwt.MapClaims)
	if !ok {
		log.Println("WebSocket connection failed: Invalid token claims")
		return
	}

	userID := uint(claims["sub"].(float64))
	username := claims["username"].(string)

	conn, err := upgrader.Upgrade(c.Writer, c.Request, nil)
	if err != nil {
		log.Println(err)
		return
	}

	client := &Client{
		Hub:      hub,
		Conn:     conn,
		Send:     make(chan []byte, 256),
		UserID:   userID,
		Username: username,
	}

	client.Hub.Register <- client

	// Allow collection of memory referenced by the caller by doing all work in
	// new goroutines.
	go client.writePump()
	go client.readPump()
}
