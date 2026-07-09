// Package review reconstructs decision points from recorded paipu and scores
// them against a served policy. It drives engine.Game and reuses internal/rl
// encoders; it must not fork rules or state-transition logic.
package review

import (
	"fmt"
	"sort"

	"github.com/plasma/fh-mahjong/internal/engine"
	"github.com/plasma/fh-mahjong/internal/rl"
	"github.com/plasma/fh-mahjong/internal/rules"
	"github.com/plasma/fh-mahjong/internal/tiles"
	pb "github.com/plasma/fh-mahjong/proto"
)

// Decision is one reviewable decision reconstructed from a paipu.
type Decision struct {
	Seat          uint32
	RoundIndex    int    // index into paipu.Rounds
	ActionIndex   int    // paipu action index this decision anchors to (see below)
	DecisionIndex uint64 // monotone counter across the whole match
	ChosenAction  int    // 204-catalog id actually taken (rl.ActionPass for silent windows)
	Observation   *pb.SeatObservation
}

// ExtractDecisions replays every round of the paipu deterministically and
// returns each seat's decisions in chronological order. Any divergence
// between the paipu and the engine aborts with an error.
func ExtractDecisions(paipu *engine.Paipu) ([]Decision, error) {
	if paipu == nil || len(paipu.Rounds) == 0 {
		return nil, fmt.Errorf("paipu has no rounds")
	}
	var decisions []Decision
	var decisionIndex uint64
	for roundIdx := range paipu.Rounds {
		roundDecisions, next, err := replayRound(paipu, roundIdx, decisionIndex)
		if err != nil {
			return nil, fmt.Errorf("round %d: %w", roundIdx, err)
		}
		decisions = append(decisions, roundDecisions...)
		decisionIndex = next
	}
	return decisions, nil
}

// replayRound re-drives a single round from a fresh classic-mode game. Every
// round is independently reproducible from its own recorded wall seed and
// dealer, so a fresh classic game (not the original chongci match) is
// sufficient — the paipu never records the original ChongciConfig, and none
// is needed since each round's wall/dealer/deal are self-contained.
func replayRound(paipu *engine.Paipu, roundIdx int, decisionIndex uint64) ([]Decision, uint64, error) {
	round := &paipu.Rounds[roundIdx]
	seed, err := engine.SeedFromBase64(round.WallSeed)
	if err != nil {
		return nil, decisionIndex, fmt.Errorf("wall seed: %w", err)
	}

	game := engine.NewGame(paipu.MatchID, &rules.FenghuaRuleset{}, engine.MatchOptions{})
	game.SetWallSeed(seed)
	// dealTiles() only consumes an extra mt.GenU32() call for a *natural*
	// dealer roll when no override is queued; forcing SetNextDealer would
	// skip that draw and desync the wall shuffle from the original run. The
	// very first hand of any match is always naturally rolled (nothing has
	// run finalizeRoundEnd yet); every later chongci hand had its dealer
	// forced via SetNextDealer inside the previous hand's finalizeRoundEnd
	// (renchan or winner-seat succession), so replay must force it too.
	if roundIdx > 0 {
		game.SetNextDealer(round.Dealer)
	}
	// A throwaway recorder gives us the exact deal/wild snapshot the engine
	// itself computed at deal time (before any flower reveal or first-draw
	// mutation touches ClosedHand), without duplicating dealTiles' shuffle
	// logic here.
	game.Recorder = engine.NewPaipuRecorder(paipu.MatchID, paipu.Ruleset)
	if err := game.Start(); err != nil {
		return nil, decisionIndex, fmt.Errorf("start: %w", err)
	}
	if err := verifyRoundSetup(game, round); err != nil {
		return nil, decisionIndex, err
	}

	r := &roundReplayer{
		game:          game,
		paipu:         paipu,
		round:         round,
		roundIdx:      roundIdx,
		decisionIndex: decisionIndex,
		lastDiscard:   -1,
	}
	if err := r.run(); err != nil {
		return nil, decisionIndex, err
	}
	return r.decisions, r.decisionIndex, nil
}

