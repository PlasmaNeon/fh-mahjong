package rl

import (
	"fmt"
	"math/rand"
	"sort"
	"testing"

	"github.com/plasma/fh-mahjong/internal/engine"
	pb "github.com/plasma/fh-mahjong/proto"
	"google.golang.org/protobuf/proto"
	"google.golang.org/protobuf/reflect/protoreflect"
)

// The observation encoder must be equivariant under every tile-face symmetry of the
// rules: any permutation of the three suits, reversing ranks 1-9 to 9-1 in every suit,
// and any permutation of the three dragons (5z/6z/7z). Encoding a transformed state
// equals transforming the original encoding. The one exception is the best-discard
// look-ahead block (scalars 33-35, 37, 40): bestVisibleDiscardLookahead breaks ties by
// face order, so a transform can pick a different tied tile. Those are measured, not
// required.
// ai/src/fh_mahjong_ai/suit_symmetry.py applies exactly these maps (faces, actions,
// planes, scalar 24, event faces) to average a policy over the symmetries, so this test
// is what licenses that transform.

// faceBlockSuits is the suit of each 9-face block in the 42-face index.
var faceBlockSuits = [3]pb.Suit{pb.Suit_SUIT_MAN, pb.Suit_SUIT_PIN, pb.Suit_SUIT_SOU}

// faceSymmetry sends suit block b to block suits[b], rank r to 8-r when reverse, and
// dragon d (0 = 5z) to dragons[d]. Winds and flowers never move.
type faceSymmetry struct {
	suits   [3]int
	reverse bool
	dragons [3]int
}

var identityOrder = [3]int{0, 1, 2}

var threePermutations = [][3]int{{0, 1, 2}, {0, 2, 1}, {1, 0, 2}, {1, 2, 0}, {2, 0, 1}, {2, 1, 0}}

// testedSymmetries are the generators (every suit permutation, rank reversal, every
// dragon permutation) plus one composition of all three.
func testedSymmetries() []faceSymmetry {
	var out []faceSymmetry
	for _, perm := range threePermutations[1:] {
		out = append(out, faceSymmetry{suits: perm, dragons: identityOrder})
		out = append(out, faceSymmetry{suits: identityOrder, dragons: perm})
	}
	out = append(out, faceSymmetry{suits: identityOrder, reverse: true, dragons: identityOrder})
	out = append(out, faceSymmetry{suits: [3]int{1, 2, 0}, reverse: true, dragons: [3]int{2, 0, 1}})
	return out
}

func (s faceSymmetry) rank(r int) int {
	if s.reverse {
		return 8 - r
	}
	return r
}

func (s faceSymmetry) face(face int) int {
	switch {
	case face >= 0 && face < 27:
		return s.suits[face/9]*9 + s.rank(face%9)
	case face >= 31 && face < 34:
		return 31 + s.dragons[face-31]
	}
	return face
}

func (s faceSymmetry) actionID(actionID int) int {
	switch {
	case actionID >= DiscardBase && actionID < DiscardBase+DiscardCount:
		return DiscardBase + s.face(actionID-DiscardBase)
	case actionID >= PonBase && actionID < ChiiBase:
		// pon and the three kan families are consecutive 34-face blocks
		base := PonBase + ((actionID-PonBase)/34)*34
		return base + s.face(actionID-base)
	case actionID >= ChiiBase && actionID < ChiiBase+ChiiCount:
		// a chii is indexed by its lowest rank (0-6); reversal sends start r to 6-r
		index := actionID - ChiiBase
		start := index % 7
		if s.reverse {
			start = 6 - start
		}
		return ChiiBase + s.suits[index/7]*7 + start
	}
	return actionID
}

func (s faceSymmetry) transformTiles(message protoreflect.Message) {
	if message.Descriptor().FullName() == "game.Tile" {
		fields := message.Descriptor().Fields()
		suitField, valueField := fields.ByName("suit"), fields.ByName("value")
		suit := pb.Suit(message.Get(suitField).Enum())
		value := int(message.Get(valueField).Uint())
		for block, blockSuit := range faceBlockSuits {
			if suit == blockSuit && value >= 1 && value <= 9 {
				message.Set(suitField, protoreflect.ValueOfEnum(protoreflect.EnumNumber(faceBlockSuits[s.suits[block]])))
				message.Set(valueField, protoreflect.ValueOfUint32(uint32(s.rank(value-1)+1)))
				return
			}
		}
		if suit == pb.Suit_SUIT_JIHAI && value >= 5 && value <= 7 {
			message.Set(valueField, protoreflect.ValueOfUint32(uint32(5+s.dragons[value-5])))
		}
		return
	}
	message.Range(func(field protoreflect.FieldDescriptor, value protoreflect.Value) bool {
		switch {
		case field.IsList() && field.Message() != nil:
			list := value.List()
			for i := 0; i < list.Len(); i++ {
				s.transformTiles(list.Get(i).Message())
			}
		case field.IsMap() && field.MapValue().Message() != nil:
			value.Map().Range(func(_ protoreflect.MapKey, v protoreflect.Value) bool {
				s.transformTiles(v.Message())
				return true
			})
		case field.Message() != nil && !field.IsList() && !field.IsMap():
			s.transformTiles(value.Message())
		}
		return true
	})
}

