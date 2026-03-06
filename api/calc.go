package api

import (
	"fmt"
	"net/http"
	"sort"
	"strings"

	"github.com/gin-gonic/gin"
	pb "github.com/plasma/fh-mahjong/proto"
	"github.com/plasma/fh-mahjong/rules"
)

type CalcTileInput struct {
	Suit  pb.Suit `json:"suit"`
	Value uint32  `json:"value"`
}

type CalcMeldInput struct {
	Type            pb.ActionType    `json:"type"`
	Tiles           []CalcTileInput  `json:"tiles"`
	CalledTileIndex int              `json:"calledTileIndex"`
	CalledDirection pb.MeldDirection `json:"calledDirection"`
	KongFlags       CalcKongFlags    `json:"kongFlags"`
}

type CalcKongFlags struct {
	HasBuddingDirectKong  bool `json:"hasBuddingDirectKong"`
	HasBloomingDirectKong bool `json:"hasBloomingDirectKong"`
	HasBuddingClosedKong  bool `json:"hasBuddingClosedKong"`
	HasBloomingClosedKong bool `json:"hasBloomingClosedKong"`
	HasBuddingRiskyKong   bool `json:"hasBuddingRiskyKong"`
	HasBloomingRiskyKong  bool `json:"hasBloomingRiskyKong"`
	HasBloomingFlowerKong bool `json:"hasBloomingFlowerKong"`
}

type CalcRequest struct {
	ClosedHand     []CalcTileInput `json:"closedHand"`
	WinTile        *CalcTileInput  `json:"winTile"`
	WildTile       *CalcTileInput  `json:"wildTile"`
	OpenMelds      []CalcMeldInput `json:"openMelds"`
	FlowerMelds    []uint32        `json:"flowerMelds"`
	SeatWind       uint32          `json:"seatWind"`
	PrevailingWind uint32          `json:"prevailingWind"`
	IsTsumo        bool            `json:"isTsumo"`
	KongFlags      CalcKongFlags   `json:"kongFlags"`
}

type CalcScoreEntry struct {
	PatternName string `json:"patternName"`
	Points      int32  `json:"points"`
}

type CalcNormalizedMeld struct {
	Type            string `json:"type"`
	Tiles           string `json:"tiles"`
	CalledTile      string `json:"calledTile"`
	CalledTileIndex int    `json:"calledTileIndex"`
	CalledDirection string `json:"calledDirection"`
	KongFlags       []string `json:"kongFlags"`
}

type CalcNormalizedSummary struct {
	ClosedHand      string               `json:"closedHand"`
	WinTile         string               `json:"winTile"`
	WildTile        string               `json:"wildTile"`
	OpenMelds       []CalcNormalizedMeld `json:"openMelds"`
	FlowerMelds     []string             `json:"flowerMelds"`
	SeatWind        string               `json:"seatWind"`
	PrevailingWind  string               `json:"prevailingWind"`
	WinType         string               `json:"winType"`
	KongFlags       []string             `json:"kongFlags"`
	ExpectedHandLen int                  `json:"expectedHandLen"`
}

type calcEvaluation struct {
	closedHand []*pb.Tile
	openMelds  []*pb.Meld
	winTile    *pb.Tile
	state      *pb.GameState
	normalized CalcNormalizedSummary
	kongCounts CalcKongFlagCounts
}

type CalcKongFlagCounts struct {
	HasBuddingDirectKong  int
	HasBloomingDirectKong int
	HasBuddingClosedKong  int
	HasBloomingClosedKong int
	HasBuddingRiskyKong   int
	HasBloomingRiskyKong  int
	HasBloomingFlowerKong int
}

func (s *Server) handleCalc(c *gin.Context) {
	var req CalcRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{
			"errors": []string{"Invalid request payload"},
		})
		return
	}

	eval, errs := buildCalcEvaluation(req)
	if len(errs) > 0 {
		c.JSON(http.StatusBadRequest, gin.H{
			"errors": errs,
		})
		return
	}

	rs := &rules.HometownRuleset{}
	score, entries, canWin := rs.EvaluateHand(eval.closedHand, eval.openMelds, eval.winTile, eval.state, 0, req.IsTsumo)
	score, entries, canWin = applyExtraKongBonuses(score, entries, canWin, req.IsTsumo, eval.kongCounts)

	responseEntries := make([]CalcScoreEntry, 0, len(entries))
	for _, entry := range entries {
		responseEntries = append(responseEntries, CalcScoreEntry{
			PatternName: entry.PatternName,
			Points:      entry.Points,
		})
	}

	c.JSON(http.StatusOK, gin.H{
		"canWin":    canWin,
		"score":     score,
		"entries":   responseEntries,
		"normalized": eval.normalized,
	})
}

