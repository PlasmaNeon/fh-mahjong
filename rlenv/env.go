package rlenv

import (
	"fmt"
	"strings"

	"github.com/plasma/fh-mahjong/bot"
	"github.com/plasma/fh-mahjong/core"
	pb "github.com/plasma/fh-mahjong/proto"
	"github.com/plasma/fh-mahjong/rules"
)

type Env struct {
	config        *pb.EnvConfig
	game          *core.Game
	heuristic     bot.Policy
	learningSeats map[uint32]bool
	decisionCount uint64
}

func New(config *pb.EnvConfig) *Env {
	normalized := normalizeConfig(config)
	return &Env{
		config:        normalized,
		heuristic:     bot.NewHeuristicPolicy(),
		learningSeats: learningSeatSet(normalized),
	}
}

func (e *Env) Reset(request *pb.EnvResetRequest) (*pb.EnvResetResponse, error) {
	if request != nil && request.Config != nil {
		e.config = normalizeConfig(request.Config)
		e.learningSeats = learningSeatSet(e.config)
	} else if e.config == nil {
		e.config = normalizeConfig(nil)
		e.learningSeats = learningSeatSet(e.config)
	}

	seed := uint64(1)
	if request != nil && request.Seed != 0 {
		seed = request.Seed
	}

	e.game = core.NewGame(fmt.Sprintf("rl-%d", seed), &rules.HometownRuleset{}, matchOptionsFromConfig(e.config))
	e.game.SetWallSeed(core.SeedFromUint64(seed))
	e.decisionCount = 0
	if err := e.game.Start(); err != nil {
		return nil, err
	}
	stepResponse, err := e.advanceToDecision()
	if err != nil {
		return nil, err
	}
	return &pb.EnvResetResponse{
		Observation:  cloneObservation(stepResponse.Observation),
		Rewards:      append([]float32(nil), stepResponse.Rewards...),
		Terminated:   stepResponse.Terminated,
		Truncated:    stepResponse.Truncated,
		RoundOutcome: cloneRoundOutcome(stepResponse.RoundOutcome),
	}, nil
}

func (e *Env) Step(request *pb.EnvStepRequest) (*pb.EnvStepResponse, error) {
	if e.game == nil || e.game.State == nil {
		return nil, fmt.Errorf("environment must be reset before stepping")
	}
	if request == nil {
		return nil, fmt.Errorf("step request is required")
	}

	seat, ok := e.currentLearningSeat()
	if !ok {
		return nil, fmt.Errorf("no learning seat is currently waiting for input")
	}

	action, err := decodeActionID(e.game.State, seat, int(request.ActionId))
	if err != nil {
		return nil, err
	}

	e.decisionCount++
	if err := e.game.ProcessPlayerAction(seat, action); err != nil {
		return nil, err
	}
	return e.advanceToDecision()
}

