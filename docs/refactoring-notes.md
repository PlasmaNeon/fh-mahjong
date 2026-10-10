# Shared Logic — Where It Lives

Pages, packages, and scripts must not re-implement anything listed here; extend the shared home
instead.

## Go

| Shared home | Owns |
|---|---|
| `internal/tiles` | `Key`/`KeyOf` (`suit*100+value` face key), `Index34`/`Index34Of`/`FromIndex34`, `WildSet`/`CountWilds`, `CloneTile`/`CloneAction` |
| `engine.FaceIndex42` / `FaceIndex34` / `FaceIndex42FromID` | the 42-face tile space (man 0-8, pin 9-17, sou 18-26, jihai 27-33, flower 34-41) |
| `rl.SortedLegalIDs` | the paipu-v2 legal-id snapshot |
| `rl.ReadyAllPlayersForNextRound` / `IsFinalReadyBeforeNextRound` / `FinalScores` | the ROUND_END ready-ack loop |
| `rl.runSlotCommands` | env-pool / search-pool command validation, fan-out, and slot ordering |
| `remote.fetchHealthzBody` / `siblingRoute` | the `/healthz` round-trip and `/act` → sibling-route mapping |
| `remote.EffectiveRLEndpointURL` / `SameServiceEndpoint` | RL endpoint resolution and endpoint identity |
| `storage.PlacementsFromScores` | competition ranking |
| `internal/review/reviewtest` | the `/evaluate` policy stub for tests |
| `api.newTestDB` / `newTestServer` | in-memory sqlite + AutoMigrate for api tests |

Rules:

- Never re-inline `suit*100+value` or add a local `cloneTile`/`cloneAction`.
- `internal/engine` does not import `tiles`; it has no tile-key needs and stays ruleset-agnostic.
- `internal/rules/fh.go` keeps its own `tileToIndex`: it returns `0` (not `-1`) for flowers, and
  its callers index `counts[tileToIndex(t)]` unguarded. Replacing it with `tiles.Index34` would
  index `counts[-1]` and panic.
- Hand-seed derivation is a parameter of `ReadyAllPlayersForNextRound`, not unified: `internal/rl`
  uses splitmix `deriveHandSeed`, review fixtures use `baseSeed*1000+handNum`. Unifying them would
  change every recorded paipu.
- The first-legal-action fallback differs on purpose: `env_test` returns `-1` when nothing is
  legal; the pool and bench copies return `0` because they feed a step request.

Do not merge:

- `review.HTTPPolicyClient.CurrentCheckpointSha256` with the `remote` healthz helpers — different
  return shape and payload, and sharing would add a package dependency.
- `remote.actionMaskJSON` and `review.actionMaskToInts` — six obvious lines across two packages.
- The remaining bespoke `httptest` stubs (fixed probability vectors, a sha that changes between
  chunks).

## Web

| Shared home | Owns |
|---|---|
| `utils/tileModel.ts` | `TileValue`/`TileDraft`, `TILE_LIBRARY`, `suitOrder`, `formatTile`/`formatHand`, `parseHand`/`parseSingleTile`, tile counting, `makeWildTilePredicate` |
| `utils/winds.ts` | `WIND_KANJI`, `WIND_I18N_KEYS`, `windI18nKey` |
| `utils/apiJson.ts` | `readJsonBody`, `errorMessage` |
| `features/room/` | Room creation, waiting room, invitation validation, room session and intentional-leave markers |
| `table/tileId.ts` | `tileIdsEqual` |
| `table/stage/computeStageLayout.ts` → `stageStyles()` | the fixed-stage `shellStyle`/`stageStyle` |
| `theme/components/LedgerTile.tsx` | `LedgerTile`, `LedgerTileRow`, `LedgerPaletteGrid` |
| `theme/components/InputApplyRow.tsx` | the `.ldg-input-row` input + Apply row |
| `test/` | `cssContract.ts`, `renderStatic.tsx`, `memoryStorage.ts` |

`features/calc/calcHelpers.ts` and `features/shanten/shantenHelpers.ts` are thin adapters over
`tileModel.ts` that keep their own output contracts: calc uses space-separated per-tile
formatting and collects all parse errors; shanten uses compact formatting and a single error.

Do not merge:

- `features/replay/reviewUtils.ts` `JIHAI_EN`/`JIHAI_ZH` with `utils/winds.ts`: jihai tile names
  cover seven faces and use simplified 东; table décor and seat plaques use traditional 東.
  `utils/winds.test.ts` asserts the split.
- `features/calc/calcHelpers.ts` `WIND_OPTIONS` — an English-only form-option list.
- `features/shanten/Shanten.tsx`'s response parse — it falls back to `{ error: 'Request failed' }`,
  so `readJsonBody` would change the message users see.
- The i18n tool keys: only 9 are shared (`tools.*`). `apply` (应用/确认), `tilePalette` (牌库/选牌),
  and `language` (English/EN) share English text but differ in Chinese between calc and
  shanten. `i18n/I18nContext.test.ts` asserts the split.

