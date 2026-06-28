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
	t.Setenv("ZEABUR", "1") // force the production redaction path

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

// Dev mode (ZEABUR unset) must be completely unchanged: opponents are visible in
// every phase, including normal play.
func TestDevModeRevealsOpponentDuringPlay(t *testing.T) {
	shanten.Prewarm()
	t.Setenv("ZEABUR", "") // dev: isProd == false

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

// The obfuscation map must be regenerated each round so that real tile ids
// revealed at round end can't be correlated to fake ids used in later rounds.
func TestObfuscationMapRegeneratesEachRound(t *testing.T) {
	r := revealRoom(t, pb.GamePhase_PHASE_PLAYER_TURN)

	r.BroadcastState()
	_ = recvState(t, r.Seats[0].Send)

	before := make(map[uint32]uint32, len(r.TileObfuscationMap))
	for k, v := range r.TileObfuscationMap {
		before[k] = v
	}

	// New deal: hand number advances.
	r.Engine.State.HandNum = 2
	r.BroadcastState()
	_ = recvState(t, r.Seats[0].Send)

	identical := true
	for k, v := range before {
		if r.TileObfuscationMap[k] != v {
			identical = false
			break
		}
	}
	if identical {
		t.Fatal("expected obfuscation map to be regenerated for a new round, but it was unchanged")
	}
}

// Within a single round the obfuscation map must stay stable, so opponent tiles
// keep consistent fake ids across broadcasts (tile-flight animations rely on it).
func TestObfuscationMapStableWithinRound(t *testing.T) {
	r := revealRoom(t, pb.GamePhase_PHASE_PLAYER_TURN)

	r.BroadcastState()
	_ = recvState(t, r.Seats[0].Send)

	before := make(map[uint32]uint32, len(r.TileObfuscationMap))
	for k, v := range r.TileObfuscationMap {
		before[k] = v
	}

	// Same hand number => same round => map unchanged.
	r.BroadcastState()
	_ = recvState(t, r.Seats[0].Send)

	for k, v := range before {
		if r.TileObfuscationMap[k] != v {
			t.Fatalf("obfuscation map changed within the same round at key %d: %d -> %d", k, v, r.TileObfuscationMap[k])
		}
	}
}
