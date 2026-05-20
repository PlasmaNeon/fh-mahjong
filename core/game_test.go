package core_test

import (
	"testing"

	"github.com/plasma/fh-mahjong/core"
	pb "github.com/plasma/fh-mahjong/proto"
	"github.com/plasma/fh-mahjong/rules"
)

func TestNewGame_ClassicDefault(t *testing.T) {
	r := &rules.HometownRuleset{}
	g := core.NewGame("test-classic", r, core.MatchOptions{})

	if got := g.State.MatchMode; got != pb.MatchMode_MATCH_MODE_CLASSIC {
		t.Fatalf("default MatchMode = %v, want CLASSIC", got)
	}
	if g.State.ChongciConfig != nil {
		t.Fatalf("classic-mode ChongciConfig should be nil, got %+v", g.State.ChongciConfig)
	}
	for i, p := range g.State.Players {
		if p.Score != 25000 {
			t.Fatalf("classic seat %d Score = %d, want 25000", i, p.Score)
		}
	}
}

func TestGameInitialization(t *testing.T) {
	r := &rules.HometownRuleset{}
	g := core.NewGame("test-uuid", r, core.MatchOptions{})

	if g.State.Phase != pb.GamePhase_PHASE_INIT {
		t.Errorf("Expected PHASE_INIT, got %v", g.State.Phase)
	}
	if len(g.State.Players) != 4 {
		t.Errorf("Expected 4 players, got %d", len(g.State.Players))
	}
}

func TestGameStartAndDeal(t *testing.T) {
	r := &rules.HometownRuleset{}
	g := core.NewGame("test-uuid", r, core.MatchOptions{})

	err := g.Start()
	if err != nil {
		t.Fatalf("Failed to start game: %v", err)
	}

	if g.State.Phase != pb.GamePhase_PHASE_PLAYER_TURN {
		t.Errorf("Expected PHASE_PLAYER_TURN, got %v", g.State.Phase)
	}

	dealer := g.State.ActivePlayer
	for i := 0; i < 4; i++ {
		// Dealer (East) draws a tile on turn start, so dealer has 14
		expectedSize := uint32(13)
		if uint32(i) == dealer {
			expectedSize = 14
		}
		if g.State.Players[i].HandSize != expectedSize {
			t.Errorf("Player %d expected hand size %d, got %d", i, expectedSize, g.State.Players[i].HandSize)
		}
	}
}

func TestDiscardAction(t *testing.T) {
	r := &rules.HometownRuleset{}
	g := core.NewGame("test-uuid", r, core.MatchOptions{})
	g.Start()

	activePlayer := g.State.ActivePlayer
	playerHand := g.State.Players[activePlayer].ClosedHand
	discardTile := playerHand[0] // pick the first tile to discard

	// Inject a matching pair into South's hand so the game recognizes a VALID PONG interrupt and enters PHASE_WAIT_DISCARDS
	southSeat := (activePlayer + 1) % 4
	clone1 := &pb.Tile{Id: discardTile.Id + 1000, Suit: discardTile.Suit, Value: discardTile.Value}
	clone2 := &pb.Tile{Id: discardTile.Id + 2000, Suit: discardTile.Suit, Value: discardTile.Value}
	g.State.Players[southSeat].ClosedHand = append(g.State.Players[southSeat].ClosedHand, clone1, clone2)

	action := &pb.PlayerAction{
		Type: pb.ActionType_ACTION_DISCARD,
		Tile: discardTile,
	}

	err := g.ProcessPlayerAction(activePlayer, action)
	if err != nil {
		t.Fatalf("Failed to process discard: %v", err)
	}

	if g.State.Phase != pb.GamePhase_PHASE_WAIT_DISCARDS {
		t.Errorf("Expected PHASE_WAIT_DISCARDS after discard, got %v", g.State.Phase)
	}

	if len(g.State.Players[activePlayer].Discards) != 1 {
		t.Errorf("Expected player %d to have 1 discard, got %d", activePlayer, len(g.State.Players[activePlayer].Discards))
	}
}

