package api

import (
	"testing"

	"github.com/plasma/fh-mahjong/internal/bot"
	pb "github.com/plasma/fh-mahjong/proto"
)

// GAP 1: seats must be recorded with their true kind/difficulty/policy
// identity, driven by the matchmaker-provided SeatInfos.
func TestRegisterPaipuPlayers_SeatInfoLabels(t *testing.T) {
	room := NewRoom("labels-room", nil, nil)
	room.SeatInfos = map[uint32]SeatInfo{
		0: {Kind: "human", Name: "Alice", UserID: 101}, // reserved, NOT connected
		1: {Kind: "bot", Difficulty: pb.Difficulty_DIFFICULTY_HEURISTIC},
		2: {Kind: "bot", Difficulty: pb.Difficulty_DIFFICULTY_RL, PolicyID: "champ.pt@step9"},
		3: {Kind: "human", Name: "Bob", UserID: 102},
	}
	room.SeatOwners[0] = 101
	room.SeatOwners[3] = 102
	room.Seats[3] = &Client{UserID: 102, Username: "Bob"} // only seat 3 is live

	room.registerPaipuPlayers()
	paipu := room.Engine.Recorder.Finalize([4]int32{})

	if p := paipu.Players[0]; p.Kind != "human" || p.UserID != 101 || p.Name != "Alice" {
		t.Fatalf("reserved-but-offline human misattributed: %+v", p)
	}
	if p := paipu.Players[1]; p.Kind != "bot" || p.Difficulty != "heuristic" || p.PolicyID != "" {
		t.Fatalf("heuristic seat mislabeled: %+v", p)
	}
	if p := paipu.Players[2]; p.Kind != "bot" || p.Difficulty != "rl" || p.PolicyID != "champ.pt@step9" {
		t.Fatalf("RL seat mislabeled: %+v", p)
	}
	if p := paipu.Players[2]; p.Name != "Bot 3 (RL)" {
		t.Fatalf("RL seat display name = %q, want %q", p.Name, "Bot 3 (RL)")
	}
	if p := paipu.Players[3]; p.Kind != "human" || p.UserID != 102 || p.Name != "Bob" {
		t.Fatalf("connected human misattributed: %+v", p)
	}
}

// GAP 2: with no SeatInfos (queue matches, legacy paths), seat ownership —
// not the live socket map — decides whether a seat is human.
func TestRegisterPaipuPlayers_SeatOwnerFallback(t *testing.T) {
	room := NewRoom("owner-room", nil, nil)
	room.SeatOwners[0] = 42 // reserved, never connected

	room.registerPaipuPlayers()
	paipu := room.Engine.Recorder.Finalize([4]int32{})

	if p := paipu.Players[0]; p.Kind != "human" || p.UserID != 42 {
		t.Fatalf("owned seat recorded as %+v, want human userId=42", p)
	}
	if p := paipu.Players[1]; p.Kind != "bot" {
		t.Fatalf("unowned seat should be a bot, got %+v", p)
	}
}

// End-to-end: StartPrivateTable must thread seat composition (incl. the RL
// policy identity) into the room so the paipu records it.
func TestStartPrivateTable_RecordsSeatComposition(t *testing.T) {
	hub := NewHub()
	hub.BindRoom = make(chan RoomBind, 1)
	m := NewMatchmaker(NewInMemoryQueue(), nil, hub)
	m.SeatPolicyResolver = func(d pb.Difficulty, _ string, _ uint32) (bot.Policy, error) {
		if d == pb.Difficulty_DIFFICULTY_RL {
			return stubPolicy{}, nil
		}
		return bot.NewPolicy(d)
	}
	m.RLPolicyIdentity = func() string { return "champ.pt@step9" }

	if _, err := m.CreatePrivateTable("t1", 101, "alice"); err != nil {
		t.Fatalf("join: %v", err)
	}
	if _, err := m.MutatePrivateTable("t1", func(pt *PrivateTable) error {
		if err := pt.setSeat(1, "bot", pb.Difficulty_DIFFICULTY_HEURISTIC); err != nil {
			return err
		}
		if err := pt.setSeat(2, "bot", pb.Difficulty_DIFFICULTY_RL); err != nil {
			return err
		}
		return pt.setSeat(3, "bot", pb.Difficulty_DIFFICULTY_HEURISTIC)
	}); err != nil {
		t.Fatalf("configure seats: %v", err)
	}

	if _, err := m.StartPrivateTable("t1", 101); err != nil {
		t.Fatalf("start: %v", err)
	}
	bind := <-hub.BindRoom

	// The host has NOT opened a websocket yet (the room normally starts via
	// the hub before clients connect). Simulate the hub's owner binding only.
	for seat, uid := range bind.Seats {
		bind.Room.SeatOwners[seat] = uid
	}
	bind.Room.registerPaipuPlayers()
	paipu := bind.Room.Engine.Recorder.Finalize([4]int32{})

	if p := paipu.Players[0]; p.Kind != "human" || p.UserID != 101 || p.Name != "alice" {
		t.Fatalf("host seat misattributed: %+v", p)
	}
	if p := paipu.Players[1]; p.Kind != "bot" || p.Difficulty != "heuristic" {
		t.Fatalf("seat 1 mislabeled: %+v", p)
	}
	if p := paipu.Players[2]; p.Kind != "bot" || p.Difficulty != "rl" || p.PolicyID != "champ.pt@step9" {
		t.Fatalf("seat 2 mislabeled: %+v", p)
	}
}

