# Duplication-Removal Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the duplicated tile-encoding / clone logic that is copy-pasted across the Go packages and the two React tile-editor helper files, consolidating each into one shared module — with zero behavior change.

**Architecture:** Introduce one new Go leaf package `tiles` (imports only `proto`) that owns the canonical tile-type key (`suit*100+value`), the 0–33 standard-tile index and its inverse, and the lightweight `*pb.Tile` / `*pb.PlayerAction` deep-clone helpers. Every Go consumer (`rules`, `rules/shanten`, `api`, `bot`, `rlenv`, `cmd/cli`) is migrated to it and its local copies deleted. On the frontend, introduce `web/src/utils/tileModel.ts` that owns the shared tile value-model + format/sort/parse primitives, and rewrite `calcHelpers.ts` and `shantenHelpers.ts` to be thin adapters over it (preserving their exact public APIs and output strings).

**Tech Stack:** Go 1.25 (`google.golang.org/protobuf`), React 19 + TypeScript + Vite 7, Vitest 2 for frontend unit tests.

## Global Constraints

- **Behavior-preserving only.** This is a pure refactor. No output, score, observation, or API response may change. Existing tests are the safety net and must stay green; do not edit existing test expectations.
- **`core/game.go` must NEVER import `rules/`.** The new `tiles` package imports **only** `github.com/plasma/fh-mahjong/proto` so any package may depend on it without creating cycles. Do not make `core` depend on `tiles` (it has no need).
- **Module path:** `github.com/plasma/fh-mahjong`, Go `1.25.0`.
- **No proto regeneration.** `proto/game.proto` is untouched; do not run `protoc`/`pbjs`.
- **Run `go test ./...` after any Go logic change; `cd web && npm test` (vitest) after any frontend change.**
- **Frequent commits** — one commit per task as specified.
- Canonical tile-type key is exactly `uint32(suit)*100 + value`. The canonical 0–33 index is man `0–8`, pin `9–17`, sou `18–26`, jihai `27–33`; flowers/unknown map to `-1`.

---

## File Structure

**Created**
- `tiles/tiles.go` — the shared Go encoding/clone package (`Key`, `KeyOf`, `Index34`, `Index34Of`, `FromIndex34`, `CloneTile`, `CloneAction`).
- `tiles/tiles_test.go` — unit tests for the package.
- `tiles/AGENTS.md` — per-directory doc (project convention).
- `web/src/utils/tileModel.ts` — shared frontend tile value-model + format/sort/parse primitives.
- `web/src/utils/tileModel.test.ts` — Vitest unit tests for the shared module.
- `docs/refactoring-notes.md` — context doc mapping every removed duplicate to its new home.

**Modified**
- `rules/shanten/shanten.go`, `rules/shanten/analysis.go` — delete `tileToIndex`, `tileHash`, `indexToTile`; route through `tiles`.
- `rules/fh.go` — replace 8 inline `suit*100+value` key sites.
- `api/shanten.go` — delete `tileToShantenIndex`, `shantenIndexToTile`; route through `tiles`.
- `bot/heuristic.go` — delete `tileTypeHash`, `cloneTile`, `cloneAction`; route through `tiles`.
- `rlenv/action.go`, `rlenv/observation.go` — delete `cloneTile`, `cloneAction`, `tileTypeKey`; route through `tiles`.
- `cmd/cli/main.go` — replace 2 inline key sites.
- `web/src/pages/shantenHelpers.ts`, `web/src/pages/calcHelpers.ts` — re-implement on top of `tileModel.ts`.
- AGENTS.md files: `rules/shanten/AGENTS.md`, `api/AGENTS.md`, `bot/AGENTS.md`, `rlenv/AGENTS.md`, `web/src/utils/AGENTS.md`, root `AGENTS.md`.

---

## Phase 1 — Go shared `tiles` package

### Task 1: Create the `tiles` package

**Files:**
- Create: `tiles/tiles.go`
- Test: `tiles/tiles_test.go`

**Interfaces:**
- Consumes: `github.com/plasma/fh-mahjong/proto` (`pb.Tile`, `pb.PlayerAction`, `pb.Suit`).
- Produces (every later Phase-1 task depends on these exact signatures):
  - `func Key(t *pb.Tile) uint32` — `suit*100+value`; `nil` → `0`.
  - `func KeyOf(suit pb.Suit, value uint32) uint32`
  - `func Index34(t *pb.Tile) int` — 0–33; flowers/`nil` → `-1`.
  - `func Index34Of(suit pb.Suit, value uint32) int`
  - `func FromIndex34(idx int) (pb.Suit, uint32)` — inverse of `Index34Of`.
  - `func CloneTile(t *pb.Tile) *pb.Tile` — `nil` → `nil`.
  - `func CloneAction(a *pb.PlayerAction) *pb.PlayerAction` — `nil` → `nil`; deep-copies `Tile` and `MeldTiles`.

- [ ] **Step 1: Confirm baseline is green**

Run: `go build ./... && go test ./...`
Expected: PASS (records the pre-refactor baseline; if anything already fails, stop and report — do not start the refactor on a red tree).

- [ ] **Step 2: Write the failing test**

Create `tiles/tiles_test.go`:

```go
package tiles

import (
	"testing"

	pb "github.com/plasma/fh-mahjong/proto"
)

func tile(suit pb.Suit, value uint32, id uint32) *pb.Tile {
	return &pb.Tile{Id: id, Suit: suit, Value: value}
}

func TestKey(t *testing.T) {
	if got := KeyOf(pb.Suit_SUIT_PIN, 5); got != uint32(pb.Suit_SUIT_PIN)*100+5 {
		t.Fatalf("KeyOf = %d", got)
	}
	if got := Key(tile(pb.Suit_SUIT_PIN, 5, 42)); got != KeyOf(pb.Suit_SUIT_PIN, 5) {
		t.Fatalf("Key ignores id mismatch: %d", got)
	}
	if got := Key(nil); got != 0 {
		t.Fatalf("Key(nil) = %d, want 0", got)
	}
}

func TestIndex34RoundTrip(t *testing.T) {
	cases := []struct {
		suit  pb.Suit
		value uint32
		idx   int
	}{
		{pb.Suit_SUIT_MAN, 1, 0},
		{pb.Suit_SUIT_MAN, 9, 8},
		{pb.Suit_SUIT_PIN, 1, 9},
		{pb.Suit_SUIT_SOU, 1, 18},
		{pb.Suit_SUIT_JIHAI, 1, 27},
		{pb.Suit_SUIT_JIHAI, 7, 33},
	}
	for _, c := range cases {
		if got := Index34Of(c.suit, c.value); got != c.idx {
			t.Fatalf("Index34Of(%v,%d) = %d, want %d", c.suit, c.value, got, c.idx)
		}
		gotSuit, gotValue := FromIndex34(c.idx)
		if gotSuit != c.suit || gotValue != c.value {
			t.Fatalf("FromIndex34(%d) = (%v,%d), want (%v,%d)", c.idx, gotSuit, gotValue, c.suit, c.value)
		}
	}
	if got := Index34(tile(pb.Suit_SUIT_FLOWER, 3, 137)); got != -1 {
		t.Fatalf("Index34(flower) = %d, want -1", got)
	}
	if got := Index34(nil); got != -1 {
		t.Fatalf("Index34(nil) = %d, want -1", got)
	}
}

func TestCloneTile(t *testing.T) {
	src := tile(pb.Suit_SUIT_SOU, 4, 99)
	dst := CloneTile(src)
	if dst == src {
		t.Fatal("CloneTile returned same pointer")
	}
	if dst.Id != src.Id || dst.Suit != src.Suit || dst.Value != src.Value {
		t.Fatalf("CloneTile mismatch: %+v", dst)
	}
	if CloneTile(nil) != nil {
		t.Fatal("CloneTile(nil) != nil")
	}
}

func TestCloneActionDeepCopiesTiles(t *testing.T) {
	src := &pb.PlayerAction{
		Type:           pb.ActionType_ACTION_KAN,
		Tile:           tile(pb.Suit_SUIT_MAN, 2, 1),
		TargetPlayer:   3,
		IsRobbingKong:  true,
		IsBottomTile:   true,
		IsBloomingKong: true,
		MeldTiles:      []*pb.Tile{tile(pb.Suit_SUIT_MAN, 2, 2), tile(pb.Suit_SUIT_MAN, 2, 3)},
	}
	dst := CloneAction(src)
	if dst == src || dst.Tile == src.Tile || &dst.MeldTiles[0] == &src.MeldTiles[0] {
		t.Fatal("CloneAction shares memory with source")
	}
	dst.MeldTiles[0].Value = 9
	if src.MeldTiles[0].Value != 2 {
		t.Fatal("CloneAction mutated source meld tile")
	}
	if dst.Type != src.Type || dst.TargetPlayer != src.TargetPlayer ||
		!dst.IsRobbingKong || !dst.IsBottomTile || !dst.IsBloomingKong {
		t.Fatalf("CloneAction scalar mismatch: %+v", dst)
	}
	if CloneAction(nil) != nil {
		t.Fatal("CloneAction(nil) != nil")
	}
}
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `go test ./tiles/...`
Expected: FAIL — build error, `undefined: KeyOf` / `undefined: Key` etc. (package has no implementation yet).

- [ ] **Step 4: Write the implementation**

Create `tiles/tiles.go`:

```go
// Package tiles holds the canonical tile encodings shared across the engine:
// the per-tile-type key (suit*100+value, ignoring tile id), the 0-33
// standard-tile index used by the shanten/scoring code, and lightweight
// deep-clone helpers for proto Tile/PlayerAction values used on the bot and
// RL hot paths. It imports only the proto package so every other package may
// depend on it without import cycles.
package tiles

import pb "github.com/plasma/fh-mahjong/proto"

// KeyOf returns the canonical per-tile-type key, suit*100+value. It uniquely
// identifies a tile face (ignoring the physical tile id) and matches the
// hashing used by the shanten, scoring and bot code.
func KeyOf(suit pb.Suit, value uint32) uint32 {
	return uint32(suit)*100 + value
}

// Key returns KeyOf(t.Suit, t.Value); a nil tile yields 0.
func Key(t *pb.Tile) uint32 {
	if t == nil {
		return 0
	}
	return KeyOf(t.Suit, t.Value)
}

// Index34Of maps a standard man/pin/sou/jihai tile to its 0-33 index, or -1
// for flowers and unknown suits.
func Index34Of(suit pb.Suit, value uint32) int {
	v := int(value) - 1
	switch suit {
	case pb.Suit_SUIT_MAN:
		return v
	case pb.Suit_SUIT_PIN:
		return 9 + v
	case pb.Suit_SUIT_SOU:
		return 18 + v
	case pb.Suit_SUIT_JIHAI:
		return 27 + v
	}
	return -1
}

// Index34 returns Index34Of(t.Suit, t.Value); a nil tile yields -1.
func Index34(t *pb.Tile) int {
	if t == nil {
		return -1
	}
	return Index34Of(t.Suit, t.Value)
}

// FromIndex34 is the inverse of Index34Of for indices 0-33.
func FromIndex34(idx int) (pb.Suit, uint32) {
	switch {
	case idx < 9:
		return pb.Suit_SUIT_MAN, uint32(idx + 1)
	case idx < 18:
		return pb.Suit_SUIT_PIN, uint32(idx - 9 + 1)
	case idx < 27:
		return pb.Suit_SUIT_SOU, uint32(idx - 18 + 1)
	default:
		return pb.Suit_SUIT_JIHAI, uint32(idx - 27 + 1)
	}
}

// CloneTile returns a deep copy of t (id/suit/value); nil yields nil.
func CloneTile(t *pb.Tile) *pb.Tile {
	if t == nil {
		return nil
	}
	return &pb.Tile{Id: t.Id, Suit: t.Suit, Value: t.Value}
}

// CloneAction returns a deep copy of a, including its Tile and MeldTiles;
// nil yields nil.
func CloneAction(a *pb.PlayerAction) *pb.PlayerAction {
	if a == nil {
		return nil
	}
	out := &pb.PlayerAction{
		Type:           a.Type,
		Tile:           CloneTile(a.Tile),
		TargetPlayer:   a.TargetPlayer,
		IsRobbingKong:  a.IsRobbingKong,
		IsBottomTile:   a.IsBottomTile,
		IsBloomingKong: a.IsBloomingKong,
	}
	if len(a.MeldTiles) > 0 {
		out.MeldTiles = make([]*pb.Tile, len(a.MeldTiles))
		for i, tile := range a.MeldTiles {
			out.MeldTiles[i] = CloneTile(tile)
		}
	}
	return out
}
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `go test ./tiles/...`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tiles/tiles.go tiles/tiles_test.go
git commit -m "refactor(tiles): add shared tile key/index/clone package"
```

---

### Task 2: Migrate `rules/shanten` onto `tiles`

**Files:**
- Modify: `rules/shanten/shanten.go` (delete `tileToIndex` at lines ~231–249; inline keys at lines ~256, ~262)
- Modify: `rules/shanten/analysis.go` (delete `tileHash` ~238–240 and `indexToTile` ~242–252; call sites at lines ~105, ~115, ~137, ~164, ~170, ~176, ~194, ~195)

**Interfaces:**
- Consumes: `tiles.Key`, `tiles.KeyOf`, `tiles.Index34`, `tiles.FromIndex34` from Task 1.
- Produces: no signature changes — `Calculate`, `CalculateFromTiles`, `AnalyzeHand` etc. keep their current public signatures.

- [ ] **Step 1: Record baseline for the package**

Run: `go test ./rules/shanten/...`
Expected: PASS (this suite is the characterization net for this task).

- [ ] **Step 2: Add the import to both files**

In `rules/shanten/shanten.go` and `rules/shanten/analysis.go`, add to the import block:

```go
"github.com/plasma/fh-mahjong/tiles"
```

- [ ] **Step 3: Replace the local helpers in `shanten.go`**

Delete the entire `tileToIndex` function (the `// tileToIndex converts ...` comment through its closing brace).

