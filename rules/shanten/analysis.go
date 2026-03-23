package shanten

import (
	"sort"

	pb "github.com/plasma/fh-mahjong/proto"
)

const RouteUnavailable = 99

type RouteBreakdown struct {
	Overall      int
	Standard     int
	SevenPairs   int
	Independence int
}

type TileType struct {
	Suit  pb.Suit
	Value uint32
}

type UsefulTile struct {
	Suit      pb.Suit
	Value     uint32
	Remaining int
}

type DiscardOption struct {
	Discard     TileType
	After       RouteBreakdown
	UsefulTiles []UsefulTile
	TotalUseful int
	IsWild      bool
}

type HandAnalysis struct {
	Routes         RouteBreakdown
	UsefulTiles    []UsefulTile
	TotalUseful    int
	DiscardOptions []DiscardOption
}

func Analyze(counts [34]int, numWilds int, numOpenMelds int) RouteBreakdown {
	ensureTables()
	m := maxMelds - numOpenMelds

	tilesToAdd := calcStandard(counts, m)
	standard := normalizeShanten(tilesToAdd - 1 - numWilds)

	sevenPairs := RouteUnavailable
	independence := RouteUnavailable
	if numOpenMelds == 0 {
		sevenPairs = normalizeShanten(calcSevenPairsWithWilds(counts, numWilds))
		independence = normalizeShanten(calcIndependenceWithWilds(counts, numWilds))
	}

	overall := standard
	if sevenPairs < overall {
		overall = sevenPairs
	}
	if independence < overall {
		overall = independence
	}

	return RouteBreakdown{
		Overall:      overall,
		Standard:     standard,
		SevenPairs:   sevenPairs,
		Independence: independence,
	}
}

func AnalyzeFromTiles(closedHand []*pb.Tile, openMelds int, wildTiles []*pb.Tile) RouteBreakdown {
	counts, numWilds, _ := buildCountsFromTiles(closedHand, wildTiles)
	return Analyze(counts, numWilds, openMelds)
}

func AnalyzeHand(closedHand []*pb.Tile, openMelds int, wildTiles []*pb.Tile) HandAnalysis {
	counts, numWilds, wildSet := buildCountsFromTiles(closedHand, wildTiles)
	routes := Analyze(counts, numWilds, openMelds)
	usefulTiles, totalUseful := findUsefulTiles(counts, numWilds, openMelds, routes.Overall, wildSet)
	discardOptions := analyzeDiscardOptions(closedHand, counts, numWilds, openMelds, wildSet)

	return HandAnalysis{
		Routes:         routes,
		UsefulTiles:    usefulTiles,
		TotalUseful:    totalUseful,
		DiscardOptions: discardOptions,
	}
}

func FindUsefulTilesFromTiles(closedHand []*pb.Tile, openMelds int, wildTiles []*pb.Tile) ([]UsefulTile, int, RouteBreakdown) {
	counts, numWilds, wildSet := buildCountsFromTiles(closedHand, wildTiles)
	routes := Analyze(counts, numWilds, openMelds)
	usefulTiles, totalUseful := findUsefulTiles(counts, numWilds, openMelds, routes.Overall, wildSet)
	return usefulTiles, totalUseful, routes
}

func analyzeDiscardOptions(closedHand []*pb.Tile, counts [34]int, numWilds int, openMelds int, wildSet map[uint32]bool) []DiscardOption {
	seen := make(map[uint32]bool)
	options := make([]DiscardOption, 0, len(closedHand))

	for _, tile := range closedHand {
		key := tileHash(tile.Suit, tile.Value)
		if seen[key] {
			continue
		}
		seen[key] = true

		isWild := wildSet[key]
		if isWild {
			numWilds--
		} else {
			idx := tileToIndex(tile)
			if idx >= 0 {
				counts[idx]--
			}
		}

		after := Analyze(counts, numWilds, openMelds)
		usefulTiles, totalUseful := findUsefulTiles(counts, numWilds, openMelds, after.Overall, wildSet)
		options = append(options, DiscardOption{
			Discard: TileType{
				Suit:  tile.Suit,
				Value: tile.Value,
			},
			After:       after,
			UsefulTiles: usefulTiles,
			TotalUseful: totalUseful,
			IsWild:      isWild,
		})

		if isWild {
			numWilds++
		} else {
			idx := tileToIndex(tile)
			if idx >= 0 {
				counts[idx]++
			}
		}
	}

	sort.Slice(options, func(i, j int) bool {
		if options[i].After.Overall != options[j].After.Overall {
			return options[i].After.Overall < options[j].After.Overall
		}
		if options[i].TotalUseful != options[j].TotalUseful {
			return options[i].TotalUseful > options[j].TotalUseful
		}
		if options[i].Discard.Suit != options[j].Discard.Suit {
			return options[i].Discard.Suit < options[j].Discard.Suit
		}
		return options[i].Discard.Value < options[j].Discard.Value
	})

	return options
}

func buildCountsFromTiles(closedHand []*pb.Tile, wildTiles []*pb.Tile) ([34]int, int, map[uint32]bool) {
	ensureTables()
	wildSet := make(map[uint32]bool)
	for _, wild := range wildTiles {
		wildSet[tileHash(wild.Suit, wild.Value)] = true
	}

	var counts [34]int
	numWilds := 0
	for _, tile := range closedHand {
		key := tileHash(tile.Suit, tile.Value)
		if wildSet[key] {
			numWilds++
			continue
		}

		idx := tileToIndex(tile)
		if idx >= 0 {
			counts[idx]++
		}
	}

	return counts, numWilds, wildSet
}

func findUsefulTiles(counts [34]int, numWilds int, openMelds int, currentShanten int, wildSet map[uint32]bool) ([]UsefulTile, int) {
	if currentShanten < 0 {
		currentShanten = 0
	}

	usefulTiles := make([]UsefulTile, 0, 34)
	totalUseful := 0

	for idx := 0; idx < 34; idx++ {
		remaining := 4 - counts[idx]
		suit, value := indexToTile(idx)
		key := tileHash(suit, value)
		if wildSet[key] {
			remaining = 4 - numWilds
		}
		if remaining <= 0 {
			continue
		}

		counts[idx]++
		newShanten := Analyze(counts, numWilds, openMelds).Overall
		if newShanten < 0 {
			newShanten = 0
		}
		counts[idx]--

		if newShanten < currentShanten {
			usefulTiles = append(usefulTiles, UsefulTile{
				Suit:      suit,
				Value:     value,
				Remaining: remaining,
			})
			totalUseful += remaining
		}
	}

	return usefulTiles, totalUseful
}

func normalizeShanten(value int) int {
	if value < -1 {
		return -1
	}
	return value
}

func tileHash(suit pb.Suit, value uint32) uint32 {
	return uint32(suit)*100 + value
}

func indexToTile(idx int) (pb.Suit, uint32) {
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