func buildCalcEvaluation(req CalcRequest) (*calcEvaluation, []string) {
	var errs []string

	if req.WinTile == nil {
		errs = append(errs, "Win tile is required.")
	}
	if req.SeatWind < 1 || req.SeatWind > 4 {
		errs = append(errs, "Seat wind must be between 1 and 4.")
	}
	if req.PrevailingWind < 1 || req.PrevailingWind > 4 {
		errs = append(errs, "Prevailing wind must be between 1 and 4.")
	}
	if len(req.FlowerMelds) > 8 {
		errs = append(errs, "Flower meld count cannot exceed 8.")
	}

	expectedHandLen := 13 - (3 * len(req.OpenMelds))
	if expectedHandLen < 0 {
		errs = append(errs, "Open meld count cannot exceed 4.")
	}
	if len(req.ClosedHand) != expectedHandLen {
		errs = append(errs, fmt.Sprintf("Closed hand must contain %d tiles for %d open meld(s).", expectedHandLen, len(req.OpenMelds)))
	}

	for idx, tile := range req.ClosedHand {
		if err := validateCalcTile(tile); err != "" {
			errs = append(errs, fmt.Sprintf("Closed hand tile %d: %s", idx+1, err))
		}
	}
	if req.WinTile != nil {
		if err := validateCalcTile(*req.WinTile); err != "" {
			errs = append(errs, fmt.Sprintf("Win tile: %s", err))
		}
	}
	if req.WildTile != nil {
		if err := validateCalcTile(*req.WildTile); err != "" {
			errs = append(errs, fmt.Sprintf("Wild tile: %s", err))
		}
	}

	for idx, flower := range req.FlowerMelds {
		if flower < 1 || flower > 8 {
			errs = append(errs, fmt.Sprintf("Flower meld %d must be between 1 and 8.", idx+1))
		}
	}

	for idx, meld := range req.OpenMelds {
		if err := validateCalcMeld(meld); err != "" {
			errs = append(errs, fmt.Sprintf("Open meld %d: %s", idx+1, err))
		}
	}

	physicalCounts := make(map[string]int)
	for _, tile := range req.ClosedHand {
		physicalCounts[tileKey(tile)]++
	}
	if req.WinTile != nil {
		physicalCounts[tileKey(*req.WinTile)]++
	}
	for _, meld := range req.OpenMelds {
		for _, tile := range meld.Tiles {
			physicalCounts[tileKey(tile)]++
		}
	}
	for key, count := range physicalCounts {
		if count > 4 {
			errs = append(errs, fmt.Sprintf("Tile %s appears %d times; physical tiles are capped at 4 copies.", key, count))
		}
	}

	if len(errs) > 0 {
		return nil, errs
	}

	var nextTileID uint32 = 1
	makeTile := func(input CalcTileInput) *pb.Tile {
		tile := &pb.Tile{
			Id:    nextTileID,
			Suit:  input.Suit,
			Value: input.Value,
		}
		nextTileID++
		return tile
	}

	closedHand := make([]*pb.Tile, 0, len(req.ClosedHand))
	for _, tile := range req.ClosedHand {
		closedHand = append(closedHand, makeTile(tile))
	}

	var winTile *pb.Tile
	if req.WinTile != nil {
		winTile = makeTile(*req.WinTile)
	}

	openMelds := make([]*pb.Meld, 0, len(req.OpenMelds))
	for _, meld := range req.OpenMelds {
		tiles := make([]*pb.Tile, 0, len(meld.Tiles))
		for _, tile := range meld.Tiles {
			tiles = append(tiles, makeTile(tile))
		}

		openMelds = append(openMelds, &pb.Meld{
			Type:            meld.Type,
			Tiles:           tiles,
			CalledTileId:    tiles[meld.CalledTileIndex].Id,
			CalledDirection: meld.CalledDirection,
		})
	}

	wildTiles := make([]*pb.Tile, 0, 1)
	if req.WildTile != nil {
		wildTiles = append(wildTiles, makeTile(*req.WildTile))
	}

	flowerMelds := make([]*pb.Tile, 0, len(req.FlowerMelds))
	for _, flower := range req.FlowerMelds {
		flowerMelds = append(flowerMelds, &pb.Tile{
			Id:    nextTileID,
			Suit:  pb.Suit_SUIT_UNKNOWN,
			Value: flower,
		})
		nextTileID++
	}

	player := &pb.PlayerState{
		SeatWind:               req.SeatWind,
		FlowerMelds:            flowerMelds,
		HasBuddingDirectKong:   false,
		HasBloomingDirectKong:  false,
		HasBuddingClosedKong:   false,
		HasBloomingClosedKong:  false,
		HasBuddingRiskyKong:    false,
		HasBloomingRiskyKong:   false,
		HasBloomingFlowerKong:  false,
	}

	kongCounts := countKongFlags(req)
	player.HasBuddingDirectKong = kongCounts.HasBuddingDirectKong > 0
	player.HasBloomingDirectKong = kongCounts.HasBloomingDirectKong > 0
	player.HasBuddingClosedKong = kongCounts.HasBuddingClosedKong > 0
	player.HasBloomingClosedKong = kongCounts.HasBloomingClosedKong > 0
	player.HasBuddingRiskyKong = kongCounts.HasBuddingRiskyKong > 0
	player.HasBloomingRiskyKong = kongCounts.HasBloomingRiskyKong > 0
	player.HasBloomingFlowerKong = kongCounts.HasBloomingFlowerKong > 0

	state := &pb.GameState{
		PrevailingWind: req.PrevailingWind,
		WildTiles:      wildTiles,
		Players:        []*pb.PlayerState{player},
	}

	normalized := CalcNormalizedSummary{
		ClosedHand:      formatTehai(req.ClosedHand),
		WinTile:         formatTilePointer(req.WinTile),
		WildTile:        formatTilePointer(req.WildTile),
		OpenMelds:       normalizeMelds(req.OpenMelds),
		FlowerMelds:     normalizeFlowers(req.FlowerMelds),
		SeatWind:        windName(req.SeatWind),
		PrevailingWind:  windName(req.PrevailingWind),
		WinType:         map[bool]string{true: "tsumo", false: "ron"}[req.IsTsumo],
		KongFlags:       normalizeKongFlags(req.KongFlags),
		ExpectedHandLen: expectedHandLen,
	}

	return &calcEvaluation{
		closedHand: closedHand,
		openMelds:  openMelds,
		winTile:    winTile,
		state:      state,
		normalized: normalized,
		kongCounts: kongCounts,
	}, nil
}

