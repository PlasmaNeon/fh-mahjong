# proto/

> `game.proto`, the single source of truth for every structure shared by Go, TypeScript, and
> Python, plus the generated Go bindings (`game.pb.go`, never hand-edited).

## game.proto

- **Core:** `Suit` (SOU=1, PIN=2, MAN=3, JIHAI=4, FLOWER=5), `Tile {id, suit, value, is_red}`,
  `ActionType` (DRAW … REFUSE_HAITEI), `GamePhase` (INIT, DEAL, PLAYER_TURN, WAIT_DISCARDS,
  ROUND_END, terminal MATCH_END), `Meld`, `PlayerAction`.
- **State:** `GameState` (incl. dice, wangpai size, live `wangpai_tiles_left`), `PlayerState`
  (incl. `last_discard_from_drawn`, the public tsumogiri flag).
- **Results:** `ScoreEntry`, `PlayerPayout`, `RoundResult`, and the compact `RoundOutcome` used
  by RL (its `breakdown` carries the winner's score entries).
- **Match modes and tables:** `MatchMode`, `ChongciConfig`, `PlayerStanding`, `MatchEndResult`,
  `Difficulty`, `SeatConfig`, `PrivateTableState`.
- **RL bridge:** `EnvConfig` (`match_mode`, `chongci_config`, `event_history_window`,
  `oracle_observation`, `lookahead_version`), `SeatObservation`, `EnvReset*`, `EnvStep*`,
  `BranchEvaluation*`, `RouteProbe*`, `Trajectory*`, the env pool (`EnvPoolNewRequest`,
  `SlotCommand`, `EnvPoolStep*`, `SlotState`), and `SearchPoolNewRequest` (clones, seed, rollout
  cap, determinizations, diagnostic options, optional `root_seat`).

## Rules

- Field changes start here; regenerate all three bindings before touching code.
- Tile id `0` is a real tile. Any optional tile id or seat must be proto3 `optional` so unset
  decodes as null (seat 0 ≠ absent).
- Enum names (`ACTION_CHII`/`PON`/`KAN`) stay as generated; use chii/pon/kan in prose.
- Paipu JSON embeds raw enum ints; renumbering one requires bumping
  `engine.ProtoEnumsRevision`.

## Regeneration

```bash
# Go
protoc --plugin=protoc-gen-go=$(go env GOPATH)/bin/protoc-gen-go --go_out=. --go_opt=paths=source_relative proto/game.proto
# TypeScript (--null-semantics is required)
web/node_modules/.bin/pbjs -t static-module -w es6 --null-semantics -o web/src/proto/game.js proto/game.proto
web/node_modules/.bin/pbts -o web/src/proto/game.d.ts web/src/proto/game.js
# Python
protoc --python_out=ai/src/fh_mahjong_ai/generated proto/game.proto
```

The Python runtime is the protobuf 6.x line, so `game_pb2.py` must be major-6 gencode. A
standalone protoc 35.x emits 7.x gencode (incompatible); use protoc **33.5**
(`protoc-33.5/bin/protoc --python_out=ai/src/fh_mahjong_ai/generated --proto_path=. proto/game.proto`).
`grpcio-tools` ≤ 1.80 (protoc 31.1) also works but churns the version header.