// verifyRoundSetup compares the freshly re-dealt hand and wild tiles against
// the paipu's recorded round-start snapshot. A mismatch here means the
// wall-seed/dealer replay itself diverged (bad seed, engine wall-shuffle
// change, etc.) before any decision was even reached.
func verifyRoundSetup(game *engine.Game, round *engine.PaipuRound) error {
	snap := game.Recorder.CurrentRound()
	if snap == nil {
		return fmt.Errorf("engine produced no round-start snapshot")
	}
	for seat := 0; seat < 4; seat++ {
		want := round.Deals[seat]
		got := snap.Deals[seat]
		if len(want) != len(got) {
			return fmt.Errorf("seat %d: deal size mismatch: paipu has %d tiles, engine dealt %d", seat, len(want), len(got))
		}
		for i := range want {
			if want[i] != got[i] {
				return fmt.Errorf("seat %d slot %d: deal tile mismatch: paipu has tile %d, engine dealt %d", seat, i, want[i], got[i])
			}
		}
	}
	if len(round.WildTiles) != len(snap.WildTiles) {
		return fmt.Errorf("wild tile count mismatch: paipu has %d, engine has %d", len(round.WildTiles), len(snap.WildTiles))
	}
	for i, wt := range round.WildTiles {
		got := snap.WildTiles[i]
		if wt.ID != got.ID || wt.Suit != got.Suit || wt.Value != got.Value {
			return fmt.Errorf("wild tile %d mismatch: paipu has %+v, engine has %+v", i, wt, got)
		}
	}
	return nil
}

// roundReplayer walks a single round's recorded action stream forward,
// feeding each recorded decision back into engine.Game and recording a
// Decision wherever the acting seat had more than one legal option.
type roundReplayer struct {
	game          *engine.Game
	paipu         *engine.Paipu
	round         *engine.PaipuRound
	roundIdx      int
	cursor        int // next unconsumed index into round.Actions
	lastDiscard   int // action index of the most recent discard (pass anchor); -1 if none yet
	decisionIndex uint64
	decisions     []Decision
	flowerIndex   map[uint32]int // per-seat cursor into player.FlowerMelds for "flower" record verification
}

// run mirrors internal/rl/env.go's advanceToDecision loop shape, except the
// paipu's recorded action stream (not a policy) dictates every action fed to
// the engine.
func (r *roundReplayer) run() error {
	r.flowerIndex = initialFlowerCounts(r.round)
	for {
		switch r.game.State.Phase {
		case pb.GamePhase_PHASE_ROUND_END, pb.GamePhase_PHASE_MATCH_END:
			if r.cursor != len(r.round.Actions) {
				return fmt.Errorf("round %d: %d trailing unconsumed paipu action(s) starting at index %d (%s)",
					r.roundIdx, len(r.round.Actions)-r.cursor, r.cursor, r.round.Actions[r.cursor].Act)
			}
			return nil

		case pb.GamePhase_PHASE_PLAYER_TURN:
			if err := r.stepPlayerTurn(); err != nil {
				return err
			}

		case pb.GamePhase_PHASE_WAIT_DISCARDS:
			if err := r.stepWaitDiscards(); err != nil {
				return err
			}

		default:
			return fmt.Errorf("round %d: unexpected phase %v at paipu action %d", r.roundIdx, r.game.State.Phase, r.cursor)
		}
	}
}