Replace the wild-set / count inline keys. The current code reads:

```go
		wildSet[uint32(w.Suit)*100+w.Value] = true
```
```go
		h := uint32(t.Suit)*100 + t.Value
```

Change them to:

```go
		wildSet[tiles.KeyOf(w.Suit, w.Value)] = true
```
```go
		h := tiles.KeyOf(t.Suit, t.Value)
```

And change the one remaining `tileToIndex` call:

```go
			idx := tileToIndex(t)
```
to
```go
			idx := tiles.Index34(t)
```

- [ ] **Step 4: Replace the local helpers in `analysis.go`**

Delete the `tileHash` and `indexToTile` functions entirely. Then:

- Replace every `tileHash(` call with `tiles.KeyOf(` (lines ~105, ~164, ~170, ~195). The arguments are already `(suit, value)` pairs, so only the function name changes.
- Replace every `tileToIndex(` call with `tiles.Index34(` (lines ~115, ~137, ~176).
- Replace `indexToTile(idx)` with `tiles.FromIndex34(idx)` (line ~194).

- [ ] **Step 5: Build and run the package tests**

Run: `go build ./rules/shanten/... && go test ./rules/shanten/...`
Expected: PASS, unchanged from Step 1. (If `go vet` flags an unused import, the deletions were incomplete — re-check.)

- [ ] **Step 6: Commit**

```bash
git add rules/shanten/shanten.go rules/shanten/analysis.go
git commit -m "refactor(shanten): use shared tiles package for key/index"
```

---

### Task 3: Migrate `rules/fh.go` key sites

**Files:**
- Modify: `rules/fh.go` (8 inline key sites: lines ~84, ~93, ~100, ~511, ~875, ~990, ~1022, ~1041, ~1132)

**Interfaces:**
- Consumes: `tiles.KeyOf`.
- Produces: no signature changes to `FenghuaRuleset`.

- [ ] **Step 1: Record baseline**

Run: `go test ./rules/...`
Expected: PASS (the `fh_test.go` scoring suite guards this task).

- [ ] **Step 2: Add the import**

In `rules/fh.go` import block add:

```go
"github.com/plasma/fh-mahjong/tiles"
```

- [ ] **Step 3: Replace the inline key expressions**

There are three distinct right-hand-side strings. Apply each as an exact text replacement (the `t.`-form occurs multiple times — replace all):

| Find | Replace |
|------|---------|
| `uint32(w.Suit)*100 + w.Value` | `tiles.KeyOf(w.Suit, w.Value)` |
| `uint32(t.Suit)*100 + t.Value` | `tiles.KeyOf(t.Suit, t.Value)` |
| `uint32(winTile.Suit)*100 + winTile.Value` | `tiles.KeyOf(winTile.Suit, winTile.Value)` |

After replacement, confirm none remain:

Run: `grep -n 'Suit)\*100' rules/fh.go`
Expected: no output.

- [ ] **Step 4: Build and test**

Run: `go build ./rules/... && go test ./rules/...`
Expected: PASS, unchanged from Step 1.

- [ ] **Step 5: Commit**

```bash
git add rules/fh.go
git commit -m "refactor(rules): use tiles.KeyOf for tile-type keys"
```

---

### Task 4: Migrate `api/shanten.go`

**Files:**
- Modify: `api/shanten.go` (delete `tileToShantenIndex` ~182–195 and `shantenIndexToTile` ~197–208; key sites ~58, ~65, ~82, ~163; index sites ~69, ~86, ~162)

**Interfaces:**
- Consumes: `tiles.KeyOf`, `tiles.Index34Of`, `tiles.FromIndex34`. Use the `*Of` variants because `CalcTileInput` (and the drawn-tile value) are plain `(Suit, Value)` structs, not `*pb.Tile`.
- Produces: no change to the `/api/v1/shanten` response shape.

- [ ] **Step 1: Record baseline**

Run: `go test ./api/...`
Expected: PASS.

- [ ] **Step 2: Add the import**

In `api/shanten.go` import block add:

```go
"github.com/plasma/fh-mahjong/tiles"
```

- [ ] **Step 3: Replace key sites**

Apply these exact replacements:

| Find | Replace |
|------|---------|
| `wildSet[uint32(req.WildTile.Suit)*100+req.WildTile.Value] = true` | `wildSet[tiles.KeyOf(req.WildTile.Suit, req.WildTile.Value)] = true` |
| `h := uint32(t.Suit)*100 + t.Value` | `h := tiles.KeyOf(t.Suit, t.Value)` |
| `h := uint32(drawn.Suit)*100 + drawn.Value` | `h := tiles.KeyOf(drawn.Suit, drawn.Value)` |
| `h := uint32(suit)*100 + value` | `h := tiles.KeyOf(suit, value)` |

- [ ] **Step 4: Replace index sites and delete the local index helpers**

Apply these exact replacements:

| Find | Replace |
|------|---------|
| `idx := tileToShantenIndex(t.Suit, t.Value)` | `idx := tiles.Index34Of(t.Suit, t.Value)` |
| `idx := tileToShantenIndex(drawn.Suit, drawn.Value)` | `idx := tiles.Index34Of(drawn.Suit, drawn.Value)` |
| `suit, value := shantenIndexToTile(idx)` | `suit, value := tiles.FromIndex34(idx)` |

Then delete the now-unused `func tileToShantenIndex(...)` and `func shantenIndexToTile(...)` definitions in their entirety.

- [ ] **Step 5: Build and test**

Run: `go build ./api/... && go test ./api/...`
Expected: PASS, unchanged from Step 1.

- [ ] **Step 6: Commit**

```bash
git add api/shanten.go
git commit -m "refactor(api): use shared tiles package in shanten handler"
```

---

### Task 5: Migrate `bot/heuristic.go`

**Files:**
- Modify: `bot/heuristic.go` (delete `tileTypeHash` ~433–435, `cloneTile` ~470–480, `cloneAction` ~446–468; call sites for hash at ~336, ~354–357, ~386, ~389, ~428 and clone at ~76, ~85, ~111, ~146, ~440, ~459, ~464)

**Interfaces:**
- Consumes: `tiles.KeyOf`, `tiles.CloneTile`, `tiles.CloneAction`.
- Produces: `HeuristicPolicy.ChooseAction` and all helper signatures unchanged. `tileTypeCounts` stays (it is bot-specific) but now calls `tiles.KeyOf` internally.

- [ ] **Step 1: Record baseline**

