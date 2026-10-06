package review

import (
	"encoding/json"
	"fmt"
	"sort"

	"github.com/plasma/fh-mahjong/internal/engine"
	"github.com/plasma/fh-mahjong/internal/rl"
	pb "github.com/plasma/fh-mahjong/proto"
)

const MaxImportBytes = 10 << 20

// validWildTile checks a recorded wild tile. A standard wild is a real tile
// whose id must match its face. Flower wilds are built by face — the other
// three flowers of the indicator's group — so the engine records them without
// an id; a recorder that sets one must use that flower's own id.
func validWildTile(w engine.PaipuTile) bool {
	if w.Suit == pb.Suit_SUIT_FLOWER {
		return w.Value >= 1 && w.Value <= 8 && (w.ID == 0 || w.ID == 135+w.Value)
	}
	s, v := engine.TileFromId(w.ID)
	return w.ID < 144 && s == w.Suit && v == w.Value
}

// ValidateImport validates the JSON envelope before any model work. Seed/deal,
// trace and action legality are additionally verified by ExtractDecisions.
func ValidateImport(data []byte) (*engine.Paipu, error) {
	if len(data) > MaxImportBytes {
		return nil, fmt.Errorf("paipu exceeds 10 MiB")
	}
	var p engine.Paipu
	if err := json.Unmarshal(data, &p); err != nil {
		return nil, fmt.Errorf("invalid paipu JSON: %w", err)
	}
	if p.Version != 1 && p.Version != 2 {
		return nil, fmt.Errorf("supported paipu versions are 1 and 2")
	}
	if p.Ruleset != "fenghua" && p.Ruleset != "hometown" {
		return nil, fmt.Errorf("this reviewer requires a Fenghua paipu")
	}
	if len(p.Players) != 4 {
		return nil, fmt.Errorf("paipu must have four players")
	}
	var seats [4]bool
	for _, v := range p.Players {
		if v.Seat >= 4 || seats[v.Seat] {
			return nil, fmt.Errorf("invalid or duplicate player seat")
		}
		seats[v.Seat] = true
	}
	if len(p.Rounds) == 0 || len(p.Rounds) > 256 {
		return nil, fmt.Errorf("paipu must have 1–256 completed rounds")
	}
	if p.Status != "" && p.Status != "completed" {
		return nil, fmt.Errorf("unfinished paipu cannot be analyzed")
	}
	if p.MatchMode != "" && p.MatchMode != "classic" && p.MatchMode != "chongci" {
		return nil, fmt.Errorf("unsupported match mode")
	}
	if p.ActionCatalogVersion != 0 && p.ActionCatalogVersion != rl.ActionCatalogVersion {
		return nil, fmt.Errorf("unsupported action catalog")
	}
	if p.ProtoEnumsRevision != 0 && p.ProtoEnumsRevision != engine.ProtoEnumsRevision {
		return nil, fmt.Errorf("unsupported tile enum revision")
	}
	if p.EventContractVersion != 0 && p.EventContractVersion != rl.EventContractV1 {
		return nil, fmt.Errorf("unsupported event contract")
	}
	sort.Slice(p.Players, func(i, j int) bool { return p.Players[i].Seat < p.Players[j].Seat })
	count := 0
	tileOK := func(id int) bool { return id >= 0 && id < 144 }
	for i, r := range p.Rounds {
		if r.Dealer >= 4 || r.PrevailingWind > 4 {
			return nil, fmt.Errorf("round %d: invalid dealer/wind", i+1)
		}
		if _, err := engine.SeedFromBase64(r.WallSeed); err != nil {
			return nil, fmt.Errorf("round %d: invalid wall seed", i+1)
		}
		if r.Result == nil || (r.Result.Type != "win" && r.Result.Type != "draw") || len(r.Result.ScoreChanges) != 4 {
			return nil, fmt.Errorf("round %d: missing complete result", i+1)
		}
		if r.Result.Type == "win" && (r.Result.Winner == nil || *r.Result.Winner < 0 || *r.Result.Winner > 3) {
			return nil, fmt.Errorf("round %d: invalid winner", i+1)
		}
		for _, hand := range r.Deals {
			if len(hand) < 13 || len(hand) > 14 {
				return nil, fmt.Errorf("round %d: invalid deal size", i+1)
			}
			for _, id := range hand {
				if !tileOK(int(id)) {
					return nil, fmt.Errorf("round %d: invalid deal tile", i+1)
				}
			}
		}
		for _, w := range r.WildTiles {
			if !validWildTile(w) {
				return nil, fmt.Errorf("round %d: invalid wild tile", i+1)
			}
		}
		for _, f := range r.InitialFlowers {
			if f.Seat >= 4 || f.Flower < 136 || f.Flower >= 144 || f.Replacement >= 144 {
				return nil, fmt.Errorf("round %d: invalid initial flower", i+1)
			}
		}
		for _, a := range r.Actions {
			if a.Seat >= 4 || (a.Tile != nil && !tileOK(*a.Tile)) || (a.From != nil && (*a.From < 0 || *a.From > 3)) {
				return nil, fmt.Errorf("round %d: invalid action seat/tile", i+1)
			}
			for _, id := range a.Tiles {
				if !tileOK(int(id)) {
					return nil, fmt.Errorf("round %d: invalid meld tile", i+1)
				}
			}
			switch a.Act {
			case "draw", "discard", "flower", "ukan", "haitei":
				if a.Tile == nil {
					return nil, fmt.Errorf("round %d: missing action tile", i+1)
				}
			}
			switch a.Act {
			case "chii", "pon", "okan", "ron":
				if a.From == nil {
					return nil, fmt.Errorf("round %d: missing source seat", i+1)
				}
			}
			switch a.Act {
			case "chii", "pon":
				if len(a.Tiles) != 2 {
					return nil, fmt.Errorf("round %d: invalid meld size", i+1)
				}
			case "okan":
				if len(a.Tiles) != 3 {
					return nil, fmt.Errorf("round %d: invalid meld size", i+1)
				}
			case "ckan":
				if len(a.Tiles) != 4 {
					return nil, fmt.Errorf("round %d: invalid meld size", i+1)
				}
			}
			switch a.Act {
			case "draw", "discard", "flower", "chii", "pon", "okan", "ckan", "ukan", "ron", "tsumo", "haitei", "haiteiRefuse":
			default:
				return nil, fmt.Errorf("round %d: unsupported operation %q", i+1, a.Act)
			}
		}
		count += len(r.Actions) + len(r.Decisions)
		if count > 100000 {
			return nil, fmt.Errorf("paipu exceeds 100,000 actions/trace rows")
		}
	}
	return &p, nil
}
