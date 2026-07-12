package engine_test

import (
	"sort"
	"testing"

	"github.com/plasma/fh-mahjong/internal/engine"
	"github.com/plasma/fh-mahjong/internal/rules"
	pb "github.com/plasma/fh-mahjong/proto"
)

// startedGame deals a real seeded game so wall geometry (wangpai, wild
// indicator) is authentic, then returns it with seat 0 to act.
func startedGame(t *testing.T, seed uint64) *engine.Game {
	t.Helper()
	g := engine.NewGame("redeal-test", &rules.FenghuaRuleset{}, engine.MatchOptions{})
	g.SetWallSeed(engine.SeedFromUint64(seed))
	g.SetNextDealer(0)
	if err := g.Start(); err != nil {
		t.Fatalf("start: %v", err)
	}
	return g
}

func tileKeys(tiles []*pb.Tile) []uint32 {
	keys := make([]uint32, 0, len(tiles))
	for _, tile := range tiles {
		keys = append(keys, tile.Id)
	}
	sort.Slice(keys, func(i, j int) bool { return keys[i] < keys[j] })
	return keys
}

func handsEqual(a, b []*pb.Tile) bool {
	if len(a) != len(b) {
		return false
	}
	ka, kb := tileKeys(a), tileKeys(b)
	for i := range ka {
		if ka[i] != kb[i] {
			return false
		}
	}
	return true
}

func TestRedealUnseen_VisibleStateFixedAndPoolConserved(t *testing.T) {
	g := startedGame(t, 42)
	clone := g.CloneForBranch()

	before := clone.CloneForBranch() // snapshot
	if err := clone.RedealUnseen(0, 7); err != nil {
		t.Fatalf("redeal: %v", err)
	}

	// Acting seat's own hand identical (ids, order irrelevant but keep ids).
	if !handsEqual(before.State.Players[0].ClosedHand, clone.State.Players[0].ClosedHand) {
		t.Fatal("acting seat's hand changed")
	}
	// Opponents' hand SIZES unchanged.
	for s := 1; s < 4; s++ {
		if len(before.State.Players[s].ClosedHand) != len(clone.State.Players[s].ClosedHand) {
			t.Fatalf("seat %d hand size changed", s)
		}
	}
	// Global tile-id multiset conserved across hands+wall (nothing created/lost):
	collect := func(g2 *engine.Game) []uint32 {
		var all []*pb.Tile
		for _, p := range g2.State.Players {
			all = append(all, p.ClosedHand...)
		}
		return append(tileKeys(all), tileKeys(g2.WallTilesForTest())...)
	}
	a, b := collect(before), collect(clone)
	if len(a) != len(b) {
		t.Fatalf("tile count changed: %d vs %d", len(a), len(b))
	}
	sort.Slice(a, func(i, j int) bool { return a[i] < a[j] })
	sort.Slice(b, func(i, j int) bool { return b[i] < b[j] })
	for i := range a {
		if a[i] != b[i] {
			t.Fatal("tile multiset not conserved")
		}
	}
	// Wall geometry: wild indicator tile identity unchanged (it is visible).
	if before.WildIndicatorForTest().Id != clone.WildIndicatorForTest().Id {
		t.Fatal("wild indicator changed — it is visible and must not be redealt")
	}
	// WallCount (visible) unchanged.
	if before.State.WallCount != clone.State.WallCount {
		t.Fatal("visible wall count changed")
	}
}

func TestRedealUnseen_OpponentsDifferAcrossSeeds(t *testing.T) {
	g := startedGame(t, 42)
	a := g.CloneForBranch()
	b := g.CloneForBranch()
	if err := a.RedealUnseen(0, 1); err != nil {
		t.Fatal(err)
	}
	if err := b.RedealUnseen(0, 2); err != nil {
		t.Fatal(err)
	}
	differ := false
	for s := 1; s < 4; s++ {
		if !handsEqual(a.State.Players[s].ClosedHand, b.State.Players[s].ClosedHand) {
			differ = true
		}
	}
	if !differ {
		t.Fatal("different seeds produced identical opponent hands")
	}
}

func TestRedealUnseen_SeedDeterminism(t *testing.T) {
	g := startedGame(t, 42)
	a := g.CloneForBranch()
	b := g.CloneForBranch()
	if err := a.RedealUnseen(0, 9); err != nil {
		t.Fatal(err)
	}
	if err := b.RedealUnseen(0, 9); err != nil {
		t.Fatal(err)
	}
	for s := 1; s < 4; s++ {
		ka := tileKeys(a.State.Players[s].ClosedHand)
		kb := tileKeys(b.State.Players[s].ClosedHand)
		for i := range ka {
			if ka[i] != kb[i] {
				t.Fatalf("seat %d differs under same seed", s)
			}
		}
	}
}