// stepPlayerTurn first drains the draw/flower records that landed the game
// in PHASE_PLAYER_TURN (Start()'s dealer draw, a discard's turn-advance
// draw, an interrupt-resolution turn-advance draw, or a self-declared
// kan/flower's supplementary draw — all of these settle before control
// returns here), then resolves the active seat's turn decision against the
// next recorded paipu action and feeds it to the engine.
func (r *roundReplayer) stepPlayerTurn() error {
	if err := r.drainSystemRecords(); err != nil {
		return err
	}
	game := r.game
	seat := game.State.ActivePlayer
	if len(game.State.Players[seat].ValidActions) == 0 {
		return fmt.Errorf("round %d: seat %d has no valid actions in PHASE_PLAYER_TURN", r.roundIdx, seat)
	}
	if r.cursor >= len(r.round.Actions) {
		return fmt.Errorf("round %d: paipu action stream exhausted while seat %d has a pending turn", r.roundIdx, seat)
	}
	pa := &r.round.Actions[r.cursor]
	if pa.Seat != seat {
		return fmt.Errorf("round %d action %d: expected seat %d's turn action next, paipu has seat %d (%s)",
			r.roundIdx, r.cursor, seat, pa.Seat, pa.Act)
	}

	id, act, err := r.paipuActionID(seat, pa)
	if err != nil {
		return fmt.Errorf("round %d action %d: %w", r.roundIdx, r.cursor, err)
	}

	legal, err := rl.LegalActions(game.State, seat)
	if err != nil {
		return err
	}
	if len(legal) > 1 {
		if err := r.recordDecision(seat, r.cursor, id); err != nil {
			return err
		}
	}
	if pa.Act == "discard" {
		r.lastDiscard = r.cursor
	}
	actionIdx := r.cursor
	r.cursor++

	if err := game.ProcessPlayerAction(seat, act); err != nil {
		return fmt.Errorf("round %d action %d: engine rejected recorded %s: %w", r.roundIdx, actionIdx, pa.Act, err)
	}
	return nil
}

// stepWaitDiscards mirrors env.currentActionSeat's PHASE_WAIT_DISCARDS scan:
// every seat with pending ValidActions that hasn't queued a response yet is
// a pending seat. If the next recorded paipu action is one of those seats'
// interrupt response to the current discard, it is fed verbatim (the
// decision anchors to the action's own index). Otherwise every pending seat
// implicitly passed (paipu never records a declined interrupt) — pass is fed
// one seat at a time, anchored to the triggering discard's index.
func (r *roundReplayer) stepWaitDiscards() error {
	game := r.game
	var pending []uint32
	for seat := uint32(0); seat < uint32(len(game.State.Players)); seat++ {
		if seat == game.State.ActivePlayer {
			continue
		}
		player := game.State.Players[seat]
		if len(player.ValidActions) == 0 || game.InterruptQueued(seat) {
			continue
		}
		pending = append(pending, seat)
	}

	if len(pending) == 0 {
		// Every pending seat already responded; the engine normally
		// auto-resolves as soon as the last response is queued, so this is
		// a defensive fallback mirroring assertInterruptsReadyToResolve.
		game.ResolveInterrupts()
		return nil
	}

	var peeked *engine.PaipuAction
	if r.cursor < len(r.round.Actions) {
		peeked = &r.round.Actions[r.cursor]
	}

	if matchSeat, ok := matchingPendingSeat(pending, game.State.ActivePlayer, peeked); ok {
		id, act, err := r.paipuActionID(matchSeat, peeked)
		if err != nil {
			return fmt.Errorf("round %d action %d: %w", r.roundIdx, r.cursor, err)
		}
		legal, err := rl.LegalActions(game.State, matchSeat)
		if err != nil {
			return err
		}
		if len(legal) > 1 {
			if err := r.recordDecision(matchSeat, r.cursor, id); err != nil {
				return err
			}
		}
		actionIdx := r.cursor
		r.cursor++
		if err := game.ProcessPlayerAction(matchSeat, act); err != nil {
			return fmt.Errorf("round %d action %d: engine rejected recorded %s: %w", r.roundIdx, actionIdx, peeked.Act, err)
		}
		return nil
	}

	// Nobody pending matches the next recorded action: feed an implicit pass
	// to one pending seat and let the loop re-evaluate.
	seat := pending[0]
	legal, err := rl.LegalActions(game.State, seat)
	if err != nil {
		return err
	}
	passAction, ok := legal[rl.ActionPass]
	if !ok {
		return fmt.Errorf("round %d: seat %d has no ACTION_PASS in its legal interrupt map", r.roundIdx, seat)
	}
	if len(legal) > 1 {
		if r.lastDiscard < 0 {
			return fmt.Errorf("round %d: implicit pass for seat %d has no triggering discard to anchor to", r.roundIdx, seat)
		}
		if err := r.recordDecision(seat, r.lastDiscard, rl.ActionPass); err != nil {
			return err
		}
	}
	if err := game.ProcessPlayerAction(seat, passAction); err != nil {
		return fmt.Errorf("round %d: engine rejected implicit pass for seat %d: %w", r.roundIdx, seat, err)
	}
	return nil
}

