package rl

import (
	"testing"

	"github.com/plasma/fh-mahjong/internal/rules/shanten"
	pb "github.com/plasma/fh-mahjong/proto"
	"google.golang.org/protobuf/proto"
)

var routeTestSuits = map[byte]pb.Suit{
	'm': pb.Suit_SUIT_MAN, 'p': pb.Suit_SUIT_PIN, 's': pb.Suit_SUIT_SOU,
	'z': pb.Suit_SUIT_JIHAI, 'f': pb.Suit_SUIT_FLOWER,
}

// routeTestTiles parses "1m4m7m1z" into tiles with distinct ids.
func routeTestTiles(t *testing.T, faces string) []*pb.Tile {
	t.Helper()
	if len(faces)%2 != 0 {
		t.Fatalf("bad faces %q", faces)
	}
	out := make([]*pb.Tile, 0, len(faces)/2)
	for i := 0; i < len(faces); i += 2 {
		suit, ok := routeTestSuits[faces[i+1]]
		if !ok {
			t.Fatalf("bad suit in %q", faces)
		}
		out = append(out, &pb.Tile{Id: uint32(1000 + i), Suit: suit, Value: uint32(faces[i] - '0')})
	}
	return out
}

func routeTestDiscardID(t *testing.T, face string) uint32 {
	t.Helper()
	index, ok := tileFaceIndex42(routeTestTiles(t, face)[0])
	if !ok {
		t.Fatalf("no face index for %s", face)
	}
	return uint32(DiscardBase + index)
}

// discardTurnState is a minimal PLAYER_TURN state where seat 0 must discard.
func discardTurnState(hand []*pb.Tile, wilds []*pb.Tile, openMelds int) *pb.GameState {
	melds := make([]*pb.Meld, openMelds)
	for i := range melds {
		melds[i] = &pb.Meld{}
	}
	return &pb.GameState{
		Phase:        pb.GamePhase_PHASE_PLAYER_TURN,
		ActivePlayer: 0,
		WildTiles:    wilds,
		Players: []*pb.PlayerState{
			{ClosedHand: hand, OpenMelds: melds,
				ValidActions: []*pb.PlayerAction{{Type: pb.ActionType_ACTION_DISCARD}}},
			{}, {}, {},
		},
	}
}

func afterByAction(probe *pb.RouteProbe) map[uint32]*pb.RouteShanten {
	out := make(map[uint32]*pb.RouteShanten, len(probe.Discards))
	for _, d := range probe.Discards {
		out[d.ActionId] = d.After
	}
	return out
}

func TestRouteProbeIndependenceShape(t *testing.T) {
	// 13 independent tiles plus 2m, which conflicts with 1m and 4m.
	hand := routeTestTiles(t, "1m2m4m7m2p5p8p3s6s9s1z2z3z4z")
	probe, err := routeProbe(discardTurnState(hand, nil, 0), 0)
	if err != nil {
		t.Fatalf("probe: %v", err)
	}
	want := shanten.AnalyzeHand(hand, 0, nil).Routes
	if probe.Routes.Independence != 0 || probe.Routes.Standard != int32(want.Standard) ||
		probe.Routes.SevenPairs != int32(want.SevenPairs) || probe.Routes.Overall != int32(want.Overall) {
		t.Fatalf("routes %v, want independence 0 and %+v", probe.Routes, want)
	}
	if len(probe.Discards) != 14 {
		t.Fatalf("want 14 discard options (14 distinct faces), got %d", len(probe.Discards))
	}
	after := afterByAction(probe)
	for face, wantIndependence := range map[string]int32{"2m": 0, "1m": 1, "4m": 1, "7m": 1, "1z": 1} {
		if got := after[routeTestDiscardID(t, face)].Independence; got != wantIndependence {
			t.Errorf("after %s: independence %d, want %d", face, got, wantIndependence)
		}
	}
	if probe.WildCount != 0 || probe.OpenMeldCount != 0 || probe.Seat != 0 {
		t.Fatalf("wild/open/seat = %d/%d/%d", probe.WildCount, probe.OpenMeldCount, probe.Seat)
	}
}