// End-to-end: a default private table must start a Chongci match, so it can
// actually reach PHASE_MATCH_END and persist as a completed, listable paipu.
// Classic mode is endless and would never produce one.
func TestStartPrivateTable_DefaultsToChongciMatch(t *testing.T) {
	hub := NewHub()
	hub.BindRoom = make(chan RoomBind, 1)
	m := NewMatchmaker(NewInMemoryQueue(), nil, hub)
	m.SeatPolicyResolver = func(d pb.Difficulty, _ string, _ uint32) (bot.Policy, error) { return bot.NewPolicy(d) }

	if _, err := m.CreatePrivateTable("t-chongci", 101, "alice"); err != nil {
		t.Fatalf("create: %v", err)
	}
	if _, err := m.MutatePrivateTable("t-chongci", func(pt *PrivateTable) error {
		if err := pt.setSeat(1, "bot", pb.Difficulty_DIFFICULTY_HEURISTIC); err != nil {
			return err
		}
		if err := pt.setSeat(2, "bot", pb.Difficulty_DIFFICULTY_HEURISTIC); err != nil {
			return err
		}
		return pt.setSeat(3, "bot", pb.Difficulty_DIFFICULTY_HEURISTIC)
	}); err != nil {
		t.Fatalf("configure seats: %v", err)
	}
	if _, err := m.StartPrivateTable("t-chongci", 101); err != nil {
		t.Fatalf("start: %v", err)
	}
	bind := <-hub.BindRoom

	if got := bind.Room.Engine.State.MatchMode; got != pb.MatchMode_MATCH_MODE_CHONGCI {
		t.Fatalf("started default private table MatchMode = %v, want CHONGCI", got)
	}
	if cfg := bind.Room.Engine.State.ChongciConfig; cfg == nil || cfg.MaxHands != 50 {
		t.Fatalf("started default private table ChongciConfig = %+v, want MaxHands=50", cfg)
	}
}

// A private table the host switches to classic must start a single-hand match
// ("1-hand chongci"): the engine stays in classic mode but carries a 1-hand cap
// so the game reaches MATCH_END and is recorded as a listable paipu.
func TestStartPrivateTable_ClassicIsSingleHand(t *testing.T) {
	hub := NewHub()
	hub.BindRoom = make(chan RoomBind, 1)
	m := NewMatchmaker(NewInMemoryQueue(), nil, hub)
	m.SeatPolicyResolver = func(d pb.Difficulty, _ string, _ uint32) (bot.Policy, error) { return bot.NewPolicy(d) }

	if _, err := m.CreatePrivateTable("t-classic", 101, "alice"); err != nil {
		t.Fatalf("create: %v", err)
	}
	if _, err := m.MutatePrivateTable("t-classic", func(pt *PrivateTable) error {
		if err := pt.setMatchMode("classic", nil); err != nil {
			return err
		}
		if err := pt.setSeat(1, "bot", pb.Difficulty_DIFFICULTY_HEURISTIC); err != nil {
			return err
		}
		if err := pt.setSeat(2, "bot", pb.Difficulty_DIFFICULTY_HEURISTIC); err != nil {
			return err
		}
		return pt.setSeat(3, "bot", pb.Difficulty_DIFFICULTY_HEURISTIC)
	}); err != nil {
		t.Fatalf("configure: %v", err)
	}
	if _, err := m.StartPrivateTable("t-classic", 101); err != nil {
		t.Fatalf("start: %v", err)
	}
	bind := <-hub.BindRoom

	if got := bind.Room.Engine.State.MatchMode; got != pb.MatchMode_MATCH_MODE_CLASSIC {
		t.Fatalf("classic table MatchMode = %v, want CLASSIC (a capped classic stays classic)", got)
	}
	if cfg := bind.Room.Engine.State.ChongciConfig; cfg == nil || cfg.MaxHands != 1 {
		t.Fatalf("classic table ChongciConfig = %+v, want MaxHands=1 (single-hand cap)", cfg)
	}
}
