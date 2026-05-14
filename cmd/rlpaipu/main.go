package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"path/filepath"

	"github.com/plasma/fh-mahjong/bot"
	"github.com/plasma/fh-mahjong/core"
	pb "github.com/plasma/fh-mahjong/proto"
	"github.com/plasma/fh-mahjong/rules"
)

func main() {
	matchID := flag.String("match-id", "rl-seed-1", "match id used by /replay/:matchId")
	seed := flag.Uint64("seed", 1, "deterministic wall seed")
	output := flag.String("output", filepath.Join("testdata", "paipu", "rl-seed-1.json"), "output paipu JSON path")
	maxActions := flag.Int("max-actions", 512, "maximum heuristic actions before failing")
	flag.Parse()

	paipu, err := generateHeuristicPaipu(*matchID, *seed, *maxActions)
	if err != nil {
		fmt.Fprintf(os.Stderr, "generate paipu: %v\n", err)
		os.Exit(1)
	}

	payload, err := json.MarshalIndent(paipu, "", "  ")
	if err != nil {
		fmt.Fprintf(os.Stderr, "marshal paipu: %v\n", err)
		os.Exit(1)
	}

	if err := os.MkdirAll(filepath.Dir(*output), 0o755); err != nil {
		fmt.Fprintf(os.Stderr, "create output dir: %v\n", err)
		os.Exit(1)
	}
	if err := os.WriteFile(*output, append(payload, '\n'), 0o644); err != nil {
		fmt.Fprintf(os.Stderr, "write paipu: %v\n", err)
		os.Exit(1)
	}

	fmt.Printf("wrote %s\n", *output)
	fmt.Printf("open http://localhost:3000/replay/%s\n", *matchID)
}

func generateHeuristicPaipu(matchID string, seed uint64, maxActions int) (*core.Paipu, error) {
	game := core.NewGame(matchID, &rules.HometownRuleset{})
	game.SetWallSeed(core.SeedFromUint64(seed))
	game.Recorder = core.NewPaipuRecorder(matchID, "hometown")
	for seat := uint32(0); seat < 4; seat++ {
		game.Recorder.AddPlayer(seat, fmt.Sprintf("Heuristic %d", seat+1), 0)
	}

	if err := game.Start(); err != nil {
		return nil, err
	}

	policy := bot.NewHeuristicPolicy()
	for actionCount := 0; actionCount < maxActions; actionCount++ {
		if game.State.Phase == pb.GamePhase_PHASE_ROUND_END {
			return game.Recorder.Finalize(finalScores(game.State)), nil
		}

		if err := playNextHeuristicAction(game, policy); err != nil {
			return nil, err
		}
	}

	return nil, fmt.Errorf("round did not finish within %d actions", maxActions)
}

func playNextHeuristicAction(game *core.Game, policy bot.Policy) error {
	switch game.State.Phase {
	case pb.GamePhase_PHASE_PLAYER_TURN:
		seat := game.State.ActivePlayer
		action := policy.ChooseAction(game.State, seat)
		if action == nil {
			return fmt.Errorf("heuristic returned nil turn action for seat %d", seat)
		}
		return game.ProcessPlayerAction(seat, action)

	case pb.GamePhase_PHASE_WAIT_DISCARDS:
		for seat := uint32(0); seat < uint32(len(game.State.Players)); seat++ {
			if seat == game.State.ActivePlayer {
				continue
			}
			player := game.State.Players[seat]
			if len(player.ValidActions) == 0 || game.InterruptQueued(seat) {
				continue
			}
			action := policy.ChooseAction(game.State, seat)
			if action == nil {
				return fmt.Errorf("heuristic returned nil interrupt action for seat %d", seat)
			}
			return game.ProcessPlayerAction(seat, action)
		}
		game.ResolveInterrupts()
		return nil

	default:
		return fmt.Errorf("unsupported phase %v", game.State.Phase)
	}
}

func finalScores(state *pb.GameState) [4]int32 {
	var scores [4]int32
	if state == nil {
		return scores
	}
	for seat := 0; seat < len(scores) && seat < len(state.Players); seat++ {
		scores[seat] = state.Players[seat].Score
	}
	return scores
}
