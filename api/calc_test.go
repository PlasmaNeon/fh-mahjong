package api

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/gin-gonic/gin"
	pb "github.com/plasma/fh-mahjong/proto"
)

type calcResponse struct {
	CanWin     bool                  `json:"canWin"`
	Score      int32                 `json:"score"`
	Entries    []CalcScoreEntry      `json:"entries"`
	Normalized CalcNormalizedSummary `json:"normalized"`
	Errors     []string              `json:"errors"`
}

func calcTile(suit pb.Suit, value uint32) CalcTileInput {
	return CalcTileInput{Suit: suit, Value: value}
}

func newCalcRouter() *gin.Engine {
	gin.SetMode(gin.TestMode)
	server := &Server{}
	router := gin.New()
	router.POST("/api/v1/calc", server.handleCalc)
	return router
}

func performCalcRequest(t *testing.T, router http.Handler, req CalcRequest) *httptest.ResponseRecorder {
	t.Helper()

	body, err := json.Marshal(req)
	if err != nil {
		t.Fatalf("marshal request: %v", err)
	}

	recorder := httptest.NewRecorder()
	httpReq := httptest.NewRequest(http.MethodPost, "/api/v1/calc", bytes.NewReader(body))
	httpReq.Header.Set("Content-Type", "application/json")
	router.ServeHTTP(recorder, httpReq)
	return recorder
}

func decodeCalcResponse(t *testing.T, recorder *httptest.ResponseRecorder) calcResponse {
	t.Helper()

	var response calcResponse
	if err := json.Unmarshal(recorder.Body.Bytes(), &response); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	return response
}

func TestBuildCalcEvaluation_PreservesCalledTileAndContext(t *testing.T) {
	req := CalcRequest{
		ClosedHand: []CalcTileInput{
			calcTile(pb.Suit_SUIT_PIN, 4),
			calcTile(pb.Suit_SUIT_PIN, 5),
			calcTile(pb.Suit_SUIT_PIN, 6),
			calcTile(pb.Suit_SUIT_MAN, 7),
			calcTile(pb.Suit_SUIT_MAN, 8),
			calcTile(pb.Suit_SUIT_MAN, 9),
			calcTile(pb.Suit_SUIT_MAN, 1),
			calcTile(pb.Suit_SUIT_MAN, 2),
			calcTile(pb.Suit_SUIT_MAN, 3),
			calcTile(pb.Suit_SUIT_JIHAI, 3),
		},
		WinTile:  &CalcTileInput{Suit: pb.Suit_SUIT_JIHAI, Value: 3},
		IsTsumo:  false,
		SeatWind: 1,
		PrevailingWind: 2,
		OpenMelds: []CalcMeldInput{
			{
				Type:            pb.ActionType_ACTION_CHII,
				Tiles:           []CalcTileInput{calcTile(pb.Suit_SUIT_SOU, 2), calcTile(pb.Suit_SUIT_SOU, 3), calcTile(pb.Suit_SUIT_SOU, 4)},
				CalledTileIndex: 1,
				CalledDirection: pb.MeldDirection_MELD_DIRECTION_LEFT,
			},
		},
		FlowerMelds: []uint32{1, 5},
		KongFlags: CalcKongFlags{
			HasBuddingDirectKong:  true,
			HasBloomingFlowerKong: true,
		},
	}

	eval, errs := buildCalcEvaluation(req)
	if len(errs) > 0 {
		t.Fatalf("unexpected validation errors: %v", errs)
	}

	if len(eval.openMelds) != 1 {
		t.Fatalf("expected 1 open meld, got %d", len(eval.openMelds))
	}
	if eval.openMelds[0].CalledTileId != eval.openMelds[0].Tiles[1].Id {
		t.Fatalf("called tile id mismatch: want %d got %d", eval.openMelds[0].Tiles[1].Id, eval.openMelds[0].CalledTileId)
	}
	if got := len(eval.state.Players[0].FlowerMelds); got != 2 {
		t.Fatalf("expected 2 flower melds, got %d", got)
	}
	if !eval.state.Players[0].HasBuddingDirectKong || !eval.state.Players[0].HasBloomingFlowerKong {
		t.Fatalf("expected kong flags to propagate into player state")
	}
	if eval.normalized.OpenMelds[0].CalledDirection != "left" {
		t.Fatalf("expected normalized direction left, got %q", eval.normalized.OpenMelds[0].CalledDirection)
	}
}

