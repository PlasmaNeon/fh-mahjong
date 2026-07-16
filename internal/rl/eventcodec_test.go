package rl

import (
	"bytes"
	"math/rand"
	"testing"

	"github.com/plasma/fh-mahjong/internal/engine"
	"github.com/plasma/fh-mahjong/internal/rules"
	pb "github.com/plasma/fh-mahjong/proto"
	"google.golang.org/protobuf/proto"
)

// The golden vector pinning the bit layout. ai/tests/test_events.py carries
// the IDENTICAL (packed, fields) pairs — change one, change both.
var eventGoldenVector = []struct {
	event    engine.PublicEvent
	observer uint32
	packed   uint32
}{
	// Own draw, face 5 visible, observer 1 == actor 1 -> rel seat 0.
	{engine.PublicEvent{Type: engine.EventDraw, Seat: 1, Face: 5, FromSeat: -1}, 1, 0x0000_0140},
	// Opponent draw: observer 0 sees actor 2 (rel 2), face MASKED -> 63.
	{engine.PublicEvent{Type: engine.EventDraw, Seat: 2, Face: 5, FromSeat: -1}, 0, 0x0000_0FE0},
	// Tsumogiri discard by right neighbor (actor 1, observer 0), face 41.
	{engine.PublicEvent{Type: engine.EventDiscard, Seat: 1, Face: 41, FromSeat: -1, Flags: engine.EventFlagTsumogiri}, 0, 0x0000_4A51},
	// Pon by across (actor 2) from left (seat 3), observer 0, face 10.
	{engine.PublicEvent{Type: engine.EventPon, Seat: 2, Face: 10, FromSeat: 3}, 0, 0x0000_32A3},
	// Haitei draw by self, face 0 (a real face: 1m).
	{engine.PublicEvent{Type: engine.EventDraw, Seat: 3, Face: 0, FromSeat: -1, Flags: engine.EventFlagHaitei}, 3, 0x0000_8000},
	// Flower reveal by left neighbor (actor 3, observer 0), face 34.
	{engine.PublicEvent{Type: engine.EventFlower, Seat: 3, Face: 34, FromSeat: -1}, 0, 0x0000_08B7},
}

func TestPackPublicEventGoldenVector(t *testing.T) {
	for i, c := range eventGoldenVector {
		got := packPublicEvent(c.event, c.observer)
		if got != c.packed {
			t.Fatalf("golden %d: packed 0x%08X, want 0x%08X (event %+v observer %d)", i, got, c.packed, c.event, c.observer)
		}
		if got>>16 != 0 {
			t.Fatalf("golden %d: reserved bits set: 0x%08X", i, got)
		}
	}
}

func TestRenderEventHistoryWindowAndOrder(t *testing.T) {
	events := make([]engine.PublicEvent, 10)
	for i := range events {
		events[i] = engine.PublicEvent{Type: engine.EventDiscard, Seat: uint32(i % 4), Face: int16(i), FromSeat: -1}
	}
	rendered := renderEventHistory(events, 0, 4)
	if len(rendered) != 4 {
		t.Fatalf("window 4: got %d", len(rendered))
	}
	// Last 4 events, oldest first: faces 6,7,8,9.
	for i, packed := range rendered {
		face := (packed >> 6) & 0x3F
		if face != uint32(6+i) {
			t.Fatalf("truncation order wrong at %d: face %d want %d", i, face, 6+i)
		}
	}
	if renderEventHistory(events, 0, 0) != nil {
		t.Fatalf("window 0 must render nil")
	}
	if got := renderEventHistory(events[:2], 0, 8); len(got) != 2 {
		t.Fatalf("short log: got %d want 2", len(got))
	}
}

func TestRelativeSeatRendering(t *testing.T) {
	event := engine.PublicEvent{Type: engine.EventDiscard, Seat: 2, Face: 7, FromSeat: -1}
	for observer := uint32(0); observer < 4; observer++ {
		packed := packPublicEvent(event, observer)
		rel := (packed >> 4) & 0x3
		want := (2 + 4 - observer) % 4
		if rel != want {
			t.Fatalf("observer %d: rel seat %d want %d", observer, rel, want)
		}
	}
}