func (s faceSymmetry) events(events []engine.PublicEvent) []engine.PublicEvent {
	out := append([]engine.PublicEvent(nil), events...)
	for i := range out {
		if out[i].Face >= 0 {
			out[i].Face = int16(s.face(int(out[i].Face)))
		}
	}
	return out
}

func (s faceSymmetry) packedEvent(packed uint32) uint32 {
	face := int((packed >> 6) & 0x3F)
	if face == 63 {
		return packed
	}
	return packed&^(0x3F<<6) | uint32(s.face(face))<<6
}

// tieBrokenScalars come from the best-discard look-ahead, whose tie-break is face order.
var tieBrokenScalars = map[int]bool{33: true, 34: true, 35: true, 37: true, 40: true}

func assertEquivariant(t *testing.T, state *pb.GameState, seat uint32, events []engine.PublicEvent, sym faceSymmetry) (tieBreakDiffers bool) {
	t.Helper()
	const window = 64
	original, err := encodeObservation(state, seat, 0, false, 0, events, window)
	if err != nil {
		t.Fatalf("encode original: %v", err)
	}
	transformed := proto.Clone(state).(*pb.GameState)
	sym.transformTiles(transformed.ProtoReflect())
	permuted, err := encodeObservation(transformed, seat, 0, false, 0, sym.events(events), window)
	if err != nil {
		t.Fatalf("encode transformed %+v: %v", sym, err)
	}

	for channel := 0; channel < ObservationPlaneChannels; channel++ {
		for face := 0; face < ObservationPlaneHeight; face++ {
			want := original.Planes[channelOffset(channel)+face]
			got := permuted.Planes[channelOffset(channel)+sym.face(face)]
			if got != want {
				t.Fatalf("%+v plane %d face %d: got %v, want %v", sym, channel, face, got, want)
			}
		}
	}
	for actionID := range original.ActionMask {
		if permuted.ActionMask[sym.actionID(actionID)] != original.ActionMask[actionID] {
			t.Fatalf("%+v action %d: mask not equivariant", sym, actionID)
		}
	}
	for i, want := range original.Scalars {
		got := permuted.Scalars[i]
		if i == 24 {
			if face, ok := tileFaceIndex42(state.ActiveDiscard); ok {
				want = float32(sym.face(face)) / 41.0
			}
		}
		if got != want {
			if tieBrokenScalars[i] {
				tieBreakDiffers = true
				continue
			}
			t.Fatalf("%+v scalar %d: got %v, want %v", sym, i, got, want)
		}
	}
	if len(permuted.EventHistory) != len(original.EventHistory) {
		t.Fatalf("%+v event history length %d vs %d", sym, len(permuted.EventHistory), len(original.EventHistory))
	}
	for i, packed := range original.EventHistory {
		if permuted.EventHistory[i] != sym.packedEvent(packed) {
			t.Fatalf("%+v event %d: got %#x, want %#x", sym, i, permuted.EventHistory[i], sym.packedEvent(packed))
		}
	}
	return tieBreakDiffers
}