// matchingPendingSeat reports whether the peeked paipu action is a pending
// seat's interrupt response to the seat currently discarding.
func matchingPendingSeat(pending []uint32, discarder uint32, peeked *engine.PaipuAction) (uint32, bool) {
	if peeked == nil {
		return 0, false
	}
	switch peeked.Act {
	case "chii", "pon", "okan", "ron":
	default:
		return 0, false
	}
	if peeked.From == nil || uint32(*peeked.From) != discarder {
		return 0, false
	}
	for _, seat := range pending {
		if seat == peeked.Seat {
			return seat, true
		}
	}
	return 0, false
}

// recordDecision captures a reviewable decision along with its 39ch policy
// observation. The observation is encoded against a dressed clone of the
// live replay state (see reviewState in context.go) — the replay game itself
// always runs in classic mode with zero scores, so encoding straight off
// r.game.State would feed the champion match context it was never trained to
// see.
func (r *roundReplayer) recordDecision(seat uint32, actionIndex int, chosenAction int) error {
	obs, err := rl.EncodeObservation(reviewState(r.game.State, r.paipu, r.roundIdx), seat, r.decisionIndex)
	if err != nil {
		return fmt.Errorf("round %d: encode observation for seat %d: %w", r.roundIdx, seat, err)
	}
	r.decisions = append(r.decisions, Decision{
		Seat:          seat,
		RoundIndex:    r.roundIdx,
		ActionIndex:   actionIndex,
		DecisionIndex: r.decisionIndex,
		ChosenAction:  chosenAction,
		Observation:   obs,
	})
	r.decisionIndex++
	return nil
}

// drainSystemRecords consumes and verifies every "draw"/"flower" record at
// the cursor. These are system events the engine performs itself
// (ExecuteSystemDraw / ExecuteDeadWallDraw / the mid-game auto flower-reveal
// loop) as a side effect of the decision just fed, not something the driver
// chooses — so the driver only checks that they happened and advances past
// them. It stops at the first non-system record (or end of stream).
func (r *roundReplayer) drainSystemRecords() error {
	for r.cursor < len(r.round.Actions) {
		pa := &r.round.Actions[r.cursor]
		switch pa.Act {
		case "draw":
			if err := r.verifyDrawRecord(pa); err != nil {
				return err
			}
		case "flower":
			if err := r.verifyFlowerRecord(pa); err != nil {
				return err
			}
		default:
			return nil
		}
		r.cursor++
	}
	return nil
}

func (r *roundReplayer) verifyDrawRecord(pa *engine.PaipuAction) error {
	if pa.Tile == nil {
		return fmt.Errorf("round %d action %d: draw record missing tile", r.roundIdx, r.cursor)
	}
	if int(pa.Seat) >= len(r.game.State.Players) {
		return fmt.Errorf("round %d action %d: draw record has invalid seat %d", r.roundIdx, r.cursor, pa.Seat)
	}
	// A draw immediately followed by a flower record is the tile that
	// revealed itself (see ExecuteSystemDraw -> autoRevealFlowers): the two
	// records must name the same tile. Otherwise this draw is the settled
	// tile the seat is now holding, checked against the live DrawnTileId.
	if r.cursor+1 < len(r.round.Actions) && r.round.Actions[r.cursor+1].Act == "flower" {
		next := r.round.Actions[r.cursor+1]
		if next.Seat != pa.Seat || next.Tile == nil || *next.Tile != *pa.Tile {
			return fmt.Errorf("round %d action %d: draw tile %d for seat %d does not match the following flower reveal",
				r.roundIdx, r.cursor, *pa.Tile, pa.Seat)
		}
		return nil
	}
	player := r.game.State.Players[pa.Seat]
	if player.DrawnTileId == nil || *player.DrawnTileId != int32(*pa.Tile) {
		return fmt.Errorf("round %d action %d: recorded draw of tile %d for seat %d does not match engine's current drawn tile (got %v)",
			r.roundIdx, r.cursor, *pa.Tile, pa.Seat, player.DrawnTileId)
	}
	return nil
}

