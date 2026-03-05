package api

import (
	"net/http"

	"github.com/gin-gonic/gin"
	pb "github.com/plasma/fh-mahjong/proto"
	"github.com/plasma/fh-mahjong/rules"
)

// CalcRequest represents the JSON payload from the frontend calculator.
type CalcRequest struct {
	ClosedHand []uint32 `json:"closedHand"` // list of tile Hashes (Suit*100 + Value)
	OpenMelds  []struct {
		Type            pb.ActionType `json:"type"`
		Tiles           []uint32      `json:"tiles"`           // Hashes
		CalledTileIndex int           `json:"calledTileIndex"` // which tile in Tiles was stolen
		CalledDirection uint32        `json:"calledDirection"` // 1: right, 2: across, 3: left
	} `json:"openMelds"`
	WinTileHash    uint32   `json:"winTile"`
	IsTsumo        bool     `json:"isTsumo"`
	WildTileHashes []uint32 `json:"wildTiles"`
	SeatWind       uint32   `json:"seatWind"`       // 1: East, 2: South, 3: West, 4: North
	PrevailingWind uint32   `json:"prevailingWind"` // 1: East, etc.
}

func hashToTile(hash uint32) *pb.Tile {
	suit := pb.Suit(hash / 100)
	val := hash % 100
	return &pb.Tile{Suit: suit, Value: val, Id: 999} // ID doesn't matter for evaluation
}

func (s *Server) handleCalc(c *gin.Context) {
	var req CalcRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid request payload"})
		return
	}

	// 1. Build proto structures
	var closed []*pb.Tile
	for _, h := range req.ClosedHand {
		closed = append(closed, hashToTile(h))
	}

	winTile := hashToTile(req.WinTileHash)

	var melds []*pb.Meld
	for _, rm := range req.OpenMelds {
		var tiles []*pb.Tile
		for _, th := range rm.Tiles {
			tiles = append(tiles, hashToTile(th))
		}
		calledId := uint32(0)
		if rm.CalledTileIndex >= 0 && rm.CalledTileIndex < len(tiles) {
			calledId = tiles[rm.CalledTileIndex].Id
		}

		melds = append(melds, &pb.Meld{
			Type:            rm.Type,
			Tiles:           tiles,
			CalledTileId:    calledId,
			CalledDirection: pb.MeldDirection(rm.CalledDirection),
		})
	}

	var wilds []*pb.Tile
	for _, wh := range req.WildTileHashes {
		wilds = append(wilds, hashToTile(wh))
	}

	// 2. Build Mock Game State
	state := &pb.GameState{
		PrevailingWind: req.PrevailingWind,
		WildTiles:      wilds,
		Players: []*pb.PlayerState{
			{SeatWind: req.SeatWind},
		},
	}

	// 3. Evaluate Hand
	rs := &rules.HometownRuleset{}
	score, entries, canWin := rs.EvaluateHand(closed, melds, winTile, state, 0, req.IsTsumo)

	c.JSON(http.StatusOK, gin.H{
		"canWin":  canWin,
		"score":   score,
		"entries": entries,
	})
}