func TestObservationIsFaceSymmetryEquivariant(t *testing.T) {
	config := &pb.EnvConfig{
		LearningSeats:      []uint32{0, 1, 2, 3},
		AutoPlayHeuristics: false,
		MaxDecisions:       600,
		MatchMode:          pb.MatchMode_MATCH_MODE_CHONGCI,
		ChongciConfig:      &pb.ChongciConfig{StartingScore: 2000, BustThreshold: 0, MaxHands: 4},
	}
	rng := rand.New(rand.NewSource(11))
	symmetries := testedSymmetries()
	checked, claims, tieBreaks := 0, 0, 0
	for seed := uint64(1); seed <= 6; seed++ {
		env := New(config)
		reset, err := env.Reset(&pb.EnvResetRequest{Seed: seed, Config: config})
		if err != nil {
			t.Fatalf("reset %d: %v", seed, err)
		}
		observation := reset.Observation
		for step := 0; step < 600 && observation != nil && !reset.Terminated; step++ {
			seat := observation.Seat
			for _, sym := range symmetries {
				if assertEquivariant(t, env.game.State, seat, env.game.PublicEvents(), sym) {
					tieBreaks++
				}
			}
			checked++
			legal := make([]int, 0, 8)
			for actionID, enabled := range observation.ActionMask {
				if enabled == 1 {
					legal = append(legal, actionID)
					if actionID >= PonBase {
						claims++
					}
				}
			}
			if len(legal) == 0 {
				break
			}
			result, err := env.Step(&pb.EnvStepRequest{ActionId: uint32(legal[rng.Intn(len(legal))])})
			if err != nil {
				t.Fatalf("step: %v", err)
			}
			if result.Terminated || result.Truncated {
				break
			}
			observation = result.Observation
		}
	}
	t.Logf("%d decisions x %d symmetries; best-discard tie-break changed a scalar in %d of %d",
		checked, len(symmetries), tieBreaks, checked*len(symmetries))
	if checked < 200 || claims == 0 {
		t.Fatalf("too little coverage: %d decisions, %d pon/kan/chii-legal", checked, claims)
	}
}

func scoreSignature(score int32, breakdown []*pb.ScoreEntry, canWin bool) string {
	entries := make([]string, 0, len(breakdown))
	for _, entry := range breakdown {
		entries = append(entries, fmt.Sprintf("%s=%d", entry.PatternId, entry.Points))
	}
	sort.Strings(entries)
	return fmt.Sprintf("win=%v score=%d %v", canWin, score, entries)
}

// The rules score every win the same after any face symmetry: a transformed winning
// hand has the same total and the same pattern breakdown. With the mask equivariance
// above, this makes the game itself symmetric, not only the encoder.
func TestScoringIsFaceSymmetryInvariant(t *testing.T) {
	config := &pb.EnvConfig{
		LearningSeats:      []uint32{0, 1, 2, 3},
		AutoPlayHeuristics: false,
		MaxDecisions:       2000,
		MatchMode:          pb.MatchMode_MATCH_MODE_CHONGCI,
		ChongciConfig:      &pb.ChongciConfig{StartingScore: 2000, BustThreshold: 0, MaxHands: 4},
	}
	rng := rand.New(rand.NewSource(13))
	symmetries := testedSymmetries()
	wins := 0
	for seed := uint64(1); seed <= 200; seed++ {
		env := New(config)
		reset, err := env.Reset(&pb.EnvResetRequest{Seed: seed, Config: config})
		if err != nil {
			t.Fatalf("reset %d: %v", seed, err)
		}
		observation := reset.Observation
		for step := 0; step < 2000 && observation != nil && !reset.Terminated; step++ {
			seat := observation.Seat
			for _, winAction := range []int{ActionTsumo, ActionRon} {
				if observation.ActionMask[winAction] != 1 {
					continue
				}
				isTsumo := winAction == ActionTsumo
				evaluate := func(state *pb.GameState) string {
					var winTile *pb.Tile
					if !isTsumo {
						winTile = state.ActiveDiscard
					}
					player := state.Players[seat]
					return scoreSignature(env.game.Rules.EvaluateHand(player.ClosedHand, player.OpenMelds, winTile, state, seat, isTsumo))
				}
				want := evaluate(env.game.State)
				for _, sym := range symmetries {
					transformed := proto.Clone(env.game.State).(*pb.GameState)
					sym.transformTiles(transformed.ProtoReflect())
					if got := evaluate(transformed); got != want {
						t.Fatalf("seed %d %+v: %s, want %s", seed, sym, got, want)
					}
				}
				wins++
			}
			// Never take the win, so each game keeps producing scorable hands.
			legal := make([]int, 0, 8)
			for actionID, enabled := range observation.ActionMask {
				if enabled == 1 && actionID != ActionTsumo && actionID != ActionRon {
					legal = append(legal, actionID)
				}
			}
			if len(legal) == 0 {
				break
			}
			result, err := env.Step(&pb.EnvStepRequest{ActionId: uint32(legal[rng.Intn(len(legal))])})
			if err != nil {
				t.Fatalf("step: %v", err)
			}
			if result.Terminated || result.Truncated {
				break
			}
			observation = result.Observation
		}
	}
	t.Logf("%d winning hands x %d symmetries scored identically", wins, len(symmetries))
	if wins < 100 {
		t.Fatalf("too little coverage: %d winning hands", wins)
	}
}