func TestHandleCalc_TsumoSuccess(t *testing.T) {
	router := newCalcRouter()

	req := CalcRequest{
		ClosedHand: []CalcTileInput{
			calcTile(pb.Suit_SUIT_SOU, 2),
			calcTile(pb.Suit_SUIT_SOU, 3),
			calcTile(pb.Suit_SUIT_SOU, 4),
			calcTile(pb.Suit_SUIT_PIN, 4),
			calcTile(pb.Suit_SUIT_PIN, 5),
			calcTile(pb.Suit_SUIT_PIN, 6),
			calcTile(pb.Suit_SUIT_MAN, 7),
			calcTile(pb.Suit_SUIT_MAN, 8),
			calcTile(pb.Suit_SUIT_MAN, 9),
			calcTile(pb.Suit_SUIT_MAN, 1),
			calcTile(pb.Suit_SUIT_MAN, 2),
			calcTile(pb.Suit_SUIT_MAN, 3),
			calcTile(pb.Suit_SUIT_JIHAI, 3),
		},
		WinTile:        &CalcTileInput{Suit: pb.Suit_SUIT_JIHAI, Value: 3},
		IsTsumo:        true,
		SeatWind:       1,
		PrevailingWind: 2,
	}

	recorder := performCalcRequest(t, router, req)
	if recorder.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", recorder.Code, recorder.Body.String())
	}

	response := decodeCalcResponse(t, recorder)
	if !response.CanWin {
		t.Fatalf("expected tsumo hand to win")
	}
	if response.Score != 5 {
		t.Fatalf("expected score 5, got %d", response.Score)
	}
	if response.Normalized.WinType != "tsumo" {
		t.Fatalf("expected normalized win type tsumo, got %q", response.Normalized.WinType)
	}
}

func TestHandleCalc_RonBelowMinimumPreservesScore(t *testing.T) {
	router := newCalcRouter()

	req := CalcRequest{
		ClosedHand: []CalcTileInput{
			calcTile(pb.Suit_SUIT_MAN, 2),
			calcTile(pb.Suit_SUIT_MAN, 3),
			calcTile(pb.Suit_SUIT_PIN, 4),
			calcTile(pb.Suit_SUIT_PIN, 5),
			calcTile(pb.Suit_SUIT_PIN, 6),
			calcTile(pb.Suit_SUIT_SOU, 7),
			calcTile(pb.Suit_SUIT_SOU, 8),
			calcTile(pb.Suit_SUIT_SOU, 9),
			calcTile(pb.Suit_SUIT_JIHAI, 1),
			calcTile(pb.Suit_SUIT_JIHAI, 1),
			calcTile(pb.Suit_SUIT_JIHAI, 1),
			calcTile(pb.Suit_SUIT_JIHAI, 2),
			calcTile(pb.Suit_SUIT_JIHAI, 2),
		},
		WinTile:        &CalcTileInput{Suit: pb.Suit_SUIT_MAN, Value: 4},
		IsTsumo:        false,
		SeatWind:       2,
		PrevailingWind: 3,
	}

	recorder := performCalcRequest(t, router, req)
	if recorder.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", recorder.Code, recorder.Body.String())
	}

	response := decodeCalcResponse(t, recorder)
	if response.CanWin {
		t.Fatalf("expected ron hand to fail minimum win check")
	}
	if response.Score != 2 {
		t.Fatalf("expected preserved score 2, got %d", response.Score)
	}
}

func TestHandleCalc_WildTileScoring(t *testing.T) {
	router := newCalcRouter()

	req := CalcRequest{
		ClosedHand: []CalcTileInput{
			calcTile(pb.Suit_SUIT_SOU, 2),
			calcTile(pb.Suit_SUIT_SOU, 3),
			calcTile(pb.Suit_SUIT_SOU, 4),
			calcTile(pb.Suit_SUIT_PIN, 4),
			calcTile(pb.Suit_SUIT_PIN, 5),
			calcTile(pb.Suit_SUIT_PIN, 6),
			calcTile(pb.Suit_SUIT_MAN, 7),
			calcTile(pb.Suit_SUIT_MAN, 8),
			calcTile(pb.Suit_SUIT_MAN, 9),
			calcTile(pb.Suit_SUIT_SOU, 9),
			calcTile(pb.Suit_SUIT_MAN, 2),
			calcTile(pb.Suit_SUIT_MAN, 3),
			calcTile(pb.Suit_SUIT_JIHAI, 3),
		},
		WinTile:        &CalcTileInput{Suit: pb.Suit_SUIT_JIHAI, Value: 3},
		WildTile:       &CalcTileInput{Suit: pb.Suit_SUIT_SOU, Value: 9},
		IsTsumo:        true,
		SeatWind:       1,
		PrevailingWind: 2,
	}

	recorder := performCalcRequest(t, router, req)
	if recorder.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", recorder.Code, recorder.Body.String())
	}

	response := decodeCalcResponse(t, recorder)
	if !response.CanWin {
		t.Fatalf("expected wild hand to win")
	}
	if response.Score != 5 {
		t.Fatalf("expected score 5, got %d", response.Score)
	}

	foundWildEntry := false
	for _, entry := range response.Entries {
		if entry.PatternName == "One Wild Tile (一搭)" {
			foundWildEntry = true
		}
	}
	if !foundWildEntry {
		t.Fatalf("expected one-wild score entry in response")
	}
	if response.Normalized.WildTile != "9s" {
		t.Fatalf("expected normalized wild tile 9s, got %q", response.Normalized.WildTile)
	}
}