`LedgerTile`'s `disabled` is an explicit prop, not derived from `dimmed`: shanten disables
exhausted palette tiles; calc's palette stays clickable. Passing `usedCounts` to
`LedgerPaletteGrid` switches on the shanten behaviour.

## Python (`ai/`)

| Shared home | Owns |
|---|---|
| `counterfactual_data` | Paired-trace divergence selection, action-risk arrays, counterfactual shard writing; CLI imports point inward to this library |
| `evaluate.parse_seed_windows` | seed-window expansion |
| `storage.write_json_report` | report JSON encoding |
| `storage.write_single_shard_dataset` | one-shard npz + manifest |
| `model.build_plane_scalar_encoders` | the plane/scalar observation trunk |
| `train_b2b._B2bMatchState` / `_finalize_b2b_match` / `_check_chongci_outcomes`, `ppo.masked_logprob` | B2b match-end semantics shared by both collectors |
| `ai/tests/conftest.py` | `SMALL_MODEL`, `small_model_config`, `make_observation`, `save_checkpoint` |

Rules:

- `build_plane_scalar_encoders` returns its modules loose (a NamedTuple) for callers to assign
  under their historical attribute names. Never wrap them in a container `Module`: those names
  are the `state_dict` keys of every committed checkpoint. `test_model.py` pins this.
- The divergence dataset builder's manifest block is named `"counterfactual"`, not
  `"divergence"` (`write_single_shard_dataset`'s default `metadata_key`) — readers depend on it;
  keep the key.
- Patch a name on the module that **calls** it, not the one that defines it; `train_b2b` calls
  `train_state.X` so one patch target covers both modules. See `ai/CLAUDE.md`.

## Refactoring rules

- Split a file in two commits — a pure rename, then the extraction — so `git log --follow`
  pairs both halves correctly.
- Prove a split is pure motion by reassembling the bodies and diffing against the original.
- Gate engine-touching Go changes on a seeded-paipu differential: `cmd/rlpaipu` over fixed seeds
  must stay byte-identical.
- Gate model or serving changes on `fh-mj-serving-parity --in-process` against the committed
  champion.
- Do word-boundary renames in Python: BSD `sed` has no `\b` and silently matches nothing.

## Ownership audit

| Area | Placement decision |
|---|---|
| Go `engine`, `rules`, `rl`, `review` | Keep separate: state transitions, rule evaluation, training environments, and replay reconstruction have different responsibilities. |
| Go `bot` and `bot/remote` | Keep separate: `rl` depends on `bot`, while the remote policy depends on `rl` encoders. Merging creates a cycle. |
| Go `api` and `storage` | Keep transport/auth/lifecycle in `api`; models and database migration in `storage`. File size alone does not justify new packages. |
| `cmd/server` | Process/database lifecycle in `main.go`; policy configuration in `policy_wiring.go`; subprocess management in `policy_autostart.go`. |
| Web `lobby`, `room`, `game` | Entry/matchmaking, private-table lifecycle, and live-match actions respectively. Room helpers serve both lobby and live play. |
| Web `table`, `theme`, `features/dev` | Shared board renderer, application design primitives, and fixtures/prototypes. Preview-only geometry stays in `dev` until adopted by production. |
| Web `calc` and `shanten` | Separate tools over `utils/tileModel.ts`; their formatting, validation, and disabled-state contracts differ. |
| Python `counterfactual_data` and `scripts` | Shared array/shard construction belongs in the library; CLI argument parsing delegates to it. Historical script imports remain compatible. |
| Python buffers and collectors | Object/array replay, streaming replay, process collection, and batched FFI collection represent different execution contracts; do not merge based on names. |
| Generated protobuf and build assets | Preserve generator-owned locations and stable public asset URLs; moving them requires build and server-route migration. |

This is a source/import-based structural audit, not proof that all similarly named functions
are duplicates or that every unused export has been found. Graph tools were unavailable.

## Open backlog

- Go: api handler/room boilerplate (private-table handler prelude, sentinel-error → status
  mapping, `BroadcastState`/`SendStateToClient` state prep — the broadcast half must keep
  per-seat redaction); a tile-notation parser for test hands; splitting `api/room.go`,
  `api/server.go`. Server policy wiring already lives in `cmd/server/policy_wiring.go`.
- Web: the three ad-hoc en/zh label mechanisms in `features/replay/`, the four hand-rolled
  segmented controls that duplicate `Toggle`, the `東` compass mark in three places, repeated
  tile-box size blocks; `public/Regular_shortnames/` → `public/tiles/` (needs the matching mount
  in `internal/api/server.go`). Room lifecycle code already lives in `features/room/`; the
  unreferenced browser WASM hook is removed.
- ai: shared argparse blocks for env/PPO flags, MLflow arg/run setup, the checkpoint→net loader,
  diagnostics statistics helpers, the `evaluate_duplicate_seats` near-copy, the four spawn
  rollout pools, the serving-test HTTP harness, and `tensorize` (serving path — gate with
  `fh-mj-serving-parity`).
- Python library layering: `selfplay_loop.py` still imports generation and IQL orchestration
  from `scripts/`. Moving those needs their CLI, checkpoint, and monkeypatch contracts migrated
  together; counterfactual data construction no longer has that dependency.
