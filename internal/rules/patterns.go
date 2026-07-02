package rules

import (
	pb "github.com/plasma/fh-mahjong/proto"
)

// Stable scoring-pattern identifiers, carried in pb.ScoreEntry.PatternId.
// Logic (reward classification, localization, analytics) must key off these,
// never off the bilingual display strings in patternDisplayNames, so display
// text can change without silently breaking behavior. Never rename an
// existing id: replays and clients persist them.
const (
	PatternBasePoint               = "base_point"
	PatternTsumo                   = "tsumo"
	PatternNoWildTiles             = "no_wild_tiles"
	PatternOneWildTile             = "one_wild_tile"
	PatternTwoWildTiles            = "two_wild_tiles"
	PatternThreeFlowerWildTiles    = "three_flower_wild_tiles"
	PatternThreeNormalWildTiles    = "three_normal_wild_tiles"
	PatternTameWildTiles           = "tame_wild_tiles"
	PatternIndependence            = "independence"
	PatternClosedSevenStars        = "closed_seven_stars"
	PatternOpenSevenStars          = "open_seven_stars"
	PatternIndependenceMissingSuit = "independence_missing_suit"
	PatternStraightSevenPairs      = "straight_seven_pairs"
	PatternWildSevenPairs          = "wild_seven_pairs"
	PatternClosedBomb              = "closed_bomb"
	PatternOpenBomb                = "open_bomb"
	PatternCommonWin               = "common_win"
	PatternSinglePairCall          = "single_pair_call"
	PatternStraightLoner           = "straight_loner"
	PatternWildLoner               = "wild_loner"
	PatternStraightAllPung         = "straight_all_pung"
	PatternWildAllPung             = "wild_all_pung"
	PatternUncompletedAllHonors    = "uncompleted_all_honors"
	PatternCompletedAllHonors      = "completed_all_honors"
	PatternPureOneSuit             = "pure_one_suit"
	PatternMixedOneSuit            = "mixed_one_suit"
	PatternUncompletedEightFlowers = "uncompleted_eight_flowers"
	PatternCompletedEightFlowers   = "completed_eight_flowers"
	PatternFourFlowers             = "four_flowers"
	PatternOwnFlower               = "own_flower"
	PatternDragonPung              = "dragon_pung"
	PatternRightWind               = "right_wind"
	PatternSeatWind                = "seat_wind"
	PatternPrevailingWind          = "prevailing_wind"
	PatternBloomingDirectKong      = "blooming_direct_kong"
	PatternBuddingDirectKong       = "budding_direct_kong"
	PatternBloomingClosedKong      = "blooming_closed_kong"
	PatternBuddingClosedKong       = "budding_closed_kong"
	PatternBloomingRiskyKong       = "blooming_risky_kong"
	PatternBuddingRiskyKong        = "budding_risky_kong"
	PatternBloomingFlowerKong      = "blooming_flower_kong"
)

// patternDisplayNames is the single source of the human-facing labels.
var patternDisplayNames = map[string]string{
	PatternBasePoint:               "Base Point (坐台)",
	PatternTsumo:                   "Tsumo (自摸)",
	PatternNoWildTiles:             "No Wild Tiles (无搭)",
	PatternOneWildTile:             "One Wild Tile (一搭)",
	PatternTwoWildTiles:            "Two Wild Tiles (二搭)",
	PatternThreeFlowerWildTiles:    "Three Flower Wild Tiles (三花三百搭)",
	PatternThreeNormalWildTiles:    "Three Normal Wild Tiles (普通三百搭)",
	PatternTameWildTiles:           "Tame Wild Tiles (还搭)",
	PatternIndependence:            "Independence (大大胡)",
	PatternClosedSevenStars:        "Closed Seven Stars (暗七星)",
	PatternOpenSevenStars:          "Open Seven Stars (明七星)",
	PatternIndependenceMissingSuit: "Independence Without Suit (缺色)",
	PatternStraightSevenPairs:      "Straight Seven Pairs (七对头无搭)",
	PatternWildSevenPairs:          "Wild Seven Pairs (七对头有搭)",
	PatternClosedBomb:              "Closed Bomb (暗炸)",
	PatternOpenBomb:                "Open Bomb (明炸)",
	PatternCommonWin:               "Common Win (朋胡)",
	PatternSinglePairCall:          "Single/Pair Call (边嵌单吊对倒)",
	PatternStraightLoner:           "Straight Loner (大吊车无搭)",
	PatternWildLoner:               "Wild Loner (大吊车有搭)",
	PatternStraightAllPung:         "Straight All Pung (大对对无搭)",
	PatternWildAllPung:             "Wild All Pung (大对对有搭)",
	PatternUncompletedAllHonors:    "Uncompleted All Honors (乱老头)",
	PatternCompletedAllHonors:      "Completed All Honors (清老头)",
	PatternPureOneSuit:             "Pure One Suit (清一色)",
	PatternMixedOneSuit:            "Mixed One Suit (混一色)",
	PatternUncompletedEightFlowers: "Uncompleted Eight Flowers (八花直胡)",
	PatternCompletedEightFlowers:   "Completed Eight Flowers (八花搓胡)",
	PatternFourFlowers:             "Four Flowers (四花)",
	PatternOwnFlower:               "Own Flower (花)",
	PatternDragonPung:              "Dragon Pung (中发白碰出)",
	PatternRightWind:               "Right Wind (正风)",
	PatternSeatWind:                "Seat Wind (位风)",
	PatternPrevailingWind:          "Prevailing Wind (圈风)",
	PatternBloomingDirectKong:      "Blooming Direct Kong (直杠开花)",
	PatternBuddingDirectKong:       "Budding Direct Kong (直杠不开花)",
	PatternBloomingClosedKong:      "Blooming Closed Kong (暗杠开花)",
	PatternBuddingClosedKong:       "Budding Closed Kong (暗杠不开花)",
	PatternBloomingRiskyKong:       "Blooming Risky Kong (风险杠开花)",
	PatternBuddingRiskyKong:        "Budding Risky Kong (风险杠不开花)",
	PatternBloomingFlowerKong:      "Blooming Flower Kong (花杠杠开)",
}

// NewScoreEntry builds a ScoreEntry carrying both the stable id and its
// display name. The display name falls back to the id itself so an
// unregistered id is visible instead of blank.
func NewScoreEntry(id string, points int32) *pb.ScoreEntry {
	name, ok := patternDisplayNames[id]
	if !ok {
		name = id
	}
	return &pb.ScoreEntry{PatternId: id, PatternName: name, Points: points}
}

// rewardPatternIds classifies "reward" bonuses — lucky tile collection
// (flowers, kong completions) rather than playing-hand quality. They are
// awarded but excluded from the 4-point Ron minimum.
var rewardPatternIds = map[string]bool{
	PatternFourFlowers:        true,
	PatternOwnFlower:          true,
	PatternBuddingDirectKong:  true,
	PatternBloomingDirectKong: true,
	PatternBuddingClosedKong:  true,
	PatternBloomingClosedKong: true,
	PatternBuddingRiskyKong:   true,
	PatternBloomingRiskyKong:  true,
	PatternBloomingFlowerKong: true,
}
