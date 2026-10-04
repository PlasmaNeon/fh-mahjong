package review

import (
	"context"
	"fmt"
	"math"
	"sort"

	"github.com/plasma/fh-mahjong/internal/engine"
	"github.com/plasma/fh-mahjong/internal/rl"
	pb "github.com/plasma/fh-mahjong/proto"
	"google.golang.org/protobuf/proto"
)

type RiskAssessment struct {
	Method     string          `json:"method"`
	Samples    int             `json:"samples"`
	Tiles      []TileRisk      `json:"tiles"`
	Operations []OperationRisk `json:"operations"`
}

type TileRisk struct {
	Face          int            `json:"face"`
	Unseen        int            `json:"unseen"`
	InHand        bool           `json:"inHand"`
	AnyRon        float64        `json:"anyRon"`
	StandardError float64        `json:"standardError"`
	Opponents     []OpponentRisk `json:"opponents"`
}

type OpponentRisk struct {
	Seat         uint32            `json:"seat"`
	Ron          float64           `json:"ron"`
	Contributors []WaitContributor `json:"contributors"`
}

type WaitContributor struct {
	PatternID    string  `json:"patternId"`
	PatternName  string  `json:"patternName"`
	Frequency    float64 `json:"frequency"`
	ExampleFaces []int   `json:"exampleFaces"`
}

type OperationRisk struct {
	ActionID int     `json:"actionId"`
	AnyRon   float64 `json:"anyRon"`
}

type DrawOpportunity struct {
	ActionIndex int        `json:"actionIndex"`
	Source      string     `json:"source"`
	Hit         bool       `json:"hit"`
	Chance      float64    `json:"chance"`
	Unseen      int        `json:"unseen"`
	Waits       []DrawWait `json:"waits"`
}

type DrawWait struct {
	Face      int   `json:"face"`
	Remaining int   `json:"remaining"`
	Points    int32 `json:"points"`
}

func faceTile(face int) *pb.Tile {
	suit := pb.Suit_SUIT_MAN
	value := face + 1
	id := (face)*4 + 36
	if face >= 9 && face < 18 {
		suit = pb.Suit_SUIT_PIN
		value = face - 8
		id = 72 + (face-9)*4
	}
	if face >= 18 && face < 27 {
		suit = pb.Suit_SUIT_SOU
		value = face - 17
		id = (face - 18) * 4
	}
	if face >= 27 && face < 34 {
		suit = pb.Suit_SUIT_JIHAI
		value = face - 26
		id = 108 + (face-27)*4
	}
	if face >= 34 {
		suit = pb.Suit_SUIT_FLOWER
		value = face - 33
		id = 136 + face - 34
	}
	return &pb.Tile{Id: uint32(id), Suit: suit, Value: uint32(value)}
}

func visibleCounts(g *engine.Game, seat uint32) [42]int {
	var counts [42]int
	seen := make(map[uint32]bool)
	add := func(t *pb.Tile) {
		if t == nil || seen[t.Id] {
			return
		}
		seen[t.Id] = true
		if f, ok := engine.FaceIndex42(t); ok {
			counts[f]++
		}
	}
	for s, p := range g.State.Players {
		if uint32(s) == seat {
			for _, t := range p.ClosedHand {
				add(t)
			}
		}
		for _, t := range p.Discards {
			add(t)
		}
		for _, t := range p.FlowerMelds {
			add(t)
		}
		for _, m := range p.OpenMelds {
			for _, t := range m.Tiles {
				add(t)
			}
		}
	}
	add(g.VisibleWildIndicator())
	add(g.State.ActiveDiscard)
	return counts
}

