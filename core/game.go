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

	// Paipu recorder (optional — nil means no recording)
	Recorder *PaipuRecorder

	// Private game state not sent to clients
	wall               []*pb.Tile
	wallIndex          int // Points to next tile to draw from the front
	deadWallIndex      int // Tracks how many tiles have been drawn from the back (using stack-pair math)
	wangpaiBoundary    int // Index where normal draws stop (exclusive). Tiles from here to end are wangpai.
	wildIndicatorIndex int // Index of the wild indicator tile in the wall (face-up, never drawn)
	haiteiDrawIndex    int // Index of the accepted haitei tile once drawn, -1 if unused

	// Interruption queue for actions that happen asynchronously (like multiple players trying to Pong/Ron).
	// We wait a few seconds before resolving priority.
	interruptQueue   map[uint32]*pb.PlayerAction
	interruptTimer   *time.Timer
	wallSeedOverride *[MT19937SeedSize]uint32
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
	g.haiteiDrawIndex = -1

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

// SetWallSeed injects a deterministic MT19937 seed for the next deal/start.
func (g *Game) SetWallSeed(seed [MT19937SeedSize]uint32) {
	copySeed := seed
	g.wallSeedOverride = &copySeed
}

// InterruptQueued reports whether the seat has already submitted an interrupt
// response in the current WAIT_DISCARDS window.
func (g *Game) InterruptQueued(seat uint32) bool {
	_, ok := g.interruptQueue[seat]
	return ok
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
	// 1. Generate or inject a 624-uint32 seed
	var seed [MT19937SeedSize]uint32
	if g.wallSeedOverride != nil {
		seed = *g.wallSeedOverride
		g.wallSeedOverride = nil
	} else {
		nano := time.Now().UnixNano()
		for i := 0; i < MT19937SeedSize; i++ {
			// Just a simple mix for the initial seed state
			seed[i] = uint32(nano ^ int64(i*192837465))
		}
	}

	// Store the base64 seed for replay verification
	seedBytes := make([]byte, MT19937SeedSize*4)
	for i := 0; i < MT19937SeedSize; i++ {
		binary.LittleEndian.PutUint32(seedBytes[i*4:(i+1)*4], seed[i])
	}
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
	g.haiteiDrawIndex = -1

	// --- Fenghua Rules: Dice Roll & Wangpai (Dead Wall) ---
	// Roll two dice to determine how many stacks from the end form the wangpai.
	d1 := (mt.GenU32() % 6) + 1
	d2 := (mt.GenU32() % 6) + 1
	diceSum := d1 + d2
	g.State.DiceSum = diceSum
	g.State.Dice1 = d1
	g.State.Dice2 = d2
	g.State.WangpaiStacks = diceSum

	// Wangpai = last diceSum stacks (2 tiles per stack) at the tail of the wall.
	// Normal draws cannot enter this zone.
	wangpaiTiles := int(diceSum) * 2
	g.wangpaiBoundary = len(g.wall) - wangpaiTiles

	// The wild indicator is the TOP tile of the INNERMOST wangpai stack
	// (closest to the live wall front). In our array, stacks are stored as
	// (top, bottom) pairs, so the top of the innermost wangpai stack is
	// at index wangpaiBoundary.
	g.wildIndicatorIndex = g.wangpaiBoundary
	wildIndicator := g.wall[g.wildIndicatorIndex]

	// WallCount = total drawable tiles (excluding dealt tiles and wild indicator).
	// This includes both normal-drawable and dead-wall-drawable tiles.
	g.State.WallCount = uint32(len(g.wall) - g.wallIndex - 1) // -1 for wild indicator
	g.updateWangpaiTilesLeft()

	// Determine wild tiles from the indicator
	if wildIndicator.Suit == pb.Suit_SUIT_FLOWER {
		// Flower indicator: the other 3 flowers in its group become wilds
		g.State.WildTiles = make([]*pb.Tile, 0, 3)
		isSeason := wildIndicator.Value >= 1 && wildIndicator.Value <= 4

		for v := uint32(1); v <= 8; v++ {
			if v == wildIndicator.Value {
				continue
			}
			if isSeason && v >= 1 && v <= 4 {
				g.State.WildTiles = append(g.State.WildTiles, &pb.Tile{Suit: pb.Suit_SUIT_FLOWER, Value: v})
			} else if !isSeason && v >= 5 && v <= 8 {
				g.State.WildTiles = append(g.State.WildTiles, &pb.Tile{Suit: pb.Suit_SUIT_FLOWER, Value: v})
			}
		}
	} else {
		// Standard tile: the 3 other copies of this exact tile type are wilds
		g.State.WildTiles = []*pb.Tile{wildIndicator}
	}

	if g.Recorder != nil {
		var deals [4][]uint32
		for i := 0; i < 4; i++ {
			deals[i] = make([]uint32, len(g.State.Players[i].ClosedHand))
			for j, t := range g.State.Players[i].ClosedHand {
				deals[i][j] = t.Id
			}
		}
		var scores [4]int32
		for i := 0; i < 4; i++ {
			scores[i] = g.State.Players[i].Score
		}
		g.Recorder.StartRound(
			g.State.HandNum,
			g.State.PrevailingWind,
			dealer,
			[2]uint32{d1, d2},
			g.State.WallSeed,
			g.State.WildTiles,
			diceSum,
			scores,
			deals,
		)
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
			// Find the first flower in hand that is NOT a wild tile
			flowerIdx := -1
			for j, t := range player.ClosedHand {
				if t.Suit == pb.Suit_SUIT_FLOWER {
					// Check if this flower is a wild tile
					isWild := false
					for _, w := range g.State.WildTiles {
						if w.Suit == pb.Suit_SUIT_FLOWER && w.Value == t.Value {
							isWild = true
							break
						}
					}

					if !isWild {
						flowerIdx = j
						break
					}
				}
			}
			if flowerIdx < 0 {
				break // No more revealable flowers
			}

			// Move flower to FlowerMelds
			flower := player.ClosedHand[flowerIdx]
			player.FlowerMelds = append(player.FlowerMelds, flower)
			player.ClosedHand = append(player.ClosedHand[:flowerIdx], player.ClosedHand[flowerIdx+1:]...)
			player.HandSize--

			// Draw replacement from dead wall (don't set DrawnTileId — this is pre-game)
			// Skip the wild indicator tile (it's face-up, never drawn).
			var drawIndex int
			drewReplacement := false
			for {
				if g.State.WallCount == 0 {
					break
				}
				k := g.deadWallIndex
				stackOffset := (k / 2) * 2
				isBottom := k % 2
				if isBottom == 1 {
					drawIndex = len(g.wall) - 1 - stackOffset
				} else {
					drawIndex = len(g.wall) - 2 - stackOffset
				}
				if drawIndex < g.wallIndex {
					break // Wall exhausted
				}
				g.deadWallIndex++
				if drawIndex == g.wildIndicatorIndex {
					continue // Skip wild indicator
				}
				drewReplacement = true
				break
			}
			if !drewReplacement {
				break
			}
			replacement := g.wall[drawIndex]
			if g.Recorder != nil {
				g.Recorder.RecordInitialFlower(seat, flower.Id, replacement.Id)
			}
			player.ClosedHand = append(player.ClosedHand, replacement)
			player.HandSize++
			g.State.WallCount--
			g.updateWangpaiTilesLeft()
			// Loop continues — if replacement is a flower, it will be caught next iteration
		}
	}
}