func TestHandleCalc_InvalidRequestReturnsValidationErrors(t *testing.T) {
	router := newCalcRouter()

	req := CalcRequest{
		ClosedHand: []CalcTileInput{
			calcTile(pb.Suit_SUIT_MAN, 1),
			calcTile(pb.Suit_SUIT_MAN, 1),
			calcTile(pb.Suit_SUIT_MAN, 1),
			calcTile(pb.Suit_SUIT_MAN, 1),
			calcTile(pb.Suit_SUIT_MAN, 1),
			calcTile(pb.Suit_SUIT_MAN, 1),
			calcTile(pb.Suit_SUIT_MAN, 1),
			calcTile(pb.Suit_SUIT_MAN, 1),
			calcTile(pb.Suit_SUIT_MAN, 1),
			calcTile(pb.Suit_SUIT_MAN, 1),
			calcTile(pb.Suit_SUIT_MAN, 1),
			calcTile(pb.Suit_SUIT_MAN, 1),
			calcTile(pb.Suit_SUIT_MAN, 1),
		},
		WinTile:        &CalcTileInput{Suit: pb.Suit_SUIT_MAN, Value: 1},
		IsTsumo:        true,
		SeatWind:       1,
		PrevailingWind: 1,
	}

	recorder := performCalcRequest(t, router, req)
	if recorder.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d: %s", recorder.Code, recorder.Body.String())
	}

	response := decodeCalcResponse(t, recorder)
	if len(response.Errors) == 0 {
		t.Fatalf("expected validation errors")
	}

	foundPhysicalLimit := false
	for _, err := range response.Errors {
		if strings.Contains(err, "capped at 4 copies") {
			foundPhysicalLimit = true
		}
	}
	if !foundPhysicalLimit {
		t.Fatalf("expected physical tile limit validation error, got %v", response.Errors)
	}
}

func TestHandleCalc_MultipleKanFlagsStackAcrossMelds(t *testing.T) {
	router := newCalcRouter()

	req := CalcRequest{
		ClosedHand: []CalcTileInput{
			calcTile(pb.Suit_SUIT_SOU, 3),
			calcTile(pb.Suit_SUIT_SOU, 4),
			calcTile(pb.Suit_SUIT_SOU, 5),
			calcTile(pb.Suit_SUIT_SOU, 6),
			calcTile(pb.Suit_SUIT_SOU, 7),
			calcTile(pb.Suit_SUIT_SOU, 8),
			calcTile(pb.Suit_SUIT_JIHAI, 1),
		},
		WinTile:        &CalcTileInput{Suit: pb.Suit_SUIT_JIHAI, Value: 1},
		IsTsumo:        true,
		SeatWind:       1,
		PrevailingWind: 2,
		OpenMelds: []CalcMeldInput{
			{
				Type:            pb.ActionType_ACTION_KAN,
				Tiles:           []CalcTileInput{calcTile(pb.Suit_SUIT_MAN, 1), calcTile(pb.Suit_SUIT_MAN, 1), calcTile(pb.Suit_SUIT_MAN, 1), calcTile(pb.Suit_SUIT_MAN, 1)},
				CalledTileIndex: 0,
				CalledDirection: pb.MeldDirection_MELD_DIRECTION_LEFT,
				KongFlags: CalcKongFlags{
					HasBuddingDirectKong: true,
				},
			},
			{
				Type:            pb.ActionType_ACTION_KAN,
				Tiles:           []CalcTileInput{calcTile(pb.Suit_SUIT_PIN, 2), calcTile(pb.Suit_SUIT_PIN, 2), calcTile(pb.Suit_SUIT_PIN, 2), calcTile(pb.Suit_SUIT_PIN, 2)},
				CalledTileIndex: 1,
				CalledDirection: pb.MeldDirection_MELD_DIRECTION_RIGHT,
				KongFlags: CalcKongFlags{
					HasBuddingDirectKong: true,
				},
			},
		},
	}

	recorder := performCalcRequest(t, router, req)
	if recorder.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", recorder.Code, recorder.Body.String())
	}

	response := decodeCalcResponse(t, recorder)
	if !response.CanWin {
		t.Fatalf("expected hand with multiple kans to win")
	}
	if response.Score != 103 {
		t.Fatalf("expected score 103, got %d", response.Score)
	}

	buddingCount := 0
	for _, entry := range response.Entries {
		if entry.PatternName == "Budding Direct Kong (直杠不开花)" {
			buddingCount++
		}
	}
	if buddingCount != 2 {
		t.Fatalf("expected 2 budding direct kong entries, got %d", buddingCount)
	}

	if len(response.Normalized.OpenMelds) != 2 {
		t.Fatalf("expected 2 normalized open melds, got %d", len(response.Normalized.OpenMelds))
	}
	if len(response.Normalized.OpenMelds[0].KongFlags) != 1 || response.Normalized.OpenMelds[0].KongFlags[0] != "Budding Direct Kong" {
		t.Fatalf("expected first kan normalized flags to include Budding Direct Kong, got %v", response.Normalized.OpenMelds[0].KongFlags)
	}
}