func assessRisk(ctx context.Context, d Decision, worlds int, seed uint64) (*RiskAssessment, error) {
	if d.Branch == nil {
		return nil, fmt.Errorf("missing review branch")
	}
	g := d.Branch
	visible := visibleCounts(g, d.Seat)
	out := &RiskAssessment{Method: "uniform-unseen-legal-waits-v1", Samples: worlds, Tiles: make([]TileRisk, 42), Operations: []OperationRisk{}}
	var own [42]int
	for _, t := range g.State.Players[d.Seat].ClosedHand {
		if f, ok := engine.FaceIndex42(t); ok {
			own[f]++
		}
	}
	hits := make([][4]int, 42)
	joint := make([]int, 42)
	contributors := make([][4]map[string]*WaitContributor, 42)
	for f := 0; f < 42; f++ {
		copies := 4
		if f >= 34 {
			copies = 1
		}
		out.Tiles[f] = TileRisk{Face: f, Unseen: max(0, copies-visible[f]), InHand: own[f] > 0, Opponents: []OpponentRisk{}}
	}
	var upgradeIDs []int
	for id, m := range d.Observation.ActionMask {
		if m != 0 && id >= rl.KanUpgradedBase && id < rl.ChiiBase {
			upgradeIDs = append(upgradeIDs, id)
		}
	}
	upgradeHits := make([]int, len(upgradeIDs))
	for k := 0; k < worlds; k++ {
		if err := ctx.Err(); err != nil {
			return nil, err
		}
		sampled := g.CloneForBranch()
		if err := sampled.RedealUnseenForReview(d.Seat, seed+uint64(k)); err != nil {
			return nil, err
		}
		for f := 0; f < 42; f++ {
			tile := faceTile(f)
			any := false
			for s, p := range sampled.State.Players {
				if uint32(s) == d.Seat {
					continue
				}
				same := 0
				for _, t := range p.ClosedHand {
					if t.Suit == tile.Suit && t.Value == tile.Value {
						same++
					}
				}
				copies := 4
				if f >= 34 {
					copies = 1
				}
				if same >= copies {
					continue
				}
				_, entries, win := sampled.Rules.EvaluateHand(p.ClosedHand, p.OpenMelds, tile, sampled.State, uint32(s), false)
				if !win {
					continue
				}
				any = true
				hits[f][s]++
				if contributors[f][s] == nil {
					contributors[f][s] = make(map[string]*WaitContributor)
				}
				for _, entry := range entries {
					key := entry.PatternId
					c := contributors[f][s][key]
					if c == nil {
						c = &WaitContributor{PatternID: key, PatternName: entry.PatternName}
						for _, t := range p.ClosedHand {
							if face, ok := engine.FaceIndex42(t); ok {
								c.ExampleFaces = append(c.ExampleFaces, face)
							}
						}
						sort.Ints(c.ExampleFaces)
						contributors[f][s][key] = c
					}
					c.Frequency += 1 / float64(worlds)
				}
			}
			if any {
				joint[f]++
			}
		}
		for j, id := range upgradeIDs {
			branch := sampled.CloneForBranch()
			act, err := rl.DecodeActionID(branch.State, d.Seat, id)
			if err != nil {
				return nil, err
			}
			if err := branch.ProcessPlayerAction(d.Seat, act); err != nil {
				return nil, err
			}
			any := false
			if branch.State.Phase == pb.GamePhase_PHASE_WAIT_DISCARDS {
				for s, p := range branch.State.Players {
					if uint32(s) == d.Seat {
						continue
					}
					for _, a := range p.ValidActions {
						if a.Type == pb.ActionType_ACTION_RON {
							any = true
						}
					}
				}
			}
			if any {
				upgradeHits[j]++
			}
		}
	}
	for f := range out.Tiles {
		tr := &out.Tiles[f]
		tr.AnyRon = float64(joint[f]) / float64(worlds)
		tr.StandardError = math.Sqrt(tr.AnyRon * (1 - tr.AnyRon) / float64(worlds))
		for s := uint32(0); s < 4; s++ {
			if s == d.Seat {
				continue
			}
			o := OpponentRisk{Seat: s, Ron: float64(hits[f][s]) / float64(worlds), Contributors: []WaitContributor{}}
			for _, c := range contributors[f][s] {
				o.Contributors = append(o.Contributors, *c)
			}
			sort.Slice(o.Contributors, func(i, j int) bool { return o.Contributors[i].PatternID < o.Contributors[j].PatternID })
			tr.Opponents = append(tr.Opponents, o)
		}
	}
	for j, id := range upgradeIDs {
		out.Operations = append(out.Operations, OperationRisk{ActionID: id, AnyRon: float64(upgradeHits[j]) / float64(worlds)})
	}
	return out, nil
}

