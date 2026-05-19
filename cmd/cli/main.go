package main

import (
	"bufio"
	"fmt"
	"os"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/plasma/fh-mahjong/bot"
	"github.com/plasma/fh-mahjong/core"
	pb "github.com/plasma/fh-mahjong/proto"
	"github.com/plasma/fh-mahjong/rules"
)

func tileName(t *pb.Tile) string {
	if t == nil {
		return "Unknown"
	}
	suits := map[pb.Suit]string{
		pb.Suit_SUIT_SOU:     "Bamboo",
		pb.Suit_SUIT_PIN:     "Dots",
		pb.Suit_SUIT_MAN:     "Characters",
		pb.Suit_SUIT_JIHAI:   "Honor",
		pb.Suit_SUIT_UNKNOWN: "Unknown",
	}

	if t.Suit == pb.Suit_SUIT_JIHAI {
		honors := map[uint32]string{
			1: "East", 2: "South", 3: "West", 4: "North",
			5: "White", 6: "Green", 7: "Red",
		}
		return honors[t.Value]
	} else if t.Suit == pb.Suit_SUIT_UNKNOWN {
		return fmt.Sprintf("Flower %d", t.Value)
	}

	return fmt.Sprintf("%d %s", t.Value, suits[t.Suit])
}

type ByValue []*pb.Tile

func (a ByValue) Len() int      { return len(a) }
func (a ByValue) Swap(i, j int) { a[i], a[j] = a[j], a[i] }
func (a ByValue) Less(i, j int) bool {
	if a[i].Suit != a[j].Suit {
		return a[i].Suit < a[j].Suit
	}
	return a[i].Value < a[j].Value
}

func printHand(closed []*pb.Tile, wilds []*pb.Tile) {
	fmt.Println("\n=== YOUR HAND ===")

	wildHashes := make(map[uint32]bool)
	if len(wilds) > 0 {
		for _, w := range wilds {
			wildHashes[uint32(w.Suit)*100+w.Value] = true
		}
	}

	sorted := make([]*pb.Tile, len(closed))
	copy(sorted, closed)
	sort.Sort(ByValue(sorted))

	for i, t := range sorted {
		isWild := wildHashes[uint32(t.Suit)*100+t.Value]
		wildStr := ""
		if isWild {
			wildStr = " [WILD]"
		}
		fmt.Printf("[%2d] %s%s\n", i, tileName(t), wildStr)
	}
	fmt.Println("=================")
}

func getRealIndex(closed []*pb.Tile, uiIdx int) int {
	sorted := make([]*pb.Tile, len(closed))
	copy(sorted, closed)
	sort.Sort(ByValue(sorted))

	if uiIdx < 0 || uiIdx >= len(sorted) {
		return -1
	}

	targetId := sorted[uiIdx].Id
	for i, t := range closed {
		if t.Id == targetId {
			return i
		}
	}
	return -1
}

