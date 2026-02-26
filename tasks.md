# Custom Mahjong Game - Implementation Plan

## Phase 1: Core Definitions & Data Structures
**Goal:** Establish the universal language (Protobuf) and the foundational game logic.
- [x] Install Protocol Buffers compiler (`protoc`) and plugins for Go, Python, and TypeScript.
- [x] Define the `.proto` schemas:
  - `Tile` (Suit, Value, Honors)
  - `PlayerAction` (Draw, Discard, Pong, Chi, Kong, Riichi/Custom Declare, Win)
  - `GameState` (Wall, Discards, Player Hands, Active Turn, Winds)
- [x] Generate the target code (Go structs, TS classes, Python modules) from the `.proto` files.
  - *Implementation Notes*: Installed `protobuf` via Homebrew and `protoc-gen-go` for Go. Defined the schemas in `proto/game.proto` and successfully compiled the type-safe Go bindings to `proto/game`. Expanded definitions later to support Fenghua rules (e.g., `wild_tiles` representing 1-3 copies of a single randomly selected tile type, `flower_melds`, `seat_wind`, and context flags like `is_robbing_kong`).
  - Implement strict round phases: `Init`, `Deal`, `Turn`, `Interrupt`, `RoundEnd`.
- [x] Implement the abstract `RuleEngine` Interface:
  - Define exact methods a ruleset must provide (e.g., `EvaluateHand`, `GetValidActions`, `CalculateScore`, `ResolveInterruptPriority`).
- [x] Implement the Base Game Loop.
  - Deck initialization, shuffling, turn transitions, action queuing (handling simultaneous network calls for a discard).
  - *Implementation Notes*: Created the `core.Game` struct in `core/game.go`, handling asynchronous Discard->Interrupt mapping using a 3-second wait queue. The abstract `RuleEngine` interface is cleanly defined in `core/rules.go`.
- [x] Implement the first "Plugin": The custom Hometown Ruleset struct that satisfies the `RuleEngine` interface.
  - *Implementation Notes*: Used a recursive Depth-First Search / DP backtracking algorithm to scan tile sets for Pongs and Chows, evaluating standard hands and unique Fenghua patterns (Seven Pairs, Independence, Straight Loner).
- [x] Write Go unit tests for both the State Machine Phase transitions and the Hometown Ruleset plugin.
  - *Implementation Notes*: Created the `rules.HometownRuleset` resolving steals via predefined weights (Ron > Kong/Pong > Chow). All Go unit tests in `core` and `rules` packages pass seamlessly.


## Phase 2: Game Server & Networking (Backend)
**Goal:** Build the Go server to manage lobbies and synchronize game states.
- [x] Set up PostgreSQL schemas (Users, Leaderboards, Match History) using an ORM like `gorm`.
- [ ] Set up Redis for fast ephemeral queuing.
- [x] Implement the REST API (`/api/v1`) for JWT user registration and matching.
- [x] Implement WebSocket connection handling (`/ws/room/{uuid}`).
- [x] Create Game Lobbies/Rooms orchestration:
  - Allocate a dedicated goroutine and Mutex per active match room.
  - Ability to select which Rule Plugin the lobby uses.
  - Flag empty seats as "AI Bot" slots.
- [x] Integrate the Go Core Event Loop into the WebSocket loop:
  - Listen for `Action` Protobufs.
  - Route through the room Mutex to the Core Engine.
  - Validate action against the State Machine and active Rule Plugin.
  - Emit `StateDelta` Protobufs to all connected players or AI proxies.
- [x] Implement Game Replay logging (appending binary Protobuf streams to a file per match).

## Phase 3: The Cross-Platform Web Client (Frontend)
**Goal:** Build the playable UI that provides instant feedback using WebAssembly.
- [ ] Initialize the React / TypeScript project (e.g., using Vite).
- [ ] Setup the WebSockets client to connect to the Go Server.
- [ ] Build the Wasm optimization bridge (`mahjong.wasm`):
  - Expose Core logic functions (e.g. `wasm_IsValidAction`) directly to the TS Window context.
  - Implement predictive UI logic (if Wasm returns true, animate immediately; rollback ONLY if network validation fails).
- [ ] Build the Game UI using HTML5 Canvas (PixiJS/2D Context):
  - Setup the render loop (60FPS tile dragging and sprite rendering).
  - Render the Player's Hand, Wall, and Discard Pools.
  - Render dynamic action buttons (Pong, Chi, Win, Riichi) derived entirely from Wasm output.
- [ ] Connect the UI strictly to deserialize and act upon incoming Protobuf `StateDelta` events from WebSockets.

## Phase 4: AI & Reinforcement Learning Pipeline
**Goal:** Expose the game to PyTorch for rapid self-play training.
- [ ] Export the Go Core Engine as a C-Shared Library (`-buildmode=c-shared`).
- [ ] Create Python bindings (`ctypes` or `cffi`) to call the Go library.
- [ ] Wrap the Go library in a standard Reinforcement Learning interface (like OpenAI Gym/PettingZoo) using the active Rule Plugin.
- [ ] Set up the PyTorch environment.
- [ ] Implement a baseline heuristic bot (Random move or simple greedy matching).
- [ ] Train the RL agent via high-speed self-play simulation.
- [ ] **AI Microservice**: Build a lightweight Python serving layer (e.g., FastAPI or gRPC) that loads the trained PyTorch weights.
- [ ] Connect the AI Microservice to the Go Backend server, allowing the Go server to request live moves from the AI when an "AI Bot" is in a human lobby.

## Phase 5: Replay & Polish
- [ ] Implement a full Replay Viewer in the React frontend (loading binary Protobuf logs to replay games locally via Wasm without connecting to a server).
- [ ] Refine the database schema (Leaderboards, matchmaking rating/ELO algorithms based on rule mode).
- [ ] Deploy the Go server and React frontend (Docker / AWS / VPS).

## Core Development Workflow
To ensure the project architecture remains sound, adhere strictly to the following workflow for every task:

1. **Proto first**: If any data structures change, update `proto/game.proto` and regenerate bindings before touching Go code.
   ```bash
   protoc --go_out=. --go_opt=paths=source_relative proto/game.proto
   ```
2. **Interface before implementation**: If new ruleset capabilities are needed, update the `RuleEngine` interface in `core/rules.go` first, then implement in `rules/fh.go`.
3. **Test everything in the rules package**: Hand evaluation logic in `rules/fh.go` must have a corresponding test case in `rules/fh_test.go`.
4. **State machine is ruleset-agnostic**: `core/game.go` must never import `rules/`. All ruleset logic flows through the `RuleEngine` interface.
5. **Run tests before marking done**:
   ```bash
   go test ./...
   ```
6. **Update this file**: Mark the relevant checkbox in the phase list above when a task is completed.
