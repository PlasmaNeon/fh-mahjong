package api

import (
	"testing"

	pb "github.com/plasma/fh-mahjong/proto"
)

func TestAdvanceAutomatedSeatsPlaysMissingSeat(t *testing.T) {
	room := NewRoom("bot-room", nil, nil)
	if err := room.Engine.Start(); err != nil {
		t.Fatalf("Start() error = %v", err)
	}

	payloads := room.advanceAutomatedSeats()
	if len(payloads) == 0 {
		t.Fatalf("expected automated seats to produce state payloads")
	}

	totalDiscards := 0
	for _, player := range room.Engine.State.Players {
		totalDiscards += len(player.Discards)
	}

	if totalDiscards == 0 && room.Engine.State.Phase != pb.GamePhase_PHASE_ROUND_END {
		t.Fatalf("expected bots to advance the game, phase=%v", room.Engine.State.Phase)
	}
}

func TestNewRoomInitializesPaipuRecorder(t *testing.T) {
	room := NewRoom("paipu-room", nil, nil)
	if room.Engine.Recorder == nil {
		t.Fatal("expected room to initialize paipu recorder")
	}
}