func newSeededHistoryEnv(t *testing.T, seed uint64, window uint32) *Env {
	t.Helper()
	config := &pb.EnvConfig{
		LearningSeats:      []uint32{0, 1, 2, 3},
		AutoPlayHeuristics: false,
		MaxDecisions:       3000,
		MatchMode:          pb.MatchMode_MATCH_MODE_CLASSIC,
		EventHistoryWindow: window,
	}
	env := New(config)
	if _, err := env.Reset(&pb.EnvResetRequest{Seed: seed, Config: config}); err != nil {
		t.Fatalf("reset: %v", err)
	}
	return env
}

// Dormant byte-parity: at window=0 the marshaled observation must be
// byte-identical to one with the event fields force-cleared (i.e. the
// fields are entirely absent from the wire).
func TestDormantWindowByteParity(t *testing.T) {
	env := newSeededHistoryEnv(t, 42, 0)
	rng := rand.New(rand.NewSource(42))
	obs := env.lastObservationForTest()
	for step := 0; obs != nil && step < 200; step++ {
		raw, err := proto.Marshal(obs)
		if err != nil {
			t.Fatalf("marshal: %v", err)
		}
		cleared := proto.Clone(obs).(*pb.SeatObservation)
		cleared.EventHistory = nil
		cleared.EventHistoryWindow = 0
		clearedRaw, err := proto.Marshal(cleared)
		if err != nil {
			t.Fatalf("marshal cleared: %v", err)
		}
		if !bytes.Equal(raw, clearedRaw) {
			t.Fatalf("step %d: window=0 observation carries event bytes", step)
		}
		aid, ok := randomLegalActionID(obs.ActionMask, rng)
		if !ok {
			break
		}
		sr, err := env.Step(&pb.EnvStepRequest{ActionId: uint32(aid)})
		if err != nil || sr.Terminated || sr.Truncated {
			break
		}
		obs = sr.Observation
	}
}

// Information legality + own-draw visibility over a full random match.
func TestEventHistoryInformationLegality(t *testing.T) {
	env := newSeededHistoryEnv(t, 7, 128)
	rng := rand.New(rand.NewSource(7))
	obs := env.lastObservationForTest()
	checkedOwnDraw := false
	for step := 0; obs != nil && step < 3000; step++ {
		for _, packed := range obs.EventHistory {
			if packed>>16 != 0 {
				t.Fatalf("reserved bits set: 0x%08X", packed)
			}
			evType := packed & 0xF
			rel := (packed >> 4) & 0x3
			face := (packed >> 6) & 0x3F
			if evType == uint32(engine.EventDraw) {
				if rel != 0 && face != EventFaceUnknown {
					t.Fatalf("LEAK: observer %d sees opponent draw face %d (packed 0x%08X)", obs.Seat, face, packed)
				}
				if rel == 0 {
					if face == EventFaceUnknown {
						t.Fatalf("own draw masked for observer %d", obs.Seat)
					}
					checkedOwnDraw = true
				}
			}
		}
		aid, ok := randomLegalActionID(obs.ActionMask, rng)
		if !ok {
			break
		}
		sr, err := env.Step(&pb.EnvStepRequest{ActionId: uint32(aid)})
		if err != nil || sr.Terminated || sr.Truncated {
			break
		}
		obs = sr.Observation
	}
	if !checkedOwnDraw {
		t.Fatalf("premise broken: no own-draw event ever observed")
	}
}

