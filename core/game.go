package core

import (
	"encoding/base64"
	"encoding/binary"
	"errors"
	"fmt"
	"time"

	pb "github.com/plasma/fh-mahjong/proto"
)

// Game is the central state machine driver for a single Mahjong match.
type Game struct {
	State *pb.GameState
	Rules RuleEngine

	// Private game state not sent to clients
	wall          []*pb.Tile
	wallIndex     int // Points to next tile to draw from the front
	deadWallIndex int // Tracks how many tiles have been drawn from the back

	// Interruption queue for actions that happen asynchronously (like multiple players trying to Pong/Ron).
	// We wait a few seconds before resolving priority.
	interruptQueue map[uint32]*pb.PlayerAction
	interruptTimer *time.Timer
}

// NewGame initializes a brand new game using the provided Ruleset plugin.
func NewGame(matchID string, rules RuleEngine) *Game {
	g := &Game{
		Rules: rules,
		State: &pb.GameState{
			MatchId:       matchID,
			Phase:         pb.GamePhase_PHASE_INIT,
			ActivePlayer:  0,
			WallCount:     0,
			HandNum:       1, // East 1
			Players:       make([]*pb.PlayerState, 4),
			ActiveDiscard: nil,
		},
		interruptQueue: make(map[uint32]*pb.PlayerAction),
	}

	for i := 0; i < 4; i++ {
		g.State.Players[i] = &pb.PlayerState{
			Seat:        uint32(i),
			Score:       25000, // Standard starting score, could be parameterized by rules
			ClosedHand:  make([]*pb.Tile, 0),
			HandSize:    0,
			DrawnTileId: nil,
			OpenMelds:   make([]*pb.Meld, 0),
			Discards:    make([]*pb.Tile, 0),
			SeatWind:    uint32(i + 1), // 1=East, 2=South, 3=West, 4=North
			FlowerMelds: make([]*pb.Tile, 0),
		}
	}

	return g
}

// Start begins the match. It shuffles the wall and deals tiles to players.
func (g *Game) Start() error {
	if g.State.Phase != pb.GamePhase_PHASE_INIT {
		return errors.New("cannot start game: already in progress")
	}

	dealer := g.dealTiles()
	g.revealInitialFlowers(dealer)
	g.State.Phase = pb.GamePhase_PHASE_PLAYER_TURN
	g.State.ActivePlayer = dealer // Dealer (East) starts

	// The round begins by having the dealer draw a tile.
	err := g.ExecuteSystemDraw(dealer)
	if err != nil {
		return err
	}
	// Auto-reveal if the dealer's drawn tile is a flower
	g.revealInitialFlowers(dealer)
	// Recalculate valid actions after any flower reveals
	g.State.Players[dealer].ValidActions = g.Rules.GetValidActions(g.State, dealer)
	return nil
}

