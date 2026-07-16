package api

import (
	"testing"
	"time"
)

// When the seat that is currently on turn is held by a (human) client, the bots
// must not act on it. After the client is freed (disconnect), the seat becomes
// bot-controlled and advanceAutomatedSeats plays it — this is the "bot takes
// over" behaviour.
func TestFreeSeatForClient_LetsBotTakeOverActiveSeat(t *testing.T) {
	room := NewRoom("disc-room", nil, nil)
	if err := room.Engine.Start(); err != nil {
		t.Fatalf("Engine.Start: %v", err)
	}

	active := room.Engine.State.ActivePlayer
	human := &Client{UserID: 99, Username: "Human"}
	room.Seats[active] = human

	if room.isAutomatedSeat(active) {
		t.Fatalf("seat %d should be human-occupied before disconnect", active)
	}
	if got := room.advanceAutomatedSeats(); len(got) != 0 {
		t.Fatalf("bots must not advance an occupied active seat, got %d payloads", len(got))
	}

	seat, ok := room.freeSeatForClient(human)
	if !ok || seat != active {
		t.Fatalf("freeSeatForClient = (%d, %v), want (%d, true)", seat, ok, active)
	}
	if !room.isAutomatedSeat(active) {
		t.Fatalf("seat %d should be automated after the client is freed", active)
	}
	if got := room.advanceAutomatedSeats(); len(got) == 0 {
		t.Fatalf("expected a bot to take over the freed seat and advance the game")
	}
}

// freeSeatForClient matches by pointer identity so a client that reconnected
// (a brand-new *Client at the same seat for the same user) is never displaced
// by a late grace-release for the stale connection.
func TestFreeSeatForClient_DoesNotDisplaceReconnectedSeat(t *testing.T) {
	room := NewRoom("reconnect-room", nil, nil)
	oldConn := &Client{UserID: 7}
	newConn := &Client{UserID: 7} // same user, fresh websocket

	room.Seats[2] = oldConn
	room.Seats[2] = newConn // reconnect overwrote the seat

	if seat, ok := room.freeSeatForClient(oldConn); ok {
		t.Fatalf("stale client must not free a reclaimed seat, freed seat %d", seat)
	}
	if room.Seats[2] != newConn {
		t.Fatal("reclaimed seat must remain bound to the new client")
	}
}

// seatForClient locates the seat a client currently holds, and reports absence
// for a client that holds no seat.
func TestSeatForClient(t *testing.T) {
	room := NewRoom("seat-lookup-room", nil, nil)
	a := &Client{UserID: 1}
	b := &Client{UserID: 2}
	room.Seats[3] = a

	if seat, ok := room.seatForClient(a); !ok || seat != 3 {
		t.Fatalf("seatForClient(a) = (%d, %v), want (3, true)", seat, ok)
	}
	if _, ok := room.seatForClient(b); ok {
		t.Fatal("seatForClient(b) should report no seat")
	}
}

func TestReleaseSeatAfterGrace_EndsMatchWhenFinalHumanLeaves(t *testing.T) {
	room := NewRoom("last-human-room", nil, nil)
	human := &Client{UserID: 1, Send: make(chan []byte)}
	room.Seats[0] = human

	if shutdown := room.releaseSeatAfterGrace(human); !shutdown {
		t.Fatal("releasing the final human seat should end the match")
	}
	if len(room.Seats) != 0 {
		t.Fatalf("seats = %d, want no connected humans", len(room.Seats))
	}
}

func TestHandleSeatDisconnect_IntentionalFinalLeaveEndsImmediately(t *testing.T) {
	room := NewRoom("intentional-leave-room", nil, nil, WithDisconnectGrace(time.Hour))
	human := &Client{UserID: 1, Send: make(chan []byte), IntentionalLeave: true}
	room.Seats[0] = human

	if shutdown := room.handleSeatDisconnect(human); !shutdown {
		t.Fatal("an intentional final leave should not wait for reconnect grace")
	}
	if len(room.Seats) != 0 {
		t.Fatalf("seats = %d, want no connected humans", len(room.Seats))
	}
}

func TestReleaseSeatAfterGrace_KeepsMatchRunningWhileHumanRemains(t *testing.T) {
	room := NewRoom("remaining-human-room", nil, nil)
	leaving := &Client{UserID: 1, Send: make(chan []byte)}
	remaining := &Client{UserID: 2, Send: make(chan []byte)}
	room.Seats[0] = leaving
	room.Seats[1] = remaining

	if shutdown := room.releaseSeatAfterGrace(leaving); shutdown {
		t.Fatal("match should continue while another human remains")
	}
	if room.Seats[1] != remaining {
		t.Fatal("remaining human seat was disturbed")
	}
	if !room.isAutomatedSeat(0) {
		t.Fatal("departed human seat should become bot-controlled")
	}
}

func TestReleaseSeatAfterGrace_IgnoresStaleConnectionAfterReconnect(t *testing.T) {
	room := NewRoom("stale-release-room", nil, nil)
	oldConn := &Client{UserID: 1, Send: make(chan []byte)}
	newConn := &Client{UserID: 1, Send: make(chan []byte)}
	room.Seats[0] = newConn

	if shutdown := room.releaseSeatAfterGrace(oldConn); shutdown {
		t.Fatal("stale grace timer must not end a reconnected player's match")
	}
	if room.Seats[0] != newConn {
		t.Fatal("reconnected human seat was disturbed")
	}
}