func (e *Env) GenerateHeuristicTrajectory(request *pb.TrajectoryRequest) (*pb.TrajectoryDataset, error) {
	episodes := uint32(1)
	startSeed := uint64(1)
	if request != nil {
		if request.Episodes > 0 {
			episodes = request.Episodes
		}
		if request.StartSeed > 0 {
			startSeed = request.StartSeed
		}
	}

	dataset := &pb.TrajectoryDataset{}
	for episode := uint32(0); episode < episodes; episode++ {
		config := configOrDefault(request)
		env := New(&pb.EnvConfig{
			LearningSeats:      []uint32{0, 1, 2, 3},
			AutoPlayHeuristics: false,
			MaxDecisions:       config.MaxDecisions,
			MatchMode:          config.MatchMode,
			ChongciConfig:      cloneChongciConfig(config.ChongciConfig),
		})

		resetResponse, err := env.Reset(&pb.EnvResetRequest{
			Seed:   startSeed + uint64(episode),
			Config: env.config,
		})
		if err != nil {
			return nil, err
		}

		episodeSamples := make([]*pb.TrajectorySample, 0)
		observation := cloneObservation(resetResponse.Observation)
		finalRewards := append([]float32(nil), resetResponse.Rewards...)

		for !resetResponse.Terminated && !resetResponse.Truncated {
			seat := observation.Seat
			action := env.heuristic.ChooseAction(env.game.State, seat)
			if action == nil {
				return nil, fmt.Errorf("heuristic returned nil action for seat %d", seat)
			}
			actionID, ok := encodeAction(env.game.State, seat, action)
			if !ok {
				return nil, fmt.Errorf("cannot encode heuristic action %v for seat %d", action.Type, seat)
			}

			stepResponse, err := env.Step(&pb.EnvStepRequest{ActionId: uint32(actionID)})
			if err != nil {
				return nil, err
			}

			sample := &pb.TrajectorySample{
				Observation:     cloneObservation(observation),
				ActionId:        uint32(actionID),
				Rewards:         append([]float32(nil), stepResponse.Rewards...),
				NextObservation: cloneObservation(stepResponse.Observation),
				Terminated:      stepResponse.Terminated,
				Truncated:       stepResponse.Truncated,
				ActingSeat:      seat,
				EpisodeIndex:    uint64(episode),
				TerminalOutcome: cloneRoundOutcome(stepResponse.RoundOutcome),
			}
			episodeSamples = append(episodeSamples, sample)
			observation = cloneObservation(stepResponse.Observation)
			resetResponse = &pb.EnvResetResponse{
				Observation:  cloneObservation(stepResponse.Observation),
				Rewards:      append([]float32(nil), stepResponse.Rewards...),
				Terminated:   stepResponse.Terminated,
				Truncated:    stepResponse.Truncated,
				RoundOutcome: cloneRoundOutcome(stepResponse.RoundOutcome),
			}
			finalRewards = append([]float32(nil), stepResponse.Rewards...)
		}

		for _, sample := range episodeSamples {
			sample.TerminalRewards = append([]float32(nil), finalRewards...)
			if sample.TerminalOutcome == nil {
				sample.TerminalOutcome = cloneRoundOutcome(resetResponse.RoundOutcome)
			}
			dataset.Samples = append(dataset.Samples, sample)
		}
	}

	return dataset, nil
}

func (e *Env) advanceToDecision() (*pb.EnvStepResponse, error) {
	for {
		if e.game.State.Phase == pb.GamePhase_PHASE_MATCH_END {
			return &pb.EnvStepResponse{
				Observation: emptyObservation(e.game.State, e.decisionCount),
				Rewards:     matchEndRewards(e.game.State),
				Terminated:  true,
			}, nil
		}

		if e.game.State.Phase == pb.GamePhase_PHASE_ROUND_END {
			if e.game.State.MatchMode == pb.MatchMode_MATCH_MODE_CHONGCI {
				if err := e.readyAllPlayersForNextRound(); err != nil {
					return nil, err
				}
				continue
			}
			return &pb.EnvStepResponse{
				Observation:  emptyObservation(e.game.State, e.decisionCount),
				Rewards:      roundRewards(e.game.State),
				Terminated:   true,
				RoundOutcome: roundOutcome(e.game.State),
			}, nil
		}

		if e.config.MaxDecisions > 0 && e.decisionCount >= uint64(e.config.MaxDecisions) {
			return &pb.EnvStepResponse{
				Observation: emptyObservation(e.game.State, e.decisionCount),
				Rewards:     make([]float32, 4),
				Truncated:   true,
			}, nil
		}

		if seat, ok := e.currentLearningSeat(); ok {
			observation, err := encodeObservation(e.game.State, seat, e.decisionCount)
			if err != nil {
				return nil, err
			}
			return &pb.EnvStepResponse{
				Observation: observation,
				Rewards:     make([]float32, 4),
			}, nil
		}

		if e.config.AutoPlayHeuristics {
			if seat, ok := e.currentHeuristicSeat(); ok {
				action := e.heuristic.ChooseAction(e.game.State, seat)
				if action == nil {
					return nil, fmt.Errorf("heuristic returned nil action for seat %d", seat)
				}

				e.decisionCount++
				if err := e.game.ProcessPlayerAction(seat, action); err != nil {
					return nil, err
				}
				continue
			}
		}

		if e.game.State.Phase == pb.GamePhase_PHASE_WAIT_DISCARDS {
			if err := e.assertInterruptsReadyToResolve(); err != nil {
				return nil, err
			}
			e.game.ResolveInterrupts()
			continue
		}

		if !e.config.AutoPlayHeuristics {
			return nil, fmt.Errorf("non-learning seat is waiting for input while auto heuristics are disabled: %s", e.decisionStateSummary())
		}

		return nil, fmt.Errorf("no actionable seat found: %s", e.decisionStateSummary())
	}
}

