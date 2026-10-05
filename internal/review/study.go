package review

import (
	"context"
	"errors"
	"fmt"
	"math"
	"time"

	"github.com/plasma/fh-mahjong/internal/engine"
	"github.com/plasma/fh-mahjong/internal/rl"
	pb "github.com/plasma/fh-mahjong/proto"
)

const StudyMethod = "paired-round-return-v1"

type StudyConfig struct {
	Worlds       int    `json:"worlds"`
	RiskWorlds   int    `json:"riskWorlds"`
	Seed         uint64 `json:"seed"`
	MaxDecisions int    `json:"maxDecisions"`
}

func DefaultStudyConfig() StudyConfig {
	return StudyConfig{Worlds: 32, RiskWorlds: 128, Seed: 20261004, MaxDecisions: 512}
}

type StudyMetadata struct {
	EventWindow uint32      `json:"eventWindow"`
	Method      string      `json:"method"`
	Objective   string      `json:"objective"`
	Units       string      `json:"units"`
	Config      StudyConfig `json:"config"`
	Complete    bool        `json:"complete"`
	BuildMillis int64       `json:"buildMillis"`
}

type ActionEvaluation struct {
	Mean          float64 `json:"mean"`
	StandardError float64 `json:"standardError"`
	Samples       int     `json:"samples"`
}

// BuildStudy checkpoints complete decisions through save. The supplied resume
// report must already be bound to the same immutable input/config/checkpoint.
// Counterfactual values measure round payout, not Mortal Q or a state value.
func BuildStudy(ctx context.Context, p *engine.Paipu, client PolicyClient, window uint32, cfg StudyConfig, expectedSHA string, resume *Report, save func(*Report, string, int, int) error) (*Report, error) {
	if cfg.Worlds < 1 || cfg.Worlds > 64 || cfg.RiskWorlds < 1 || cfg.RiskWorlds > 256 || cfg.MaxDecisions < 1 || cfg.MaxDecisions > 1024 {
		return nil, fmt.Errorf("invalid study budget")
	}
	started := time.Now()
	ds, err := extractDecisionsContext(ctx, p, window, true)
	if err != nil {
		if errors.Is(err, context.Canceled) || errors.Is(err, context.DeadlineExceeded) {
			return nil, err
		}
		return nil, fmt.Errorf("%w: %v", ErrUnreviewable, err)
	}
	total := len(ds) * 2
	var report *Report
	if resume != nil && resume.SchemaVersion == SchemaVersion && resume.CheckpointSha256 == expectedSHA && resume.Study != nil && resume.Study.Method == StudyMethod && resume.Study.Config == cfg && len(resume.Decisions) == len(ds) {
		report = resume
		for i, d := range ds {
			if report.Decisions[i].ID != fmt.Sprintf("r%d-d%d-s%d", d.RoundIndex, d.DecisionIndex, d.Seat) {
				return nil, fmt.Errorf("resume decision identity mismatch")
			}
		}
	} else {
		obs := make([]*pb.SeatObservation, len(ds))
		for i, d := range ds {
			obs[i] = d.Observation
		}
		results, info, err := client.Evaluate(ctx, obs)
		if err != nil {
			return nil, err
		}
		if len(results) != len(ds) || info.Sha256 == "" || info.Sha256 != expectedSHA {
			return nil, fmt.Errorf("checkpoint or evaluation count changed during study")
		}
		report = &Report{SchemaVersion: SchemaVersion, MatchID: p.MatchID, Ruleset: p.Ruleset, CheckpointPath: info.Path, CheckpointStep: info.Step, CheckpointSha256: info.Sha256, GeneratedAt: time.Now().UTC(), ValuesCalibrated: info.ValuesCalibrated, Decisions: make([]ReportDecision, len(ds))}
		for i, d := range ds {
			rd, err := buildReportDecision(d, results[i])
			if err != nil {
				return nil, err
			}
			report.Decisions[i] = rd
		}
		report.Seats = buildSeatSummaries(report.Decisions)
		report.Study = &StudyMetadata{Method: StudyMethod, EventWindow: window, Objective: "expected net payout through the current round under the reviewed policy; uniform unseen worlds", Units: "Fenghua points", Config: cfg}
	}
	// Cheap deterministic scorer queries are reconstructed on every resume.
	for i, d := range ds {
		if err := ctx.Err(); err != nil {
			return nil, err
		}
		report.Decisions[i].Draw = assessDraw(d, p)
	}
	completed := 0
	for _, rd := range report.Decisions {
		if rd.Risk != nil {
			completed++
		}
		if evaluationsComplete(rd) {
			completed++
		}
	}
	checkpoint := func(phase string) error {
		report.Study.BuildMillis += time.Since(started).Milliseconds()
		started = time.Now()
		if save != nil {
			return save(report, phase, completed, total)
		}
		return nil
	}
	if err := checkpoint("policy"); err != nil {
		return nil, err
	}
	for i, d := range ds {
		if err := ctx.Err(); err != nil {
			return nil, err
		}
		rd := &report.Decisions[i]
		seed := cfg.Seed + uint64(i)*1000003
		if rd.Risk == nil {
			risk, err := assessRisk(ctx, d, cfg.RiskWorlds, seed)
			if err != nil {
				return nil, fmt.Errorf("decision %d risk: %w", i, err)
			}
			rd.Risk = risk
			completed++
			if err := checkpoint("risk"); err != nil {
				return nil, err
			}
		}
		if !evaluationsComplete(*rd) {
			values, err := evaluateActions(ctx, d, rd.Actions, client, window, cfg, seed, expectedSHA)
			if err != nil {
				return nil, fmt.Errorf("decision %d rollout: %w", i, err)
			}
			for j := range rd.Actions {
				v := values[j]
				rd.Actions[j].Evaluation = &v
			}
			completed++
			if err := checkpoint("evaluation"); err != nil {
				return nil, err
			}
		}
	}
	report.Study.Complete = true
	if err := checkpoint("complete"); err != nil {
		return nil, err
	}
	return report, nil
}

