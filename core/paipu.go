package core

import pb "github.com/plasma/fh-mahjong/proto"

// --- Paipu JSON Types ---

type PaipuTile struct {
	ID    uint32  `json:"id"`
	Suit  pb.Suit `json:"suit"`
	Value uint32  `json:"value"`
}

type PaipuPlayer struct {
	Seat   uint32 `json:"seat"`
	Name   string `json:"name"`
	UserID uint   `json:"userId"`
}

type PaipuAction struct {
	Act   string   `json:"act"`
	Seat  uint32   `json:"seat"`
	Tile  *int     `json:"tile,omitempty"`  // tile ID (pointer to handle tile 0 = 1s correctly)
	Tiles []uint32 `json:"tiles,omitempty"` // tile IDs for meld actions
	From  *int     `json:"from,omitempty"`  // discarder seat (pointer to handle seat 0 correctly)
}

// IntPtr creates an int pointer for PaipuAction fields.
func IntPtr(v int) *int { return &v }

type PaipuFlowerReveal struct {
	Seat        uint32 `json:"seat"`
	Flower      uint32 `json:"flower"`      // tile ID of flower
	Replacement uint32 `json:"replacement"` // tile ID of replacement drawn
}

type PaipuMeld struct {
	Type  string   `json:"type"`           // "chii", "pon", "kan"
	Tiles []uint32 `json:"tiles"`          // tile IDs in the meld
	From  int      `json:"from,omitempty"` // discarder seat; -1 for closed kan
}

type PaipuBreakdown struct {
	Name   string `json:"name"`
	Points int32  `json:"points"`
}

type PaipuRoundResult struct {
	Type         string           `json:"type"`              // "win" or "draw"
	Winner       *int             `json:"winner"`            // seat (pointer: seat 0 is valid); nil for draw
	WinType      string           `json:"winType,omitempty"` // "tsumo" or "ron"
	Discarder    *int             `json:"discarder"`         // seat (pointer); nil for tsumo/draw
	WinTile      *int             `json:"winTile,omitempty"` // tile ID (pointer: tile 0 is valid)
	Hand         []uint32         `json:"hand,omitempty"`    // winning hand tile IDs
	Melds        []PaipuMeld      `json:"melds,omitempty"`   // open melds
	Flowers      []uint32         `json:"flowers,omitempty"` // flower tile IDs
	Breakdown    []PaipuBreakdown `json:"breakdown,omitempty"`
	TotalScore   int32            `json:"totalScore,omitempty"`
	ScoreChanges []int32          `json:"scoreChanges"` // length 4, per-seat delta
}

type PaipuRound struct {
	Round          uint32              `json:"round"`
	PrevailingWind uint32              `json:"prevailingWind"`
	Dealer         uint32              `json:"dealer"`
	Dice           [2]uint32           `json:"dice"`
	WallSeed       string              `json:"wallSeed"`
	WildTiles      []PaipuTile         `json:"wildTiles"`
	WangpaiStacks  uint32              `json:"wangpaiStacks"`
	StartingScores [4]int32            `json:"startingScores"`
	Deals          [4][]uint32         `json:"deals"`          // 4 arrays of 13 tile IDs each
	InitialFlowers []PaipuFlowerReveal `json:"initialFlowers"` // auto-revealed during deal
	Actions        []PaipuAction       `json:"actions"`
	Result         *PaipuRoundResult   `json:"result"`
}

type Paipu struct {
	Version     int           `json:"version"`
	MatchID     string        `json:"matchId"`
	Ruleset     string        `json:"ruleset"`
	Players     []PaipuPlayer `json:"players"`
	Rounds      []PaipuRound  `json:"rounds"`
	FinalScores [4]int32      `json:"finalScores"`
}

// TileFromId converts a tile ID (0-143) to its suit and value.
// Layout mirrors rules/fh.go GetInitialWall():
//
//	  0-35: SOU 1-9 (4 copies each)
//	 36-71: MAN 1-9 (4 copies each)
//	72-107: PIN 1-9 (4 copies each)
//	108-135: JIHAI 1-7 (4 copies each)
//	136-143: FLOWER 1-8 (1 each)
func TileFromId(id uint32) (pb.Suit, uint32) {
	switch {
	case id < 36:
		return pb.Suit_SUIT_SOU, (id / 4) + 1
	case id < 72:
		return pb.Suit_SUIT_MAN, ((id - 36) / 4) + 1
	case id < 108:
		return pb.Suit_SUIT_PIN, ((id - 72) / 4) + 1
	case id < 136:
		return pb.Suit_SUIT_JIHAI, ((id - 108) / 4) + 1
	default:
		return pb.Suit_SUIT_FLOWER, (id - 136) + 1
	}
}

// PaipuRecorder accumulates game events into a structured Paipu.
type PaipuRecorder struct {
	paipu        Paipu
	currentRound *PaipuRound
}

func NewPaipuRecorder(matchID, ruleset string) *PaipuRecorder {
	return &PaipuRecorder{
		paipu: Paipu{
			Version: 1,
			MatchID: matchID,
			Ruleset: ruleset,
		},
	}
}

