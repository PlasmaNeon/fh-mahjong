# Technical Design Document: Custom Mahjong Game

## 1. Introduction
This document details the architecture and technology stack for a cross-platform Mahjong platform designed originally for custom "hometown" rules. The platform supports standard web-based PvP gameplay, match replays, and advanced AI training through Reinforcement Learning (RL).

## 2. Technology Stack

### 2.1 Core Game Logic Engine & Backend: Go (Golang)
**Purpose**: Go serves dual purposes in this architecture: it is the single definitive source of truth for the game rules *and* the high-concurrency WebSocket backend that orchestrates the matches.
- **Why Go**: Unifies the logic and the server, avoiding the complexity of C++ or Rust. It provides exceptional performance, easy concurrency (`goroutines`), and has strong compilation support for WebAssembly (Wasm) and C-Shared libraries.
- **Ruleset Plugin Architecture**: The core engine will be designed with a strict `RuleEngine` interface. 
  - The game loop (State Machine: `Init`, `Deal`, `PlayerTurn`, `WaitDiscards`, `RoundEnd`) is completely agnostic to *how* a hand wins or what melds are legal.
  - The `RuleEngine` interface will dictate methods such as: `IsValidChii(hand, tile)`, `IsValidPon(hand, tile)`, `GetWinningScore(hand, tableState)`, and `GetAvailableActions(hand, tableState)`.
  - Specific rulesets (e.g., "Hometown Rules", "Standard Riichi", "Sichuan Bloody Rules") will be implemented as discrete structs satisfying the `RuleEngine` interface.
  - This allows the server to load different ruleset "plugins" dynamically per lobby (e.g. `NewGame(RiichiPlugin)`) without altering the core game state machine.
- **Backend Architecture**:
  - **REST API (`/api/v1`)**: Handles stateless requests—User registration (JWT Auth), fetching Match History, viewing Leaderboards, and retrieving Replay files.
  - **WebSocket Server (`/ws`)**: Upgrades the connection. Each `Lobby` spawns a dedicated goroutine. The loop listens for `ClientEvent` Protobufs (actions), locks the GameState mutex, applies the action to the state machine, and broadcasts an `UpdateEvent` Protobuf to the 4 connected clients.
  - **Concurrency Model**: Go channels will route real-time game actions to the specific room's worker goroutine to prevent race conditions when two players attempt to "Pong" simultaneously.

### 2.2 Frontend UI: React / TypeScript / Canvas
**Purpose**: The cross-platform web interface for lobbies, authentication, and the high-fidelity game board renderer.
- **Why React/TS**: Industry standard for building highly interactive UIs.
- **Rendering**: The lobby and menus will be standard DOM/CSS. The actual Game Board will be rendered using HTML5 Canvas (via a library like PixiJS or standard 2D context) to handle 60FPS fluid animations of tile dragging, discards, and win effects securely and consistently across screens.
- **Integration with Go (Wasm)**: The React application will load the Go Core Game Logic compiled natively to WebAssembly (`GOOS=js GOARCH=wasm`).
  - *Local Prediction (Wasm)*: When a user clicks a tile to discard, the TS client serializes it to Wasm. Wasm verifies legality (`RulesEngine.CanDiscard()`). If true, the UI animates the action instantly, providing a zero-latency feel while the server verifies via WebSockets.

### 2.3 AI & Reinforcement Learning (RL) Pipeline: Python (PyTorch)
**Purpose**: Training reinforcement learning agents to discover optimal strategies, and serving as intelligent opponents for humans.
- **Why Python**: The absolute standard ecosystem for modern RL architectures (PPO, AlphaZero variants) and tensor math.
- **Integration with Go (C-Shared Library for Training)**: 
  - The Go Core engine will be compiled to a C-shared library (`go build -buildmode=c-shared`).
  - Python scripts will load this library (via `ctypes` or `cffi`) to simulate thousands of games per second inside the Go environment, feeding high-volume state/reward data back to the PyTorch models.