func (e *Env) readyAllPlayersForNextRound() error {
	for seat := uint32(0); seat < 4; seat++ {
		if e.game.State.Phase != pb.GamePhase_PHASE_ROUND_END {
			return nil
		}
		if len(e.game.State.PlayerReady) > int(seat) && e.game.State.PlayerReady[seat] {
			continue
		}
		if err := e.game.ProcessPlayerAction(seat, &pb.PlayerAction{Type: pb.ActionType_ACTION_READY}); err != nil {
			return err
		}
	}
	return nil
}

func (e *Env) currentLearningSeat() (uint32, bool) {
	return e.currentSeat(true)
}

func (e *Env) currentHeuristicSeat() (uint32, bool) {
	return e.currentSeat(false)
}

func (e *Env) currentSeat(learning bool) (uint32, bool) {
	if e.game == nil || e.game.State == nil {
		return 0, false
	}

	switch e.game.State.Phase {
	case pb.GamePhase_PHASE_PLAYER_TURN:
		seat := e.game.State.ActivePlayer
		if len(e.game.State.Players[seat].ValidActions) == 0 {
			return 0, false
		}
		if e.learningSeats[seat] == learning {
			return seat, true
		}
	case pb.GamePhase_PHASE_WAIT_DISCARDS:
		for seat := uint32(0); seat < uint32(len(e.game.State.Players)); seat++ {
			if seat == e.game.State.ActivePlayer {
				continue
			}
			player := e.game.State.Players[seat]
			if len(player.ValidActions) == 0 || e.game.InterruptQueued(seat) {
				continue
			}
			if e.learningSeats[seat] == learning {
				return seat, true
			}
		}
	}

	return 0, false
}

func (e *Env) assertInterruptsReadyToResolve() error {
	if e.game == nil || e.game.State == nil || e.game.State.Phase != pb.GamePhase_PHASE_WAIT_DISCARDS {
		return nil
	}

	for seat := uint32(0); seat < uint32(len(e.game.State.Players)); seat++ {
		if seat == e.game.State.ActivePlayer {
			continue
		}

		player := e.game.State.Players[seat]
		if len(player.ValidActions) == 0 || e.game.InterruptQueued(seat) {
			continue
		}
		return fmt.Errorf("cannot resolve interrupts while seat %d still has an unqueued response", seat)
	}
	return nil
}

func (e *Env) decisionStateSummary() string {
	if e == nil || e.game == nil || e.game.State == nil {
		return "state=<nil>"
	}

	parts := []string{
		fmt.Sprintf("phase=%v", e.game.State.Phase),
		fmt.Sprintf("active=%d", e.game.State.ActivePlayer),
		fmt.Sprintf("auto=%t", e.config != nil && e.config.AutoPlayHeuristics),
	}
	for seat, player := range e.game.State.Players {
		if player == nil {
			parts = append(parts, fmt.Sprintf("seat%d=<nil>", seat))
			continue
		}
		parts = append(parts, fmt.Sprintf(
			"seat%d{learning=%t valid=%d queued=%t}",
			seat,
			e.learningSeats[uint32(seat)],
			len(player.ValidActions),
			e.game.InterruptQueued(uint32(seat)),
		))
	}
	return strings.Join(parts, " ")
}