func evaluationsComplete(d ReportDecision) bool {
	if len(d.Actions) == 0 {
		return false
	}
	for _, a := range d.Actions {
		if a.Evaluation == nil || a.Evaluation.Samples < 1 {
			return false
		}
	}
	return true
}

type rollout struct {
	game  *engine.Game
	steps int
	done  bool
	score float64
}

func evaluateActions(ctx context.Context, d Decision, actions []ActionProb, client PolicyClient, window uint32, cfg StudyConfig, seed uint64, sha string) ([]ActionEvaluation, error) {
	slots := make([]rollout, len(actions)*cfg.Worlds)
	for a, choice := range actions {
		for k := 0; k < cfg.Worlds; k++ {
			g := d.Branch.CloneForBranch()
			if err := g.RedealUnseenForReview(d.Seat, seed+uint64(k)); err != nil {
				return nil, err
			}
			act, err := rl.DecodeActionID(g.State, d.Seat, choice.ActionID)
			if err != nil {
				return nil, err
			}
			if err := g.ProcessPlayerAction(d.Seat, act); err != nil {
				return nil, err
			}
			slots[a*cfg.Worlds+k] = rollout{game: g, steps: 1}
		}
	}
	for {
		if err := ctx.Err(); err != nil {
			return nil, err
		}
		var obs []*pb.SeatObservation
		var indices []int
		for i := range slots {
			r := &slots[i]
			if r.done {
				continue
			}
			for {
				state := r.game.State
				if state.Phase == pb.GamePhase_PHASE_ROUND_END || state.Phase == pb.GamePhase_PHASE_MATCH_END {
					if state.RoundResult == nil {
						return nil, fmt.Errorf("rollout ended without result")
					}
					for _, v := range state.RoundResult.Payouts {
						if v.Seat == d.Seat {
							r.score = float64(v.Amount)
						}
					}
					r.done = true
					break
				}
				if r.steps >= cfg.MaxDecisions {
					return nil, fmt.Errorf("round rollout exceeded %d decisions; retry with a larger budget", cfg.MaxDecisions)
				}
				seat, ok := nextRolloutSeat(r.game)
				if !ok {
					if state.Phase == pb.GamePhase_PHASE_WAIT_DISCARDS {
						r.game.ResolveInterrupts()
						continue
					}
					return nil, fmt.Errorf("rollout has no actionable seat")
				}
				legal, err := rl.LegalActions(state, seat)
				if err != nil {
					return nil, err
				}
				if len(legal) == 1 {
					for _, act := range legal {
						if err := r.game.ProcessPlayerAction(seat, act); err != nil {
							return nil, err
						}
					}
					r.steps++
					continue
				}
				o, err := rl.EncodeObservationWithEvents(state, seat, uint64(r.steps), r.game.PublicEvents(), window)
				if err != nil {
					return nil, err
				}
				obs = append(obs, o)
				indices = append(indices, i)
				break
			}
		}
		if len(obs) == 0 {
			break
		}
		results, info, err := client.Evaluate(ctx, obs)
		if err != nil {
			return nil, err
		}
		if info.Sha256 != sha || len(results) != len(obs) {
			return nil, fmt.Errorf("checkpoint or batch count changed during rollout")
		}
		for j, i := range indices {
			rd, err := buildReportDecision(Decision{Observation: obs[j], ChosenAction: firstLegalID(obs[j])}, results[j])
			if err != nil {
				return nil, err
			}
			r := &slots[i]
			act, err := rl.DecodeActionID(r.game.State, obs[j].Seat, rd.RecommendedID)
			if err != nil {
				return nil, err
			}
			if err := r.game.ProcessPlayerAction(obs[j].Seat, act); err != nil {
				return nil, err
			}
			r.steps++
		}
	}
	out := make([]ActionEvaluation, len(actions))
	for a := range actions {
		mean := 0.0
		for k := 0; k < cfg.Worlds; k++ {
			mean += slots[a*cfg.Worlds+k].score / float64(cfg.Worlds)
		}
		variance := 0.0
		for k := 0; k < cfg.Worlds; k++ {
			delta := slots[a*cfg.Worlds+k].score - mean
			variance += delta * delta
		}
		se := 0.0
		if cfg.Worlds > 1 {
			se = math.Sqrt(variance / float64(cfg.Worlds-1) / float64(cfg.Worlds))
		}
		out[a] = ActionEvaluation{Mean: mean, StandardError: se, Samples: cfg.Worlds}
	}
	return out, nil
}

func firstLegalID(o *pb.SeatObservation) int {
	for i, m := range o.ActionMask {
		if m != 0 {
			return i
		}
	}
	return -1
}

func nextRolloutSeat(g *engine.Game) (uint32, bool) {
	if g.State.Phase == pb.GamePhase_PHASE_PLAYER_TURN {
		return g.State.ActivePlayer, true
	}
	if g.State.Phase == pb.GamePhase_PHASE_WAIT_DISCARDS {
		for s, p := range g.State.Players {
			if uint32(s) != g.State.ActivePlayer && len(p.ValidActions) > 0 && !g.InterruptQueued(uint32(s)) {
				return uint32(s), true
			}
		}
	}
	return 0, false
}
