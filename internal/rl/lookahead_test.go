package rl

import (
	"testing"

	"github.com/plasma/fh-mahjong/internal/rules/shanten"
	pb "github.com/plasma/fh-mahjong/proto"
)

func lookaheadCell(obs *pb.SeatObservation, channel, face int) float32 {
	return obs.Planes[channelOffset(ObservationPlaneChannels+channel)+face]
}

func testFace(t *testing.T, face string) int {
	t.Helper()
	index, ok := tileFaceIndex42(routeTestTiles(t, face)[0])
	if !ok {
		t.Fatalf("no face index for %s", face)
	}
	return index
}

func faceOfType(t *testing.T, tile shanten.TileType) int {
	t.Helper()
	index, ok := tileFaceIndex42(&pb.Tile{Suit: tile.Suit, Value: tile.Value})
	if !ok {
		t.Fatalf("no face index for %+v", tile)
	}
	return index
}

// claimState is a WAIT_DISCARDS state where seat 0 may answer seat 3's discard.
func claimState(hand []*pb.Tile, discard *pb.Tile, actions []*pb.PlayerAction) *pb.GameState {
	return &pb.GameState{
		Phase:         pb.GamePhase_PHASE_WAIT_DISCARDS,
		ActivePlayer:  3,
		ActiveDiscard: discard,
		Players: []*pb.PlayerState{
			{ClosedHand: hand, ValidActions: actions},
			{}, {}, {Discards: []*pb.Tile{discard}},
		},
	}
}

// bestStandardAfterDiscard is the reference for the pon/chii channels: the
// best (lowest standard shanten, then most live useful tiles) discard after
// the call, computed from an explicitly written post-call hand.
func bestStandardAfterDiscard(rest []*pb.Tile, melds int, wilds []*pb.Tile, visible [42]int) (int, int) {
	best, bestLive := shanten.RouteUnavailable, 0
	for _, option := range shanten.AnalyzeHand(rest, melds, wilds).DiscardOptions {
		live := liveUsefulCount(option.UsefulTiles, visible)
		if option.After.Standard < best || (option.After.Standard == best && live > bestLive) {
			best, bestLive = option.After.Standard, live
		}
	}
	return best, bestLive
}

func TestLookaheadVersionZeroUnchangedAndVersionOneShiftsOracle(t *testing.T) {
	hand := routeTestTiles(t, "1m2m4m7m2p5p8p3s6s9s1z2z3z4z")
	state := discardTurnState(hand, nil, 0)
	state.Players[1].ClosedHand = routeTestTiles(t, "1p1p1p")
	for _, oracle := range []bool{false, true} {
		v0, err := encodeObservation(state, 0, 0, oracle, 0, nil, 0)
		if err != nil {
			t.Fatalf("v0: %v", err)
		}
		v1, err := encodeObservation(state, 0, 0, oracle, 1, nil, 0)
		if err != nil {
			t.Fatalf("v1: %v", err)
		}
		if int(v0.PlaneChannels) != observationChannels(oracle, 0) || int(v1.PlaneChannels) != int(v0.PlaneChannels)+13 {
			t.Fatalf("oracle=%v channels v0=%d v1=%d", oracle, v0.PlaneChannels, v1.PlaneChannels)
		}
		for i := 0; i < channelOffset(ObservationPlaneChannels); i++ {
			if v0.Planes[i] != v1.Planes[i] {
				t.Fatalf("oracle=%v public plane cell %d differs", oracle, i)
			}
		}
		if oracle {
			for i := 0; i < channelOffset(12); i++ {
				if v0.Planes[channelOffset(39)+i] != v1.Planes[channelOffset(52)+i] {
					t.Fatalf("oracle cell %d not shifted to channel 52+", i)
				}
			}
		}
		for i := range v0.Scalars {
			if v0.Scalars[i] != v1.Scalars[i] {
				t.Fatalf("scalar %d differs", i)
			}
		}
		if string(v0.ActionMask) != string(v1.ActionMask) {
			t.Fatalf("mask differs")
		}
	}
	if _, err := encodeObservation(state, 0, 0, false, 2, nil, 0); err == nil {
		t.Fatalf("version 2 must be rejected")
	}
}

