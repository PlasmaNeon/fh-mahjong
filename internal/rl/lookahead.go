package rl

import (
	"fmt"

	"github.com/plasma/fh-mahjong/internal/rules/shanten"
	pb "github.com/plasma/fh-mahjong/proto"
)

// MaxLookaheadVersion is the highest EnvConfig.lookahead_version the encoder
// knows. Version 1 adds the 13 discard/call look-ahead channels of
// worklog/specs/20261004-discard-call-lookahead-planes.md; 0 adds none.
const MaxLookaheadVersion = 1

// Channel offsets inside the version-1 block, which starts at channel 39.
const (
	lookaheadDiscardOverall = iota
	lookaheadDiscardStandard
	lookaheadDiscardSevenPairs
	lookaheadDiscardIndependence
	lookaheadDiscardUseful
	lookaheadDiscardLive
	lookaheadDiscardDanger
	lookaheadPonShanten
	lookaheadPonLive
	lookaheadChiiShanten
	lookaheadChiiLive
	lookaheadKanShanten
	lookaheadKanLive
	lookaheadV1Channels
)

// LookaheadPlaneCount is the number of plane channels a look-ahead version adds.
func LookaheadPlaneCount(version uint32) int {
	if version == 1 {
		return lookaheadV1Channels
	}
	return 0
}

func validateLookaheadVersion(version uint32) error {
	if version > MaxLookaheadVersion {
		return fmt.Errorf("lookahead_version %d exceeds maximum %d", version, MaxLookaheadVersion)
	}
	return nil
}

// observationChannels is the plane channel count of an encoder configuration:
// the 39 public channels, the look-ahead block, then the 12 oracle channels.
func observationChannels(oracle bool, lookahead uint32) int {
	channels := ObservationPlaneChannels + LookaheadPlaneCount(lookahead)
	if oracle {
		channels += 12
	}
	return channels
}

// liveUsefulCount is the useful-tile count net of copies the seat can see
// (`visible` is publicSeenCounts, which includes the face-up wild indicator).
func liveUsefulCount(useful []shanten.UsefulTile, visible [42]int) int {
	total := 0
	for _, tile := range useful {
		face, ok := tileFaceIndex42(&pb.Tile{Suit: tile.Suit, Value: tile.Value})
		if !ok {
			continue
		}
		if live := tile.Remaining - visible[face]; live > 0 {
			total += live
		}
	}
	return total
}

// handWithout is the closed hand minus the tiles (by id) a call reveals.
func handWithout(hand []*pb.Tile, revealed []*pb.Tile) ([]*pb.Tile, error) {
	drop := make(map[uint32]bool, len(revealed))
	for _, tile := range revealed {
		drop[tile.GetId()] = true
	}
	rest := make([]*pb.Tile, 0, len(hand))
	for _, tile := range hand {
		if drop[tile.GetId()] {
			delete(drop, tile.GetId())
			continue
		}
		rest = append(rest, tile)
	}
	if len(drop) > 0 {
		return nil, fmt.Errorf("call reveals %d tile(s) not in the closed hand", len(drop))
	}
	return rest, nil
}

// handWithoutFace is the hand minus one tile of `face`, and that tile (nil when
// the hand holds none).
func handWithoutFace(hand []*pb.Tile, face shanten.TileType) ([]*pb.Tile, *pb.Tile) {
	for i, tile := range hand {
		if tile.GetSuit() == face.Suit && tile.GetValue() == face.Value {
			rest := make([]*pb.Tile, 0, len(hand)-1)
			rest = append(rest, hand[:i]...)
			return append(rest, hand[i+1:]...), tile
		}
	}
	return hand, nil
}

// seenAfterMoving adds the tiles the seat's own action moves to its river or
// melds: copies it can see that are no longer in its hand.
func seenAfterMoving(visible [42]int, moved ...*pb.Tile) [42]int {
	for _, tile := range moved {
		if face, ok := tileFaceIndex42(tile); ok {
			visible[face]++
		}
	}
	return visible
}

// lookaheadUseful is a look-ahead hand's useful tiles: the draws that lower its
// shanten or, at tenpai (where findUsefulTiles lists none), the draws that
// complete it.
func lookaheadUseful(rest []*pb.Tile, melds int, wilds []*pb.Tile, routeShanten int,
	useful []shanten.UsefulTile, total int) ([]shanten.UsefulTile, int) {
	if routeShanten == 0 {
		return shanten.WinningTiles(rest, melds, wilds)
	}
	return useful, total
}

