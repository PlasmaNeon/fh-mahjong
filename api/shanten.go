package api

import (
	"math/rand"
	"net/http"

	"github.com/gin-gonic/gin"
	pb "github.com/plasma/fh-mahjong/proto"
	"github.com/plasma/fh-mahjong/rules/shanten"
)

type ShantenRequest struct {
	ClosedHand []CalcTileInput `json:"closedHand"`
	WildTile   *CalcTileInput  `json:"wildTile"`
	OpenMelds  int             `json:"openMelds"`
}

type UsefulTile struct {
	Suit      pb.Suit `json:"suit"`
	Value     uint32  `json:"value"`
	Remaining int     `json:"remaining"`
}

type DiscardOption struct {
	Discard     CalcTileInput `json:"discard"`
	Shanten     int           `json:"shanten"`
	UsefulTiles []UsefulTile  `json:"usefulTiles"`
	TotalUseful int           `json:"totalUseful"`
}

type ShantenResponse struct {
	Shanten        int             `json:"shanten"`
	DrawnTile      *CalcTileInput  `json:"drawnTile,omitempty"`
	DiscardOptions []DiscardOption `json:"discardOptions"`
}

func (s *Server) handleShanten(c *gin.Context) {
	var req ShantenRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid request body"})
		return
	}

	if req.OpenMelds < 0 || req.OpenMelds > 4 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "openMelds must be 0-4"})
		return
	}

	expectedBase := 13 - 3*req.OpenMelds
	handSize := len(req.ClosedHand)
	if handSize != expectedBase && handSize != expectedBase+1 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Closed hand must be 13 or 14 tiles (minus 3 per open meld)"})
		return
	}

	wildSet := make(map[uint32]bool)
	if req.WildTile != nil {
		wildSet[uint32(req.WildTile.Suit)*100+req.WildTile.Value] = true
	}

	// Build counts from hand
	var counts [34]int
	numWilds := 0
	for _, t := range req.ClosedHand {
		h := uint32(t.Suit)*100 + t.Value
		if wildSet[h] {
			numWilds++
		} else {
			idx := tileToShantenIndex(t.Suit, t.Value)
			if idx >= 0 {
				counts[idx]++
			}
		}
	}

	// For 13-tile hands: randomly draw a tile from remaining pool to make 14
	var drawnTile *CalcTileInput
	if handSize == expectedBase {
		drawn := drawRandomTile(counts, numWilds, wildSet)
		if drawn != nil {
			drawnTile = drawn
			h := uint32(drawn.Suit)*100 + drawn.Value
			if wildSet[h] {
				numWilds++
			} else {
				idx := tileToShantenIndex(drawn.Suit, drawn.Value)
				if idx >= 0 {
					counts[idx]++
				}
			}
			req.ClosedHand = append(req.ClosedHand, *drawn)
		}
	}

	// Discard analysis on the (now 14-tile) hand
	pbHand := make([]*pb.Tile, 0, len(req.ClosedHand))
	for idx, tile := range req.ClosedHand {
		pbHand = append(pbHand, &pb.Tile{
			Id:    uint32(idx),
			Suit:  tile.Suit,
			Value: tile.Value,
		})
	}

	wildTiles := make([]*pb.Tile, 0, len(wildSet))
	if req.WildTile != nil {
		wildTiles = append(wildTiles, &pb.Tile{
			Suit:  req.WildTile.Suit,
			Value: req.WildTile.Value,
		})
	}

	analysis := shanten.AnalyzeHand(pbHand, req.OpenMelds, wildTiles)
	currentShanten := analysis.Routes.Overall
	if currentShanten < 0 {
		currentShanten = 0
	}

	options := make([]DiscardOption, 0, len(analysis.DiscardOptions))
	for _, option := range analysis.DiscardOptions {
		usefulTiles := make([]UsefulTile, 0, len(option.UsefulTiles))
		for _, useful := range option.UsefulTiles {
			usefulTiles = append(usefulTiles, UsefulTile{
				Suit:      useful.Suit,
				Value:     useful.Value,
				Remaining: useful.Remaining,
			})
		}

		afterShanten := option.After.Overall
		if afterShanten < 0 {
			afterShanten = 0
		}

		options = append(options, DiscardOption{
			Discard: CalcTileInput{
				Suit:  option.Discard.Suit,
				Value: option.Discard.Value,
			},
			Shanten:     afterShanten,
			UsefulTiles: usefulTiles,
			TotalUseful: option.TotalUseful,
		})
	}

	c.JSON(http.StatusOK, ShantenResponse{
		Shanten:        currentShanten,
		DrawnTile:      drawnTile,
		DiscardOptions: options,
	})
}

// drawRandomTile picks a random tile from the remaining pool (tiles with count < 4)
func drawRandomTile(counts [34]int, numWilds int, wildSet map[uint32]bool) *CalcTileInput {
	type candidate struct {
		suit  pb.Suit
		value uint32
	}
	var pool []candidate

	for idx := 0; idx < 34; idx++ {
		suit, value := shantenIndexToTile(idx)
		h := uint32(suit)*100 + value
		var remaining int
		if wildSet[h] {
			remaining = 4 - numWilds
		} else {
			remaining = 4 - counts[idx]
		}
		for i := 0; i < remaining; i++ {
			pool = append(pool, candidate{suit, value})
		}
	}

	if len(pool) == 0 {
		return nil
	}

	pick := pool[rand.Intn(len(pool))]
	return &CalcTileInput{Suit: pick.suit, Value: pick.value}
}
func tileToShantenIndex(suit pb.Suit, value uint32) int {
	v := int(value) - 1
	switch suit {
	case pb.Suit_SUIT_MAN:
		return v
	case pb.Suit_SUIT_PIN:
		return 9 + v
	case pb.Suit_SUIT_SOU:
		return 18 + v
	case pb.Suit_SUIT_JIHAI:
		return 27 + v
	}
	return -1
}

func shantenIndexToTile(idx int) (pb.Suit, uint32) {
	switch {
	case idx < 9:
		return pb.Suit_SUIT_MAN, uint32(idx + 1)
	case idx < 18:
		return pb.Suit_SUIT_PIN, uint32(idx - 9 + 1)
	case idx < 27:
		return pb.Suit_SUIT_SOU, uint32(idx - 18 + 1)
	default:
		return pb.Suit_SUIT_JIHAI, uint32(idx - 27 + 1)
	}
}
