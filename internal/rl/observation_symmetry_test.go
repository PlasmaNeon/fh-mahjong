package rl

import (
	"math/rand"
	"testing"

	"github.com/plasma/fh-mahjong/internal/engine"
	pb "github.com/plasma/fh-mahjong/proto"
	"google.golang.org/protobuf/proto"
	"google.golang.org/protobuf/reflect/protoreflect"
)

// The observation encoder must be equivariant under any permutation of the three
// suits: encoding a suit-permuted state equals permuting the original encoding.
// The one exception is the best-discard look-ahead block (scalars 33-35, 37, 40):
// bestVisibleDiscardLookahead breaks ties by face order, so a permutation can pick a
// different tied tile. Those are measured, not required.
// ai/src/fh_mahjong_ai/suit_symmetry.py applies exactly these maps (faces, actions,
// planes, scalar 24, event faces) to average a policy over suit permutations, so
// this test is what licenses that transform.

// faceBlockSuits is the suit of each 9-face block in the 42-face index.
var faceBlockSuits = [3]pb.Suit{pb.Suit_SUIT_MAN, pb.Suit_SUIT_PIN, pb.Suit_SUIT_SOU}

func suitPermutations() [][3]int {
	return [][3]int{{0, 1, 2}, {0, 2, 1}, {1, 0, 2}, {1, 2, 0}, {2, 0, 1}, {2, 1, 0}}
}

func permuteFace(face int, perm [3]int) int {
	if face >= 0 && face < 27 {
		return perm[face/9]*9 + face%9
	}
	return face
}

func permuteActionID(actionID int, perm [3]int) int {
	switch {
	case actionID >= DiscardBase && actionID < DiscardBase+DiscardCount:
		return DiscardBase + permuteFace(actionID-DiscardBase, perm)
	case actionID >= PonBase && actionID < ChiiBase:
		// pon and the three kan families are consecutive 34-face blocks
		base := PonBase + ((actionID-PonBase)/34)*34
		return base + permuteFace(actionID-base, perm)
	case actionID >= ChiiBase && actionID < ChiiBase+ChiiCount:
		index := actionID - ChiiBase
		return ChiiBase + perm[index/7]*7 + index%7
	}
	return actionID
}

func permuteTileSuits(message protoreflect.Message, perm [3]int) {
	if message.Descriptor().FullName() == "game.Tile" {
		suitField := message.Descriptor().Fields().ByName("suit")
		suit := pb.Suit(message.Get(suitField).Enum())
		for block, blockSuit := range faceBlockSuits {
			if suit == blockSuit {
				message.Set(suitField, protoreflect.ValueOfEnum(protoreflect.EnumNumber(faceBlockSuits[perm[block]])))
				break
			}
		}
		return
	}
	message.Range(func(field protoreflect.FieldDescriptor, value protoreflect.Value) bool {
		switch {
		case field.IsList() && field.Message() != nil:
			list := value.List()
			for i := 0; i < list.Len(); i++ {
				permuteTileSuits(list.Get(i).Message(), perm)
			}
		case field.IsMap() && field.MapValue().Message() != nil:
			value.Map().Range(func(_ protoreflect.MapKey, v protoreflect.Value) bool {
				permuteTileSuits(v.Message(), perm)
				return true
			})
		case field.Message() != nil && !field.IsList() && !field.IsMap():
			permuteTileSuits(value.Message(), perm)
		}
		return true
	})
}

func permuteEvents(events []engine.PublicEvent, perm [3]int) []engine.PublicEvent {
	out := append([]engine.PublicEvent(nil), events...)
	for i := range out {
		if out[i].Face >= 0 {
			out[i].Face = int16(permuteFace(int(out[i].Face), perm))
		}
	}
	return out
}

func permutePackedEvent(packed uint32, perm [3]int) uint32 {
	face := int((packed >> 6) & 0x3F)
	if face == 63 {
		return packed
	}
	return packed&^(0x3F<<6) | uint32(permuteFace(face, perm))<<6
}

// tieBrokenScalars come from the best-discard look-ahead, whose tie-break is face order.
var tieBrokenScalars = map[int]bool{33: true, 34: true, 35: true, 37: true, 40: true}

func assertSuitEquivariant(t *testing.T, state *pb.GameState, seat uint32, events []engine.PublicEvent, perm [3]int) (tieBreakDiffers bool) {
	t.Helper()
	const window = 64
	original, err := encodeObservation(state, seat, 0, false, events, window)
	if err != nil {
		t.Fatalf("encode original: %v", err)
	}
	permutedState := proto.Clone(state).(*pb.GameState)
	permuteTileSuits(permutedState.ProtoReflect(), perm)
	permuted, err := encodeObservation(permutedState, seat, 0, false, permuteEvents(events, perm), window)
	if err != nil {
		t.Fatalf("encode permuted %v: %v", perm, err)
	}

	for channel := 0; channel < ObservationPlaneChannels; channel++ {
		for face := 0; face < ObservationPlaneHeight; face++ {
			want := original.Planes[channelOffset(channel)+face]
			got := permuted.Planes[channelOffset(channel)+permuteFace(face, perm)]
			if got != want {
				t.Fatalf("perm %v plane %d face %d: got %v, want %v", perm, channel, face, got, want)
			}
		}
	}
	for actionID := range original.ActionMask {
		if permuted.ActionMask[permuteActionID(actionID, perm)] != original.ActionMask[actionID] {
			t.Fatalf("perm %v action %d: mask not equivariant", perm, actionID)
		}
	}
	for i, want := range original.Scalars {
		got := permuted.Scalars[i]
		if i == 24 {
			if face, ok := tileFaceIndex42(state.ActiveDiscard); ok {
				want = float32(permuteFace(face, perm)) / 41.0
			}
		}
		if got != want {
			if tieBrokenScalars[i] {
				tieBreakDiffers = true
				continue
			}
			t.Fatalf("perm %v scalar %d: got %v, want %v", perm, i, got, want)
		}
	}
	if len(permuted.EventHistory) != len(original.EventHistory) {
		t.Fatalf("perm %v event history length %d vs %d", perm, len(permuted.EventHistory), len(original.EventHistory))
	}
	for i, packed := range original.EventHistory {
		if permuted.EventHistory[i] != permutePackedEvent(packed, perm) {
			t.Fatalf("perm %v event %d: got %#x, want %#x", perm, i, permuted.EventHistory[i], permutePackedEvent(packed, perm))
		}
	}
	return tieBreakDiffers
}

func TestObservationIsSuitEquivariant(t *testing.T) {
	config := &pb.EnvConfig{
		LearningSeats:      []uint32{0, 1, 2, 3},
		AutoPlayHeuristics: false,
		MaxDecisions:       600,
		MatchMode:          pb.MatchMode_MATCH_MODE_CHONGCI,
		ChongciConfig:      &pb.ChongciConfig{StartingScore: 2000, BustThreshold: 0, MaxHands: 4},
	}
	rng := rand.New(rand.NewSource(11))
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
			for _, perm := range suitPermutations() {
				if assertSuitEquivariant(t, env.game.State, seat, env.game.PublicEvents(), perm) {
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
	t.Logf("%d decisions x 6 permutations; best-discard tie-break changed a scalar in %d of %d",
		checked, tieBreaks, checked*6)
	if checked < 200 || claims == 0 {
		t.Fatalf("too little coverage: %d decisions, %d pon/kan/chii-legal", checked, claims)
	}
}