// dealTiles uses the rule engine to get a full deck, shuffles it, and distributes 13 tiles to each player.
// Returns the dealer seat (East).
func (g *Game) dealTiles() uint32 {
	wall := g.Rules.GetInitialWall()

	// Shuffle using Tenhou's MT19937 algorithm
	// 1. Generate a random 624-uint32 seed
	nano := time.Now().UnixNano()
	var seed [MT19937SeedSize]uint32
	seedBytes := make([]byte, MT19937SeedSize*4)
	for i := 0; i < MT19937SeedSize; i++ {
		// Just a simple mix for the initial seed state
		seed[i] = uint32(nano ^ int64(i*192837465))
		binary.LittleEndian.PutUint32(seedBytes[i*4:(i+1)*4], seed[i])
	}

	// Store the base64 seed for replay verification
	g.State.WallSeed = base64.StdEncoding.EncodeToString(seedBytes)

	mt := MTFromSeed(seed)

	// Pick a random dealer (0-3) and assign seat winds accordingly
	dealer := mt.GenU32() % 4
	for i := 0; i < 4; i++ {
		// Wind offset: dealer=East(1), next=South(2), etc.
		g.State.Players[i].SeatWind = uint32(((i - int(dealer) + 4) % 4) + 1)
	}

	// 2. Generate an array of indices 0..135
	indices := make([]byte, len(wall))
	for i := 0; i < len(wall); i++ {
		indices[i] = byte(i)
	}

	// 3. Shuffle indices
	ShuffleWithMT(indices, mt)

	// 4. Rearrange the actual tile slice based on shuffled indices
	shuffledWall := make([]*pb.Tile, len(wall))
	for i := 0; i < len(wall); i++ {
		shuffledWall[i] = wall[indices[i]]
	}
	wall = shuffledWall

	// Deal 13 tiles to each of the 4 players (4+4+4+1)
	dealIndex := 0

	// 3 rounds of 4 tiles
	for round := 0; round < 3; round++ {
		for seat := 0; seat < 4; seat++ {
			g.State.Players[seat].ClosedHand = append(g.State.Players[seat].ClosedHand, wall[dealIndex:dealIndex+4]...)
			g.State.Players[seat].HandSize += 4
			dealIndex += 4
		}
	}

	// 1 round of 1 tile
	for seat := 0; seat < 4; seat++ {
		g.State.Players[seat].ClosedHand = append(g.State.Players[seat].ClosedHand, wall[dealIndex])
		g.State.Players[seat].HandSize += 1
		dealIndex += 1
	}

	g.wall = wall
	g.wallIndex = dealIndex
	g.deadWallIndex = 0

	g.State.WallCount = uint32(len(g.wall) - g.wallIndex)

	// Fenghua Rules: Select the "Wild Tile" indicator.
	// We draw it from the *head* of the wall (front) so that the tail
	// remains perfectly paired for Kan/Flower dead-wall draws.
	if len(g.wall) > g.wallIndex {
		wildIndicator := g.wall[g.wallIndex]
		g.wallIndex++
		g.State.WallCount-- // Remove indicator from drawable wall
		// Store the indicator tile type. Players match their hand tiles against this
		// Suit+Value combo to identify wild tiles.
		g.State.WildTiles = []*pb.Tile{wildIndicator}
	}

	return dealer
}

// revealInitialFlowers auto-separates flower tiles from all players' hands after dealing.
// For each seat (starting from dealer), any flower tiles are moved to FlowerMelds
// and replacement tiles are drawn from the dead wall. If a replacement is also a flower,
// it is immediately revealed as well.
func (g *Game) revealInitialFlowers(dealer uint32) {
	for i := 0; i < 4; i++ {
		seat := (dealer + uint32(i)) % 4
		player := g.State.Players[seat]

		for {
			// Find the first flower in hand
			flowerIdx := -1
			for j, t := range player.ClosedHand {
				if t.Suit == pb.Suit_SUIT_FLOWER {
					flowerIdx = j
					break
				}
			}
			if flowerIdx < 0 {
				break // No more flowers
			}

			// Move flower to FlowerMelds
			flower := player.ClosedHand[flowerIdx]
			player.FlowerMelds = append(player.FlowerMelds, flower)
			player.ClosedHand = append(player.ClosedHand[:flowerIdx], player.ClosedHand[flowerIdx+1:]...)
			player.HandSize--

			// Draw replacement from dead wall (don't set DrawnTileId — this is pre-game)
			if g.wallIndex+g.deadWallIndex >= len(g.wall) || g.State.WallCount == 0 {
				break // Wall exhausted
			}
			k := g.deadWallIndex
			stackOffset := (k / 2) * 2
			isBottom := k % 2
			var drawIndex int
			if isBottom == 1 {
				drawIndex = len(g.wall) - 1 - stackOffset
			} else {
				drawIndex = len(g.wall) - 2 - stackOffset
			}
			replacement := g.wall[drawIndex]
			g.deadWallIndex++
			player.ClosedHand = append(player.ClosedHand, replacement)
			player.HandSize++
			g.State.WallCount--
			// Loop continues — if replacement is a flower, it will be caught next iteration
		}
	}
}