func TestLiveUsefulCountSubtractsVisibleCopiesAndIndicator(t *testing.T) {
	state := &pb.GameState{
		WildTiles: routeTestTiles(t, "5m"),
		Players:   []*pb.PlayerState{{}, {Discards: routeTestTiles(t, "3s3s")}, {}, {}},
	}
	useful := []shanten.UsefulTile{
		{Suit: pb.Suit_SUIT_SOU, Value: 3, Remaining: 3}, // 2 discarded -> 1 live
		{Suit: pb.Suit_SUIT_MAN, Value: 5, Remaining: 4}, // indicator face-up -> 3 live
		{Suit: pb.Suit_SUIT_PIN, Value: 1, Remaining: 2}, // unseen -> 2 live
	}
	if got := liveUsefulCount(useful, publicSeenCounts(state)); got != 6 {
		t.Fatalf("live useful %d, want 6", got)
	}
	state.WildTiles = []*pb.Tile{{Suit: pb.Suit_SUIT_FLOWER, Value: 2}}
	if got := liveUsefulCount(useful, publicSeenCounts(state)); got != 7 {
		t.Fatalf("flower indicator hides no suited copy: live %d, want 7", got)
	}
}

func TestLookaheadDiscardChannelsMatchAnalysis(t *testing.T) {
	hand := routeTestTiles(t, "1m2m3m4m4m5p6p7p3s4s1z1z5z6z")
	wilds := routeTestTiles(t, "9p")
	state := discardTurnState(hand, wilds, 0)
	state.Players[1].Discards = routeTestTiles(t, "2s5s")
	obs, err := encodeObservation(state, 0, 0, false, 1, nil, 0)
	if err != nil {
		t.Fatalf("encode: %v", err)
	}
	visible := publicSeenCounts(state)
	liveBelowRaw := false
	for _, option := range shanten.AnalyzeHand(hand, 0, wilds).DiscardOptions {
		face := faceOfType(t, option.Discard)
		live := liveUsefulCount(option.UsefulTiles, visible)
		liveBelowRaw = liveBelowRaw || live < option.TotalUseful
		want := map[int]float32{
			0: normalizeShanten(option.After.Overall),
			1: normalizeShanten(option.After.Standard),
			2: normalizeShanten(option.After.SevenPairs),
			3: normalizeShanten(option.After.Independence),
			4: normalizeUsefulTileCount(option.TotalUseful),
			5: normalizeUsefulTileCount(live),
			6: publicDangerScore(state, 0, &pb.Tile{Suit: option.Discard.Suit, Value: option.Discard.Value}),
		}
		for channel, value := range want {
			if got := lookaheadCell(obs, channel, face); got != value {
				t.Fatalf("discard %+v channel %d: got %v, want %v", option.Discard, channel, got, value)
			}
		}
	}
	if !liveBelowRaw {
		t.Fatalf("the visible 2s/5s should lower some discard's live count below its raw count")
	}
	for channel := 0; channel < 13; channel++ {
		if got := lookaheadCell(obs, channel, testFace(t, "9m")); got != 0 {
			t.Fatalf("face 9m is not in hand but channel %d = %v", channel, got)
		}
	}
}

func TestLookaheadPonAndChiiChannels(t *testing.T) {
	hand := routeTestTiles(t, "2m4m5m6m6m7p8p9p1s1s3z3z5z")
	discard := &pb.Tile{Id: 900, Suit: pb.Suit_SUIT_MAN, Value: 6}
	sixes := []*pb.Tile{hand[3], hand[4]} // 6m 6m
	actions := []*pb.PlayerAction{
		{Type: pb.ActionType_ACTION_PON, Tile: discard, MeldTiles: sixes, TargetPlayer: 3},
		// 4m5m + 6m is the only chii (no 7m or 8m in hand); its middle face is 5m.
		{Type: pb.ActionType_ACTION_CHII, Tile: discard, MeldTiles: []*pb.Tile{hand[1], hand[2]}, TargetPlayer: 3},
	}
	state := claimState(hand, discard, actions)
	obs, err := encodeObservation(state, 0, 0, false, 1, nil, 0)
	if err != nil {
		t.Fatalf("encode: %v", err)
	}
	visible := publicSeenCounts(state)

	ponRest := routeTestTiles(t, "2m4m5m7p8p9p1s1s3z3z5z")
	ponShanten, ponLive := bestStandardAfterDiscard(ponRest, 1, nil, visible)
	if got := lookaheadCell(obs, 7, testFace(t, "6m")); got != normalizeShanten(ponShanten) {
		t.Fatalf("pon shanten %v, want %v", got, normalizeShanten(ponShanten))
	}
	if got := lookaheadCell(obs, 8, testFace(t, "6m")); got != normalizeUsefulTileCount(ponLive) {
		t.Fatalf("pon live %v, want %v", got, normalizeUsefulTileCount(ponLive))
	}

	chiiRest := routeTestTiles(t, "2m6m6m7p8p9p1s1s3z3z5z")
	chiiShanten, chiiLive := bestStandardAfterDiscard(chiiRest, 1, nil, visible)
	middle := testFace(t, "5m") // 4m5m6m
	if got := lookaheadCell(obs, 9, middle); got != normalizeShanten(chiiShanten) {
		t.Fatalf("chii shanten %v, want %v", got, normalizeShanten(chiiShanten))
	}
	if got := lookaheadCell(obs, 10, middle); got != normalizeUsefulTileCount(chiiLive) {
		t.Fatalf("chii live %v, want %v", got, normalizeUsefulTileCount(chiiLive))
	}
	if got := lookaheadCell(obs, 9, testFace(t, "4m")); got != 0 {
		t.Fatalf("chii must sit in the middle face, not the start face")
	}
}