// bestAfterCall analyses the hand after a pon or chii and the discard that must
// follow: the lowest standard shanten, then the most live useful tiles.
func bestAfterCall(player *pb.PlayerState, action *pb.PlayerAction, wilds []*pb.Tile, visible [42]int) (int, int, error) {
	rest, err := handWithout(player.ClosedHand, action.MeldTiles)
	if err != nil {
		return 0, 0, err
	}
	melds := len(player.OpenMelds) + 1
	seen := seenAfterMoving(visible, action.MeldTiles...)
	best, bestLive := shanten.RouteUnavailable, 0
	for _, option := range shanten.AnalyzeHand(rest, melds, wilds).DiscardOptions {
		after, discarded := handWithoutFace(rest, option.Discard)
		useful, _ := lookaheadUseful(after, melds, wilds, option.After.Standard, option.UsefulTiles, option.TotalUseful)
		live := liveUsefulCount(useful, seenAfterMoving(seen, discarded))
		if option.After.Standard < best || (option.After.Standard == best && live > bestLive) {
			best, bestLive = option.After.Standard, live
		}
	}
	return best, bestLive, nil
}

// afterKan analyses the hand after a kan, before the replacement draw.
func afterKan(player *pb.PlayerState, action *pb.PlayerAction, melds int, wilds []*pb.Tile, visible [42]int) (int, int, error) {
	rest, err := handWithout(player.ClosedHand, action.MeldTiles)
	if err != nil {
		return 0, 0, err
	}
	analysis := shanten.AnalyzeHand(rest, melds, wilds)
	useful, _ := lookaheadUseful(rest, melds, wilds, analysis.Routes.Standard, analysis.UsefulTiles, analysis.TotalUseful)
	return analysis.Routes.Standard, liveUsefulCount(useful, seenAfterMoving(visible, action.MeldTiles...)), nil
}

// setLookaheadPlanes writes the version-1 block starting at channel `base`.
func setLookaheadPlanes(planes []float32, base int, state *pb.GameState, seat uint32,
	legal map[int]*pb.PlayerAction, analysis shanten.HandAnalysis) error {
	player := state.Players[seat]
	visible := publicSeenCounts(state)
	options := make(map[int]shanten.DiscardOption, len(analysis.DiscardOptions))
	for _, option := range analysis.DiscardOptions {
		if face, ok := tileFaceIndex42(&pb.Tile{Suit: option.Discard.Suit, Value: option.Discard.Value}); ok {
			options[face] = option
		}
	}
	set := func(channel, face int, value float32) {
		planes[channelOffset(base+channel)+face] = value
	}
	setCall := func(shantenChannel, face, standard, live int) {
		set(shantenChannel, face, normalizeShanten(standard))
		set(shantenChannel+1, face, normalizeUsefulTileCount(live))
	}
	for _, actionID := range SortedLegalIDs(legal) {
		action := legal[actionID]
		switch {
		case actionID >= DiscardBase && actionID < DiscardBase+DiscardCount:
			face := actionID - DiscardBase
			option, ok := options[face]
			if !ok {
				return fmt.Errorf("legal discard %d has no shanten option", actionID)
			}
			set(lookaheadDiscardOverall, face, normalizeShanten(option.After.Overall))
			set(lookaheadDiscardStandard, face, normalizeShanten(option.After.Standard))
			set(lookaheadDiscardSevenPairs, face, normalizeShanten(option.After.SevenPairs))
			set(lookaheadDiscardIndependence, face, normalizeShanten(option.After.Independence))
			rest, err := handWithout(player.ClosedHand, []*pb.Tile{action.Tile})
			if err != nil {
				return err
			}
			useful, total := lookaheadUseful(rest, len(player.OpenMelds), state.WildTiles,
				option.After.Overall, option.UsefulTiles, option.TotalUseful)
			set(lookaheadDiscardUseful, face, normalizeUsefulTileCount(total))
			set(lookaheadDiscardLive, face, normalizeUsefulTileCount(liveUsefulCount(useful, seenAfterMoving(visible, action.Tile))))
			set(lookaheadDiscardDanger, face, publicDangerScore(state, seat, action.Tile))
		case actionID >= PonBase && actionID < PonBase+PonCount:
			standard, live, err := bestAfterCall(player, action, state.WildTiles, visible)
			if err != nil {
				return err
			}
			setCall(lookaheadPonShanten, actionID-PonBase, standard, live)
		case actionID >= KanDirectBase && actionID < ChiiBase:
			melds := len(player.OpenMelds) + 1
			if actionID >= KanUpgradedBase {
				melds = len(player.OpenMelds) // the pon becomes the kan
			}
			standard, live, err := afterKan(player, action, melds, state.WildTiles, visible)
			if err != nil {
				return err
			}
			setCall(lookaheadKanShanten, (actionID-KanDirectBase)%KanModeCount, standard, live)
		case actionID >= ChiiBase && actionID < ChiiBase+ChiiCount:
			index := actionID - ChiiBase
			middle := (index/7)*9 + index%7 + 1
			standard, live, err := bestAfterCall(player, action, state.WildTiles, visible)
			if err != nil {
				return err
			}
			setCall(lookaheadChiiShanten, middle, standard, live)
		}
	}
	return nil
}