// TestRedealUnseen_HaiteiWindowRonOnly guards against a redeal-time
// interrupt refresh offering Chii/Pon/Kan during a haitei window, where the
// live engine (offerInterrupts, game.go) restricts opponents to Ron only.
// A search fork can land RedealUnseen inside such a window (WAIT_DISCARDS +
// IsHaitei), and its ValidActions refresh must apply the same restriction —
// serving a redealt opponent a meld interrupt the real rules forbid would
// corrupt search results.
func TestRedealUnseen_HaiteiWindowRonOnly(t *testing.T) {
	g := startedGame(t, 42)
	base := g.CloneForBranch()

	actingSeat := uint32(0)
	discardTile := base.State.Players[actingSeat].ClosedHand[0]
	base.State.Phase = pb.GamePhase_PHASE_WAIT_DISCARDS
	base.State.ActiveDiscard = discardTile
	base.State.IsHaitei = true
	// Mark seat 1 as already holding interrupt options pre-redeal, so the
	// refresh path (len(ValidActions) > 0) recomputes for it.
	base.State.Players[1].ValidActions = []*pb.PlayerAction{{Type: pb.ActionType_ACTION_RON}}

	found := false
	for seed := uint64(0); seed < 500; seed++ {
		trial := base.CloneForBranch()
		if err := trial.RedealUnseen(actingSeat, seed); err != nil {
			t.Fatalf("redeal: %v", err)
		}
		// Recompute the raw (unfiltered) interrupt set on the post-redeal hand
		// to confirm this seed actually presents a meld opportunity — proving
		// the assertion below is meaningful (would fail without the filter).
		raw := trial.Rules.GetValidInterrupts(trial.State, discardTile, 1)
		hasMeld := false
		for _, a := range raw {
			if a.Type == pb.ActionType_ACTION_PON || a.Type == pb.ActionType_ACTION_CHII || a.Type == pb.ActionType_ACTION_KAN {
				hasMeld = true
				break
			}
		}
		if !hasMeld {
			continue
		}
		found = true
		for _, a := range trial.State.Players[1].ValidActions {
			if a.Type != pb.ActionType_ACTION_RON {
				t.Fatalf("seed %d: haitei redeal refresh offered non-Ron interrupt %v", seed, a.Type)
			}
		}
		break
	}
	if !found {
		t.Fatal("no seed within range produced a meld opportunity to exercise the haitei filter")
	}
}

// TestRedealUnseen_GainingEligibilityAdmitted guards LEAK 1: interrupt
// eligibility derives from the hidden hand, so the PRE-redeal eligibility set is
// itself hidden information. A non-acting seat whose PRE-redeal hand held no
// interrupt but whose REDEALT hand can now Pon the active discard MUST be
// admitted to the window; gating the refresh on prior non-emptiness (the
// pre-fix behaviour) would wrongly exclude it, simulating a response window
// correlated with the true hidden hands.
//
// We force the case deterministically: the redeal pool is exactly the three
// opponents' concealed hands plus the undrawn wall. By overwriting every pool
// tile in place with a copy of the active discard's Suit+Value (ids untouched, so
// the multiset stays legal), every non-acting seat's redealt hand is guaranteed
// to hold >=2 matching tiles and thus a Pon — regardless of shuffle seed. Seat 1
// starts with EMPTY pre-redeal ValidActions, so the pre-fix refresh skips it.
func TestRedealUnseen_GainingEligibilityAdmitted(t *testing.T) {
	g := startedGame(t, 42)
	base := g.CloneForBranch()

	actingSeat := uint32(0)
	base.State.ActivePlayer = actingSeat
	discard := &pb.Tile{Id: 7777, Suit: pb.Suit_SUIT_MAN, Value: 3}
	base.State.Phase = pb.GamePhase_PHASE_WAIT_DISCARDS
	base.State.ActiveDiscard = discard
	base.State.IsHaitei = false

	// Force the redeal pool (opponents' hands + undrawn wall) to be entirely
	// copies of the discard's Suit+Value, in place. tileKeys/ids are preserved so
	// the conservation invariant holds; only Suit/Value are rewritten.
	for s := 1; s < 4; s++ {
		for _, tile := range base.State.Players[s].ClosedHand {
			tile.Suit, tile.Value = discard.Suit, discard.Value
		}
	}
	for _, tile := range base.WallTilesForTest() { // pointers into the live wall
		tile.Suit, tile.Value = discard.Suit, discard.Value
	}

	// Seat 1 holds NO interrupt options pre-redeal: the pre-fix refresh path
	// (len(ValidActions) > 0) therefore skips it entirely and leaves it empty.
	base.State.Players[1].ValidActions = nil

	if err := base.RedealUnseen(actingSeat, 1); err != nil {
		t.Fatalf("redeal: %v", err)
	}

	// Premise check: the redealt hand genuinely presents a Pon (proves the
	// assertion below is meaningful, not vacuously satisfied by some other path).
	raw := base.Rules.GetValidInterrupts(base.State, discard, 1)
	hasPon := false
	for _, a := range raw {
		if a.Type == pb.ActionType_ACTION_PON {
			hasPon = true
			break
		}
	}
	if !hasPon {
		t.Fatalf("test premise broken: redealt seat 1 hand cannot Pon the discard")
	}

	// The refresh must ADMIT seat 1 to the window despite its empty pre-redeal
	// options. Pre-fix this stays nil (skipped) and the test fails.
	if len(base.State.Players[1].ValidActions) == 0 {
		t.Fatal("seat 1 gained a Pon on redeal but was excluded from the window — pre-redeal eligibility leaked")
	}
	for _, a := range base.State.Players[1].ValidActions {
		if a.Type != pb.ActionType_ACTION_RON && a.Type != pb.ActionType_ACTION_PON && a.Type != pb.ActionType_ACTION_KAN {
			t.Fatalf("unexpected refreshed interrupt type %v", a.Type)
		}
	}
}