func TestDirectedMelds(t *testing.T) {
	r := &rules.HometownRuleset{}
	g := core.NewGame("test-uuid", r, core.MatchOptions{})
	g.Start()

	activePlayer := g.State.ActivePlayer
	playerHand := g.State.Players[activePlayer].ClosedHand
	discardTile := playerHand[0]

	// Inject a pair into next player's hand BEFORE discarding so GetValidInterrupts sees the Pon
	southSeat := (activePlayer + 1) % 4
	clone1 := &pb.Tile{Id: discardTile.Id + 1000, Suit: discardTile.Suit, Value: discardTile.Value}
	clone2 := &pb.Tile{Id: discardTile.Id + 2000, Suit: discardTile.Suit, Value: discardTile.Value}
	g.State.Players[southSeat].ClosedHand = append(g.State.Players[southSeat].ClosedHand, clone1, clone2)

	err := g.ProcessPlayerAction(activePlayer, &pb.PlayerAction{
		Type: pb.ActionType_ACTION_DISCARD,
		Tile: discardTile,
	})
	if err != nil {
		t.Fatalf("Failed to discard: %v", err)
	}

	if g.State.Phase != pb.GamePhase_PHASE_WAIT_DISCARDS {
		t.Fatalf("Expected PHASE_WAIT_DISCARDS after discard with valid interrupts, got %v", g.State.Phase)
	}

	err = g.ProcessPlayerAction(southSeat, &pb.PlayerAction{
		Type:      pb.ActionType_ACTION_PON,
		MeldTiles: []*pb.Tile{clone1, clone2},
	})
	if err != nil {
		t.Fatalf("Failed to interrupt: %v", err)
	}

	// ResolveInterrupts called automatically when all expected responses are in

	melds := g.State.Players[southSeat].OpenMelds
	if len(melds) != 1 {
		t.Fatalf("Expected 1 open meld, got %d", len(melds))
	}

	meld := melds[0]
	// Direction = (discarder - claimer + 4) % 4
	expectedDir := pb.MeldDirection((activePlayer - southSeat + 4) % 4)
	if meld.CalledDirection != expectedDir {
		t.Errorf("Expected direction %v, got %v", expectedDir, meld.CalledDirection)
	}

	if meld.CalledTileId != discardTile.Id {
		t.Errorf("Expected called tile ID %d, got %d", discardTile.Id, meld.CalledTileId)
	}
}

func TestDeadWallKanDraw(t *testing.T) {
	r := &rules.HometownRuleset{}
	g := core.NewGame("test-uuid", r, core.MatchOptions{})
	g.Start()

	activePlayer := g.State.ActivePlayer
	playerHand := g.State.Players[activePlayer].ClosedHand
	discardTile := playerHand[0]

	southSeat := (activePlayer + 1) % 4
	// South MUST already hold 3 matching tiles to trigger the waiting window for a valid Kan.
	clone1 := &pb.Tile{Id: discardTile.Id + 100, Suit: discardTile.Suit, Value: discardTile.Value}
	clone2 := &pb.Tile{Id: discardTile.Id + 200, Suit: discardTile.Suit, Value: discardTile.Value}
	clone3 := &pb.Tile{Id: discardTile.Id + 300, Suit: discardTile.Suit, Value: discardTile.Value}

	southPlayer := g.State.Players[southSeat]
	southPlayer.ClosedHand = append(southPlayer.ClosedHand, clone1, clone2, clone3)
	initialHandSize := len(southPlayer.ClosedHand)
	initialWallCount := g.State.WallCount

	// Player 0 discards a tile
	err := g.ProcessPlayerAction(activePlayer, &pb.PlayerAction{
		Type: pb.ActionType_ACTION_DISCARD,
		Tile: discardTile,
	})
	if err != nil {
		t.Fatalf("Failed to discard: %v", err)
	}
	// South has already had the triplet injected before the discard.
	// Proceed directly to the Kan call.

	// South calls Kan on the discard
	err = g.ProcessPlayerAction(southSeat, &pb.PlayerAction{
		Type:      pb.ActionType_ACTION_KAN,
		MeldTiles: []*pb.Tile{clone1, clone2, clone3},
	})
	if err != nil {
		t.Fatalf("Failed to interrupt Kan: %v", err)
	}

	// ResolveInterrupts is called automatically inside handleInterruptAction
	// when all expected responses are received (only south has valid actions).

	// Verify Melds
	if len(southPlayer.OpenMelds) != 1 {
		t.Fatalf("Expected 1 open meld for South player")
	}
	if southPlayer.OpenMelds[0].Type != pb.ActionType_ACTION_KAN {
		t.Errorf("Expected MELD type KAN")
	}

	// Verify Dead Wall Draw functionality
	// Hand size should have decreased by 3 (the meld tiles removed)
	// and increased by 1 (the dead wall draw). Total: initial - 2
	expectedHandSize := initialHandSize - 2
	if len(southPlayer.ClosedHand) != expectedHandSize {
		t.Errorf("Expected hand size %d, got %d", expectedHandSize, len(southPlayer.ClosedHand))
	}

	// Wall count drops by at least 1 for the dead-wall draw. It may drop by 2
	// if the supplement tile is a non-wild flower and auto-reveals immediately.
	if g.State.WallCount > initialWallCount-1 || g.State.WallCount < initialWallCount-2 {
		t.Errorf("Expected wall count to drop by 1 or 2 from %d, got %d", initialWallCount, g.State.WallCount)
	}

	// It should now be South player's turn to discard
	if g.State.ActivePlayer != southSeat {
		t.Errorf("Expected active player %d, got %d", southSeat, g.State.ActivePlayer)
	}
	if g.State.Phase != pb.GamePhase_PHASE_PLAYER_TURN {
		t.Errorf("Expected phase PHASE_PLAYER_TURN after Kan, got %v", g.State.Phase)
	}
}