func validateCalcTile(tile CalcTileInput) string {
	switch tile.Suit {
	case pb.Suit_SUIT_MAN, pb.Suit_SUIT_PIN, pb.Suit_SUIT_SOU:
		if tile.Value < 1 || tile.Value > 9 {
			return "suited tile value must be between 1 and 9"
		}
	case pb.Suit_SUIT_JIHAI:
		if tile.Value < 1 || tile.Value > 7 {
			return "jihai tile value must be between 1 and 7"
		}
	default:
		return "tile suit must be man, pin, sou, or jihai"
	}

	return ""
}

func validateCalcMeld(meld CalcMeldInput) string {
	switch meld.Type {
	case pb.ActionType_ACTION_CHII, pb.ActionType_ACTION_PON, pb.ActionType_ACTION_KAN:
	default:
		return "meld type must be chii, pon, or kan"
	}

	switch meld.CalledDirection {
	case pb.MeldDirection_MELD_DIRECTION_RIGHT, pb.MeldDirection_MELD_DIRECTION_ACROSS, pb.MeldDirection_MELD_DIRECTION_LEFT:
	default:
		return "called direction must be right, across, or left"
	}

	expectedLen := 3
	if meld.Type == pb.ActionType_ACTION_KAN {
		expectedLen = 4
	}
	if len(meld.Tiles) != expectedLen {
		return fmt.Sprintf("meld must contain exactly %d tile(s)", expectedLen)
	}
	if meld.CalledTileIndex < 0 || meld.CalledTileIndex >= len(meld.Tiles) {
		return "called tile index is out of range"
	}

	for _, tile := range meld.Tiles {
		if err := validateCalcTile(tile); err != "" {
			return err
		}
	}

	switch meld.Type {
	case pb.ActionType_ACTION_CHII:
		suit := meld.Tiles[0].Suit
		if suit != pb.Suit_SUIT_MAN && suit != pb.Suit_SUIT_PIN && suit != pb.Suit_SUIT_SOU {
			return "chii tiles must be suited tiles"
		}
		values := []int{int(meld.Tiles[0].Value), int(meld.Tiles[1].Value), int(meld.Tiles[2].Value)}
		sort.Ints(values)
		if meld.Tiles[1].Suit != suit || meld.Tiles[2].Suit != suit {
			return "chii tiles must share the same suit"
		}
		if values[0]+1 != values[1] || values[1]+1 != values[2] {
			return "chii tiles must form a consecutive sequence"
		}
	case pb.ActionType_ACTION_PON:
		first := meld.Tiles[0]
		for _, tile := range meld.Tiles[1:] {
			if tile.Suit != first.Suit || tile.Value != first.Value {
				return "pon tiles must all be identical"
			}
		}
	case pb.ActionType_ACTION_KAN:
		first := meld.Tiles[0]
		for _, tile := range meld.Tiles[1:] {
			if tile.Suit != first.Suit || tile.Value != first.Value {
				return "kan tiles must all be identical"
			}
		}
	}

	return ""
}