func (g *Game) isFlowerWild(tile *pb.Tile) bool {
	if tile == nil || tile.Suit != pb.Suit_SUIT_FLOWER {
		return false
	}
	for _, w := range g.State.WildTiles {
		if w.Suit == pb.Suit_SUIT_FLOWER && w.Value == tile.Value {
			return true
		}
	}
	return false
}

func (g *Game) findRevealableFlowerTile(seat uint32) *pb.Tile {
	player := g.State.Players[seat]
	for _, t := range player.ClosedHand {
		if t.Suit == pb.Suit_SUIT_FLOWER && !g.isFlowerWild(t) {
			return t
		}
	}
	return nil
}

func (g *Game) autoRevealFlowers(seat uint32) error {
	for {
		flower := g.findRevealableFlowerTile(seat)
		if flower == nil {
			g.State.Players[seat].ValidActions = g.Rules.GetValidActions(g.State, seat)
			return nil
		}
		err := g.handleActiveTurnAction(seat, &pb.PlayerAction{
			Type:      pb.ActionType_ACTION_FLOWER_REVEAL,
			MeldTiles: []*pb.Tile{flower},
		})
		if err != nil {
			return err
		}
	}
}

func (g *Game) updateWangpaiTilesLeft() {
	if len(g.wall) == 0 {
		g.State.WangpaiTilesLeft = 0
		return
	}

	remaining := 0
	for idx := g.wangpaiBoundary; idx < len(g.wall); idx++ {
		if idx == g.wildIndicatorIndex || idx == g.haiteiDrawIndex {
			continue
		}
		if g.isTileConsumedByDeadWall(idx) {
			continue
		}
		remaining++
	}

	g.State.WangpaiTilesLeft = uint32(remaining)
}