func normalizeConfig(config *pb.EnvConfig) *pb.EnvConfig {
	if config == nil {
		return &pb.EnvConfig{
			LearningSeats:      []uint32{0},
			AutoPlayHeuristics: true,
			MaxDecisions:       512,
			MatchMode:          pb.MatchMode_MATCH_MODE_CLASSIC,
		}
	}

	normalized := &pb.EnvConfig{
		LearningSeats:      append([]uint32(nil), config.LearningSeats...),
		AutoPlayHeuristics: config.AutoPlayHeuristics,
		MaxDecisions:       config.MaxDecisions,
		MatchMode:          config.MatchMode,
		ChongciConfig:      cloneChongciConfig(config.ChongciConfig),
	}
	if len(normalized.LearningSeats) == 0 {
		normalized.LearningSeats = []uint32{0}
	}
	if normalized.MaxDecisions == 0 {
		if normalized.MatchMode == pb.MatchMode_MATCH_MODE_CHONGCI {
			normalized.MaxDecisions = 8192
		} else {
			normalized.MaxDecisions = 512
		}
	}
	if normalized.MatchMode == pb.MatchMode_MATCH_MODE_UNSPECIFIED {
		normalized.MatchMode = pb.MatchMode_MATCH_MODE_CLASSIC
	}
	return normalized
}

func learningSeatSet(config *pb.EnvConfig) map[uint32]bool {
	set := make(map[uint32]bool)
	for _, seat := range config.LearningSeats {
		set[seat] = true
	}
	return set
}

func roundRewards(state *pb.GameState) []float32 {
	rewards := make([]float32, 4)
	if state == nil || state.RoundResult == nil {
		return rewards
	}
	for _, payout := range state.RoundResult.Payouts {
		if int(payout.Seat) < len(rewards) {
			rewards[payout.Seat] = float32(payout.Amount) / 1000.0
		}
	}
	return rewards
}

func matchEndRewards(state *pb.GameState) []float32 {
	rewards := make([]float32, 4)
	if state == nil || state.MatchEndResult == nil {
		return rewards
	}
	for _, standing := range state.MatchEndResult.Standings {
		if int(standing.Seat) < len(rewards) {
			rewards[standing.Seat] = float32(standing.NetChange) / 1000.0
		}
	}
	return rewards
}

func matchOptionsFromConfig(config *pb.EnvConfig) core.MatchOptions {
	if config == nil || config.MatchMode != pb.MatchMode_MATCH_MODE_CHONGCI {
		return core.MatchOptions{}
	}
	return core.MatchOptions{
		Mode:          pb.MatchMode_MATCH_MODE_CHONGCI,
		ChongciConfig: cloneChongciConfig(config.ChongciConfig),
	}
}

func cloneChongciConfig(config *pb.ChongciConfig) *pb.ChongciConfig {
	if config == nil {
		return nil
	}
	cloned := *config
	return &cloned
}

func roundOutcome(state *pb.GameState) *pb.RoundOutcome {
	if state == nil || state.RoundResult == nil {
		return nil
	}
	result := state.RoundResult
	return &pb.RoundOutcome{
		IsDraw:        result.IsDraw,
		WinnerSeat:    result.WinnerSeat,
		WinType:       result.WinType,
		DiscarderSeat: result.DiscarderSeat,
		TotalScore:    result.TotalScore,
		Payouts:       clonePayouts(result.Payouts),
	}
}

func cloneRoundOutcome(outcome *pb.RoundOutcome) *pb.RoundOutcome {
	if outcome == nil {
		return nil
	}
	return &pb.RoundOutcome{
		IsDraw:        outcome.IsDraw,
		WinnerSeat:    outcome.WinnerSeat,
		WinType:       outcome.WinType,
		DiscarderSeat: outcome.DiscarderSeat,
		TotalScore:    outcome.TotalScore,
		Payouts:       clonePayouts(outcome.Payouts),
	}
}

func clonePayouts(payouts []*pb.PlayerPayout) []*pb.PlayerPayout {
	if len(payouts) == 0 {
		return nil
	}
	cloned := make([]*pb.PlayerPayout, 0, len(payouts))
	for _, payout := range payouts {
		if payout == nil {
			continue
		}
		cloned = append(cloned, &pb.PlayerPayout{
			Seat:   payout.Seat,
			Amount: payout.Amount,
		})
	}
	return cloned
}

func configOrDefault(request *pb.TrajectoryRequest) *pb.EnvConfig {
	if request != nil && request.Config != nil {
		return normalizeConfig(request.Config)
	}
	return normalizeConfig(nil)
}