func tileKey(tile CalcTileInput) string {
	return formatTile(tile)
}

func formatTile(tile CalcTileInput) string {
	switch tile.Suit {
	case pb.Suit_SUIT_MAN:
		return fmt.Sprintf("%dm", tile.Value)
	case pb.Suit_SUIT_PIN:
		return fmt.Sprintf("%dp", tile.Value)
	case pb.Suit_SUIT_SOU:
		return fmt.Sprintf("%ds", tile.Value)
	case pb.Suit_SUIT_JIHAI:
		return fmt.Sprintf("%dz", tile.Value)
	default:
		return fmt.Sprintf("f%d", tile.Value)
	}
}

func formatTilePointer(tile *CalcTileInput) string {
	if tile == nil {
		return ""
	}
	return formatTile(*tile)
}

func formatTehai(tiles []CalcTileInput) string {
	if len(tiles) == 0 {
		return ""
	}

	sortedTiles := append([]CalcTileInput(nil), tiles...)
	sort.Slice(sortedTiles, func(i, j int) bool {
		leftOrder := suitSortOrder(sortedTiles[i].Suit)
		rightOrder := suitSortOrder(sortedTiles[j].Suit)
		if leftOrder != rightOrder {
			return leftOrder < rightOrder
		}
		return sortedTiles[i].Value < sortedTiles[j].Value
	})

	var groups []string
	currentSuit := pb.Suit_SUIT_UNKNOWN
	var builder strings.Builder
	for _, tile := range sortedTiles {
		if tile.Suit != currentSuit && builder.Len() > 0 {
			groups = append(groups, builder.String())
			builder.Reset()
		}
		builder.WriteString(formatTile(tile))
		currentSuit = tile.Suit
	}
	if builder.Len() > 0 {
		groups = append(groups, builder.String())
	}

	return strings.Join(groups, " ")
}

func normalizeMelds(melds []CalcMeldInput) []CalcNormalizedMeld {
	normalized := make([]CalcNormalizedMeld, 0, len(melds))
	for _, meld := range melds {
		tileStrings := make([]string, 0, len(meld.Tiles))
		for _, tile := range meld.Tiles {
			tileStrings = append(tileStrings, formatTile(tile))
		}

		calledTile := ""
		if meld.CalledTileIndex >= 0 && meld.CalledTileIndex < len(meld.Tiles) {
			calledTile = formatTile(meld.Tiles[meld.CalledTileIndex])
		}

		normalized = append(normalized, CalcNormalizedMeld{
			Type:            actionName(meld.Type),
			Tiles:           strings.Join(tileStrings, ""),
			CalledTile:      calledTile,
			CalledTileIndex: meld.CalledTileIndex,
			CalledDirection: directionName(meld.CalledDirection),
			KongFlags:       normalizeKongFlags(meld.KongFlags),
		})
	}
	return normalized
}

func normalizeFlowers(flowers []uint32) []string {
	normalized := make([]string, 0, len(flowers))
	for _, flower := range flowers {
		normalized = append(normalized, fmt.Sprintf("Flower %d", flower))
	}
	return normalized
}

func normalizeKongFlags(flags CalcKongFlags) []string {
	var active []string
	if flags.HasBuddingDirectKong {
		active = append(active, "Budding Direct Kong")
	}
	if flags.HasBloomingDirectKong {
		active = append(active, "Blooming Direct Kong")
	}
	if flags.HasBuddingClosedKong {
		active = append(active, "Budding Closed Kong")
	}
	if flags.HasBloomingClosedKong {
		active = append(active, "Blooming Closed Kong")
	}
	if flags.HasBuddingRiskyKong {
		active = append(active, "Budding Risky Kong")
	}
	if flags.HasBloomingRiskyKong {
		active = append(active, "Blooming Risky Kong")
	}
	if flags.HasBloomingFlowerKong {
		active = append(active, "Blooming Flower Kong")
	}
	return active
}