Run: `go test ./bot/...`
Expected: PASS (`heuristic_test.go` guards this task).

- [ ] **Step 2: Add the import**

In `bot/heuristic.go` import block add (keep the existing `"sort"` and `rules/shanten` imports — both are still used):

```go
"github.com/plasma/fh-mahjong/tiles"
```

- [ ] **Step 3: Replace call sites**

Apply these exact replacements (all occurrences):

| Find | Replace |
|------|---------|
| `tileTypeHash(` | `tiles.KeyOf(` |
| `cloneAction(` | `tiles.CloneAction(` |
| `cloneTile(` | `tiles.CloneTile(` |

- [ ] **Step 4: Delete the local helper definitions**

Delete `func tileTypeHash(...)`, `func cloneAction(...)`, and `func cloneTile(...)` in their entirety. Keep `tileTypeCounts` (its body now reads `counts[tiles.KeyOf(tile.Suit, tile.Value)]++`), `firstActionOfType` (now returns `tiles.CloneAction(action)`), `compareKanAction`, and `compareActionTiles`.

- [ ] **Step 5: Build and test**

Run: `go build ./bot/... && go test ./bot/...`
Expected: PASS, unchanged from Step 1.

- [ ] **Step 6: Commit**

```bash
git add bot/heuristic.go
git commit -m "refactor(bot): use shared tiles package for key/clone"
```

---

### Task 6: Migrate `rlenv`

**Files:**
- Modify: `rlenv/action.go` (delete `cloneTile` ~334–342 and `cloneAction` ~313–332; call sites ~89, ~130, ~186)
- Modify: `rlenv/observation.go` (delete `tileTypeKey` ~676–681; call sites ~506, ~511)

**Interfaces:**
- Consumes: `tiles.Key`, `tiles.CloneTile`, `tiles.CloneAction`.
- Produces: `EncodeObservation`, `DecodeActionID`, `actionMask`, etc. unchanged. Keep `firstTile`, `sortedTilesByID`, `hasActionType`, `tileFaceIndex42`, `tileFaceIndex34` (these are rlenv-specific — the 42-plane index is not part of the shared package).

- [ ] **Step 1: Record baseline**

Run: `go test ./rlenv/...`
Expected: PASS.

- [ ] **Step 2: Migrate `rlenv/action.go`**

Add `"github.com/plasma/fh-mahjong/tiles"` to the import block (keep `"fmt"` and `"sort"`). Then apply (all occurrences):

| Find | Replace |
|------|---------|
| `cloneAction(` | `tiles.CloneAction(` |
| `cloneTile(` | `tiles.CloneTile(` |

Then delete the local `func cloneAction(...)` and `func cloneTile(...)` definitions.

- [ ] **Step 3: Migrate `rlenv/observation.go`**

Add `"github.com/plasma/fh-mahjong/tiles"` to the import block. Replace the two call sites:

```go
		wildSet[tileTypeKey(tile)] = true
```
```go
		if wildSet[tileTypeKey(tile)] {
```
with
```go
		wildSet[tiles.Key(tile)] = true
```
```go
		if wildSet[tiles.Key(tile)] {
```

Then delete the local `func tileTypeKey(...)` definition. (`tiles.Key` is nil-safe, matching the old `tileTypeKey` behavior of returning 0 for a nil tile.)

- [ ] **Step 4: Build and test**

Run: `go build ./rlenv/... && go test ./rlenv/...`
Expected: PASS, unchanged from Step 1.

- [ ] **Step 5: Commit**

```bash
git add rlenv/action.go rlenv/observation.go
git commit -m "refactor(rlenv): use shared tiles package for key/clone"
```

---

### Task 7: Migrate `cmd/cli`, sweep, and verify the whole module

**Files:**
- Modify: `cmd/cli/main.go` (key sites ~60, ~69)
- Modify: `rules/shanten/AGENTS.md`, `api/AGENTS.md`, `bot/AGENTS.md`, `rlenv/AGENTS.md`

**Interfaces:**
- Consumes: `tiles.KeyOf`.

- [ ] **Step 1: Migrate `cmd/cli/main.go`**

Add `"github.com/plasma/fh-mahjong/tiles"` to the import block, then:

| Find | Replace |
|------|---------|
| `wildHashes[uint32(w.Suit)*100+w.Value] = true` | `wildHashes[tiles.KeyOf(w.Suit, w.Value)] = true` |
| `isWild := wildHashes[uint32(t.Suit)*100+t.Value]` | `isWild := wildHashes[tiles.KeyOf(t.Suit, t.Value)]` |

- [ ] **Step 2: Confirm no inline key/index duplicates remain outside `tiles`**

Run: `grep -rn 'Suit)\*100' --include='*.go' . | grep -v '/tiles/'`
Expected: no output. (Any hit is a missed site — migrate it the same way.)

- [ ] **Step 3: Full-module build, vet, and test**

Run: `go build ./... && go vet ./... 2>&1 | grep -v 'cmd/wasm' ; go test ./...`
Expected: build clean; `go test ./...` PASS. (The `cmd/wasm` `go vet` line about `syscall/js` build constraints is pre-existing and unrelated — it is filtered out above.)

- [ ] **Step 4: Update the touched AGENTS.md files**

In each of `rules/shanten/AGENTS.md`, `api/AGENTS.md`, `bot/AGENTS.md`, `rlenv/AGENTS.md`, add a one-line note under the relevant section, e.g.:

```markdown
- Tile-type keys, the 0-33 index, and proto Tile/Action deep-clones come from the shared `tiles` package (`github.com/plasma/fh-mahjong/tiles`) — do not re-inline `suit*100+value` or re-add local `cloneTile`/`cloneAction`.
```

- [ ] **Step 5: Commit**

```bash
git add cmd/cli/main.go rules/shanten/AGENTS.md api/AGENTS.md bot/AGENTS.md rlenv/AGENTS.md
git commit -m "refactor(cli): finish tiles migration and document shared package"
```

---

## Phase 2 — Frontend shared tile model

### Task 8: Create `web/src/utils/tileModel.ts`

**Files:**
- Create: `web/src/utils/tileModel.ts`
- Test: `web/src/utils/tileModel.test.ts`

**Interfaces:**
- Consumes: `Suit` from `../proto/game.ts`.
- Produces (Tasks 9 & 10 depend on these exact names):
  - types `TileValue { suit: Suit; value: number }`, `TileDraft extends TileValue { id: string }`
  - `buildSuitTiles(suit, maxValue)`, `TILE_LIBRARY`
  - `suitOrder(suit)`, `suitChar(suit)`, `charToSuit(char)`, `maxValueForSuit(suit)`, `isValueValidForSuit(suit, value)`, `isSuitedTile(suit)`
  - `sameTileValue(a, b)`, `compareBySuitValue(a, b)`, `sortBySuitValue<T extends TileValue>(tiles)`
  - `formatTile(tile)`, `formatHand(tiles, options?)` with `FormatHandOptions { separator?: string; perTile?: boolean }`
  - `parseHand(input, messages, collectAll)`, `parseSingleTile(input, messages)` with `ParseMessages` and `ParseResult { tiles: TileValue[]; errors: string[] }`
  - `tileKey(tile)`, `countTiles(tiles)`, `remainingCount(tile, usedCounts)`