// ExecuteSystemDraw handles drawing a tile from the wall at the start of a turn.
func (g *Game) ExecuteSystemDraw(seat uint32) error {
	// Clear kong/flower bonus flags — a normal draw means any previous dead-wall context is stale
	player := g.State.Players[seat]
	player.HasBuddingDirectKong = false
	player.HasBloomingDirectKong = false
	player.HasBuddingClosedKong = false
	player.HasBloomingClosedKong = false
	player.HasBuddingRiskyKong = false
	player.HasBloomingRiskyKong = false
	player.HasBloomingFlowerKong = false

	if g.wallIndex+g.deadWallIndex >= len(g.wall) || g.State.WallCount == 0 {
		g.State.Phase = pb.GamePhase_PHASE_ROUND_END
		g.State.RoundResult = &pb.RoundResult{IsDraw: true}
		g.State.PlayerReady = []bool{false, false, false, false}
		for _, p := range g.State.Players {
			p.ValidActions = nil
		}
		return nil // Exhaustive draw (Ryukyoku)
	}

	drawnTile := g.wall[g.wallIndex]
	g.wallIndex++

	player.ClosedHand = append(player.ClosedHand, drawnTile)
	player.HandSize++
	drawnID := int32(drawnTile.Id)
	player.DrawnTileId = &drawnID
	g.State.WallCount--

	player.ValidActions = g.Rules.GetValidActions(g.State, seat)

	return nil
}

// ExecuteDeadWallDraw handles drawing a supplementary tile from the back of the wall
// (the "dead wall") after a Kong or Flower reveal.
func (g *Game) ExecuteDeadWallDraw(seat uint32) error {
	if g.wallIndex+g.deadWallIndex >= len(g.wall) || g.State.WallCount == 0 {
		g.State.Phase = pb.GamePhase_PHASE_ROUND_END
		g.State.RoundResult = &pb.RoundResult{IsDraw: true}
		g.State.PlayerReady = []bool{false, false, false, false}
		for _, p := range g.State.Players {
			p.ValidActions = nil
		}
		return nil // Exhaustive draw
	}

	player := g.State.Players[seat]

	// The wall is physically built in 2-tile high stacks.
	// When drawing from the end of the wall, we always draw from the top layer of the last stack first.
	// A stack is (Top, Bottom). Their indices at the end of the array are `L-2` and `L-1`.
	k := g.deadWallIndex
	stackOffset := (k / 2) * 2
	isBottom := k % 2

	var drawIndex int
	if isBottom == 1 {
		drawIndex = len(g.wall) - 1 - stackOffset
	} else {
		drawIndex = len(g.wall) - 2 - stackOffset
	}

	drawnTile := g.wall[drawIndex]
	g.deadWallIndex++

	player.ClosedHand = append(player.ClosedHand, drawnTile)
	player.HandSize++
	drawnID := int32(drawnTile.Id)
	player.DrawnTileId = &drawnID
	g.State.WallCount--

	player.ValidActions = g.Rules.GetValidActions(g.State, seat)

	return nil
}

// ProcessPlayerAction is the main entry point for the network. It validates the Protobuf action securely.
func (g *Game) ProcessPlayerAction(seat uint32, action *pb.PlayerAction) error {
	switch g.State.Phase {
	case pb.GamePhase_PHASE_PLAYER_TURN:
		if seat != g.State.ActivePlayer {
			return fmt.Errorf("not player %d's turn", seat)
		}
		return g.handleActiveTurnAction(seat, action)

	case pb.GamePhase_PHASE_WAIT_DISCARDS:
		// Accept steals/interrupts asynchronously from other players
		return g.handleInterruptAction(seat, action)

	case pb.GamePhase_PHASE_ROUND_END:
		if action.Type == pb.ActionType_ACTION_READY {
			return g.handleReadyAction(seat)
		}
		return errors.New("only READY action accepted in ROUND_END phase")

	default:
		return errors.New("actions not accepted in current phase")
	}
}