func main() {
	fmt.Println("Starting Fenghua Mahjong CLI Demo...")
	game := core.NewGame("demo-1", &rules.HometownRuleset{}, core.MatchOptions{})
	botPolicy := bot.NewHeuristicPolicy()
	err := game.Start()
	if err != nil {
		fmt.Println("Error starting game:", err)
		return
	}

	reader := bufio.NewReader(os.Stdin)

	for {
		state := game.State

		if state.Phase == pb.GamePhase_PHASE_ROUND_END {
			fmt.Println("\nGame Over or Round Ended!")
			fmt.Println("Scores:")
			for i := 0; i < 4; i++ {
				fmt.Printf("Player %d: %d\n", i, state.Players[i].Score)
			}
			break
		}

		if state.Phase == pb.GamePhase_PHASE_WAIT_DISCARDS {
			validInterrupts := game.Rules.GetValidInterrupts(state, state.ActiveDiscard, 0)

			// Let bot seats respond through the same heuristic policy used elsewhere.
			for i := uint32(1); i < 4; i++ {
				if len(state.Players[i].ValidActions) == 0 {
					continue
				}
				action := botPolicy.ChooseAction(state, i)
				if action == nil {
					action = &pb.PlayerAction{Type: pb.ActionType_ACTION_PASS}
				}
				game.ProcessPlayerAction(i, action)
			}

			if len(validInterrupts) > 0 {
				fmt.Printf("\n--- INTERRUPT OPPORTUNITY! Player %d discarded **%s** ---\n", state.ActivePlayer, tileName(state.ActiveDiscard))
				fmt.Println("Available actions (type letter and press enter):")
				for _, act := range validInterrupts {
					switch act.Type {
					case pb.ActionType_ACTION_PON:
						fmt.Println("  (p) Pong")
					case pb.ActionType_ACTION_CHII:
						fmt.Println("  (c) Chow")
					case pb.ActionType_ACTION_KAN:
						fmt.Println("  (k) Kong")
					case pb.ActionType_ACTION_RON:
						fmt.Println("  (r) Ron (Win!)")
					}
				}
				fmt.Println("  (s) Skip")
				fmt.Print("Choice: ")

				input, _ := reader.ReadString('\n')
				input = strings.TrimSpace(strings.ToLower(input))

				var actionType pb.ActionType = pb.ActionType_ACTION_PASS
				switch input {
				case "p":
					actionType = pb.ActionType_ACTION_PON
				case "c":
					actionType = pb.ActionType_ACTION_CHII
				case "k":
					actionType = pb.ActionType_ACTION_KAN
				case "r":
					actionType = pb.ActionType_ACTION_RON
				}

				// Basic interrupt dispatch
				var meldTiles []*pb.Tile
				if actionType == pb.ActionType_ACTION_PON {
					// Dummy find 2 matching tiles for pon
					matches := 0
					for _, t := range state.Players[0].ClosedHand {
						if t.Suit == state.ActiveDiscard.Suit && t.Value == state.ActiveDiscard.Value {
							meldTiles = append(meldTiles, t)
							matches++
							if matches == 2 {
								break
							}
						}
					}
				}

				game.ProcessPlayerAction(0, &pb.PlayerAction{
					Type:      actionType,
					MeldTiles: meldTiles,
				})
			} else {
				// We still need to explicitly skip since player didn't interrupt
				game.ProcessPlayerAction(0, &pb.PlayerAction{Type: pb.ActionType_ACTION_PASS})
				time.Sleep(10 * time.Millisecond)
			}

			// Resolve queue state explicitly because game engine doesn't auto-tick without Room orchestrator
			game.ResolveInterrupts()
			continue
		}

		if state.Phase == pb.GamePhase_PHASE_PLAYER_TURN {
			activeSeat := state.ActivePlayer
			if activeSeat == 0 {
				fmt.Println("\n==========================")
				fmt.Printf("YOUR TURN (Tiles Left: %d)\n", state.WallCount)

				if len(state.WildTiles) > 0 {
					fmt.Printf("Wild Indicator is %s\n", tileName(state.WildTiles[0]))
				}

				playerHand := state.Players[0].ClosedHand
				printHand(playerHand, state.WildTiles)

				// Determine valid active actions (e.g. Tsumo, Kan)
				validActions := game.Rules.GetValidActions(state, 0)
				for _, act := range validActions {
					if act.Type == pb.ActionType_ACTION_TSUMO {
						fmt.Println("\n>>> YOU CAN TSUMO! (Type 't' to win) <<<")
					} else if act.Type == pb.ActionType_ACTION_KAN {
						fmt.Println("\n>>> YOU CAN KONG! (Type 'k' to kong) <<<")
					}
				}

				for {
					fmt.Print("\nEnter index to discard (or 't'/'k'): ")
					input, _ := reader.ReadString('\n')
					input = strings.TrimSpace(strings.ToLower(input))

					if input == "t" {
						game.ProcessPlayerAction(0, &pb.PlayerAction{Type: pb.ActionType_ACTION_TSUMO})
						break
					}

					// Just simple UI index parsing
					uiIdx, err := strconv.Atoi(input)
					if err != nil {
						fmt.Println("Invalid input.")
						continue
					}

					realIdx := getRealIndex(playerHand, uiIdx)
					if realIdx == -1 {
						fmt.Println("Invalid index, try again.")
						continue
					}

					tileToDiscard := playerHand[realIdx]
					fmt.Printf("=> You discarded %s\n", tileName(tileToDiscard))

					err = game.ProcessPlayerAction(0, &pb.PlayerAction{
						Type: pb.ActionType_ACTION_DISCARD,
						Tile: tileToDiscard,
					})

					if err != nil {
						fmt.Println("Invalid move:", err)
					} else {
						break
					}
				}
			} else {
				// Bot turn
				action := botPolicy.ChooseAction(state, activeSeat)
				if action == nil {
					fmt.Printf("\n[Bot %d] No legal action found\n", activeSeat)
					break
				}

				err := game.ProcessPlayerAction(activeSeat, action)
				if err != nil {
					fmt.Println("Bot error:", err)
				} else if action.Type == pb.ActionType_ACTION_DISCARD && action.Tile != nil {
					fmt.Printf("\n[Bot %d] Discarded %s\n", activeSeat, tileName(action.Tile))
				} else {
					fmt.Printf("\n[Bot %d] Chose %s\n", activeSeat, action.Type.String())
				}
			}
		}
	}
}