- [ ] **Step 1: Write the failing test**

Create `web/src/utils/tileModel.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { Suit } from '../proto/game.ts'
import {
  TILE_LIBRARY,
  formatTile,
  formatHand,
  parseHand,
  sortBySuitValue,
  sameTileValue,
  remainingCount,
  countTiles,
  type ParseMessages,
} from './tileModel'

const messages: ParseMessages = {
  notation: 'bad',
  unknownSuit: (ch) => `Unknown suit: ${ch}`,
  outOfRange: (d, ch) => `Tile ${d}${ch} out of range`,
}

describe('tileModel', () => {
  it('builds the 34-tile library', () => {
    expect(TILE_LIBRARY).toHaveLength(34)
    expect(TILE_LIBRARY[0]).toEqual({ suit: Suit.SUIT_MAN, value: 1 })
  })

  it('formats a single tile', () => {
    expect(formatTile({ suit: Suit.SUIT_PIN, value: 5 })).toBe('5p')
    expect(formatTile(null)).toBe('')
  })

  it('formats a hand compact (no separator) and per-tile (spaced)', () => {
    const hand = [
      { suit: Suit.SUIT_PIN, value: 4 },
      { suit: Suit.SUIT_MAN, value: 1 },
      { suit: Suit.SUIT_MAN, value: 2 },
    ]
    expect(formatHand(hand)).toBe('12m4p')
    expect(formatHand(hand, { separator: ' ', perTile: true })).toBe('1m2m 4p')
  })

  it('sorts man < pin < sou < jihai then by value', () => {
    const sorted = sortBySuitValue([
      { suit: Suit.SUIT_JIHAI, value: 1 },
      { suit: Suit.SUIT_MAN, value: 3 },
      { suit: Suit.SUIT_MAN, value: 1 },
    ])
    expect(sorted.map((t) => `${t.value}-${t.suit}`)).toEqual([
      `1-${Suit.SUIT_MAN}`,
      `3-${Suit.SUIT_MAN}`,
      `1-${Suit.SUIT_JIHAI}`,
    ])
  })

  it('parses valid notation', () => {
    const r = parseHand('123m4p', messages, true)
    expect(r.errors).toEqual([])
    expect(r.tiles).toHaveLength(4)
  })

  it('collectAll=false stops at first error with empty tiles', () => {
    const r = parseHand('1z9z', messages, false)
    expect(r.errors).toEqual(['Tile 9z out of range'])
    expect(r.tiles).toEqual([])
  })

  it('collectAll=true keeps valid tiles and all errors', () => {
    const r = parseHand('1z9z', messages, true)
    expect(r.tiles).toEqual([{ suit: Suit.SUIT_JIHAI, value: 1 }])
    expect(r.errors).toEqual(['Tile 9z out of range'])
  })

  it('counts tiles and computes remaining', () => {
    const used = countTiles([
      { suit: Suit.SUIT_SOU, value: 5 },
      { suit: Suit.SUIT_SOU, value: 5 },
    ])
    expect(remainingCount({ suit: Suit.SUIT_SOU, value: 5 }, used)).toBe(2)
  })

  it('sameTileValue compares by face', () => {
    expect(sameTileValue({ suit: Suit.SUIT_MAN, value: 1 }, { suit: Suit.SUIT_MAN, value: 1 })).toBe(true)
    expect(sameTileValue({ suit: Suit.SUIT_MAN, value: 1 }, null)).toBe(false)
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd web && npx vitest run src/utils/tileModel.test.ts`
Expected: FAIL — cannot resolve `./tileModel`.

- [ ] **Step 3: Write the implementation**

Create `web/src/utils/tileModel.ts`:

```ts
import { Suit } from '../proto/game.ts'

export interface TileValue {
  suit: Suit
  value: number
}

export interface TileDraft extends TileValue {
  id: string
}

export function buildSuitTiles(suit: Suit, maxValue: number): TileValue[] {
  const tiles: TileValue[] = []
  for (let value = 1; value <= maxValue; value += 1) {
    tiles.push({ suit, value })
  }
  return tiles
}

export const TILE_LIBRARY: TileValue[] = [
  ...buildSuitTiles(Suit.SUIT_MAN, 9),
  ...buildSuitTiles(Suit.SUIT_PIN, 9),
  ...buildSuitTiles(Suit.SUIT_SOU, 9),
  ...buildSuitTiles(Suit.SUIT_JIHAI, 7),
]

export function suitOrder(suit: Suit): number {
  switch (suit) {
    case Suit.SUIT_MAN: return 0
    case Suit.SUIT_PIN: return 1
    case Suit.SUIT_SOU: return 2
    case Suit.SUIT_JIHAI: return 3
    default: return 9
  }
}

export function suitChar(suit: Suit): string {
  switch (suit) {
    case Suit.SUIT_MAN: return 'm'
    case Suit.SUIT_PIN: return 'p'
    case Suit.SUIT_SOU: return 's'
    case Suit.SUIT_JIHAI: return 'z'
    default: return '?'
  }
}

export function charToSuit(char: string): Suit | null {
  switch (char) {
    case 'm': return Suit.SUIT_MAN
    case 'p': return Suit.SUIT_PIN
    case 's': return Suit.SUIT_SOU
    case 'z': return Suit.SUIT_JIHAI
    default: return null
  }
}

export function maxValueForSuit(suit: Suit): number {
  return suit === Suit.SUIT_JIHAI ? 7 : 9
}

export function isValueValidForSuit(suit: Suit, value: number): boolean {
  return value >= 1 && value <= maxValueForSuit(suit)
}

export function isSuitedTile(
  suit: Suit | undefined,
): suit is Suit.SUIT_MAN | Suit.SUIT_PIN | Suit.SUIT_SOU {
  return suit === Suit.SUIT_MAN || suit === Suit.SUIT_PIN || suit === Suit.SUIT_SOU
}

export function sameTileValue(a: TileValue | null, b: TileValue | null): boolean {
  return Boolean(a && b && a.suit === b.suit && a.value === b.value)
}

export function compareBySuitValue(a: TileValue, b: TileValue): number {
  const ao = suitOrder(a.suit)
  const bo = suitOrder(b.suit)
  return ao !== bo ? ao - bo : a.value - b.value
}

export function sortBySuitValue<T extends TileValue>(tiles: T[]): T[] {
  return [...tiles].sort(compareBySuitValue)
}

// Returns '' for non-standard suits (man/pin/sou/jihai only are renderable here).
export function formatTile(tile: TileValue | null): string {
  if (!tile) return ''
  const ch = suitChar(tile.suit)
  return ch === '?' ? '' : `${tile.value}${ch}`
}

export interface FormatHandOptions {
  separator?: string
  perTile?: boolean
}

// perTile=false yields compact groups ("123m"); perTile=true repeats the suit
// per tile ("1m2m3m"). Groups are joined by `separator`.
export function formatHand(tiles: TileValue[], options: FormatHandOptions = {}): string {
  const { separator = '', perTile = false } = options
  if (tiles.length === 0) return ''
  const sorted = sortBySuitValue(tiles)
  const groups: string[] = []
  let currentSuit: Suit | null = null
  let currentGroup = ''
  for (const tile of sorted) {
    if (currentSuit !== null && tile.suit !== currentSuit) {
      groups.push(perTile ? currentGroup : `${currentGroup}${suitChar(currentSuit)}`)
      currentGroup = ''
    }
    currentGroup += perTile ? formatTile(tile) : String(tile.value)
    currentSuit = tile.suit
  }
  if (currentGroup && currentSuit !== null) {
    groups.push(perTile ? currentGroup : `${currentGroup}${suitChar(currentSuit)}`)
  }
  return groups.join(separator)
}

export interface ParseMessages {
  notation: string
  unknownSuit: (rawChar: string) => string
  outOfRange: (digit: string, rawChar: string) => string
}

export interface ParseResult {
  tiles: TileValue[]
  errors: string[]
}

// Parses compact notation like "123m4p". With collectAll=false it returns on
// the first error with empty tiles; with collectAll=true it keeps valid tiles
// and accumulates every error. Message strings are supplied by the caller so
// each page keeps its exact wording.
export function parseHand(input: string, messages: ParseMessages, collectAll: boolean): ParseResult {
  const compact = input.trim().replace(/\s+/g, '')
  if (!compact) return { tiles: [], errors: [] }

  const matches = [...compact.matchAll(/([0-9]+)([mpsz])/gi)]
  const consumed = matches.map((m) => m[0]).join('')
  if (consumed !== compact) {
    return { tiles: [], errors: [messages.notation] }
  }

  const tiles: TileValue[] = []
  const errors: string[] = []
  for (const match of matches) {
    const digits = match[1]
    const rawChar = match[2]
    const suit = charToSuit(rawChar.toLowerCase())
    if (suit === null) {
      errors.push(messages.unknownSuit(rawChar))
      if (!collectAll) return { tiles: [], errors }
      continue
    }
    for (const d of digits) {
      const v = Number(d)
      if (!isValueValidForSuit(suit, v)) {
        errors.push(messages.outOfRange(d, rawChar))
        if (!collectAll) return { tiles: [], errors }
        continue
      }
      tiles.push({ suit, value: v })
    }
  }
  return { tiles, errors }
}

export function parseSingleTile(
  input: string,
  messages: ParseMessages,
): { tile: TileValue | null; errors: string[] } {
  const trimmed = input.trim()
  if (!trimmed) return { tile: null, errors: [] }
  const parsed = parseHand(trimmed, messages, true)
  if (parsed.errors.length > 0) return { tile: null, errors: parsed.errors }
  if (parsed.tiles.length !== 1) return { tile: null, errors: [] }
  return { tile: parsed.tiles[0], errors: [] }
}

export function tileKey(tile: TileValue): string {
  return `${tile.suit}-${tile.value}`
}

export function countTiles(tiles: TileValue[]): Map<string, number> {
  const counts = new Map<string, number>()
  for (const t of tiles) {
    const k = tileKey(t)
    counts.set(k, (counts.get(k) ?? 0) + 1)
  }
  return counts
}

export function remainingCount(tile: TileValue, usedCounts: Map<string, number>): number {
  return 4 - (usedCounts.get(tileKey(tile)) ?? 0)
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd web && npx vitest run src/utils/tileModel.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/utils/tileModel.ts web/src/utils/tileModel.test.ts
git commit -m "feat(web): add shared tileModel for calc/shanten helpers"
```

---

### Task 9: Re-implement `shantenHelpers.ts` on `tileModel`

**Files:**
- Modify: `web/src/pages/shantenHelpers.ts`

**Interfaces:**
- Consumes: everything exported from `../utils/tileModel`.
- Produces: **unchanged public API** — `TileValue`, `TileDraft`, `UsefulTileInfo`, `DiscardOption`, `ShantenResult`, `TILE_LIBRARY`, `createDraft`, `sameTile`, `sortHand`, `formatTile`, `formatHand`, `parseHand`, `parseSingleTile`, `tileKey`, `countTiles`, `remainingCount`, `encodeUrlState`, `decodeUrlState`. `Shanten.tsx` must not need any edit.

- [ ] **Step 1: Record the frontend baseline**

Run: `cd web && npm test`
Expected: PASS (existing suites: `rejoinMatch`, `handOrdering`, `meldOrdering`, plus `tileModel` from Task 8).

- [ ] **Step 2: Rewrite the file as an adapter**

Replace the whole contents of `web/src/pages/shantenHelpers.ts` with:

```ts
import {
  TILE_LIBRARY as SHARED_TILE_LIBRARY,
  formatHand as sharedFormatHand,
  formatTile as sharedFormatTile,
  parseHand as sharedParseHand,
  sameTileValue,
  sortBySuitValue,
  countTiles as sharedCountTiles,
  remainingCount as sharedRemainingCount,
  tileKey as sharedTileKey,
  type ParseMessages,
  type TileValue as SharedTileValue,
  type TileDraft as SharedTileDraft,
} from '../utils/tileModel'

export type TileValue = SharedTileValue
export type TileDraft = SharedTileDraft

export interface UsefulTileInfo {
  suit: SharedTileValue['suit']
  value: number
  remaining: number
}

export interface DiscardOption {
  discard: TileValue
  shanten: number
  usefulTiles: UsefulTileInfo[]
  totalUseful: number
}

export interface ShantenResult {
  shanten: number
  drawnTile?: TileValue | null
  discardOptions: DiscardOption[]
}

export const TILE_LIBRARY: TileValue[] = SHARED_TILE_LIBRARY

const messages: ParseMessages = {
  notation: 'Use notation like 123m456p789s1z',
  unknownSuit: (ch) => `Unknown suit: ${ch}`,
  outOfRange: (digit, ch) => `Tile ${digit}${ch} is out of range`,
}

let nextId = 1

export function createDraft(tile: TileValue): TileDraft {
  return { ...tile, id: `st-${nextId++}` }
}

export function sameTile(a: TileValue | null, b: TileValue | null): boolean {
  return sameTileValue(a, b)
}

export function sortHand(tiles: TileDraft[]): TileDraft[] {
  return sortBySuitValue(tiles)
}

export function formatTile(tile: TileValue): string {
  return sharedFormatTile(tile)
}

export function formatHand(tiles: TileValue[]): string {
  return sharedFormatHand(tiles)
}

export function parseHand(input: string): { tiles: TileValue[]; error: string | null } {
  const { tiles, errors } = sharedParseHand(input, messages, false)
  return { tiles, error: errors.length > 0 ? errors[0] : null }
}

export function parseSingleTile(input: string): { tile: TileValue | null; error: string | null } {
  const { tiles, error } = parseHand(input)
  if (error) return { tile: null, error }
  if (tiles.length !== 1) return { tile: null, error: 'Enter exactly one tile (e.g. 3z)' }
  return { tile: tiles[0], error: null }
}

export function tileKey(tile: TileValue): string {
  return sharedTileKey(tile)
}

export function countTiles(tiles: TileValue[]): Map<string, number> {
  return sharedCountTiles(tiles)
}

export function remainingCount(tile: TileValue, usedCounts: Map<string, number>): number {
  return sharedRemainingCount(tile, usedCounts)
}

export function encodeUrlState(hand: TileValue[], wildTile: TileValue | null, openMelds: number): string {
  const params = new URLSearchParams()
  if (hand.length > 0) params.set('q', formatHand(hand))
  if (wildTile) params.set('w', formatTile(wildTile))
  if (openMelds > 0) params.set('m', String(openMelds))
  return params.toString()
}

export function decodeUrlState(search: string): {
  hand: TileValue[]
  wildTile: TileValue | null
  openMelds: number
} {
  const params = new URLSearchParams(search)
  const q = params.get('q')
  const w = params.get('w')
  const m = params.get('m')

  let hand: TileValue[] = []
  if (q) {
    const parsed = parseHand(q)
    if (!parsed.error) hand = parsed.tiles
  }

  let wildTile: TileValue | null = null
  if (w) {
    const parsed = parseSingleTile(w)
    if (!parsed.error && parsed.tile) wildTile = parsed.tile
  }

  const openMelds = m ? Math.min(4, Math.max(0, parseInt(m, 10) || 0)) : 0

  return { hand, wildTile, openMelds }
}
```

> Note: `parseSingleTile` here keeps the original "exactly one tile" message and single-error contract, so it wraps the local `parseHand` rather than the shared `parseSingleTile`. That shared export is intentionally not imported in this file.

- [ ] **Step 3: Type-check and test**

Run: `cd web && npx tsc --noEmit && npm test`
Expected: PASS, and `Shanten.tsx` compiles unchanged.

- [ ] **Step 4: Commit**

```bash
git add web/src/pages/shantenHelpers.ts
git commit -m "refactor(web): build shantenHelpers on shared tileModel"
```

---

### Task 10: Re-implement `calcHelpers.ts` tile primitives on `tileModel`

**Files:**
- Modify: `web/src/pages/calcHelpers.ts`
- Modify: `web/src/utils/AGENTS.md`

**Interfaces:**
- Consumes: `tileModel` primitives.
- Produces: **unchanged public API.** Only the tile value-model internals are swapped. `CalcTileValue`/`CalcTileDraft` become aliases of the shared types; `TILE_LIBRARY`, `sortTiles`, `sameTileValue`, `formatTile`, `formatTehai`, `parseTehaiInput`, `parseSingleTileInput` are re-expressed via the shared module. All meld/kong/validation/normalization exports stay exactly as they are. `Calc.tsx` must not need any edit.

- [ ] **Step 1: Swap the type aliases and `TILE_LIBRARY`**

At the top of `calcHelpers.ts`, change the import line and the two interface declarations. Replace:

```ts
import { ActionType, MeldDirection, Suit } from '../proto/game.ts'

export interface CalcTileValue {
  suit: Suit
  value: number
}

export interface CalcTileDraft extends CalcTileValue {
  id: string
}
```

with:

```ts
import { ActionType, MeldDirection, Suit } from '../proto/game.ts'
import {
  TILE_LIBRARY as SHARED_TILE_LIBRARY,
  formatHand as sharedFormatHand,
  formatTile as sharedFormatTile,
  parseHand as sharedParseHand,
  sameTileValue as sharedSameTileValue,
  sortBySuitValue,
  isSuitedTile as sharedIsSuitedTile,
  type ParseMessages,
  type TileValue as SharedTileValue,
  type TileDraft as SharedTileDraft,
} from '../utils/tileModel'

export type CalcTileValue = SharedTileValue
export type CalcTileDraft = SharedTileDraft
```

- [ ] **Step 2: Replace `TILE_LIBRARY` and `buildSuitTiles`**

Replace the existing `TILE_LIBRARY` definition (the `export const TILE_LIBRARY: CalcTileValue[] = [ ... ]` block) with:

```ts
export const TILE_LIBRARY: CalcTileValue[] = SHARED_TILE_LIBRARY
```

Delete the local `function buildSuitTiles(...)` (now provided by the shared module). Leave `WIND_OPTIONS`, `FLOWER_OPTIONS`, `DEFAULT_KONG_FLAGS`, and the `nextTileDraftId`/`nextMeldDraftId` counters in place.

- [ ] **Step 3: Re-express the tile primitives**

Replace the bodies of `sameTileValue`, `sortTiles`, `formatTile`, `formatTehai`, `parseTehaiInput`, `parseSingleTileInput` as follows (keep their exported signatures byte-for-byte):

```ts
export function sameTileValue(left: CalcTileDraft | CalcTileValue | null, right: CalcTileDraft | CalcTileValue | null): boolean {
  return sharedSameTileValue(left, right)
}

export function sortTiles(tiles: CalcTileDraft[]): CalcTileDraft[] {
  return sortBySuitValue(tiles)
}

export function formatTile(tile: CalcTileValue | CalcTileDraft | null): string {
  return sharedFormatTile(tile)
}

export function formatTehai(tiles: Array<CalcTileDraft | CalcTileValue>): string {
  return sharedFormatHand(tiles, { separator: ' ', perTile: true })
}

const calcParseMessages: ParseMessages = {
  notation: 'Use canonical tile notation like 1m2m3m 4p5p6p 7z.',
  unknownSuit: (ch) => `Unknown suit: ${ch.toLowerCase()}`,
  outOfRange: (digit, ch) => `Tile ${digit}${ch.toLowerCase()} is out of range.`,
}

export function parseTehaiInput(input: string): { tiles: CalcTileValue[]; errors: string[] } {
  return sharedParseHand(input, calcParseMessages, true)
}

export function parseSingleTileInput(input: string): { tile: CalcTileValue | null; errors: string[] } {
  const trimmed = input.trim()
  if (!trimmed) {
    return { tile: null, errors: [] }
  }
  const parsed = parseTehaiInput(trimmed)
  if (parsed.errors.length > 0) {
    return { tile: null, errors: parsed.errors }
  }
  if (parsed.tiles.length !== 1) {
    return { tile: null, errors: ['Enter exactly one tile, like 3z or 9s.'] }
  }
  return { tile: parsed.tiles[0], errors: [] }
}
```