// handleActiveTurnAction processes normal turn actions like Discard or Tsumo.
func (g *Game) handleActiveTurnAction(seat uint32, action *pb.PlayerAction) error {
	if action.Type == pb.ActionType_ACTION_DISCARD {
		player := g.State.Players[seat]

		// Remove from hand, add to discards
		found := false
		for i, t := range player.ClosedHand {
			if t.Id == action.Tile.Id {
				player.ClosedHand = append(player.ClosedHand[:i], player.ClosedHand[i+1:]...)
				found = true
				break
			}
		}
		if !found {
			return errors.New("discard tile not in hand")
		}

		player.Discards = append(player.Discards, action.Tile)
		player.HandSize--
		player.DrawnTileId = nil
		g.State.ActiveDiscard = action.Tile

		// Calculate valid actions for all other players
		anyoneCanInterrupt := false
		for pSeat, p := range g.State.Players {
			if uint32(pSeat) == seat {
				p.ValidActions = nil // Active player has no interrupts
				continue
			}

			interrupts := g.Rules.GetValidInterrupts(g.State, action.Tile, uint32(pSeat))
			p.ValidActions = interrupts

			if len(interrupts) > 0 {
				anyoneCanInterrupt = true
			}
		}

		if anyoneCanInterrupt {
			// Transition to wait for interrupts
			g.State.Phase = pb.GamePhase_PHASE_WAIT_DISCARDS
			g.interruptQueue = make(map[uint32]*pb.PlayerAction) // clear queue
		} else {
			// No one can interrupt, immediately advance turn
			g.State.ActivePlayer = (g.State.ActivePlayer + 1) % 4
			g.State.Phase = pb.GamePhase_PHASE_PLAYER_TURN
			g.State.ActiveDiscard = nil
			g.ExecuteSystemDraw(g.State.ActivePlayer)
		}

		return nil
	} else if action.Type == pb.ActionType_ACTION_KAN || action.Type == pb.ActionType_ACTION_FLOWER_REVEAL {
		player := g.State.Players[seat]

		// Verify and remove the tiles from the closed hand
		for _, requiredTile := range action.MeldTiles {
			found := false
			for i, handTile := range player.ClosedHand {
				if handTile.Id == requiredTile.Id {
					player.ClosedHand = append(player.ClosedHand[:i], player.ClosedHand[i+1:]...)
					player.HandSize--
					found = true
					break
				}
			}
			if !found {
				return fmt.Errorf("tile %d for action %v not found in hand", requiredTile.Id, action.Type)
			}
		}

		if action.Type == pb.ActionType_ACTION_KAN {
			upgraded := false
			// Check if we are upgrading an existing Pon
			for _, m := range player.OpenMelds {
				if m.Type == pb.ActionType_ACTION_PON && m.Tiles[0].Suit == action.MeldTiles[0].Suit && m.Tiles[0].Value == action.MeldTiles[0].Value {
					m.Type = pb.ActionType_ACTION_KAN
					m.Tiles = append(m.Tiles, action.MeldTiles...)
					upgraded = true
					break
				}
			}

			if !upgraded {
				// Add a new Closed Kan
				meld := &pb.Meld{
					Type:            pb.ActionType_ACTION_KAN,
					Tiles:           action.MeldTiles,
					CalledDirection: pb.MeldDirection_MELD_DIRECTION_UNKNOWN, // Closed/Upgraded Kan is self-drawn
				}
				player.OpenMelds = append(player.OpenMelds, meld)
			}
		} else if action.Type == pb.ActionType_ACTION_FLOWER_REVEAL {
			// Add to Flower Melds
			player.FlowerMelds = append(player.FlowerMelds, action.MeldTiles...)
		}

		// Player immediately gets a supplementary tile from the Dead Wall
		g.ExecuteDeadWallDraw(seat)

		// Set kong bonus flag: winning on the dead wall draw after a flower reveal
		if action.Type == pb.ActionType_ACTION_FLOWER_REVEAL {
			player.HasBloomingFlowerKong = true
		}

		// It remains their turn to either discard, declare another Kan/Flower, or Tsumo
		g.State.Phase = pb.GamePhase_PHASE_PLAYER_TURN

		return nil
	} else if action.Type == pb.ActionType_ACTION_TSUMO {
		player := g.State.Players[seat]

		score, breakdown, canWin := g.Rules.EvaluateHand(
			player.ClosedHand, player.OpenMelds, nil, g.State, seat, true,
		)
		if !canWin {
			return errors.New("hand is not a valid tsumo win")
		}

		// Find the drawn tile (the winning tile for tsumo)
		var winTile *pb.Tile
		if player.DrawnTileId != nil {
			for _, t := range player.ClosedHand {
				if int32(t.Id) == *player.DrawnTileId {
					winTile = t
					break
				}
			}
		}

		payouts := g.Rules.CalculatePayouts(score, pb.ActionType_ACTION_TSUMO, seat, 0)
		for _, p := range payouts {
			g.State.Players[p.Seat].Score += p.Amount
		}

		g.State.RoundResult = &pb.RoundResult{
			WinnerSeat:   seat,
			WinType:      pb.ActionType_ACTION_TSUMO,
			WinningHand:  player.ClosedHand,
			WinningMelds: player.OpenMelds,
			WinTile:      winTile,
			Breakdown:    breakdown,
			TotalScore:   score,
			Payouts:      payouts,
			IsDraw:       false,
		}

		g.State.Phase = pb.GamePhase_PHASE_ROUND_END
		g.State.PlayerReady = []bool{false, false, false, false}
		for _, p := range g.State.Players {
			p.ValidActions = nil
		}

		return nil
	}

	return fmt.Errorf("unsupported active action: %v", action.Type)
}

