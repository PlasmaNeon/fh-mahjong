package api

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/gorilla/websocket"
	pb "github.com/plasma/fh-mahjong/proto"
	"github.com/plasma/fh-mahjong/rules/shanten"
	"google.golang.org/protobuf/proto"
)

// TestPrivateMatchDeliversInitialStateToHost mirrors the real browser flow:
// the host holds an open websocket (as on the waiting-room page), then joins,
// fills seats 1-3 with heuristic bots, and starts. The host must receive the
// initial GameState broadcast so the client leaves "Waiting for server to deal".
func TestPrivateMatchDeliversInitialStateToHost(t *testing.T) {
	// Pre-warm the shanten lookup tables off the critical path, mirroring the
	// server-startup prewarm (cmd/server/main.go). Without this, the first
	// BroadcastState blocks ~15s building tables and the host stays on
	// "Waiting for server to deal" the whole time.
	shanten.Prewarm()

	server := newPrivateTableTestServer()
	ts := httptest.NewServer(server.Router)
	defer ts.Close()

	hostToken := privateTableAuthToken(t, 101, "alice")

	// 1. Host opens a websocket BEFORE starting (like the waiting room page).
	wsURL := "ws" + strings.TrimPrefix(ts.URL, "http") + "/api/v1/ws?token=" + hostToken
	conn, _, err := websocket.DefaultDialer.Dial(wsURL, nil)
	if err != nil {
		t.Fatalf("ws dial failed: %v", err)
	}
	defer conn.Close()

	// Give the hub a moment to register the client.
	time.Sleep(100 * time.Millisecond)

	// 2. Host joins the room (claims a human seat).
	rec, _ := doPrivateTableRequest(t, server, http.MethodPost, "/api/v1/rooms/repro/join", hostToken, map[string]any{})
	if rec.Code != http.StatusOK {
		t.Fatalf("join failed: %d %s", rec.Code, rec.Body.String())
	}

	// 3. Fill seats 1-3 with heuristic bots.
	for seat := 1; seat <= 3; seat++ {
		rec, _ := doPrivateTableRequest(t, server, http.MethodPost, "/api/v1/rooms/repro/seat", hostToken, map[string]any{
			"seat":       seat,
			"kind":       "bot",
			"difficulty": int(pb.Difficulty_DIFFICULTY_HEURISTIC),
		})
		if rec.Code != http.StatusOK {
			t.Fatalf("seat %d failed: %d %s", seat, rec.Code, rec.Body.String())
		}
	}

	// 4. Start the match.
	rec, body := doPrivateTableRequest(t, server, http.MethodPost, "/api/v1/rooms/repro/start", hostToken, map[string]any{})
	if rec.Code != http.StatusOK {
		t.Fatalf("start failed: %d %s", rec.Code, rec.Body.String())
	}
	t.Logf("start response: %#v", body)

	// 5. Read from the websocket. We expect a seat_assignment (text) and at
	// least one binary GameState within a few seconds.
	conn.SetReadDeadline(time.Now().Add(3 * time.Second))
	gotState := false
	gotSeat := false
	for i := 0; i < 20; i++ {
		mt, data, err := conn.ReadMessage()
		if err != nil {
			t.Logf("read ended after %d msgs: %v", i, err)
			break
		}
		typeName := "BINARY"
		if mt == websocket.TextMessage {
			typeName = "TEXT"
		}
		preview := string(data)
		if len(preview) > 80 {
			preview = preview[:80]
		}
		t.Logf("msg #%d type=%s len=%d preview=%q", i, typeName, len(data), preview)

		if mt == websocket.TextMessage {
			if strings.Contains(string(data), "seat_assignment") {
				gotSeat = true
			}
			continue
		}
		var st pb.GameState
		if err := proto.Unmarshal(data, &st); err != nil {
			t.Logf("  binary msg failed to decode: %v", err)
			continue
		}
		gotState = true
		t.Logf("  GameState: phase=%v activePlayer=%d wallCount=%d players=%d matchId=%q",
			st.Phase, st.ActivePlayer, st.WallCount, len(st.Players), st.MatchId)
	}

	if !gotSeat {
		t.Errorf("host never received seat_assignment")
	}
	if !gotState {
		t.Errorf("host never received a GameState broadcast (stuck on 'Waiting for server to deal')")
	}
}