func TestLookaheadKanMeldCounts(t *testing.T) {
	// Closed kan on own turn: 4 tiles leave, one more meld.
	hand := routeTestTiles(t, "1m1m1m1m3p4p5p7s8s2z2z6z7z9s")
	state := discardTurnState(hand, nil, 0)
	state.Players[0].ValidActions = append(state.Players[0].ValidActions,
		&pb.PlayerAction{Type: pb.ActionType_ACTION_KAN, MeldTiles: hand[:4]})
	obs, err := encodeObservation(state, 0, 0, false, 1, nil, 0)
	if err != nil {
		t.Fatalf("encode closed kan: %v", err)
	}
	rest := routeTestTiles(t, "3p4p5p7s8s2z2z6z7z9s")
	want := shanten.AnalyzeHand(rest, 1, nil)
	if got := lookaheadCell(obs, 11, testFace(t, "1m")); got != normalizeShanten(want.Routes.Standard) {
		t.Fatalf("closed kan shanten %v, want %v", got, normalizeShanten(want.Routes.Standard))
	}
	if got := lookaheadCell(obs, 12, testFace(t, "1m")); got != normalizeUsefulTileCount(liveUsefulCount(want.UsefulTiles, publicSeenCounts(state))) {
		t.Fatalf("closed kan live %v", got)
	}

	// Upgraded kan: one tile leaves, the pon becomes a kan, the meld count is unchanged.
	pon := &pb.Meld{Type: pb.ActionType_ACTION_PON, Tiles: routeTestTiles(t, "7z7z7z")}
	upHand := routeTestTiles(t, "7z2m3m4m5p6p7p1s2s3s9s")
	upState := discardTurnState(upHand, nil, 0)
	upState.Players[0].OpenMelds = []*pb.Meld{pon}
	upState.Players[0].ValidActions = append(upState.Players[0].ValidActions,
		&pb.PlayerAction{Type: pb.ActionType_ACTION_KAN, MeldTiles: upHand[:1]})
	upObs, err := encodeObservation(upState, 0, 0, false, 1, nil, 0)
	if err != nil {
		t.Fatalf("encode upgraded kan: %v", err)
	}
	upWant := shanten.AnalyzeHand(upHand[1:], 1, nil)
	if got := lookaheadCell(upObs, 11, testFace(t, "7z")); got != normalizeShanten(upWant.Routes.Standard) {
		t.Fatalf("upgraded kan shanten %v, want %v (meld count must stay 1)", got, normalizeShanten(upWant.Routes.Standard))
	}
}

func TestLookaheadRejectsCallTilesMissingFromHand(t *testing.T) {
	hand := routeTestTiles(t, "2m4m5m6m6m7p8p9p1s1s3z3z5z")
	discard := &pb.Tile{Id: 900, Suit: pb.Suit_SUIT_MAN, Value: 6}
	ghost := []*pb.Tile{{Id: 4242, Suit: pb.Suit_SUIT_MAN, Value: 6}, hand[4]}
	state := claimState(hand, discard, []*pb.PlayerAction{
		{Type: pb.ActionType_ACTION_PON, Tile: discard, MeldTiles: ghost, TargetPlayer: 3},
	})
	if _, err := encodeObservation(state, 0, 0, false, 1, nil, 0); err == nil {
		t.Fatalf("a call revealing a tile not in the closed hand must be an encoder error")
	}
	if _, err := encodeObservation(state, 0, 0, false, 0, nil, 0); err != nil {
		t.Fatalf("version 0 never inspects meld tiles: %v", err)
	}
}

func TestEnvCarriesLookaheadVersion(t *testing.T) {
	config := &pb.EnvConfig{LearningSeats: []uint32{0, 1, 2, 3}, LookaheadVersion: 1}
	env := New(config)
	reset, err := env.Reset(&pb.EnvResetRequest{Seed: 7, Config: config})
	if err != nil {
		t.Fatalf("reset: %v", err)
	}
	if reset.Observation.PlaneChannels != 52 {
		t.Fatalf("channels %d, want 52", reset.Observation.PlaneChannels)
	}
	bad := &pb.EnvConfig{LearningSeats: []uint32{0}, LookaheadVersion: 2}
	if _, err := New(bad).Reset(&pb.EnvResetRequest{Seed: 7, Config: bad}); err == nil {
		t.Fatalf("version 2 must be rejected at reset")
	}
}