- **Integration with Go Backend (Human vs AI Gameplay)**:
  - Once an AI model is trained, it will be wrapped in a lightweight Python or Go inference microservice (e.g., via gRPC).
  - When a human creates a lobby, they can choose to "Add AI Bot". The Go Game Server will treat the AI inference service exactly like a connected WebSocket player.
  - The Go Server sends the `GameState` Protobuf to the AI service, and the AI evaluates the state and returns a `PlayerAction` Protobuf.

### 2.4 Data Serialization: Protocol Buffers (gRPC / Protobuf)
**Purpose**: Ensures that Go, TypeScript, and Python all communicate using identical, highly-optimized data structures.
- **Why Protobuf**: Standard JSON serialization is too slow for the millions of state representations required during AI training. Protobufs allow defining a `GameState` or `PlayerAction` once in a `.proto` file and automatically generating type-safe, binary-encoded objects for Go, TS, and Python.
  - The `GameState` includes complex tracking elements directly supported by specific rulesets like Fenghua, such as `wild_tiles`, `prevailing_wind`, and `active_discard`.
  - The `PlayerState` tracks `closed_hand`, `open_melds` (chii/pon/kan), and edge cases like `flower_melds` or `seat_wind`.

### 2.5 Database & Storage Layer
- **Relational DB (PostgreSQL)**: Stores persistent data like user accounts, ELO ratings, and structural match metadata.
- **In-Memory Store (Redis)**: Manages fast, ephemeral data like the matchmaking queues and currently active lobbies.
- **Blob Storage (S3 / File System)**: Stores serialized replay files of every completed match to allow users to review games and for offline AI analysis.

## 3. Communication Flow

### Standard PvP and PvE Gameplay Event Loop (Goroutines)
1. **User Action**: Target player is prompted to discard. They drag a tile in React Canvas.
2. **Local Wasm Validation**: The React client consults the compiled Go Wasm logic: `core.IsValidAction(Action_DISCARD, tile)`. Wasm returns `true`. React drops the tile in the discard pool UI instantly.
3. **Transmission**: The React client serializes the `Action` Protobuf and shoots it up the WebSocket pipe (`/ws/room/123`).
4. **Server State Machine**: The Go Server's room goroutine receives it. 
   - It validates `core.IsValidAction()` again for security.
   - It mutations the state: `core.ApplyAction()`.
   - The State Machine transitions from `PlayerTurn` -> `WaitDiscards` (allowing a brief 3-second window for other players to claim the tile for pon/chii).
5. **State Broadcast**: The Go Server serializes a `StateDelta` Protobuf (only the changes) and broadcasts to the room.
6. **AI Interaction (gRPC)**: If an AI Bot is in the room, the Server fires the `StateDelta` over localhost gRPC to the Python service. Python returns an `Action` Protobuf (e.g. `Action_PONG`). The Server routes it into the exact same validation channel as the WebSockets.
7. **Reconciliation**: Once the `WaitDiscard` timer expires, the Engine resolves priority (Ron > pon > chii), commits the result, and broadcasts the next `PlayerTurn` phase.

### AI Training Simulation
1. **Initialization**: PyTorch model initialized; Python instantiates the Go Shared Library environment.
2. **Batch Simulation**: Python commands the Go environment: "Simulate 1,000 matches using this batch of AI policies."
3. **Execution**: The Go engine runs the games rapidly using its internal concurrency and returns the final serialized states and rewards.
4. **Learning**: Python updates the neural network weights based on the results and repeats the loop.

## 4. Immediate Development Phases
1. **Phase 1: Protobufs & Core Rules**
   - Define the `.proto` schemas for Tiles, Actions, and Hands.
   - Implement the custom hometown Mahjong ruleset strictly in an isolated Go package.
2. **Phase 2: Backend & WebSockets**
   - Build the Go WebSocket server.
   - Setup basic matchmaking logic.
3. **Phase 3: Web UI Validation**
   - Build the React UI shell.
   - Verify Wasm compilation to ensure the browser responds locally to the Go Core.
4. **Phase 4: RL Gym Environment**
   - Compile the Go Core to `c-shared` and wrap it in a standard Python Gym interface for training tests.
