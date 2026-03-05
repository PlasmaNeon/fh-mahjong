package main

import (
	"encoding/json"
	"fmt"

	pb "github.com/plasma/fh-mahjong/proto"
	"github.com/plasma/fh-mahjong/rules"
)

func main() {
	var closed []*pb.Tile
	// 1s to 9s
	for i := uint32(1); i <= 9; i++ {
		closed = append(closed, &pb.Tile{Suit: pb.Suit_SUIT_SOU, Value: i, Id: 100 + i})
	}
	// 1p, 1p
	closed = append(closed, &pb.Tile{Suit: pb.Suit_SUIT_PIN, Value: 1, Id: 201})
	closed = append(closed, &pb.Tile{Suit: pb.Suit_SUIT_PIN, Value: 1, Id: 202})
	// 2p, 2p
	closed = append(closed, &pb.Tile{Suit: pb.Suit_SUIT_PIN, Value: 2, Id: 203})
	closed = append(closed, &pb.Tile{Suit: pb.Suit_SUIT_PIN, Value: 2, Id: 204})

	winTile := &pb.Tile{Suit: pb.Suit_SUIT_PIN, Value: 2, Id: 205}

	state := &pb.GameState{
		PrevailingWind: 1,
		Players: []*pb.PlayerState{
			{SeatWind: 1},
		},
	}

	rs := &rules.HometownRuleset{}
	score, entries, canWin := rs.EvaluateHand(closed, nil, winTile, state, 0, true)

	fmt.Printf("Can Win Evaluator: %v\n", canWin)
	fmt.Printf("Score: %v\n", score)

	// Test isValidHand directly
	fullHand := append([]*pb.Tile{}, closed...)
	fullHand = append(fullHand, winTile)

	isValid := rs.IsValidHand(fullHand, nil, nil)
	fmt.Printf("Direct isValidHand: %v\n", isValid)

	b, _ := json.MarshalIndent(entries, "", "  ")
	fmt.Println(string(b))
}