func TestRedealUnseen_RejectsBadSeat(t *testing.T) {
	g := startedGame(t, 42)
	if err := g.CloneForBranch().RedealUnseen(4, 1); err == nil {
		t.Fatal("expected error for seat 4")
	}
}

// TestRedealUnseen_DiscarderExcludedFromOpenWindow pins FINDING P2. The
// open-window ValidActions refresh previously skipped only the SEARCH ROOT
// (actingSeat). When the root is NOT the discarder, the ACTIVE DISCARDER is a
// non-acting seat and gets a freshly computed interrupt against its OWN discard.
// The live engine never offers the discarder (offerInterrupts always clears it),
// and handleInterruptAction counts every non-empty ValidActions toward window
// completeness — so a discarder with phantom ValidActions inflates the expected
// response count into a window the live engine can never reach. The refresh must
// mirror offerInterrupts: clear the discarder.
//
// We root the search on seat 2 (so the discarder, seat 0, is a NON-acting seat
// the loop visits) and force the redeal pool homogeneous to the discard's
// Suit+Value, so seat 0's redealt hand would present a Pon on its own discard.
func TestRedealUnseen_DiscarderExcludedFromOpenWindow(t *testing.T) {
	g := startedGame(t, 42)
	base := g.CloneForBranch()

	const actingSeat = uint32(2) // search root — NOT the discarder
	const discarder = uint32(0)  // ActivePlayer
	base.State.ActivePlayer = discarder
	discard := &pb.Tile{Id: 6666, Suit: pb.Suit_SUIT_MAN, Value: 3}
	base.State.Phase = pb.GamePhase_PHASE_WAIT_DISCARDS
	base.State.ActiveDiscard = discard
	base.State.IsHaitei = false

	// Force the redeal pool (non-acting seats 0,1,3 + undrawn wall) homogeneous to
	// the discard's Suit+Value, in place (ids preserved → multiset stays legal).
	// After redeal the discarder's hand is all matching tiles → it WOULD Pon its
	// own discard if the refresh recomputed it.
	for _, s := range []uint32{0, 1, 3} {
		for _, tile := range base.State.Players[s].ClosedHand {
			tile.Suit, tile.Value = discard.Suit, discard.Value
		}
	}
	for _, tile := range base.WallTilesForTest() {
		tile.Suit, tile.Value = discard.Suit, discard.Value
	}

	if err := base.RedealUnseen(actingSeat, 1); err != nil {
		t.Fatalf("redeal: %v", err)
	}

	// Premise: the discarder's REDEALT hand genuinely presents a Pon, so a
	// recompute would have populated its ValidActions — the assertion below is not
	// vacuously satisfied.
	raw := base.Rules.GetValidInterrupts(base.State, discard, discarder)
	hasPon := false
	for _, a := range raw {
		if a.Type == pb.ActionType_ACTION_PON {
			hasPon = true
			break
		}
	}
	if !hasPon {
		t.Fatalf("test premise broken: redealt discarder hand cannot Pon the discard")
	}

	// The fix: the discarder is excluded from the window and its ValidActions
	// cleared, even though its redealt hand matches its own discard. Pre-fix this
	// is non-empty (the discarder was refreshed like any other non-acting seat).
	if len(base.State.Players[discarder].ValidActions) != 0 {
		t.Fatalf("discarder (seat %d) got %d ValidActions against its own discard — it must be excluded from the window",
			discarder, len(base.State.Players[discarder].ValidActions))
	}

	// Sanity: an ordinary non-acting, non-discarder seat is STILL admitted, so the
	// exclusion is specific to the discarder, not a blanket clear.
	if len(base.State.Players[1].ValidActions) == 0 {
		t.Fatal("non-discarder seat 1 gained a Pon on redeal but was not admitted — refresh over-cleared")
	}
}