func TestRouteProbeCountsWildsAndFlagsWildDiscards(t *testing.T) {
	// 7z is wild; a wild flower (1f with 2f as the indicator's group) sits in hand too.
	hand := routeTestTiles(t, "1m4m7m2p5p8p3s6s9s1z2z3z7z1f")
	wilds := routeTestTiles(t, "7z1f")
	probe, err := routeProbe(discardTurnState(hand, wilds, 0), 0)
	if err != nil {
		t.Fatalf("probe: %v", err)
	}
	if probe.WildCount != 2 {
		t.Fatalf("wild count %d, want 2", probe.WildCount)
	}
	wildIDs := map[uint32]bool{routeTestDiscardID(t, "7z"): true, routeTestDiscardID(t, "1f"): true}
	for _, d := range probe.Discards {
		if d.IsWild != wildIDs[d.ActionId] {
			t.Errorf("action %d: is_wild %v", d.ActionId, d.IsWild)
		}
	}
	if _, ok := afterByAction(probe)[routeTestDiscardID(t, "1f")]; !ok {
		t.Fatalf("flower wild discard missing from probe")
	}
}

func TestRouteProbeOpenMeldMakesClosedRoutesUnavailable(t *testing.T) {
	hand := routeTestTiles(t, "1m4m7m2p5p8p3s6s9s1z2z")
	probe, err := routeProbe(discardTurnState(hand, nil, 1), 0)
	if err != nil {
		t.Fatalf("probe: %v", err)
	}
	if probe.Routes.Independence != shanten.RouteUnavailable || probe.Routes.SevenPairs != shanten.RouteUnavailable {
		t.Fatalf("closed routes should be unavailable: %v", probe.Routes)
	}
	if probe.OpenMeldCount != 1 {
		t.Fatalf("open meld count %d", probe.OpenMeldCount)
	}
}

func TestEnvRouteProbeMatchesLegalDiscardsAndLeavesStateUnchanged(t *testing.T) {
	config := &pb.EnvConfig{LearningSeats: []uint32{0, 1, 2, 3}, MaxDecisions: 512}
	env := New(config)
	if _, err := env.RouteProbe(&pb.RouteProbeRequest{}); err == nil {
		t.Fatalf("probe before reset should fail")
	}
	reset, err := env.Reset(&pb.EnvResetRequest{Seed: 71, Config: config})
	if err != nil {
		t.Fatalf("reset: %v", err)
	}
	seat := reset.Observation.Seat
	before := proto.Clone(env.game.State).(*pb.GameState)
	probe, err := env.RouteProbe(&pb.RouteProbeRequest{Seat: seat})
	if err != nil {
		t.Fatalf("probe: %v", err)
	}
	if !proto.Equal(before, env.game.State) {
		t.Fatalf("route probe mutated the game state")
	}
	legal, err := legalActionMap(env.game.State, seat)
	if err != nil {
		t.Fatalf("legal: %v", err)
	}
	var want []uint32
	for _, id := range SortedLegalIDs(legal) {
		if id >= DiscardBase && id < DiscardBase+DiscardCount {
			want = append(want, uint32(id))
		}
	}
	if len(want) == 0 {
		t.Fatalf("premise: first decision of seed 71 has no discard")
	}
	var got []uint32
	for _, d := range probe.Discards {
		got = append(got, d.ActionId)
	}
	if len(got) != len(want) {
		t.Fatalf("discard ids %v, want %v", got, want)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("discard ids %v, want %v", got, want)
		}
	}
	other, err := env.RouteProbe(&pb.RouteProbeRequest{Seat: (seat + 1) % 4})
	if err != nil {
		t.Fatalf("probe other seat: %v", err)
	}
	if len(other.Discards) != 0 {
		t.Fatalf("a seat without a discard action should have no discard routes")
	}
}