// ExecuteSystemDraw handles drawing a tile from the wall at the start of a turn.
// Normal draws go forward from wallIndex and STOP at the wangpai boundary.
// When the live wall is exhausted, the player is offered the haitei (last drawable) tile.
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

	// Check if the live wall (front → wangpai boundary) is exhausted
	if g.wallIndex >= g.wangpaiBoundary {
		// The live wall is empty. Offer the haitei tile.
		// Find the haitei tile = the last undrawn tile (excluding the wild indicator).
		haiteiIdx := g.findHaiteiIndex()
		if haiteiIdx < 0 {
			// No drawable tiles remain at all → ryuukyoku
			g.State.Phase = pb.GamePhase_PHASE_ROUND_END
			g.State.RoundResult = &pb.RoundResult{IsDraw: true}
			g.State.PlayerReady = []bool{false, false, false, false}
			for _, p := range g.State.Players {
				p.ValidActions = nil
			}
			g.recordRoundEnd()
			return nil
		}

		// The player decides BEFORE seeing the tile.
		g.State.IsHaitei = true
		player.ValidActions = []*pb.PlayerAction{
			{Type: pb.ActionType_ACTION_ACCEPT_HAITEI},
			{Type: pb.ActionType_ACTION_REFUSE_HAITEI},
		}
		return nil
	}

	// Normal draw from front of wall
	drawnTile := g.wall[g.wallIndex]
	g.wallIndex++

	player.ClosedHand = append(player.ClosedHand, drawnTile)
	player.HandSize++
	drawnID := int32(drawnTile.Id)
	player.DrawnTileId = &drawnID
	g.State.WallCount--
	g.updateWangpaiTilesLeft()

	if g.Recorder != nil {
		g.Recorder.RecordDraw(seat, drawnTile.Id)
	}

	if g.findRevealableFlowerTile(seat) != nil {
		return g.autoRevealFlowers(seat)
	}

	player.ValidActions = g.Rules.GetValidActions(g.State, seat)

	return nil
}

// findHaiteiIndex returns the wall array index of the haitei (last drawable) tile,
// which is the tile under the wild indicator (wangpaiBoundary + 1).
// If that tile has already been consumed by a kong draw, it scans for the last
// remaining undrawn tile in the wangpai. Returns -1 if nothing is left.
func (g *Game) findHaiteiIndex() int {
	// The haitei tile is the one below the wild indicator
	haiteiIdx := g.wildIndicatorIndex + 1
	if haiteiIdx < len(g.wall) && !g.isTileConsumedByDeadWall(haiteiIdx) {
		return haiteiIdx
	}

	// If the tile under the wild indicator was already consumed by kong draws,
	// there are no drawable tiles left.
	return -1
}

