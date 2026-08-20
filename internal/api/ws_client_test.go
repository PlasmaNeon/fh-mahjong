package api

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/gorilla/websocket"
	pb "github.com/plasma/fh-mahjong/proto"
	"google.golang.org/protobuf/proto"
)

// TestWritePumpDoesNotCoalesceFrames guards the one-frame-per-message
// invariant. The protocol mixes JSON text frames with protobuf binary frames,
// so messages that are already queued when the pump drains must NOT be
// concatenated into a single frame — a GameState glued onto a seat_assignment
// is undecodable and left the host stuck on "Waiting for server to deal".
func TestWritePumpDoesNotCoalesceFrames(t *testing.T) {
	upgrader := websocket.Upgrader{}
	serverConns := make(chan *websocket.Conn, 1)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		conn, err := upgrader.Upgrade(w, r, nil)
		if err != nil {
			t.Errorf("upgrade failed: %v", err)
			return
		}
		serverConns <- conn
	}))
	defer srv.Close()

	clientConn, _, err := websocket.DefaultDialer.Dial("ws"+strings.TrimPrefix(srv.URL, "http"), nil)
	if err != nil {
		t.Fatalf("dial failed: %v", err)
	}
	defer clientConn.Close()
	serverConn := <-serverConns

	c := &Client{Conn: serverConn, Send: make(chan []byte, 8)}

	// Queue both messages BEFORE the pump starts so the drain loop sees the
	// second one already waiting — the exact backlog that used to coalesce.
	seatMsg := []byte(`{"type":"seat_assignment","seat":0}`)
	state := &pb.GameState{MatchId: "match-1", Phase: pb.GamePhase_PHASE_PLAYER_TURN}
	stateBin, err := proto.Marshal(state)
	if err != nil {
		t.Fatalf("marshal failed: %v", err)
	}
	c.Send <- seatMsg
	c.Send <- stateBin
	go c.writePump()
	defer close(c.Send)

	clientConn.SetReadDeadline(time.Now().Add(5 * time.Second))

	mt, data, err := clientConn.ReadMessage()
	if err != nil {
		t.Fatalf("first read failed: %v", err)
	}
	if mt != websocket.TextMessage {
		t.Errorf("first frame: want TextMessage, got type %d", mt)
	}
	if string(data) != string(seatMsg) {
		t.Errorf("first frame: want exactly the seat_assignment JSON, got %d bytes: %q", len(data), data)
	}

	mt, data, err = clientConn.ReadMessage()
	if err != nil {
		t.Fatalf("second read failed: %v", err)
	}
	if mt != websocket.BinaryMessage {
		t.Errorf("second frame: want BinaryMessage, got type %d", mt)
	}
	var got pb.GameState
	if err := proto.Unmarshal(data, &got); err != nil {
		t.Fatalf("second frame: failed to decode GameState: %v", err)
	}
	if got.MatchId != "match-1" || got.Phase != pb.GamePhase_PHASE_PLAYER_TURN {
		t.Errorf("second frame: decoded wrong state: %+v", &got)
	}
}
