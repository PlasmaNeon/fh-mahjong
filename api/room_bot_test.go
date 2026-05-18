package api

import (
	"testing"

	"github.com/plasma/fh-mahjong/bot"
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

func TestNewRoomAcceptsInjectedBotPolicy(t *testing.T) {
	room := NewRoom("custom-bot-room", nil, nil, WithBotPolicy(stubPolicy{}))
	if _, ok := room.BotPolicy.(stubPolicy); !ok {
		t.Fatalf("expected injected bot policy, got %T", room.BotPolicy)
	}
}

func TestMatchmakerCreateMatchUsesBotPolicyFactory(t *testing.T) {
	hub := NewHub()
	hub.BindRoom = make(chan RoomBind, 1)
	matchmaker := NewMatchmaker(NewInMemoryQueue(), nil, hub)
	factoryCalled := false
	matchmaker.BotPolicyFactory = func() bot.Policy {
		factoryCalled = true
		return stubPolicy{}
	}

	matchmaker.createMatch([]string{"1", "2", "3", "4"}, "hometown", "")

	if !factoryCalled {
		t.Fatal("expected bot policy factory to be called")
	}
	bind := <-hub.BindRoom
	if _, ok := bind.Room.BotPolicy.(stubPolicy); !ok {
		t.Fatalf("expected room to use factory bot policy, got %T", bind.Room.BotPolicy)
	}
}

func TestRegisterPaipuPlayersIncludesBotSeats(t *testing.T) {
	room := NewRoom("paipu-room", nil, nil)
	room.Seats[1] = &Client{UserID: 42, Username: "Alice"}

	room.registerPaipuPlayers()

	paipu := room.Engine.Recorder.Finalize([4]int32{})
	if got := len(paipu.Players); got != 4 {
		t.Fatalf("expected 4 paipu players, got %d", got)
	}
	if paipu.Players[1].Name != "Alice" || paipu.Players[1].UserID != 42 {
		t.Fatalf("expected connected seat metadata to be preserved, got %+v", paipu.Players[1])
	}
	if paipu.Players[0].Name != "Bot 1" || paipu.Players[2].Name != "Bot 3" || paipu.Players[3].Name != "Bot 4" {
		t.Fatalf("expected placeholder bot names, got %+v", paipu.Players)
	}
}

func TestAdvanceAutomatedSeatsReadyBotsAtRoundEnd(t *testing.T) {
	room := NewRoom("round-end-room", nil, nil)
	room.Seats[0] = &Client{UserID: 1, Username: "Human"}
	room.Engine.State.Phase = pb.GamePhase_PHASE_ROUND_END
	room.Engine.State.PlayerReady = []bool{false, false, false, false}

	payloads := room.advanceAutomatedSeats()
	if len(payloads) == 0 {
		t.Fatalf("expected automated ready payloads at round end")
	}
	if room.Engine.State.Phase != pb.GamePhase_PHASE_ROUND_END {
		t.Fatalf("expected room to wait for connected human, phase=%v", room.Engine.State.Phase)
	}
	if room.Engine.State.PlayerReady[0] {
		t.Fatal("expected connected human seat to remain unready")
	}
	for seat := 1; seat < 4; seat++ {
		if !room.Engine.State.PlayerReady[seat] {
			t.Fatalf("expected automated seat %d to auto-ready", seat)
		}
	}
}

func TestAdvanceAutomatedSeatsAllBotsStartNextRound(t *testing.T) {
	room := NewRoom("bot-ready-room", nil, nil)
	room.BotPolicy = stubPolicy{}
	room.Engine.State.Phase = pb.GamePhase_PHASE_ROUND_END
	room.Engine.State.PlayerReady = []bool{false, false, false, false}
	initialHandNum := room.Engine.State.HandNum

	payloads := room.advanceAutomatedSeats()
	if len(payloads) == 0 {
		t.Fatalf("expected automated ready flow to broadcast next-round state")
	}
	if room.Engine.State.HandNum <= initialHandNum {
		t.Fatalf("expected next round to start, hand num=%d", room.Engine.State.HandNum)
	}
	if room.Engine.State.Phase != pb.GamePhase_PHASE_PLAYER_TURN {
		t.Fatalf("expected next round to stop at player turn after stub policy, phase=%v", room.Engine.State.Phase)
	}
}

type stubPolicy struct{}

func (stubPolicy) ChooseAction(_ *pb.GameState, _ uint32) *pb.PlayerAction {
	return nil
}
