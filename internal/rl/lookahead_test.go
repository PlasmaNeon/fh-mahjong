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

// refUseful is the reference for the useful-tile channels: the draws that
// lower the shanten, or at tenpai the draws that complete the hand.
func refUseful(rest []*pb.Tile, melds int, wilds []*pb.Tile, routeShanten int, useful []shanten.UsefulTile, total int) ([]shanten.UsefulTile, int) {
	if routeShanten == 0 {
		return shanten.WinningTiles(rest, melds, wilds)
	}
	return useful, total
}

// bestStandardAfterDiscard is the reference for the pon/chii channels: the
// best (lowest standard shanten, then most live useful tiles) discard after
// the call, computed from an explicitly written post-call hand. `visible`
// must already include the call's meld tiles.
func bestStandardAfterDiscard(t *testing.T, rest []*pb.Tile, melds int, wilds []*pb.Tile, visible [42]int) (int, int) {
	t.Helper()
	best, bestLive := shanten.RouteUnavailable, 0
	for _, option := range shanten.AnalyzeHand(rest, melds, wilds).DiscardOptions {
		after, discarded := handWithoutFace(rest, option.Discard)
		if discarded == nil {
			t.Fatalf("option %+v not in hand", option.Discard)
		}
		useful, _ := refUseful(after, melds, wilds, option.After.Standard, option.UsefulTiles, option.TotalUseful)
		live := liveUsefulCount(useful, seenAfterMoving(visible, discarded))
		if option.After.Standard < best || (option.After.Standard == best && live > bestLive) {
			best, bestLive = option.After.Standard, live
		}
	}
	return best, bestLive
}

// assertDiscardChannels checks every discard channel against the reference.
func assertDiscardChannels(t *testing.T, state *pb.GameState) *pb.SeatObservation {
	t.Helper()
	obs, err := encodeObservation(state, 0, 0, false, 1, nil, 0)
	if err != nil {
		t.Fatalf("encode: %v", err)
	}
	player := state.Players[0]
	melds := len(player.OpenMelds)
	visible := publicSeenCounts(state)
	for _, option := range shanten.AnalyzeHand(player.ClosedHand, melds, state.WildTiles).DiscardOptions {
		face := faceOfType(t, option.Discard)
		rest, discarded := handWithoutFace(player.ClosedHand, option.Discard)
		useful, total := refUseful(rest, melds, state.WildTiles, option.After.Overall, option.UsefulTiles, option.TotalUseful)
		want := map[int]float32{
			0: normalizeShanten(option.After.Overall),
			1: normalizeShanten(option.After.Standard),
			2: normalizeShanten(option.After.SevenPairs),
			3: normalizeShanten(option.After.Independence),
			4: normalizeUsefulTileCount(total),
			5: normalizeUsefulTileCount(liveUsefulCount(useful, seenAfterMoving(visible, discarded))),
			6: publicDangerScore(state, 0, discarded),
		}
		for channel, value := range want {
			if got := lookaheadCell(obs, channel, face); got != value {
				t.Fatalf("discard %+v channel %d: got %v, want %v", option.Discard, channel, got, value)
			}
		}
	}
	return obs
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
	plain := discardTurnState(routeTestTiles(t, "1m2m3m4m4m5p6p7p3s4s1z1z5z6z"), routeTestTiles(t, "9p"), 0)
	plain.Players[1].Discards = routeTestTiles(t, "2s5s")
	obs := assertDiscardChannels(t, plain)
	for channel := 0; channel < 13; channel++ {
		if got := lookaheadCell(obs, channel, testFace(t, "9m")); got != 0 {
			t.Fatalf("face 9m is not in hand but channel %d = %v", channel, got)
		}
	}
	// A held wild (9p) is a legal discard with its own option.
	assertDiscardChannels(t, discardTurnState(routeTestTiles(t, "1m2m3m4m4m5p6p7p3s4s1z1z9p6z"), routeTestTiles(t, "9p"), 0))
	// Independence alive: 13 disconnected tiles plus 2m.
	independent := discardTurnState(routeTestTiles(t, "1m2m4m7m2p5p8p3s6s9s1z2z3z4z"), nil, 0)
	obs = assertDiscardChannels(t, independent)
	if got := lookaheadCell(obs, 3, testFace(t, "2m")); got != normalizeShanten(0) {
		t.Fatalf("discarding 2m leaves Independence tenpai: channel 42 = %v", got)
	}
	if got := lookaheadCell(obs, 4, testFace(t, "2m")); got == 0 {
		t.Fatalf("an Independence-tenpai discard must count its winning tiles")
	}
}