// handleInterruptAction processes out-of-turn actions like Pong or Ron during the waiting window.
func (g *Game) handleInterruptAction(seat uint32, action *pb.PlayerAction) error {
	if seat == g.State.ActivePlayer {
		return errors.New("active player cannot interrupt their own discard")
	}
	// Add to queue
	g.interruptQueue[seat] = action

	// Check if all players who have valid actions have submitted a response
	expectedResponses := 0
	for _, p := range g.State.Players {
		if len(p.ValidActions) > 0 {
			expectedResponses++
		}
	}

	if len(g.interruptQueue) >= expectedResponses {
		g.ResolveInterrupts()
	}

	return nil
}

// ResolveInterrupts is called by the server after the 3-second wait window expires.
func (g *Game) ResolveInterrupts() {
	if len(g.interruptQueue) == 0 {
		// No one interrupted. Next player's turn!
		g.State.ActivePlayer = (g.State.ActivePlayer + 1) % 4
		g.State.Phase = pb.GamePhase_PHASE_PLAYER_TURN
		g.State.ActiveDiscard = nil
		g.ExecuteSystemDraw(g.State.ActivePlayer)
		return
	}

	// Delegate to the ruleset plugin to decide who wins the priority
	winnerSeat, winningAction := g.Rules.ResolveInterruptPriority(g.interruptQueue)

	if winningAction == nil {
		g.State.ActivePlayer = (g.State.ActivePlayer + 1) % 4
		g.State.Phase = pb.GamePhase_PHASE_PLAYER_TURN
		g.State.ActiveDiscard = nil
		g.ExecuteSystemDraw(g.State.ActivePlayer)
		return
	}

	// Apply the interrupt
	if winningAction.Type == pb.ActionType_ACTION_PON || winningAction.Type == pb.ActionType_ACTION_CHII || winningAction.Type == pb.ActionType_ACTION_KAN {
		discarder := g.State.ActivePlayer
		direction := pb.MeldDirection((discarder - winnerSeat + 4) % 4)

		meld := &pb.Meld{
			Type:            winningAction.Type,
			Tiles:           append(winningAction.MeldTiles, g.State.ActiveDiscard),
			CalledDirection: direction,
			CalledTileId:    g.State.ActiveDiscard.Id,
		}

		player := g.State.Players[winnerSeat]
		player.OpenMelds = append(player.OpenMelds, meld)

		// Remove MeldTiles from player's ClosedHand
		for _, t := range winningAction.MeldTiles {
			for i, handTile := range player.ClosedHand {
				if handTile.Id == t.Id {
					player.ClosedHand = append(player.ClosedHand[:i], player.ClosedHand[i+1:]...)
					break
				}
			}
		}

		// Remove the discard from the discarder's pile since it was claimed
		discarderPlayer := g.State.Players[discarder]
		if len(discarderPlayer.Discards) > 0 {
			discarderPlayer.Discards = discarderPlayer.Discards[:len(discarderPlayer.Discards)-1]
		}

		g.State.ActivePlayer = winnerSeat
		g.State.ActiveDiscard = nil
		player.DrawnTileId = nil // Clear drawn tile formatting for steals

		if winningAction.Type == pb.ActionType_ACTION_KAN {
			// A Kong requires a supplementary tile from the dead wall before discarding
			g.ExecuteDeadWallDraw(winnerSeat)
			g.State.Phase = pb.GamePhase_PHASE_PLAYER_TURN
		} else {
			// Chii or Pon just resume turn phase (player must discard now, no drawing)
			g.State.Phase = pb.GamePhase_PHASE_PLAYER_TURN
			player.ValidActions = g.Rules.GetValidActions(g.State, winnerSeat)
		}
	} else if winningAction.Type == pb.ActionType_ACTION_RON {
		// Handle Ron (end of round)
		player := g.State.Players[winnerSeat]
		discarderSeat := g.State.ActivePlayer
		winTile := g.State.ActiveDiscard

		score, breakdown, canWin := g.Rules.EvaluateHand(
			player.ClosedHand, player.OpenMelds, winTile, g.State, winnerSeat, false,
		)
		if !canWin {
			// Should not happen since GetValidInterrupts already checked, but guard
			g.State.ActivePlayer = (g.State.ActivePlayer + 1) % 4
			g.State.Phase = pb.GamePhase_PHASE_PLAYER_TURN
			g.State.ActiveDiscard = nil
			g.ExecuteSystemDraw(g.State.ActivePlayer)
			return
		}

		payouts := g.Rules.CalculatePayouts(score, pb.ActionType_ACTION_RON, winnerSeat, discarderSeat)
		for _, p := range payouts {
			g.State.Players[p.Seat].Score += p.Amount
		}

		// Remove discard from discarder's pile since it was claimed for the win
		discarderPlayer := g.State.Players[discarderSeat]
		if len(discarderPlayer.Discards) > 0 {
			discarderPlayer.Discards = discarderPlayer.Discards[:len(discarderPlayer.Discards)-1]
		}

		g.State.RoundResult = &pb.RoundResult{
			WinnerSeat:    winnerSeat,
			WinType:       pb.ActionType_ACTION_RON,
			DiscarderSeat: discarderSeat,
			WinningHand:   player.ClosedHand,
			WinningMelds:  player.OpenMelds,
			WinTile:       winTile,
			Breakdown:     breakdown,
			TotalScore:    score,
			Payouts:       payouts,
			IsDraw:        false,
		}

		g.State.Phase = pb.GamePhase_PHASE_ROUND_END
		g.State.PlayerReady = []bool{false, false, false, false}
		for _, p := range g.State.Players {
			p.ValidActions = nil
		}
	}

	// clear queue
	g.interruptQueue = make(map[uint32]*pb.PlayerAction)
}

