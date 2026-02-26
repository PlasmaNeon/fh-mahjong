package api

import (
	"log"
	"net/http"

	"github.com/gin-gonic/gin"
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

	// Map user IDs to their current Room
	UserRooms map[uint]*Room
}

func NewHub() *Hub {
	return &Hub{
		ActionStream: make(chan ClientAction),
		Register:     make(chan *Client),
		Unregister:   make(chan *Client),
		Clients:      make(map[*Client]bool),
		UserRooms:    make(map[uint]*Room),
	}
}

func (h *Hub) Run() {
	for {
		select {
		case client := <-h.Register:
			h.Clients[client] = true
			log.Printf("User %d connected via WS", client.UserID)
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
		}
	}
}

// ServeWs handles websocket requests from the peer.
func ServeWs(hub *Hub, c *gin.Context) {
	// Since this is a websocket connection, the standard Gin Header middleware
	// for JWT often fails because browsers can't set headers on WebSocket(url) connections easily.
	// Normally we pass token as a query param `?token=XYZ`
	token := c.Query("token")

	// TODO: Actually validate the JWT token here
	userID := uint(1) // stub
	username := "stub_user"

	if token == "" {
		_ = token // ignore for now
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
		UserID:   userID,
		Username: username,
	}

	client.Hub.Register <- client

	// Allow collection of memory referenced by the caller by doing all work in
	// new goroutines.
	go client.writePump()
	go client.readPump()
}