func TestLookaheadUsefulAtTenpaiCountsWinsAndOwnDiscards(t *testing.T) {
	// 123m 456p 789s 111z 5m5m. Discard 5m: single wait on 5m, 4 - 1 held = 3
	// raw, and the discarded 5m is in the seat's own river, so 2 live.
	state := discardTurnState(routeTestTiles(t, "1m2m3m4p5p6p7s8s9s1z1z1z5m5m"), nil, 0)
	obs, err := encodeObservation(state, 0, 0, false, 1, nil, 0)
	if err != nil {
		t.Fatalf("encode: %v", err)
	}
	if got := lookaheadCell(obs, 4, testFace(t, "5m")); got != normalizeUsefulTileCount(3) {
		t.Fatalf("discard 5m raw useful %v, want 3/64", got)
	}
	if got := lookaheadCell(obs, 5, testFace(t, "5m")); got != normalizeUsefulTileCount(2) {
		t.Fatalf("discard 5m live useful %v, want 2/64", got)
	}
	// Discard 1m: 23m waits on 1m (4, one now in the river) or 4m (4): raw 8, live 7.
	if got := lookaheadCell(obs, 4, testFace(t, "1m")); got != normalizeUsefulTileCount(8) {
		t.Fatalf("discard 1m raw useful %v, want 8/64", got)
	}
	if got := lookaheadCell(obs, 5, testFace(t, "1m")); got != normalizeUsefulTileCount(7) {
		t.Fatalf("discard 1m live useful %v, want 7/64", got)
	}
}

func TestLookaheadKanLiveExcludesTheKanTiles(t *testing.T) {
	// Closed kan of 1m leaves 23m 567p 123s 99s: tenpai on 1m or 4m. All four 1m
	// sit in the kan, so only the four 4m are live.
	hand := routeTestTiles(t, "1m1m1m1m2m3m5p6p7p1s2s3s9s9s")
	state := discardTurnState(hand, nil, 0)
	state.Players[0].ValidActions = append(state.Players[0].ValidActions,
		&pb.PlayerAction{Type: pb.ActionType_ACTION_KAN, MeldTiles: hand[:4]})
	obs, err := encodeObservation(state, 0, 0, false, 1, nil, 0)
	if err != nil {
		t.Fatalf("encode: %v", err)
	}
	if got := lookaheadCell(obs, 11, testFace(t, "1m")); got != normalizeShanten(0) {
		t.Fatalf("kan shanten %v, want tenpai", got)
	}
	if got := lookaheadCell(obs, 12, testFace(t, "1m")); got != normalizeUsefulTileCount(4) {
		t.Fatalf("kan live %v, want 4/64", got)
	}
}