func TestSetNextDealer_ConsumedOnce(t *testing.T) {
	r := &rules.HometownRuleset{}
	g := core.NewGame("test-override", r, core.MatchOptions{})
	if err := g.Start(); err != nil {
		t.Fatalf("Start failed: %v", err)
	}

	// Confirm there is exactly one East-wind seat after Start.
	eastCount := 0
	for _, p := range g.State.Players {
		if p.SeatWind == 1 {
			eastCount++
		}
	}
	if eastCount != 1 {
		t.Fatalf("after Start, expected exactly one East seat, got %d", eastCount)
	}

	// Override the next dealer and re-deal.
	g.SetNextDealer(2)
	g.DealForNextHand()

	if g.State.Players[2].SeatWind != 1 {
		t.Fatalf("after SetNextDealer(2), seat 2 SeatWind = %d, want 1 (East)", g.State.Players[2].SeatWind)
	}

	// Override is single-shot — running 20 more deals should produce at least one non-2 dealer.
	sawOther := false
	for i := 0; i < 20 && !sawOther; i++ {
		g.DealForNextHand()
		if g.State.Players[2].SeatWind != 1 {
			sawOther = true
		}
	}
	if !sawOther {
		t.Fatalf("override leaked: seat 2 was dealer for 20 consecutive deals")
	}
}

func TestNewGame_ChongciInitialization(t *testing.T) {
	r := &rules.HometownRuleset{}
	cfg := &pb.ChongciConfig{
		StartingScore: 2000,
		BustThreshold: 0,
		MaxHands:      50,
	}
	g := core.NewGame("test-chongci", r, core.MatchOptions{
		Mode:          pb.MatchMode_MATCH_MODE_CHONGCI,
		ChongciConfig: cfg,
	})

	if g.State.MatchMode != pb.MatchMode_MATCH_MODE_CHONGCI {
		t.Fatalf("MatchMode = %v, want CHONGCI", g.State.MatchMode)
	}
	if g.State.ChongciConfig == nil {
		t.Fatalf("ChongciConfig is nil")
	}
	if got := g.State.ChongciConfig.StartingScore; got != 2000 {
		t.Fatalf("ChongciConfig.StartingScore = %d, want 2000", got)
	}
	for i, p := range g.State.Players {
		if p.Score != 2000 {
			t.Fatalf("chongci seat %d Score = %d, want 2000", i, p.Score)
		}
	}
}

func TestComputeMatchEndResult_Standings(t *testing.T) {
	cases := []struct {
		name      string
		scores    [4]int32
		startScore int32
		wantRanks [4]uint32 // indexed by seat
	}{
		{
			name:       "all distinct",
			scores:     [4]int32{1500, 3000, -200, 1700},
			startScore: 2000,
			wantRanks:  [4]uint32{3, 1, 4, 2},
		},
		{
			name:       "two-way tie for first",
			scores:     [4]int32{3000, 3000, 1000, -1000},
			startScore: 2000,
			wantRanks:  [4]uint32{1, 1, 3, 4},
		},
		{
			name:       "four-way tie",
			scores:     [4]int32{2000, 2000, 2000, 2000},
			startScore: 2000,
			wantRanks:  [4]uint32{1, 1, 1, 1},
		},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			r := &rules.HometownRuleset{}
			g := core.NewGame("t", r, core.MatchOptions{
				Mode: pb.MatchMode_MATCH_MODE_CHONGCI,
				ChongciConfig: &pb.ChongciConfig{
					StartingScore: c.startScore,
					BustThreshold: 0,
					MaxHands:      0,
				},
			})
			for i, s := range c.scores {
				g.State.Players[i].Score = s
			}
			result := g.ComputeMatchEndResultForTest("bust")
			if result == nil || len(result.Standings) != 4 {
				t.Fatalf("nil or wrong-length standings: %+v", result)
			}
			gotRanks := [4]uint32{}
			for _, s := range result.Standings {
				gotRanks[s.Seat] = s.Rank
			}
			if gotRanks != c.wantRanks {
				t.Fatalf("ranks = %v, want %v", gotRanks, c.wantRanks)
			}
		})
	}
}

func TestShouldEndChongciMatch(t *testing.T) {
	r := &rules.HometownRuleset{}
	g := core.NewGame("t", r, core.MatchOptions{
		Mode: pb.MatchMode_MATCH_MODE_CHONGCI,
		ChongciConfig: &pb.ChongciConfig{
			StartingScore: 2000,
			BustThreshold: 0,
			MaxHands:      3,
		},
	})

	if g.ShouldEndChongciMatchForTest() {
		t.Fatal("unexpected end on healthy state")
	}

	g.State.Players[1].Score = 0
	if !g.ShouldEndChongciMatchForTest() {
		t.Fatal("expected bust on score == 0 with threshold 0")
	}

	g.State.Players[1].Score = 1500
	g.State.HandNum = 3
	if !g.ShouldEndChongciMatchForTest() {
		t.Fatal("expected hand_cap on HandNum == MaxHands")
	}
}

func TestCurrentDealerSeat(t *testing.T) {
	r := &rules.HometownRuleset{}
	g := core.NewGame("t", r, core.MatchOptions{})
	for i := uint32(0); i < 4; i++ {
		g.State.Players[i].SeatWind = ((i + 2) % 4) + 1 // East lands at seat 2
	}
	if got := g.CurrentDealerSeatForTest(); got != 2 {
		t.Fatalf("CurrentDealerSeat = %d, want 2", got)
	}
}