func countKongFlags(req CalcRequest) CalcKongFlagCounts {
	var counts CalcKongFlagCounts

	for _, meld := range req.OpenMelds {
		if meld.Type != pb.ActionType_ACTION_KAN {
			continue
		}
		addKongFlags(&counts, meld.KongFlags)
	}

	if counts == (CalcKongFlagCounts{}) {
		addKongFlags(&counts, req.KongFlags)
	}

	return counts
}

func addKongFlags(counts *CalcKongFlagCounts, flags CalcKongFlags) {
	if flags.HasBuddingDirectKong {
		counts.HasBuddingDirectKong++
	}
	if flags.HasBloomingDirectKong {
		counts.HasBloomingDirectKong++
	}
	if flags.HasBuddingClosedKong {
		counts.HasBuddingClosedKong++
	}
	if flags.HasBloomingClosedKong {
		counts.HasBloomingClosedKong++
	}
	if flags.HasBuddingRiskyKong {
		counts.HasBuddingRiskyKong++
	}
	if flags.HasBloomingRiskyKong {
		counts.HasBloomingRiskyKong++
	}
	if flags.HasBloomingFlowerKong {
		counts.HasBloomingFlowerKong++
	}
}

func applyExtraKongBonuses(score int32, entries []*pb.ScoreEntry, canWin bool, isTsumo bool, counts CalcKongFlagCounts) (int32, []*pb.ScoreEntry, bool) {
	score, entries = addExtraKongEntries(score, entries, counts.HasBuddingDirectKong, "Budding Direct Kong (直杠不开花)", 50)
	score, entries = addExtraKongEntries(score, entries, counts.HasBloomingDirectKong, "Blooming Direct Kong (直杠开花)", 100)
	score, entries = addExtraKongEntries(score, entries, counts.HasBuddingClosedKong, "Budding Closed Kong (暗杠不开花)", 100)
	score, entries = addExtraKongEntries(score, entries, counts.HasBloomingClosedKong, "Blooming Closed Kong (暗杠开花)", 150)
	score, entries = addExtraKongEntries(score, entries, counts.HasBuddingRiskyKong, "Budding Risky Kong (风险杠不开花)", 100)
	score, entries = addExtraKongEntries(score, entries, counts.HasBloomingRiskyKong, "Blooming Risky Kong (风险杠开花)", 200)
	score, entries = addExtraKongEntries(score, entries, counts.HasBloomingFlowerKong, "Blooming Flower Kong (花杠杠开)", 50)

	if !isTsumo && !canWin && len(entries) > 0 && score >= 4 {
		canWin = true
	}

	return score, entries, canWin
}

func addExtraKongEntries(score int32, entries []*pb.ScoreEntry, count int, patternName string, points int32) (int32, []*pb.ScoreEntry) {
	for i := 1; i < count; i++ {
		entries = append(entries, &pb.ScoreEntry{PatternName: patternName, Points: points})
		score += points
	}
	return score, entries
}

func actionName(action pb.ActionType) string {
	switch action {
	case pb.ActionType_ACTION_CHII:
		return "chii"
	case pb.ActionType_ACTION_PON:
		return "pon"
	case pb.ActionType_ACTION_KAN:
		return "kan"
	default:
		return "unknown"
	}
}

func directionName(direction pb.MeldDirection) string {
	switch direction {
	case pb.MeldDirection_MELD_DIRECTION_RIGHT:
		return "right"
	case pb.MeldDirection_MELD_DIRECTION_ACROSS:
		return "across"
	case pb.MeldDirection_MELD_DIRECTION_LEFT:
		return "left"
	default:
		return "unknown"
	}
}

func windName(wind uint32) string {
	switch wind {
	case 1:
		return "East"
	case 2:
		return "South"
	case 3:
		return "West"
	case 4:
		return "North"
	default:
		return "Unknown"
	}
}

func suitSortOrder(suit pb.Suit) int {
	switch suit {
	case pb.Suit_SUIT_MAN:
		return 1
	case pb.Suit_SUIT_PIN:
		return 2
	case pb.Suit_SUIT_SOU:
		return 3
	case pb.Suit_SUIT_JIHAI:
		return 4
	default:
		return 5
	}
}
