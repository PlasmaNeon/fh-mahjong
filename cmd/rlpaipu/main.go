package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"sort"

	"github.com/plasma/fh-mahjong/internal/bot"
	"github.com/plasma/fh-mahjong/internal/engine"
	"github.com/plasma/fh-mahjong/internal/rl"
	"github.com/plasma/fh-mahjong/internal/rules"
	pb "github.com/plasma/fh-mahjong/proto"
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

func generateHeuristicPaipu(matchID string, seed uint64, maxActions int) (*engine.Paipu, error) {
	game := engine.NewGame(matchID, &rules.FenghuaRuleset{}, engine.MatchOptions{})
	game.SetWallSeed(engine.SeedFromUint64(seed))
	game.Recorder = engine.NewPaipuRecorder(matchID, "fenghua")
	for seat := uint32(0); seat < 4; seat++ {
		game.Recorder.AddPlayerInfo(engine.PaipuPlayer{
			Seat:       seat,
			Name:       fmt.Sprintf("Heuristic %d", seat+1),
			Kind:       "bot",
			Difficulty: "heuristic",
		})
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

func playNextHeuristicAction(game *engine.Game, policy bot.Policy) error {
	switch game.State.Phase {
	case pb.GamePhase_PHASE_PLAYER_TURN:
		seat := game.State.ActivePlayer
		action := policy.ChooseAction(game.State, seat)
		if action == nil {
			return fmt.Errorf("heuristic returned nil turn action for seat %d", seat)
		}
		return feedTracedAction(game, seat, action)

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
			// Explicit interrupt responses (including explicit passes) are
			// real decision points and must be traced. ResolveInterrupts
			// below is engine-internal, so it never gets a row.
			return feedTracedAction(game, seat, action)
		}
		game.ResolveInterrupts()
		return nil

	default:
		return fmt.Errorf("unsupported phase %v", game.State.Phase)
	}
}

// feedTracedAction snapshots the v2 supervision trace row on the PRE-action
// state, feeds the action, and records the row only once the engine accepted
// it — the same shape as the room layer's snapshotDecision/recordDecision
// pair (internal/api/room_decisions.go). Without this, the paipu this tool
// writes carries Version 2 with an empty trace, which internal/review's
// cross-check rightly rejects as a wholesale-deleted trace.
func feedTracedAction(game *engine.Game, seat uint32, action *pb.PlayerAction) error {
	row := snapshotDecision(game, seat, action)
	if err := game.ProcessPlayerAction(seat, action); err != nil {
		return err
	}
	game.Recorder.RecordDecision(row)
	return nil
}

func snapshotDecision(game *engine.Game, seat uint32, action *pb.PlayerAction) engine.PaipuDecision {
	row := engine.PaipuDecision{Seat: seat, ChosenID: -1, Source: "heuristic"}
	legal, err := rl.LegalActions(game.State, seat)
	if err != nil {
		row.LegalIDsError = true
	} else {
		ids := make([]int, 0, len(legal))
		for id := range legal {
			ids = append(ids, id)
		}
		sort.Ints(ids)
		row.LegalIDs = ids
	}
	if id, ok := rl.EncodeAction(game.State, seat, action); ok {
		row.ChosenID = id
	} else {
		row.LegalIDsError = true
	}
	return row
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