- [ ] **Step 4: Remove now-dead local helpers**

Delete the now-unused local `function suitSortOrder(...)`, `function charToSuit(...)`, `function isValueValidForSuit(...)` (near lines 518–553). For `isSuitedTile`: delete the local `function isSuitedTile(...)` and add, alongside the other re-exports, a thin wrapper so `validateMeldShape` keeps working:

```ts
function isSuitedTile(suit: Suit | undefined): suit is Suit.SUIT_MAN | Suit.SUIT_PIN | Suit.SUIT_SOU {
  return sharedIsSuitedTile(suit)
}
```

> Caution: only delete a local helper after confirming no other code in the file still calls it. Run `grep -n 'suitSortOrder\|charToSuit\|isValueValidForSuit' web/src/pages/calcHelpers.ts` — every remaining reference must be inside a function you have already rewritten, otherwise keep the helper.

- [ ] **Step 5: Type-check, test, and build**

Run: `cd web && npx tsc --noEmit && npm test && npm run build`
Expected: PASS. `Calc.tsx` and `Shanten.tsx` compile unchanged; the production build succeeds.

- [ ] **Step 6: Update `web/src/utils/AGENTS.md`**

Add a bullet documenting the new module, e.g.:

```markdown
- **tileModel.ts** — shared tile value-model + format/sort/parse primitives. `pages/calcHelpers.ts` and `pages/shantenHelpers.ts` are thin adapters over it; do not re-implement `TILE_LIBRARY`, tile parsing, or suit ordering in page helpers.
```

- [ ] **Step 7: Commit**

```bash
git add web/src/pages/calcHelpers.ts web/src/utils/AGENTS.md
git commit -m "refactor(web): build calcHelpers tile primitives on shared tileModel"
```

---

## Phase 3 — Context documentation

### Task 11: Write the refactoring context doc

**Files:**
- Create: `docs/refactoring-notes.md`
- Modify: root `AGENTS.md`

**Interfaces:** none (documentation only).

- [ ] **Step 1: Write `docs/refactoring-notes.md`**

Create the file capturing the dedup map so future work doesn't re-introduce the duplication:

```markdown
# Refactoring Notes — Duplication Removal (2026-06-27)

## Go: `tiles` package (`github.com/plasma/fh-mahjong/tiles`)

A leaf package (imports only `proto`) that owns:
- `Key` / `KeyOf` — canonical tile-type key `suit*100+value`.
- `Index34` / `Index34Of` / `FromIndex34` — 0-33 standard-tile index + inverse.
- `CloneTile` / `CloneAction` — lightweight proto deep-clones.

Replaced these previously-duplicated definitions:
| Removed | Was in |
|---------|--------|
| `tileToIndex`, inline `*100+value` | `rules/shanten/shanten.go` |
| `tileHash`, `indexToTile` | `rules/shanten/analysis.go` |
| 8 inline `*100+value` sites | `rules/fh.go` |
| `tileToShantenIndex`, `shantenIndexToTile`, inline keys | `api/shanten.go` |
| `tileTypeHash`, `cloneTile`, `cloneAction` | `bot/heuristic.go` |
| `cloneTile`, `cloneAction`, `tileTypeKey` | `rlenv/action.go`, `rlenv/observation.go` |
| 2 inline `*100+value` sites | `cmd/cli/main.go` |

Rule: never re-inline `suit*100+value` or re-add a local `cloneTile`/`cloneAction`; use `tiles`.
Note: the 42-plane index (`tileFaceIndex42`) stays in `rlenv` — it is observation-specific, not shared.
`core/` deliberately does NOT depend on `tiles` (it has no tile-key needs and must stay ruleset-agnostic).

## Frontend: `web/src/utils/tileModel.ts`

Owns the shared tile value-model (`TileValue`/`TileDraft`), `TILE_LIBRARY`, suit
ordering, `formatTile`/`formatHand`, `parseHand`/`parseSingleTile`, and tile
counting. `pages/calcHelpers.ts` and `pages/shantenHelpers.ts` are now thin
adapters that preserve their exact public APIs and output strings (calc uses
space-separated/per-tile formatting and collects all parse errors; shanten uses
compact formatting and a single-error contract).

Rule: page helpers must not re-implement tile parsing/formatting/sorting — extend `tileModel.ts`.
```

- [ ] **Step 2: Add a pointer in root `AGENTS.md`**

Add one line under the docs/reference section of the root `AGENTS.md`:

```markdown
- `docs/refactoring-notes.md` — shared `tiles` (Go) and `tileModel.ts` (web) modules; where the de-duplicated tile-key/index/clone logic now lives.
```

- [ ] **Step 3: Final whole-repo verification**

Run: `go build ./... && go test ./... && cd web && npm test && npx tsc --noEmit`
Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add docs/refactoring-notes.md AGENTS.md
git commit -m "docs: record tile dedup refactor context"
```

---

## Self-Review

**Spec coverage** (request was: "find which parts can be removed or refactored; extract duplicate code to a module to reduce complexity"):
- Go tile-key duplication (~20 inline sites + 4 named helpers) → `tiles` package (Tasks 1–7). ✅
- Go clone duplication (`cloneTile`/`cloneAction` ×2 packages) → `tiles.CloneTile`/`CloneAction` (Tasks 1, 5, 6). ✅
- Go index-conversion duplication (`tileToIndex`/`tileToShantenIndex`/`indexToTile`/`shantenIndexToTile`) → `tiles.Index34*`/`FromIndex34` (Tasks 1, 2, 4). ✅
- Frontend duplication (`calcHelpers.ts` ≈ `shantenHelpers.ts`) → `tileModel.ts` (Tasks 8–10). ✅
- "Removed": the local helper definitions are deleted in each migration task; net line count drops. ✅
- Context docs (per the user's request to add context md files) → Task 11 + AGENTS.md updates throughout. ✅
- **Out of scope by decision:** large-file splits (`core/game.go`, `api/room.go`, `Calc.tsx`) — user chose "safe dedup only". The unused WASM path (`cmd/wasm` + `useMahjongWasm` + 7.9 MB asset) — user chose "keep as-is"; left untouched.

**Type consistency:** Go consumers use `KeyOf`/`Index34Of` where the source is a `(Suit, Value)` struct (`api/shanten.go`, `cmd/cli`) and `Key`/`Index34` where the source is `*pb.Tile`; both variants are defined in Task 1. Frontend `CalcTileValue`/`CalcTileDraft` are aliased to the shared `TileValue`/`TileDraft`, so existing `Calc.tsx`/`Shanten.tsx` references stay valid. `formatHand`/`parseHand` option and message shapes are defined once (Task 8) and consumed with matching arguments (Tasks 9, 10).

**Placeholder scan:** no "TBD"/"handle edge cases"/"similar to Task N" — every code step shows the literal code or an explicit find→replace table.
