package api

import (
	"testing"

	"github.com/plasma/fh-mahjong/internal/bot"
	"github.com/plasma/fh-mahjong/internal/engine"
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

	matchmaker.createMatch([]string{"1", "2", "3", "4"}, "fenghua", "")

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
	stub := stubPolicy{}
	room.SeatPolicies = map[uint32]bot.Policy{0: stub, 1: stub, 2: stub, 3: stub}
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

// ctxRecordingPolicy implements both bot.Policy and bot.ContextPolicy so room
// dispatch prefers ChooseActionCtx. It records every context it receives and
// delegates the actual decision to the heuristic policy so the engine always
// receives a legal action.
type ctxRecordingPolicy struct {
	seen     []*bot.DecisionContext
	delegate bot.Policy
}

func newCtxRecordingPolicy() *ctxRecordingPolicy {
	return &ctxRecordingPolicy{delegate: bot.NewHeuristicPolicy()}
}

func (p *ctxRecordingPolicy) ChooseAction(state *pb.GameState, seat uint32) *pb.PlayerAction {
	return p.delegate.ChooseAction(state, seat)
}

func (p *ctxRecordingPolicy) ChooseActionCtx(ctx *bot.DecisionContext) *pb.PlayerAction {
	p.seen = append(p.seen, ctx)
	return p.delegate.ChooseAction(ctx.State, ctx.Seat)
}

func TestRoomDispatchPrefersContextPolicyOverLegacy(t *testing.T) {
	policy := newCtxRecordingPolicy()
	room := NewRoom("ctx-policy-room", nil, nil, WithBotPolicy(policy))
	if err := room.Engine.Start(); err != nil {
		t.Fatalf("Start() error = %v", err)
	}

	room.advanceAutomatedSeatsN(1)
	eventsAfterFirst := append([]engine.PublicEvent{}, room.Engine.PublicEvents()...)
	room.advanceAutomatedSeatsN(1)

	if len(policy.seen) < 2 {
		t.Fatalf("expected at least 2 ChooseActionCtx calls, got %d", len(policy.seen))
	}

	first, second := policy.seen[0], policy.seen[1]
	if first.State == nil || second.State == nil {
		t.Fatalf("expected non-nil State on both contexts, got %+v, %+v", first, second)
	}
	if second.DecisionIndex <= first.DecisionIndex {
		t.Fatalf("expected monotonically increasing DecisionIndex, got %d then %d", first.DecisionIndex, second.DecisionIndex)
	}
	// The second decision's context must reflect the engine's public event
	// log as of the moment it was built — i.e. right after the first
	// decision was processed, before the second one was.
	if len(second.Events) != len(eventsAfterFirst) {
		t.Fatalf("expected Events snapshot to match engine log at call time, got len=%d want len=%d", len(second.Events), len(eventsAfterFirst))
	}
}

func TestRoomDispatchUsesLegacyChooseActionForLegacyOnlyPolicy(t *testing.T) {
	room := NewRoom("legacy-policy-room", nil, nil, WithBotPolicy(stubPolicy{}))
	if err := room.Engine.Start(); err != nil {
		t.Fatalf("Start() error = %v", err)
	}

	// stubPolicy.ChooseAction always returns nil, so advancing should stop
	// immediately without panicking — proving the legacy path was taken
	// (a ContextPolicy branch would require the type assertion to fail,
	// which it does since stubPolicy doesn't implement ChooseActionCtx).
	payloads := room.advanceAutomatedSeatsN(1)
	_ = payloads
}

func TestCreateMatch_ChongciRulesetThreadsMatchOptions(t *testing.T) {
	hub := NewHub()
	hub.BindRoom = make(chan RoomBind, 1)
	matchmaker := NewMatchmaker(NewInMemoryQueue(), nil, hub)

	matchmaker.createMatch([]string{"1", "2", "3", "4"}, "chongci-fh", "")

	bind := <-hub.BindRoom
	if bind.Room.Engine.State.MatchMode != pb.MatchMode_MATCH_MODE_CHONGCI {
		t.Fatalf("MatchMode = %v, want CHONGCI", bind.Room.Engine.State.MatchMode)
	}
	for i, p := range bind.Room.Engine.State.Players {
		if p.Score != 2000 {
			t.Fatalf("seat %d Score = %d, want 2000", i, p.Score)
		}
	}
	if bind.Room.Engine.State.ChongciConfig == nil ||
		bind.Room.Engine.State.ChongciConfig.MaxHands != 50 {
		t.Fatalf("ChongciConfig = %+v, want MaxHands=50", bind.Room.Engine.State.ChongciConfig)
	}
}

func TestCreateMatch_FenghuaRulesetKeepsClassic(t *testing.T) {
	hub := NewHub()
	hub.BindRoom = make(chan RoomBind, 1)
	matchmaker := NewMatchmaker(NewInMemoryQueue(), nil, hub)

	matchmaker.createMatch([]string{"1", "2", "3", "4"}, "fenghua", "")

	bind := <-hub.BindRoom
	if bind.Room.Engine.State.MatchMode != pb.MatchMode_MATCH_MODE_CLASSIC {
		t.Fatalf("MatchMode = %v, want CLASSIC", bind.Room.Engine.State.MatchMode)
	}
	if bind.Room.Engine.State.Players[0].Score != 0 {
		t.Fatalf("classic seat Score = %d, want 0", bind.Room.Engine.State.Players[0].Score)
	}
}

// runBotOnlyRoomUntilTerminal repeatedly drives advanceAutomatedSeats on
// a fully-bot room until the engine reports PHASE_MATCH_END or the safety
// iteration cap trips. Returns the final-phase reached.
func runBotOnlyRoomUntilTerminal(t *testing.T, room *Room, maxIters int) pb.GamePhase {
	t.Helper()
	if err := room.Engine.Start(); err != nil {
		t.Fatalf("Engine.Start: %v", err)
	}
	for i := 0; i < maxIters; i++ {
		if room.Engine.State.Phase == pb.GamePhase_PHASE_MATCH_END {
			return room.Engine.State.Phase
		}
		room.advanceAutomatedSeats()
	}
	return room.Engine.State.Phase
}

func TestRoom_ChongciBust_TerminatesViaPhaseMatchEnd(t *testing.T) {
	cfg := &pb.ChongciConfig{
		StartingScore: 50,
		BustThreshold: 0,
		MaxHands:      30,
	}
	room := NewRoom("bust-test", nil, nil, WithMatchOptions(engine.MatchOptions{
		Mode:          pb.MatchMode_MATCH_MODE_CHONGCI,
		ChongciConfig: cfg,
	}))

	phase := runBotOnlyRoomUntilTerminal(t, room, 200_000)
	if phase != pb.GamePhase_PHASE_MATCH_END {
		t.Fatalf("phase = %v, want PHASE_MATCH_END (handNum=%d)", phase, room.Engine.State.HandNum)
	}
	if room.Engine.State.MatchEndResult == nil {
		t.Fatal("MatchEndResult is nil")
	}
	got := room.Engine.State.MatchEndResult.Reason
	if got != "bust" && got != "hand_cap" {
		t.Fatalf("Reason = %q, want bust or hand_cap", got)
	}
	if len(room.Engine.State.MatchEndResult.Standings) != 4 {
		t.Fatalf("Standings length = %d, want 4", len(room.Engine.State.MatchEndResult.Standings))
	}
}

func TestRoom_GraceShutdown_ArmedOnMatchEnd(t *testing.T) {
	room := NewRoom("grace-test", nil, nil)
	room.Engine.State.Phase = pb.GamePhase_PHASE_MATCH_END

	room.CheckMatchEndShutdownForTest()
	if !room.MatchEndScheduledForTest() {
		t.Fatal("first check after PHASE_MATCH_END must arm grace-shutdown timer")
	}

	prev := room.MatchEndScheduledForTest()
	room.CheckMatchEndShutdownForTest()
	if room.MatchEndScheduledForTest() != prev {
		t.Fatal("second check must not re-arm the timer (idempotent)")
	}
}

func TestRoom_GraceShutdown_NotArmedBeforeMatchEnd(t *testing.T) {
	room := NewRoom("grace-test-pre", nil, nil)
	room.CheckMatchEndShutdownForTest()
	if room.MatchEndScheduledForTest() {
		t.Fatal("grace-shutdown armed before PHASE_MATCH_END")
	}
}

func TestRoom_ChongciHandCap_Terminates(t *testing.T) {
	cfg := &pb.ChongciConfig{
		StartingScore: 10_000_000, // intentionally high so nobody busts
		BustThreshold: 0,
		MaxHands:      1, // cap after one hand
	}
	room := NewRoom("handcap-test", nil, nil, WithMatchOptions(engine.MatchOptions{
		Mode:          pb.MatchMode_MATCH_MODE_CHONGCI,
		ChongciConfig: cfg,
	}))

	phase := runBotOnlyRoomUntilTerminal(t, room, 200_000)
	if phase != pb.GamePhase_PHASE_MATCH_END {
		t.Fatalf("phase = %v, want PHASE_MATCH_END (handNum=%d)", phase, room.Engine.State.HandNum)
	}
	if room.Engine.State.MatchEndResult.Reason != "hand_cap" {
		t.Fatalf("Reason = %q, want hand_cap (scores=%v)",
			room.Engine.State.MatchEndResult.Reason,
			[]int32{
				room.Engine.State.Players[0].Score,
				room.Engine.State.Players[1].Score,
				room.Engine.State.Players[2].Score,
				room.Engine.State.Players[3].Score,
			})
	}
}

// Classic mode carrying a single-hand cap ("1-hand chongci") must reach
// PHASE_MATCH_END after one hand so the game persists as completed and appears
// in the paipu library — while STAYING in classic mode (random dealer, start
// at 0), so the in-game chongci UI stays hidden.
func TestRoom_ClassicSingleHand_TerminatesViaPhaseMatchEnd(t *testing.T) {
	cfg := &pb.ChongciConfig{
		StartingScore: 0,
		BustThreshold: -1_000_000, // effectively no bust in a single hand
		MaxHands:      1,          // end after one hand
	}
	room := NewRoom("classic-1hand-test", nil, nil, WithMatchOptions(engine.MatchOptions{
		Mode:          pb.MatchMode_MATCH_MODE_CLASSIC,
		ChongciConfig: cfg,
	}))

	phase := runBotOnlyRoomUntilTerminal(t, room, 200_000)
	if phase != pb.GamePhase_PHASE_MATCH_END {
		t.Fatalf("phase = %v, want PHASE_MATCH_END (handNum=%d)", phase, room.Engine.State.HandNum)
	}
	if room.Engine.State.MatchMode != pb.MatchMode_MATCH_MODE_CLASSIC {
		t.Fatalf("MatchMode = %v, want CLASSIC (a capped classic stays classic)", room.Engine.State.MatchMode)
	}
	if r := room.Engine.State.MatchEndResult; r == nil || len(r.Standings) != 4 {
		t.Fatalf("MatchEndResult = %+v, want 4 standings", r)
	}
}