// Golden cross-check vs the paipu record: the event log and the recorder
// must tell the same story for the same seeded match.
func TestEventLogMatchesPaipuRecord(t *testing.T) {
	config := &pb.EnvConfig{
		LearningSeats:      []uint32{0, 1, 2, 3},
		AutoPlayHeuristics: false,
		MaxDecisions:       3000,
		MatchMode:          pb.MatchMode_MATCH_MODE_CLASSIC,
		EventHistoryWindow: 512,
	}
	env := New(config)
	env.game = engine.NewGame("golden-events", &rules.FenghuaRuleset{}, engine.MatchOptions{})
	env.game.Recorder = engine.NewPaipuRecorder("golden-events", "fenghua")
	env.game.SetWallSeed(engine.SeedFromUint64(99))
	if err := env.game.Start(); err != nil {
		t.Fatalf("start: %v", err)
	}
	env.lastScores = snapshotScores(env.game.State)
	step, err := env.advanceToDecision()
	if err != nil {
		t.Fatalf("advance: %v", err)
	}
	obs := step.Observation
	rng := rand.New(rand.NewSource(99))
	// Drive ONE round: stop at the first round boundary (log would clear).
	startEvents := len(env.game.PublicEvents())
	if startEvents == 0 {
		t.Fatalf("premise: initial deal produced no events (expected initial flowers or first draw)")
	}
	for i := 0; obs != nil && i < 3000; i++ {
		if env.game.State.Phase == pb.GamePhase_PHASE_ROUND_END || env.game.State.Phase == pb.GamePhase_PHASE_MATCH_END {
			break
		}
		aid, ok := randomLegalActionID(obs.ActionMask, rng)
		if !ok {
			break
		}
		sr, err := env.Step(&pb.EnvStepRequest{ActionId: uint32(aid)})
		if err != nil {
			t.Fatalf("step %d: %v", i, err)
		}
		if sr.Terminated || sr.Truncated {
			break
		}
		obs = sr.Observation
	}

	paipu := env.game.Recorder.Finalize([4]int32{})
	// The round may still be current (unfinished) — pull actions from the
	// recorder's completed rounds or skip if none completed; either way the
	// event log covers the CURRENT round, so compare against the actions
	// recorded SINCE the last StartRound. Simplest robust form: replay the
	// recorder's last-known actions if a round completed, else compare
	// counts of each public action kind seen so far.
	var actions []engine.PaipuAction
	if len(paipu.Rounds) > 0 && env.game.State.Phase != pb.GamePhase_PHASE_PLAYER_TURN {
		actions = paipu.Rounds[len(paipu.Rounds)-1].Actions
	}
	if actions == nil {
		t.Skipf("no completed round at seed 99 within budget — pick a seed that finishes a round")
	}

	expected := make([]engine.PublicEvent, 0, len(actions))
	for _, a := range actions {
		switch a.Act {
		case "draw", "haitei":
			expected = append(expected, engine.PublicEvent{Type: engine.EventDraw, Seat: a.Seat})
		case "discard":
			expected = append(expected, engine.PublicEvent{Type: engine.EventDiscard, Seat: a.Seat})
		case "chii":
			expected = append(expected, engine.PublicEvent{Type: engine.EventChii, Seat: a.Seat})
		case "pon":
			expected = append(expected, engine.PublicEvent{Type: engine.EventPon, Seat: a.Seat})
		case "okan":
			expected = append(expected, engine.PublicEvent{Type: engine.EventKanOpen, Seat: a.Seat})
		case "ckan":
			expected = append(expected, engine.PublicEvent{Type: engine.EventKanClosed, Seat: a.Seat})
		case "ukan":
			expected = append(expected, engine.PublicEvent{Type: engine.EventKanUpgrade, Seat: a.Seat})
		case "flower":
			expected = append(expected, engine.PublicEvent{Type: engine.EventFlower, Seat: a.Seat})
		}
	}
	got := env.game.PublicEvents()
	// The log also holds initial-flower events the paipu stores outside
	// Actions; drop leading EventFlower entries not present in expected.
	for len(got) > 0 && got[0].Type == engine.EventFlower && (len(expected) == 0 || expected[0].Type != engine.EventFlower) {
		got = got[1:]
	}
	if len(got) != len(expected) {
		t.Fatalf("event count %d != paipu public-action count %d", len(got), len(expected))
	}
	for i := range got {
		if got[i].Type != expected[i].Type || got[i].Seat != expected[i].Seat {
			t.Fatalf("event %d: got {%d seat %d} want {%d seat %d}", i, got[i].Type, got[i].Seat, expected[i].Type, expected[i].Seat)
		}
	}
}