// assessDraw rebuilds the player's information BEFORE the recorded draw. It
// uses public unseen-copy counts, never the true wall or observed draw face to
// choose waits. Ordinary flower replacements are conditioned on a playable
// tile. The actual hit/miss is attached only after the estimate is computed.
func assessDraw(d Decision, p *engine.Paipu) *DrawOpportunity {
	state := d.Branch.State
	if state.Phase != pb.GamePhase_PHASE_PLAYER_TURN || state.Players[d.Seat].DrawnTileId == nil {
		return nil
	}
	drawID := int(*state.Players[d.Seat].DrawnTileId)
	index := -1
	round := p.Rounds[d.RoundIndex]
	for i := min(d.PositionIndex, len(round.Actions)-1); i >= 0; i-- {
		a := round.Actions[i]
		if a.Seat != d.Seat {
			continue
		}
		if (a.Act == "draw" || a.Act == "haitei" || a.Act == "flower") && a.Tile != nil && *a.Tile == drawID {
			index = i
			break
		}
		if a.Act == "discard" {
			break
		}
	}
	if index < 0 {
		return nil
	}
	g := d.Branch.CloneForBranch()
	player := g.State.Players[d.Seat]
	before := player.ClosedHand[:0]
	for _, t := range player.ClosedHand {
		if int(t.Id) != drawID {
			before = append(before, t)
		}
	}
	player.ClosedHand = before
	player.HandSize = uint32(len(before))
	player.DrawnTileId = nil
	counts := visibleCounts(g, d.Seat)
	out := &DrawOpportunity{ActionIndex: index, Source: "wall; uniform public unseen-copy model", Waits: []DrawWait{}}
	if state.IsHaitei {
		out.Source = "haitei; uniform public unseen-copy model"
	} else if player.HasBloomingFlowerKong || player.HasBloomingClosedKong || player.HasBloomingDirectKong || player.HasBloomingRiskyKong {
		out.Source = "wangpai replacement; uniform public unseen-copy model"
	}
	for f := 0; f < 42; f++ {
		tile := faceTile(f)
		copies := 4
		if f >= 34 {
			copies = 1
		}
		left := max(0, copies-counts[f])
		if left == 0 {
			continue
		}
		wild := false
		for _, w := range state.WildTiles {
			if w.Suit == tile.Suit && w.Value == tile.Value {
				wild = true
			}
		}
		if tile.Suit == pb.Suit_SUIT_FLOWER && !wild {
			continue
		}
		out.Unseen += left
		hand := append(append([]*pb.Tile(nil), before...), tile)
		gs := proto.Clone(g.State).(*pb.GameState)
		gs.Players[d.Seat].ClosedHand = hand
		gs.Players[d.Seat].HandSize = uint32(len(hand))
		points, _, win := g.Rules.EvaluateHand(before, player.OpenMelds, tile, gs, d.Seat, true)
		if win {
			out.Waits = append(out.Waits, DrawWait{Face: f, Remaining: left, Points: points})
			out.Chance += float64(left)
		}
	}
	if out.Unseen > 0 {
		out.Chance /= float64(out.Unseen)
	}
	_, _, out.Hit = g.Rules.EvaluateHand(state.Players[d.Seat].ClosedHand, state.Players[d.Seat].OpenMelds, nil, state, d.Seat, true)
	return out
}
