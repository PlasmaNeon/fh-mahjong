package rl

import "testing"

// TestActionCatalogPinned freezes every constant of the action-ID catalog.
// Paipu v2 stores raw catalog IDs (chosenId/legalIds) pinned to
// ActionCatalogVersion; ANY change to these values silently re-labels
// historical decisions. If this test fails you MUST bump
// ActionCatalogVersion and add a translation note — never just update the
// expected numbers.
func TestActionCatalogPinned(t *testing.T) {
	if ActionCatalogVersion != 1 {
		t.Fatalf("ActionCatalogVersion = %d; version bumps require a migration note", ActionCatalogVersion)
	}
	pins := map[string][2]int{
		"ActionPass":         {ActionPass, 0},
		"ActionTsumo":        {ActionTsumo, 1},
		"ActionRon":          {ActionRon, 2},
		"ActionAcceptHaitei": {ActionAcceptHaitei, 3},
		"ActionRefuseHaitei": {ActionRefuseHaitei, 4},
		"DiscardBase":        {DiscardBase, 5},
		"DiscardCount":       {DiscardCount, 42},
		"PonBase":            {PonBase, 47},
		"PonCount":           {PonCount, 34},
		"KanDirectBase":      {KanDirectBase, 81},
		"KanClosedBase":      {KanClosedBase, 115},
		"KanUpgradedBase":    {KanUpgradedBase, 149},
		"ChiiBase":           {ChiiBase, 183},
		"ChiiCount":          {ChiiCount, 21},
		"ActionSpaceSize":    {ActionSpaceSize, 204},
	}
	for name, v := range pins {
		if v[0] != v[1] {
			t.Errorf("%s = %d, pinned %d (catalog drift without version bump)", name, v[0], v[1])
		}
	}
}