func (r *roundReplayer) verifyFlowerRecord(pa *engine.PaipuAction) error {
	if pa.Tile == nil {
		return fmt.Errorf("round %d action %d: flower record missing tile", r.roundIdx, r.cursor)
	}
	if int(pa.Seat) >= len(r.game.State.Players) {
		return fmt.Errorf("round %d action %d: flower record has invalid seat %d", r.roundIdx, r.cursor, pa.Seat)
	}
	player := r.game.State.Players[pa.Seat]
	idx := r.flowerIndex[pa.Seat]
	if idx >= len(player.FlowerMelds) || player.FlowerMelds[idx].Id != uint32(*pa.Tile) {
		return fmt.Errorf("round %d action %d: recorded flower reveal of tile %d for seat %d not found at engine flower-meld position %d",
			r.roundIdx, r.cursor, *pa.Tile, pa.Seat, idx)
	}
	r.flowerIndex[pa.Seat] = idx + 1
	return nil
}

// initialFlowerCounts returns, per seat, how many flowers were auto-revealed
// during the initial deal (recorded separately from Actions in
// round.InitialFlowers). verifyFlowerRecord's per-seat FlowerMelds cursor
// starts here so it lines up with the mid-game "flower" Action records that
// follow the initial-deal reveals in player.FlowerMelds.
func initialFlowerCounts(round *engine.PaipuRound) map[uint32]int {
	counts := make(map[uint32]int, 4)
	for _, f := range round.InitialFlowers {
		counts[f.Seat]++
	}
	return counts
}

// paipuActionID maps a recorded paipu action to its 204-catalog id and the
// concrete legal pb.PlayerAction to feed the engine, with recorded tile ids
// substituted in verbatim (see exactTileAction) so the resulting discard
// pile / meld tile ids match the paipu exactly even when the acting seat
// held two physical copies of the same face.
func (r *roundReplayer) paipuActionID(seat uint32, pa *engine.PaipuAction) (int, *pb.PlayerAction, error) {
	legal, err := rl.LegalActions(r.game.State, seat)
	if err != nil {
		return 0, nil, err
	}

	var id int
	switch pa.Act {
	case "discard":
		if pa.Tile == nil {
			return 0, nil, fmt.Errorf("discard record missing tile")
		}
		id = rl.DiscardBase + faceIndex42FromTileID(uint32(*pa.Tile))
	case "pon":
		if len(pa.Tiles) == 0 {
			return 0, nil, fmt.Errorf("pon record missing tiles")
		}
		id = rl.PonBase + faceIndex34FromTileID(pa.Tiles[0])
	case "okan":
		if len(pa.Tiles) == 0 {
			return 0, nil, fmt.Errorf("okan record missing tiles")
		}
		id = rl.KanDirectBase + faceIndex34FromTileID(pa.Tiles[0])
	case "ckan":
		if len(pa.Tiles) == 0 {
			return 0, nil, fmt.Errorf("ckan record missing tiles")
		}
		id = rl.KanClosedBase + faceIndex34FromTileID(pa.Tiles[0])
	case "ukan":
		if pa.Tile == nil {
			return 0, nil, fmt.Errorf("ukan record missing tile")
		}
		id = rl.KanUpgradedBase + faceIndex34FromTileID(uint32(*pa.Tile))
	case "chii":
		matchedID, err := matchChiiID(legal, pa)
		if err != nil {
			return 0, nil, err
		}
		id = matchedID
	case "tsumo":
		id = rl.ActionTsumo
	case "ron":
		id = rl.ActionRon
	case "haitei":
		id = rl.ActionAcceptHaitei
	case "haiteiRefuse":
		id = rl.ActionRefuseHaitei
	default:
		return 0, nil, fmt.Errorf("unmappable paipu act %q", pa.Act)
	}

	template, ok := legal[id]
	if !ok {
		return 0, nil, fmt.Errorf("recorded %s action (id %d) is not legal for seat %d", pa.Act, id, seat)
	}

	act, err := r.exactTileAction(seat, template, pa)
	if err != nil {
		return 0, nil, err
	}
	return id, act, nil
}