// isTileConsumedByDeadWall checks if a specific wall index has already been
// drawn by a dead-wall (kong/flower) draw.
func (g *Game) isTileConsumedByDeadWall(targetIndex int) bool {
	for i := 0; i < g.deadWallIndex; i++ {
		k := i
		stackOffset := (k / 2) * 2
		isBottom := k % 2
		var drawIndex int
		if isBottom == 1 {
			drawIndex = len(g.wall) - 1 - stackOffset
		} else {
			drawIndex = len(g.wall) - 2 - stackOffset
		}
		if drawIndex == targetIndex {
			return true
		}
	}
	return false
}

// ExecuteDeadWallDraw handles drawing a supplementary tile from the back of the wall
// (the "dead wall") after a Kong or Flower reveal.
// Kong draws come from the tail end of the wall going backward, skipping the wild indicator.
func (g *Game) ExecuteDeadWallDraw(seat uint32) error {
	if g.State.WallCount == 0 {
		g.State.Phase = pb.GamePhase_PHASE_ROUND_END
		g.State.RoundResult = &pb.RoundResult{IsDraw: true}
		g.State.PlayerReady = []bool{false, false, false, false}
		for _, p := range g.State.Players {
			p.ValidActions = nil
		}
		g.recordRoundEnd()
		return nil // Exhaustive draw
	}

	player := g.State.Players[seat]

	// The wall is physically built in 2-tile high stacks.
	// When drawing from the end of the wall, we always draw the top tile of the last stack first,
	// then the bottom. We SKIP the wild indicator tile (it's face-up, never drawn).
	var drawIndex int
	for {
		k := g.deadWallIndex
		stackOffset := (k / 2) * 2
		isBottom := k % 2

		if isBottom == 1 {
			drawIndex = len(g.wall) - 1 - stackOffset
		} else {
			drawIndex = len(g.wall) - 2 - stackOffset
		}

		// Safety: if we've somehow gone past the wall start, stop
		if drawIndex < g.wallIndex {
			g.State.Phase = pb.GamePhase_PHASE_ROUND_END
			g.State.RoundResult = &pb.RoundResult{IsDraw: true}
			g.State.PlayerReady = []bool{false, false, false, false}
			for _, p := range g.State.Players {
				p.ValidActions = nil
			}
			g.recordRoundEnd()
			return nil
		}

		g.deadWallIndex++

		// Skip the wild indicator tile — it's face-up and never drawn
		if drawIndex == g.wildIndicatorIndex {
			continue
		}
		break
	}

	drawnTile := g.wall[drawIndex]

	player.ClosedHand = append(player.ClosedHand, drawnTile)
	player.HandSize++
	drawnID := int32(drawnTile.Id)
	player.DrawnTileId = &drawnID
	g.State.WallCount--
	g.updateWangpaiTilesLeft()

	if g.Recorder != nil {
		g.Recorder.RecordDraw(seat, drawnTile.Id)
	}

	if g.findRevealableFlowerTile(seat) != nil {
		return g.autoRevealFlowers(seat)
	}

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
	// --- Haitei Accept/Refuse ---
	if action.Type == pb.ActionType_ACTION_ACCEPT_HAITEI {
		// Player accepts the haitei tile. Draw it from the wangpai.
		haiteiIdx := g.findHaiteiIndex()
		if haiteiIdx < 0 {
			return errors.New("no haitei tile available")
		}

		player := g.State.Players[seat]
		drawnTile := g.wall[haiteiIdx]
		player.ClosedHand = append(player.ClosedHand, drawnTile)
		player.HandSize++
		drawnID := int32(drawnTile.Id)
		player.DrawnTileId = &drawnID
		g.State.WallCount--
		g.haiteiDrawIndex = haiteiIdx
		g.updateWangpaiTilesLeft()

		if g.Recorder != nil {
			g.Recorder.RecordHaiteiAccept(seat, drawnTile.Id)
		}

		// If the accepted haitei tile is a revealable flower, the replacement comes
		// from the dead wall and the haitei-only restriction no longer applies.
		if g.findRevealableFlowerTile(seat) != nil {
			g.State.IsHaitei = false
			return g.autoRevealFlowers(seat)
		}

		// Get valid actions — during haitei, only Tsumo or Discard of the drawn tile
		player.ValidActions = g.Rules.GetValidActions(g.State, seat)

		return nil
	}

	if action.Type == pb.ActionType_ACTION_REFUSE_HAITEI {
		// Player refuses the haitei tile → ryuukyoku
		g.State.IsHaitei = false
		if g.Recorder != nil {
			g.Recorder.RecordHaiteiRefuse(seat)
		}
		g.State.Phase = pb.GamePhase_PHASE_ROUND_END
		g.State.RoundResult = &pb.RoundResult{IsDraw: true}
		g.State.PlayerReady = []bool{false, false, false, false}
		for _, p := range g.State.Players {
			p.ValidActions = nil
		}
		g.recordRoundEnd()
		return nil
	}

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

		if g.Recorder != nil {
			g.Recorder.RecordDiscard(seat, action.Tile.Id)
		}

		// Choosing to discard means the player did not win on any dead-wall replacement tile,
		// so all kong/flower bonus flags are now stale and must be cleared.
		player.HasBuddingDirectKong = false
		player.HasBloomingDirectKong = false
		player.HasBuddingClosedKong = false
		player.HasBloomingClosedKong = false
		player.HasBuddingRiskyKong = false
		player.HasBloomingRiskyKong = false
		player.HasBloomingFlowerKong = false

		// During haitei, only Ron is allowed as an interrupt (no Chii/Pon/Kan)
		if g.State.IsHaitei {
			anyoneCanRon := false
			for pSeat, p := range g.State.Players {
				if uint32(pSeat) == seat {
					p.ValidActions = nil
					continue
				}
				// Only check for Ron during haitei
				interrupts := g.Rules.GetValidInterrupts(g.State, action.Tile, uint32(pSeat))
				var ronOnly []*pb.PlayerAction
				for _, intr := range interrupts {
					if intr.Type == pb.ActionType_ACTION_RON {
						ronOnly = append(ronOnly, intr)
					}
				}
				p.ValidActions = ronOnly
				if len(ronOnly) > 0 {
					anyoneCanRon = true
				}
			}

			if anyoneCanRon {
				g.State.Phase = pb.GamePhase_PHASE_WAIT_DISCARDS
				g.interruptQueue = make(map[uint32]*pb.PlayerAction)
			} else {
				// No one can Ron → ryuukyoku (no more tiles to draw after haitei)
				g.State.IsHaitei = false
				g.State.Phase = pb.GamePhase_PHASE_ROUND_END
				g.State.RoundResult = &pb.RoundResult{IsDraw: true}
				g.State.PlayerReady = []bool{false, false, false, false}
				for _, p := range g.State.Players {
					p.ValidActions = nil
				}
				g.recordRoundEnd()
			}
			return nil
		}

		// Normal (non-haitei) discard path
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

			if g.Recorder != nil {
				if upgraded {
					g.Recorder.RecordUpgradeKan(seat, action.MeldTiles[0].Id)
				} else {
					ids := make([]uint32, len(action.MeldTiles))
					for i, t := range action.MeldTiles {
						ids[i] = t.Id
					}
					g.Recorder.RecordClosedKan(seat, ids)
				}
			}
		} else if action.Type == pb.ActionType_ACTION_FLOWER_REVEAL {
			// Add to Flower Melds
			player.FlowerMelds = append(player.FlowerMelds, action.MeldTiles...)

			if g.Recorder != nil {
				g.Recorder.RecordFlowerReveal(seat, action.MeldTiles[0].Id)
			}
		}

		// Player immediately gets a supplementary tile from the Dead Wall.
		// If the supplementary draw exhausts the wall, the round is already over;
		// do not restore PLAYER_TURN with an empty valid-action set.
		if err := g.ExecuteDeadWallDraw(seat); err != nil {
			return err
		}
		if g.State.Phase == pb.GamePhase_PHASE_ROUND_END {
			return nil
		}

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

		if g.Recorder != nil {
			tileID := uint32(0)
			if winTile != nil {
				tileID = winTile.Id
			}
			g.Recorder.RecordTsumo(seat, tileID)
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
		g.recordRoundEnd()

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

		if g.Recorder != nil {
			ids := make([]uint32, len(winningAction.MeldTiles))
			for i, t := range winningAction.MeldTiles {
				ids[i] = t.Id
			}
			switch winningAction.Type {
			case pb.ActionType_ACTION_CHII:
				g.Recorder.RecordChii(winnerSeat, ids, discarder)
			case pb.ActionType_ACTION_PON:
				g.Recorder.RecordPon(winnerSeat, ids, discarder)
			case pb.ActionType_ACTION_KAN:
				g.Recorder.RecordOpenKan(winnerSeat, ids, discarder)
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
			// Chii or Pon just resume turn phase (player must discard now, no drawing).
			// If the claimer is already holding any non-wild flowers, reveal them
			// immediately before valid actions are exposed to the client.
			g.State.Phase = pb.GamePhase_PHASE_PLAYER_TURN
			if g.findRevealableFlowerTile(winnerSeat) != nil {
				if err := g.autoRevealFlowers(winnerSeat); err != nil {
					player.ValidActions = g.Rules.GetValidActions(g.State, winnerSeat)
				}
			} else {
				player.ValidActions = g.Rules.GetValidActions(g.State, winnerSeat)
			}
		}
	} else if winningAction.Type == pb.ActionType_ACTION_RON {
		// Handle Ron (end of round)
		player := g.State.Players[winnerSeat]
		discarderSeat := g.State.ActivePlayer
		winTile := g.State.ActiveDiscard

		if g.Recorder != nil {
			g.Recorder.RecordRon(winnerSeat, g.State.ActiveDiscard.Id, discarderSeat)
		}

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
		g.recordRoundEnd()
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

// recordRoundEnd captures the round result into the paipu recorder.
func (g *Game) recordRoundEnd() {
	if g.Recorder == nil || g.State.RoundResult == nil {
		return
	}
	result := g.State.RoundResult

	paipuResult := &PaipuRoundResult{
		ScoreChanges: make([]int32, 4),
	}

	if result.IsDraw {
		paipuResult.Type = "draw"
	} else {
		paipuResult.Type = "win"
		paipuResult.Winner = IntPtr(int(result.WinnerSeat))
		if result.WinType == pb.ActionType_ACTION_TSUMO {
			paipuResult.WinType = "tsumo"
		} else {
			paipuResult.WinType = "ron"
			paipuResult.Discarder = IntPtr(int(result.DiscarderSeat))
		}
		if result.WinTile != nil {
			paipuResult.WinTile = IntPtr(int(result.WinTile.Id))
		}
		for _, t := range result.WinningHand {
			paipuResult.Hand = append(paipuResult.Hand, t.Id)
		}
		for _, m := range result.WinningMelds {
			pm := PaipuMeld{From: -1}
			switch m.Type {
			case pb.ActionType_ACTION_CHII:
				pm.Type = "chii"
			case pb.ActionType_ACTION_PON:
				pm.Type = "pon"
			case pb.ActionType_ACTION_KAN:
				pm.Type = "kan"
			}
			for _, t := range m.Tiles {
				pm.Tiles = append(pm.Tiles, t.Id)
			}
			if m.CalledDirection != pb.MeldDirection_MELD_DIRECTION_UNKNOWN {
				pm.From = int(m.CalledDirection)
			}
			paipuResult.Melds = append(paipuResult.Melds, pm)
		}
		winner := g.State.Players[result.WinnerSeat]
		for _, f := range winner.FlowerMelds {
			paipuResult.Flowers = append(paipuResult.Flowers, f.Id)
		}
		for _, entry := range result.Breakdown {
			paipuResult.Breakdown = append(paipuResult.Breakdown, PaipuBreakdown{
				Name:   entry.PatternName,
				Points: entry.Points,
			})
		}
		paipuResult.TotalScore = result.TotalScore
	}

	for _, p := range result.Payouts {
		if int(p.Seat) < 4 {
			paipuResult.ScoreChanges[p.Seat] = p.Amount
		}
	}

	g.Recorder.EndRound(paipuResult)
}
