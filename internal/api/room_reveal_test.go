package api

import (
	"testing"
	"time"

	"github.com/plasma/fh-mahjong/internal/rules/shanten"
	pb "github.com/plasma/fh-mahjong/proto"
	"google.golang.org/protobuf/proto"
)

// manHand builds a closed hand of real Man tiles 1..9 starting at the given tile
// id, so tests can assert whether a broadcast revealed real suits/values or
// obfuscated them.
func manHand(startID uint32) []*pb.Tile {
	tiles := make([]*pb.Tile, 0, 9)
	for v := uint32(1); v <= 9; v++ {
		tiles = append(tiles, &pb.Tile{
			Id:    startID + (v - 1),
			Suit:  pb.Suit_SUIT_MAN,
			Value: v,
		})
	}
	return tiles
}

// recvState reads and decodes one GameState broadcast from a seat's Send channel.
func recvState(t *testing.T, ch chan []byte) *pb.GameState {
	t.Helper()
	select {
	case data := <-ch:
		st := &pb.GameState{}
		if err := proto.Unmarshal(data, st); err != nil {
			t.Fatalf("unmarshal broadcast: %v", err)
		}
		return st
	case <-time.After(2 * time.Second):
		t.Fatal("no broadcast received")
		return nil
	}
}

func seatPlayer(st *pb.GameState, seat uint32) *pb.PlayerState {
	for _, p := range st.Players {
		if p.Seat == seat {
			return p
		}
	}
	return nil
}

// revealRoom builds a prod-mode room with two seated players and a crafted state.
func revealRoom(t *testing.T, phase pb.GamePhase) *Room {
	t.Helper()
	shanten.Prewarm()
	t.Setenv(revealAllHandsEnv, "") // force the fail-closed (redacting) path

	r := NewRoom("reveal-test", nil, nil)
	r.Engine.State = &pb.GameState{
		Phase:   phase,
		HandNum: 1,
		Players: []*pb.PlayerState{
			{Seat: 0, ClosedHand: manHand(0), HandSize: 9},
			{Seat: 1, ClosedHand: manHand(9), HandSize: 9},
		},
	}
	r.Seats[0] = &Client{UserID: 100, Send: make(chan []byte, 4)}
	return r
}

func assertOpponentRedacted(t *testing.T, st *pb.GameState) {
	t.Helper()
	opp := seatPlayer(st, 1)
	if opp == nil {
		t.Fatal("opponent seat 1 missing from broadcast")
	}
	for _, tile := range opp.ClosedHand {
		if tile.Suit != pb.Suit_SUIT_UNKNOWN {
			t.Fatalf("expected opponent hand redacted (SUIT_UNKNOWN), got suit %v id %d", tile.Suit, tile.Id)
		}
	}
}

func assertOpponentRevealed(t *testing.T, st *pb.GameState) {
	t.Helper()
	opp := seatPlayer(st, 1)
	if opp == nil {
		t.Fatal("opponent seat 1 missing from broadcast")
	}
	for _, tile := range opp.ClosedHand {
		if tile.Suit != pb.Suit_SUIT_MAN {
			t.Fatalf("expected opponent hand revealed (real SUIT_MAN), got suit %v id %d", tile.Suit, tile.Id)
		}
	}
}

// During normal play, production redacts opponents' closed hands (regression guard).
func TestBroadcastRedactsOpponentDuringPlay(t *testing.T) {
	r := revealRoom(t, pb.GamePhase_PHASE_PLAYER_TURN)
	r.BroadcastState()
	assertOpponentRedacted(t, recvState(t, r.Seats[0].Send))
}

// At round end, production reveals all hands so players see the loser's tiles.
func TestBroadcastRevealsOpponentAtRoundEnd(t *testing.T) {
	r := revealRoom(t, pb.GamePhase_PHASE_ROUND_END)
	r.BroadcastState()
	assertOpponentRevealed(t, recvState(t, r.Seats[0].Send))
}

// At match end, production reveals all hands too.
func TestBroadcastRevealsOpponentAtMatchEnd(t *testing.T) {
	r := revealRoom(t, pb.GamePhase_PHASE_MATCH_END)
	r.BroadcastState()
	assertOpponentRevealed(t, recvState(t, r.Seats[0].Send))
}

// SendStateToClient (reconnect path) must also reveal at round end.
func TestSendStateToClientRevealsAtRoundEnd(t *testing.T) {
	r := revealRoom(t, pb.GamePhase_PHASE_ROUND_END)
	r.SendStateToClient(r.Seats[0])
	assertOpponentRevealed(t, recvState(t, r.Seats[0].Send))
}

// SendStateToClient still redacts during play (regression guard).
func TestSendStateToClientRedactsDuringPlay(t *testing.T) {
	r := revealRoom(t, pb.GamePhase_PHASE_PLAYER_TURN)
	r.SendStateToClient(r.Seats[0])
	assertOpponentRedacted(t, recvState(t, r.Seats[0].Send))
}