func (r *PaipuRecorder) AddPlayer(seat uint32, name string, userID uint) {
	r.paipu.Players = append(r.paipu.Players, PaipuPlayer{
		Seat:   seat,
		Name:   name,
		UserID: userID,
	})
}

func (r *PaipuRecorder) StartRound(
	round, prevailingWind, dealer uint32,
	dice [2]uint32,
	wallSeed string,
	wildTiles []*pb.Tile,
	wangpaiStacks uint32,
	startingScores [4]int32,
	deals [4][]uint32,
) {
	wt := make([]PaipuTile, len(wildTiles))
	for i, t := range wildTiles {
		wt[i] = PaipuTile{ID: t.Id, Suit: t.Suit, Value: t.Value}
	}
	r.currentRound = &PaipuRound{
		Round:          round,
		PrevailingWind: prevailingWind,
		Dealer:         dealer,
		Dice:           dice,
		WallSeed:       wallSeed,
		WildTiles:      wt,
		WangpaiStacks:  wangpaiStacks,
		StartingScores: startingScores,
		Deals:          deals,
		Actions:        make([]PaipuAction, 0),
	}
}

func (r *PaipuRecorder) RecordInitialFlower(seat, flowerTileID, replacementTileID uint32) {
	if r.currentRound == nil {
		return
	}
	r.currentRound.InitialFlowers = append(r.currentRound.InitialFlowers, PaipuFlowerReveal{
		Seat:        seat,
		Flower:      flowerTileID,
		Replacement: replacementTileID,
	})
}

func (r *PaipuRecorder) record(a PaipuAction) {
	if r.currentRound == nil {
		return
	}
	r.currentRound.Actions = append(r.currentRound.Actions, a)
}

func (r *PaipuRecorder) RecordDraw(seat uint32, tileID uint32) {
	r.record(PaipuAction{Act: "draw", Seat: seat, Tile: IntPtr(int(tileID))})
}

func (r *PaipuRecorder) RecordDiscard(seat uint32, tileID uint32) {
	r.record(PaipuAction{Act: "discard", Seat: seat, Tile: IntPtr(int(tileID))})
}

func (r *PaipuRecorder) RecordChii(seat uint32, handTileIDs []uint32, fromSeat uint32) {
	r.record(PaipuAction{Act: "chii", Seat: seat, Tiles: handTileIDs, From: IntPtr(int(fromSeat))})
}

func (r *PaipuRecorder) RecordPon(seat uint32, handTileIDs []uint32, fromSeat uint32) {
	r.record(PaipuAction{Act: "pon", Seat: seat, Tiles: handTileIDs, From: IntPtr(int(fromSeat))})
}

func (r *PaipuRecorder) RecordOpenKan(seat uint32, handTileIDs []uint32, fromSeat uint32) {
	r.record(PaipuAction{Act: "okan", Seat: seat, Tiles: handTileIDs, From: IntPtr(int(fromSeat))})
}

func (r *PaipuRecorder) RecordClosedKan(seat uint32, tileIDs []uint32) {
	r.record(PaipuAction{Act: "ckan", Seat: seat, Tiles: tileIDs})
}

func (r *PaipuRecorder) RecordUpgradeKan(seat uint32, tileID uint32) {
	r.record(PaipuAction{Act: "ukan", Seat: seat, Tile: IntPtr(int(tileID))})
}

func (r *PaipuRecorder) RecordFlowerReveal(seat uint32, tileID uint32) {
	r.record(PaipuAction{Act: "flower", Seat: seat, Tile: IntPtr(int(tileID))})
}

func (r *PaipuRecorder) RecordTsumo(seat uint32, tileID uint32) {
	r.record(PaipuAction{Act: "tsumo", Seat: seat, Tile: IntPtr(int(tileID))})
}

func (r *PaipuRecorder) RecordRon(seat uint32, tileID uint32, fromSeat uint32) {
	r.record(PaipuAction{Act: "ron", Seat: seat, Tile: IntPtr(int(tileID)), From: IntPtr(int(fromSeat))})
}

func (r *PaipuRecorder) RecordHaiteiAccept(seat uint32, tileID uint32) {
	r.record(PaipuAction{Act: "haitei", Seat: seat, Tile: IntPtr(int(tileID))})
}

func (r *PaipuRecorder) RecordHaiteiRefuse(seat uint32) {
	r.record(PaipuAction{Act: "haiteiRefuse", Seat: seat})
}

func (r *PaipuRecorder) EndRound(result *PaipuRoundResult) {
	if r.currentRound == nil {
		return
	}
	r.currentRound.Result = result
	r.paipu.Rounds = append(r.paipu.Rounds, *r.currentRound)
	r.currentRound = nil
}

func (r *PaipuRecorder) Finalize(finalScores [4]int32) *Paipu {
	r.paipu.FinalScores = finalScores
	return &r.paipu
}

// CurrentRound returns the in-progress round (for testing).
func (r *PaipuRecorder) CurrentRound() *PaipuRound {
	return r.currentRound
}