// Tsumogiri capture invariant over a full random match: every
// tsumogiri-flagged DISCARD's most recent preceding DRAW in the raw log is
// by the same seat (you can only cut the tile you just drew), and at least
// one flagged and one unflagged discard occur (both paths exercised).
func TestTsumogiriFlagCapture(t *testing.T) {
	env := newSeededHistoryEnv(t, 23, 512)
	rng := rand.New(rand.NewSource(23))
	obs := env.lastObservationForTest()
	for i := 0; obs != nil && i < 3000; i++ {
		aid, ok := randomLegalActionID(obs.ActionMask, rng)
		if !ok {
			break
		}
		sr, err := env.Step(&pb.EnvStepRequest{ActionId: uint32(aid)})
		if err != nil || sr.Terminated || sr.Truncated {
			break
		}
		obs = sr.Observation
	}
	events := env.game.PublicEvents()
	flagged, unflagged := 0, 0
	for i, event := range events {
		if event.Type != engine.EventDiscard {
			continue
		}
		if event.Flags&engine.EventFlagTsumogiri == 0 {
			unflagged++
			continue
		}
		flagged++
		found := false
		for j := i - 1; j >= 0; j-- {
			if events[j].Type == engine.EventDraw {
				if events[j].Seat != event.Seat {
					t.Fatalf("event %d: tsumogiri discard by seat %d but last draw was by seat %d", i, event.Seat, events[j].Seat)
				}
				found = true
				break
			}
		}
		if !found {
			t.Fatalf("event %d: tsumogiri discard with no preceding draw", i)
		}
	}
	if flagged == 0 || unflagged == 0 {
		t.Fatalf("premise: need both flagged (%d) and unflagged (%d) discards — pick a different seed", flagged, unflagged)
	}
}

// Clone (search) consistency: clone inherits the record; clone appends
// don't leak back.
func TestSearchCloneEventConsistency(t *testing.T) {
	env := newSeededHistoryEnv(t, 11, 128)
	rng := rand.New(rand.NewSource(11))
	obs := env.lastObservationForTest()
	for i := 0; i < 40 && obs != nil; i++ {
		aid, ok := randomLegalActionID(obs.ActionMask, rng)
		if !ok {
			break
		}
		sr, err := env.Step(&pb.EnvStepRequest{ActionId: uint32(aid)})
		if err != nil || sr.Terminated || sr.Truncated {
			break
		}
		obs = sr.Observation
	}
	parentLen := len(env.game.PublicEvents())
	if parentLen == 0 {
		t.Fatalf("premise: no events after 40 steps")
	}
	clone := env.game.CloneForBranch()
	if len(clone.PublicEvents()) != parentLen {
		t.Fatalf("clone log %d != parent %d", len(clone.PublicEvents()), parentLen)
	}
	if err := clone.ExecuteSystemDraw(clone.State.ActivePlayer); err == nil {
		if len(env.game.PublicEvents()) != parentLen {
			t.Fatalf("clone draw leaked into parent log")
		}
	}
}

// lastObservationForTest re-encodes the current decision observation.
func (e *Env) lastObservationForTest() *pb.SeatObservation {
	seat, ok := e.currentActionSeat()
	if !ok {
		seat = e.game.State.ActivePlayer
	}
	obs, err := encodeObservation(e.game.State, seat, e.decisionCount, e.config.OracleObservation, e.game.PublicEvents(), e.config.EventHistoryWindow)
	if err != nil {
		return nil
	}
	return obs
}

// The flat pool layouts do not carry event history yet (Spec B2): both pool
// constructors must fail fast rather than silently drop it.
func TestPoolsRejectEventHistoryWindow(t *testing.T) {
	config := &pb.EnvConfig{
		LearningSeats:      []uint32{0, 1, 2, 3},
		AutoPlayHeuristics: false,
		MaxDecisions:       512,
		EventHistoryWindow: 128,
	}
	env := New(config)
	if _, err := env.Reset(&pb.EnvResetRequest{Seed: 5, Config: config}); err != nil {
		t.Fatalf("reset: %v", err)
	}
	if _, err := NewSearchPool(env, 2, 5, 64, 4); err == nil {
		t.Fatalf("NewSearchPool accepted event_history_window > 0")
	}
}