// exactTileAction clones the catalog's representative legal action and
// substitutes the paipu's recorded physical tile ids, verifying the acting
// seat currently holds each one. This matters because legalActionMap
// collapses same-face duplicate tiles to a single representative id (e.g.
// the lowest-id copy for discards); the recorded historical action may have
// used the other physical copy, and replay must reproduce discard piles and
// melds tile-for-tile.
func (r *roundReplayer) exactTileAction(seat uint32, template *pb.PlayerAction, pa *engine.PaipuAction) (*pb.PlayerAction, error) {
	act := tiles.CloneAction(template)
	player := r.game.State.Players[seat]

	switch pa.Act {
	case "discard":
		tile, err := holdTile(player, uint32(*pa.Tile))
		if err != nil {
			return nil, err
		}
		act.Tile = tile
	case "ukan":
		tile, err := holdTile(player, uint32(*pa.Tile))
		if err != nil {
			return nil, err
		}
		act.MeldTiles = []*pb.Tile{tile}
	case "pon", "okan", "chii", "ckan":
		melds := make([]*pb.Tile, 0, len(pa.Tiles))
		for _, tid := range pa.Tiles {
			tile, err := holdTile(player, tid)
			if err != nil {
				return nil, err
			}
			melds = append(melds, tile)
		}
		act.MeldTiles = melds
	}
	return act, nil
}

// holdTile finds the exact physical tile (by id) in the player's closed
// hand, returning a clone. It errors if the seat does not currently hold
// that id — the sharpest possible divergence signal for a corrupted paipu.
func holdTile(player *pb.PlayerState, tileID uint32) (*pb.Tile, error) {
	for _, t := range player.ClosedHand {
		if t.Id == tileID {
			return tiles.CloneTile(t), nil
		}
	}
	return nil, fmt.Errorf("seat %d does not hold tile %d", player.Seat, tileID)
}

// matchChiiID scans the legal action map for the ACTION_CHII entry whose
// meld tiles match the recorded meld faces (suit+value, ignoring id — see
// exactTileAction for id fidelity). ChiiCount=21 (3 suits x 7 sequence
// starts) is derived structurally by rl.EncodeAction; this does not
// re-derive that index, it only disambiguates which of up to three legal
// sequence variants was recorded.
func matchChiiID(legal map[int]*pb.PlayerAction, pa *engine.PaipuAction) (int, error) {
	want := make([]uint32, 0, len(pa.Tiles))
	for _, tid := range pa.Tiles {
		suit, value := engine.TileFromId(tid)
		want = append(want, tiles.KeyOf(suit, value))
	}
	sort.Slice(want, func(i, j int) bool { return want[i] < want[j] })

	for id, act := range legal {
		if act.Type != pb.ActionType_ACTION_CHII || len(act.MeldTiles) != len(want) {
			continue
		}
		got := make([]uint32, 0, len(act.MeldTiles))
		for _, t := range act.MeldTiles {
			got = append(got, tiles.Key(t))
		}
		sort.Slice(got, func(i, j int) bool { return got[i] < got[j] })
		match := true
		for i := range want {
			if want[i] != got[i] {
				match = false
				break
			}
		}
		if match {
			return id, nil
		}
	}
	return 0, fmt.Errorf("no legal chii action matches recorded tiles %v", pa.Tiles)
}

// faceIndex42FromTileID converts a tile id (0-143) to its 0-41 face index:
// man(0-8), pin(9-17), sou(18-26), jihai(27-33), flower(34-41). Paipu tile
// ids are laid out SOU-first (see engine.TileFromId); the face order used by
// the rl catalog is MAN-first — this function bridges the two.
func faceIndex42FromTileID(id uint32) int {
	suit, value := engine.TileFromId(id)
	switch suit {
	case pb.Suit_SUIT_MAN:
		return int(value - 1)
	case pb.Suit_SUIT_PIN:
		return 9 + int(value-1)
	case pb.Suit_SUIT_SOU:
		return 18 + int(value-1)
	case pb.Suit_SUIT_JIHAI:
		return 27 + int(value-1)
	case pb.Suit_SUIT_FLOWER:
		return 34 + int(value-1)
	default:
		return -1
	}
}

// faceIndex34FromTileID is faceIndex42FromTileID restricted to the standard
// 0-33 tile range (man/pin/sou/jihai) used by pon/kan/chii catalog ids.
func faceIndex34FromTileID(id uint32) int {
	index := faceIndex42FromTileID(id)
	if index >= 34 {
		return -1
	}
	return index
}