// The debug god-view opt-in (MAHJONG_DEV_REVEAL_HANDS=1) reveals opponents in
// every phase, including normal play.
func TestDevModeRevealsOpponentDuringPlay(t *testing.T) {
	shanten.Prewarm()
	t.Setenv(revealAllHandsEnv, "1") // explicit god-view opt-in

	r := NewRoom("dev-reveal-test", nil, nil)
	r.Engine.State = &pb.GameState{
		Phase:   pb.GamePhase_PHASE_PLAYER_TURN,
		HandNum: 1,
		Players: []*pb.PlayerState{
			{Seat: 0, ClosedHand: manHand(0), HandSize: 9},
			{Seat: 1, ClosedHand: manHand(9), HandSize: 9},
		},
	}
	r.Seats[0] = &Client{UserID: 100, Send: make(chan []byte, 4)}

	r.BroadcastState()
	assertOpponentRevealed(t, recvState(t, r.Seats[0].Send))
}

// The viewer's own closed hand must never be obfuscated, even during play.
func TestBroadcastKeepsOwnHandDuringPlay(t *testing.T) {
	r := revealRoom(t, pb.GamePhase_PHASE_PLAYER_TURN)
	r.BroadcastState()
	st := recvState(t, r.Seats[0].Send)

	own := seatPlayer(st, 0)
	if own == nil {
		t.Fatal("own seat 0 missing from broadcast")
	}
	for _, tile := range own.ClosedHand {
		if tile.Suit != pb.Suit_SUIT_MAN {
			t.Fatalf("expected own hand intact (real SUIT_MAN), got suit %v id %d", tile.Suit, tile.Id)
		}
	}
}

// An opponent's drawn tile is obfuscated during play and revealed at round end.
func TestBroadcastRedactsThenRevealsOpponentDrawnTile(t *testing.T) {
	r := revealRoom(t, pb.GamePhase_PHASE_PLAYER_TURN)
	drawn := int32(9) // first tile of seat 1's hand (real id 9)
	seatPlayer(r.Engine.State, 1).DrawnTileId = &drawn

	r.BroadcastState()
	st := recvState(t, r.Seats[0].Send)
	opp := seatPlayer(st, 1)
	if opp.DrawnTileId == nil {
		t.Fatal("opponent drawn tile id missing during play")
	}
	if *opp.DrawnTileId < 1000 {
		t.Fatalf("expected opponent drawn tile id obfuscated (>=1000), got %d", *opp.DrawnTileId)
	}

	r.Engine.State.Phase = pb.GamePhase_PHASE_ROUND_END
	r.BroadcastState()
	st = recvState(t, r.Seats[0].Send)
	opp = seatPlayer(st, 1)
	if opp.DrawnTileId == nil || *opp.DrawnTileId != 9 {
		t.Fatalf("expected opponent drawn tile id revealed (9), got %v", opp.DrawnTileId)
	}
}

// opponentHandIDs decodes one broadcast for seat 0 and returns seat 1's
// concealed (fake) tile ids in order.
func opponentHandIDs(t *testing.T, r *Room) []uint32 {
	t.Helper()
	r.BroadcastState()
	st := recvState(t, r.Seats[0].Send)
	opp := seatPlayer(st, 1)
	ids := make([]uint32, 0, len(opp.ClosedHand))
	for _, tile := range opp.ClosedHand {
		ids = append(ids, tile.Id)
	}
	return ids
}

func sameIDs(a, b []uint32) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}

// The obfuscation map must be re-randomized every broadcast (not per deal), so a
// concealed tile never keeps a stable fake id within a hand. This defeats both
// cross-turn tracking of a tile and de-anonymizing the map from revealed
// discards. Two broadcasts of the SAME state must yield different fake ids.
func TestObfuscationRotatesEveryBroadcast(t *testing.T) {
	r := revealRoom(t, pb.GamePhase_PHASE_PLAYER_TURN)

	first := opponentHandIDs(t, r)
	second := opponentHandIDs(t, r) // same hand number, same state

	if len(first) == 0 {
		t.Fatal("expected opponent to hold concealed tiles")
	}
	for _, id := range first {
		if id < 1000 {
			t.Fatalf("expected obfuscated fake id (>=1000), got %d", id)
		}
	}
	if sameIDs(first, second) {
		t.Fatalf("obfuscation did not rotate between broadcasts: %v", first)
	}
}

// Redaction must NOT depend on any deploy-specific env var: with the god-view
// opt-out absent, opponents are obfuscated even though ZEABUR is unset.
func TestRedactionDefaultsClosedWithoutEnv(t *testing.T) {
	shanten.Prewarm()
	t.Setenv(revealAllHandsEnv, "")
	t.Setenv("ZEABUR", "") // the old gate; must no longer matter

	r := NewRoom("default-closed-test", nil, nil)
	r.Engine.State = &pb.GameState{
		Phase:   pb.GamePhase_PHASE_PLAYER_TURN,
		HandNum: 1,
		Players: []*pb.PlayerState{
			{Seat: 0, ClosedHand: manHand(0), HandSize: 9},
			{Seat: 1, ClosedHand: manHand(9), HandSize: 9},
		},
	}
	r.Seats[0] = &Client{UserID: 100, Send: make(chan []byte, 4)}

	r.BroadcastState()
	assertOpponentRedacted(t, recvState(t, r.Seats[0].Send))
}
