package api

import (
	"encoding/json"
	"log"
	"time"

	"github.com/gorilla/websocket"
	pb "github.com/plasma/fh-mahjong/proto"
	"google.golang.org/protobuf/proto"
)

const (
	writeWait      = 10 * time.Second
	pongWait       = 60 * time.Second
	pingPeriod     = (pongWait * 9) / 10
	maxMessageSize = 512
	// Application close code sent by the table UI when the player explicitly
	// leaves. Network drops and refreshes use ordinary WebSocket close codes and
	// retain the reconnect grace period.
	intentionalLeaveCloseCode = 4000
)

// Client tracks a single connected user over a WebSocket
type Client struct {
	Hub      *Hub
	Conn     *websocket.Conn
	Send     chan []byte
	UserID   uint
	Username string
	// IntentionalLeave is set by readPump before Unregister is sent, so the room
	// can release this seat immediately instead of waiting out reconnect grace.
	IntentionalLeave bool
}

// readPump pumps messages from the websocket connection to the hub.
func (c *Client) readPump() {
	defer func() {
		c.Hub.Unregister <- c
		c.Conn.Close()
	}()

	c.Conn.SetReadLimit(maxMessageSize)
	c.Conn.SetReadDeadline(time.Now().Add(pongWait))
	c.Conn.SetPongHandler(func(string) error { c.Conn.SetReadDeadline(time.Now().Add(pongWait)); return nil })

	for {
		_, message, err := c.Conn.ReadMessage()
		if err != nil {
			if websocket.IsCloseError(err, intentionalLeaveCloseCode) {
				c.IntentionalLeave = true
			}
			if websocket.IsUnexpectedCloseError(err, websocket.CloseGoingAway, websocket.CloseAbnormalClosure, intentionalLeaveCloseCode) {
				log.Printf("error: %v", err)
			}
			break
		}

		// Expecting protobuf PlayerAction
		var action pb.PlayerAction
		if err := proto.Unmarshal(message, &action); err != nil {
			log.Printf("Invalid Protobuf received from user %d: %v", c.UserID, err)
			continue
		}

		// Route the action to the player's active room (via Hub or directly)
		c.Hub.ActionStream <- ClientAction{
			Client: c,
			Action: &action,
		}
	}
}

// writeFrame sends one queued payload as its own websocket frame, sniffing
// JSON control messages into text frames and protobuf blobs into binary ones.
func (c *Client) writeFrame(message []byte) error {
	messageType := websocket.BinaryMessage
	if len(message) > 0 && message[0] == '{' && json.Valid(message) {
		messageType = websocket.TextMessage
	}
	if err := c.Conn.SetWriteDeadline(time.Now().Add(writeWait)); err != nil {
		return err
	}
	return c.Conn.WriteMessage(messageType, message)
}

// writePump pumps messages from the hub to the websocket connection.
func (c *Client) writePump() {
	ticker := time.NewTicker(pingPeriod)
	defer func() {
		ticker.Stop()
		c.Conn.Close()
	}()

	for {
		select {
		case message, ok := <-c.Send:
			if !ok {
				c.Conn.SetWriteDeadline(time.Now().Add(writeWait))
				c.Conn.WriteMessage(websocket.CloseMessage, []byte{})
				return
			}

			if err := c.writeFrame(message); err != nil {
				return
			}

			// Drain anything already queued, one frame per message. Never
			// concatenate into a single frame: this protocol mixes JSON text
			// frames with protobuf binary frames, and a merged frame is
			// undecodable on the client (e.g. a GameState glued onto a
			// seat_assignment left the host stuck on "Waiting for server to
			// deal" whenever two broadcasts queued up back to back).
			n := len(c.Send)
			for i := 0; i < n; i++ {
				queued, ok := <-c.Send
				if !ok {
					c.Conn.SetWriteDeadline(time.Now().Add(writeWait))
					c.Conn.WriteMessage(websocket.CloseMessage, []byte{})
					return
				}
				if err := c.writeFrame(queued); err != nil {
					return
				}
			}
		case <-ticker.C:
			c.Conn.SetWriteDeadline(time.Now().Add(writeWait))
			if err := c.Conn.WriteMessage(websocket.PingMessage, nil); err != nil {
				return
			}
		}
	}
}
