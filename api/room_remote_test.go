package api

import (
	"os"
	"testing"

	"github.com/plasma/fh-mahjong/bot/remote"
	pb "github.com/plasma/fh-mahjong/proto"
)

func TestAdvanceAutomatedSeatsWithLiveRemotePolicy(t *testing.T) {
	endpoint := os.Getenv("FH_MAHJONG_REMOTE_POLICY_TEST_URL")
	if endpoint == "" {
		t.Skip("set FH_MAHJONG_REMOTE_POLICY_TEST_URL=http://127.0.0.1:8765/act to run live remote policy integration")
	}

	room := NewRoom("remote-policy-room", nil, nil, WithBotPolicy(remote.NewHTTPPolicy(endpoint)))
	if err := room.Engine.Start(); err != nil {
		t.Fatalf("Start() error = %v", err)
	}

	payloads := room.advanceAutomatedSeats()
	if len(payloads) == 0 {
		t.Fatalf("expected remote policy automated seats to produce state payloads")
	}
	if room.Engine.State.Phase == pb.GamePhase_PHASE_INIT {
		t.Fatalf("expected room to advance beyond init")
	}
}