// handleReadyAction marks a player as ready for the next round.
func (g *Game) handleReadyAction(seat uint32) error {
	if int(seat) >= len(g.State.PlayerReady) {
		return fmt.Errorf("invalid seat %d for ready action", seat)
	}
	if g.State.PlayerReady[seat] {
		return nil // Already ready, idempotent
	}
	g.State.PlayerReady[seat] = true

	// Check if all 4 players are ready
	allReady := true
	for _, ready := range g.State.PlayerReady {
		if !ready {
			allReady = false
			break
		}
	}

	if allReady {
		g.startNextRound()
	}
	return nil
}

// startNextRound resets the game state for a new round while preserving scores.
func (g *Game) startNextRound() {
	g.State.HandNum++
	g.State.RoundResult = nil
	g.State.PlayerReady = nil
	g.State.ActiveDiscard = nil

	// Reset player states (preserve score)
	for i := 0; i < 4; i++ {
		p := g.State.Players[i]
		p.ClosedHand = make([]*pb.Tile, 0)
		p.HandSize = 0
		p.DrawnTileId = nil
		p.OpenMelds = make([]*pb.Meld, 0)
		p.Discards = make([]*pb.Tile, 0)
		p.FlowerMelds = make([]*pb.Tile, 0)
		p.ValidActions = nil
		p.HasBuddingDirectKong = false
		p.HasBloomingDirectKong = false
		p.HasBuddingClosedKong = false
		p.HasBloomingClosedKong = false
		p.HasBuddingRiskyKong = false
		p.HasBloomingRiskyKong = false
		p.HasBloomingFlowerKong = false
	}

	// Re-deal
	g.interruptQueue = make(map[uint32]*pb.PlayerAction)
	dealer := g.dealTiles()
	g.revealInitialFlowers(dealer)
	g.State.Phase = pb.GamePhase_PHASE_PLAYER_TURN
	g.State.ActivePlayer = dealer // Dealer (East) starts
	g.ExecuteSystemDraw(dealer)
	// Auto-reveal if the dealer's drawn tile is a flower
	g.revealInitialFlowers(dealer)
	g.State.Players[dealer].ValidActions = g.Rules.GetValidActions(g.State, dealer)
}
