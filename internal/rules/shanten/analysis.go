package shanten

import (
	"sort"

	"github.com/plasma/fh-mahjong/internal/tiles"
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

	tilesToAdd := calcStandard(&counts, m)
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
	usefulTiles, totalUseful := findUsefulTiles(counts, numWilds, openMelds, routes, wildSet)
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
	usefulTiles, totalUseful := findUsefulTiles(counts, numWilds, openMelds, routes, wildSet)
	return usefulTiles, totalUseful, routes
}

func analyzeDiscardOptions(closedHand []*pb.Tile, counts [34]int, numWilds int, openMelds int, wildSet map[uint32]bool) []DiscardOption {
	seen := make(map[uint32]bool)
	options := make([]DiscardOption, 0, len(closedHand))

	for _, tile := range closedHand {
		key := tiles.KeyOf(tile.Suit, tile.Value)
		if seen[key] {
			continue
		}
		seen[key] = true

		isWild := wildSet[key]
		if isWild {
			numWilds--
		} else {
			idx := tiles.Index34(tile)
			if idx >= 0 {
				counts[idx]--
			}
		}

		after := Analyze(counts, numWilds, openMelds)
		usefulTiles, totalUseful := findUsefulTiles(counts, numWilds, openMelds, after, wildSet)
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
			idx := tiles.Index34(tile)
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
	wildSet := tiles.WildSet(wildTiles)

	var counts [34]int
	numWilds := 0
	for _, tile := range closedHand {
		key := tiles.KeyOf(tile.Suit, tile.Value)
		if wildSet[key] {
			numWilds++
			continue
		}

		idx := tiles.Index34(tile)
		if idx >= 0 {
			counts[idx]++
		}
	}

	return counts, numWilds, wildSet
}

// findUsefulTiles lists the draws that lower the hand's overall shanten
// (clamped at 0) below before.Overall's. `before` must be Analyze of exactly
// these counts, numWilds and openMelds.
func findUsefulTiles(counts [34]int, numWilds int, openMelds int, before RouteBreakdown, wildSet map[uint32]bool) ([]UsefulTile, int) {
	currentShanten := max(before.Overall, 0)

	usefulTiles := make([]UsefulTile, 0, 34)
	totalUseful := 0
	if currentShanten == 0 {
		// A draw's shanten is clamped at 0 too, so nothing can be below it.
		return usefulTiles, totalUseful
	}

	prefix := newStandardPrefix(&counts, maxMelds-openMelds)
	for idx := 0; idx < 34; idx++ {
		suit, value := tiles.FromIndex34(idx)
		key := tiles.KeyOf(suit, value)
		remaining := 4 - counts[idx]
		if wildSet[key] {
			remaining = 4 - numWilds
		}
		if remaining <= 0 {
			continue
		}

		var useful bool
		if wildSet[key] {
			// A wild draw leaves the natural counts, so the table value, unchanged.
			useful = drawBeats(&counts, prefix.base, numWilds+1, openMelds, before, currentShanten)
		} else {
			counts[idx]++
			useful = drawBeats(&counts, prefix.withDraw(&counts, idx), numWilds, openMelds, before, currentShanten)
			counts[idx]--
		}

		if useful {
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

// standardPrefix caches the fixed part of calcStandard's combination chain
// (honor, then add1 sou, then add1 pin, then add2 man) for one hand, so a
// one-tile draw recomputes only the chain from the group it lands in. add1
// is a pure function of its operands, so a resumed chain equals the full one.
type standardPrefix struct {
	m                      int
	honor, sou, souPin     [10]uint8 // chain state after honor / +sou / +pin
	manRow, pinRow, souRow [10]uint8 // the hand's suit table rows
	base                   int       // calcStandard of the hand itself
}

func newStandardPrefix(counts *[34]int, m int) standardPrefix {
	ensureTables()
	p := standardPrefix{m: m}
	p.manRow = suitTable[hash(counts[0:9])]
	p.pinRow = suitTable[hash(counts[9:18])]
	p.souRow = suitTable[hash(counts[18:27])]
	p.honor = honorTable[hash(counts[27:34])]
	p.sou = p.honor
	add1(&p.sou, p.souRow, m)
	p.souPin = p.sou
	add1(&p.souPin, p.pinRow, m)
	ret := p.souPin
	add2(&ret, p.manRow, m)
	p.base = int(ret[m+5])
	return p
}

// withDraw is calcStandard(counts, m) for counts = the prefix's hand plus
// one tile at idx (already added to counts).
func (p *standardPrefix) withDraw(counts *[34]int, idx int) int {
	m := p.m
	var ret [10]uint8
	switch {
	case idx < 9: // man: only the final add2 changes
		ret = p.souPin
		add2(&ret, suitTable[hash(counts[0:9])], m)
	case idx < 18: // pin
		ret = p.sou
		add1(&ret, suitTable[hash(counts[9:18])], m)
		add2(&ret, p.manRow, m)
	case idx < 27: // sou
		ret = p.honor
		add1(&ret, suitTable[hash(counts[18:27])], m)
		add1(&ret, p.pinRow, m)
		add2(&ret, p.manRow, m)
	default:
		return calcStandard(counts, m)
	}
	return int(ret[m+5])
}

// drawBeats reports whether Analyze(counts, numWilds, openMelds).Overall is
// below target (>= 1), where counts/numWilds are the hand plus one drawn tile,
// tilesToAdd is calcStandard of counts, and `before` is Analyze of the hand
// without the draw. One added tile, natural or wild, raises pairs+min(kinds,7)
// and the independence overlap by at most one, so the seven-pairs and
// independence shanten fall by at most one: a route with before >= target+1
// cannot reach below target, and is skipped.
func drawBeats(counts *[34]int, tilesToAdd int, numWilds int, openMelds int, before RouteBreakdown, target int) bool {
	if normalizeShanten(tilesToAdd-1-numWilds) < target {
		return true
	}
	if openMelds != 0 {
		return false
	}
	if before.SevenPairs-1 < target && normalizeShanten(calcSevenPairsWithWilds(*counts, numWilds)) < target {
		return true
	}
	return before.Independence-1 < target && normalizeShanten(calcIndependenceWithWilds(*counts, numWilds)) < target
}

func normalizeShanten(value int) int {
	if value < -1 {
		return -1
	}
	return value
}