func TestLookaheadDirectKanAndThreeChiiVariants(t *testing.T) {
	discard := &pb.Tile{Id: 900, Suit: pb.Suit_SUIT_MAN, Value: 6}
	hand := routeTestTiles(t, "4m5m7m8m2p3p4p7s8s9s1z1z5z")
	actions := []*pb.PlayerAction{
		{Type: pb.ActionType_ACTION_CHII, Tile: discard, MeldTiles: []*pb.Tile{hand[0], hand[1]}, TargetPlayer: 3}, // 456m
		{Type: pb.ActionType_ACTION_CHII, Tile: discard, MeldTiles: []*pb.Tile{hand[1], hand[2]}, TargetPlayer: 3}, // 567m
		{Type: pb.ActionType_ACTION_CHII, Tile: discard, MeldTiles: []*pb.Tile{hand[2], hand[3]}, TargetPlayer: 3}, // 678m
	}
	state := claimState(hand, discard, actions)
	obs, err := encodeObservation(state, 0, 0, false, 1, nil, 0)
	if err != nil {
		t.Fatalf("encode: %v", err)
	}
	visible := publicSeenCounts(state)
	for _, c := range []struct {
		middle, rest string
		meld         []*pb.Tile
	}{
		{"5m", "7m8m2p3p4p7s8s9s1z1z5z", actions[0].MeldTiles},
		{"6m", "4m8m2p3p4p7s8s9s1z1z5z", actions[1].MeldTiles},
		{"7m", "4m5m2p3p4p7s8s9s1z1z5z", actions[2].MeldTiles},
	} {
		wantShanten, wantLive := bestStandardAfterDiscard(t, routeTestTiles(t, c.rest), 1, nil, seenAfterMoving(visible, c.meld...))
		if got := lookaheadCell(obs, 9, testFace(t, c.middle)); got != normalizeShanten(wantShanten) {
			t.Fatalf("chii middle %s shanten %v, want %v", c.middle, got, normalizeShanten(wantShanten))
		}
		if got := lookaheadCell(obs, 10, testFace(t, c.middle)); got != normalizeUsefulTileCount(wantLive) {
			t.Fatalf("chii middle %s live %v, want %v", c.middle, got, normalizeUsefulTileCount(wantLive))
		}
	}

	kanHand := routeTestTiles(t, "6m6m6m2p3p4p7s8s9s1z1z5z6z")
	kan := claimState(kanHand, discard, []*pb.PlayerAction{
		{Type: pb.ActionType_ACTION_KAN, Tile: discard, MeldTiles: kanHand[:3], TargetPlayer: 3},
		{Type: pb.ActionType_ACTION_PON, Tile: discard, MeldTiles: kanHand[:2], TargetPlayer: 3},
	})
	kanObs, err := encodeObservation(kan, 0, 0, false, 1, nil, 0)
	if err != nil {
		t.Fatalf("encode direct kan: %v", err)
	}
	rest := routeTestTiles(t, "2p3p4p7s8s9s1z1z5z6z")
	analysis := shanten.AnalyzeHand(rest, 1, nil)
	useful, _ := refUseful(rest, 1, nil, analysis.Routes.Standard, analysis.UsefulTiles, analysis.TotalUseful)
	if got := lookaheadCell(kanObs, 11, testFace(t, "6m")); got != normalizeShanten(analysis.Routes.Standard) {
		t.Fatalf("direct kan shanten %v, want %v", got, normalizeShanten(analysis.Routes.Standard))
	}
	wantLive := liveUsefulCount(useful, seenAfterMoving(publicSeenCounts(kan), kanHand[:3]...))
	if got := lookaheadCell(kanObs, 12, testFace(t, "6m")); got != normalizeUsefulTileCount(wantLive) {
		t.Fatalf("direct kan live %v, want %v", got, normalizeUsefulTileCount(wantLive))
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
	ponShanten, ponLive := bestStandardAfterDiscard(t, ponRest, 1, nil, seenAfterMoving(visible, sixes...))
	if got := lookaheadCell(obs, 7, testFace(t, "6m")); got != normalizeShanten(ponShanten) {
		t.Fatalf("pon shanten %v, want %v", got, normalizeShanten(ponShanten))
	}
	if got := lookaheadCell(obs, 8, testFace(t, "6m")); got != normalizeUsefulTileCount(ponLive) {
		t.Fatalf("pon live %v, want %v", got, normalizeUsefulTileCount(ponLive))
	}

	chiiRest := routeTestTiles(t, "2m6m6m7p8p9p1s1s3z3z5z")
	chiiShanten, chiiLive := bestStandardAfterDiscard(t, chiiRest, 1, nil, seenAfterMoving(visible, hand[1], hand[2]))
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
	wantUseful, _ := refUseful(rest, 1, nil, want.Routes.Standard, want.UsefulTiles, want.TotalUseful)
	if got := lookaheadCell(obs, 12, testFace(t, "1m")); got != normalizeUsefulTileCount(liveUsefulCount(wantUseful, seenAfterMoving(publicSeenCounts(state), hand[:4]...))) {
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
	upUseful, _ := refUseful(upHand[1:], 1, nil, upWant.Routes.Standard, upWant.UsefulTiles, upWant.TotalUseful)
	if got := lookaheadCell(upObs, 12, testFace(t, "7z")); got != normalizeUsefulTileCount(liveUsefulCount(upUseful, seenAfterMoving(publicSeenCounts(upState), upHand[0]))) {
		t.Fatalf("upgraded kan live %v", got)
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
