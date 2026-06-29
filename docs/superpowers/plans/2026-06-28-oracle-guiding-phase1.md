# Oracle Guiding — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a perfect-information oracle agent (sees the three opponents' concealed hands) and gate on whether it significantly beats the heuristic anchor on placement.

**Architecture:** Add an `oracle_observation` flag to the env that appends the three opponents' closed-hand planes to the observation (39→51 channels). Warm-start a 51-channel policy from the 39-channel anchor (zero the new channels so it starts equal), train it as the single Python-controlled seat against the env's built-in heuristic opponents with plain dense score reward, and evaluate it (duplicate-seat, oracle mode) against the anchor baseline.

**Tech Stack:** Go 1.25 (`internal/rl`, proto), Python/PyTorch (`ai/src/fh_mahjong_ai`), Protocol Buffers.

## Global Constraints

- `oracle_observation=false` (default) must be **byte-identical** to today: exactly 39 channels, same values. Behavior-preserving regression guard.
- Oracle planes are an **appended suffix** (channels 39–50); channels 0–38 of an oracle observation equal the normal observation exactly. The warm-start and the regression guard depend on this.
- Proto changes regenerate **Go, Python, and TS** bindings (commands in each task).
- `internal/engine/game.go` must never import `internal/rules/`.
- Run `go test ./...` after Go changes; `uv run --project ai pytest <files>` after Python changes.
- Anchor checkpoint (4090): `/root/fh-mahjong-runs/chongci-broader-mixed-iql-20260607-034720/checkpoints/broader_mixed_iql_highrisk_pairwise/epoch_001.pt` (39-channel).
- The oracle is the **only** net in the training loop; opponents are the env's in-engine heuristic (`auto_play_heuristics=True`, `learning_seats=(0,)`). No opponent nets, no obs slicing.

---

### Task 1: Proto flag `oracle_observation` + regenerate bindings

**Files:**
- Modify: `proto/game.proto` (EnvConfig message)
- Regenerate: `proto/game.pb.go`, `ai/src/fh_mahjong_ai/generated/proto/game_pb2.py`, `web/src/proto/game.js` + `web/src/proto/game.d.ts`
- Test: `ai/tests/test_bridge.py`

**Interfaces:**
- Produces: proto field `EnvConfig.oracle_observation` (bool, tag 6); Go accessor `config.OracleObservation`; Python `game_pb2.EnvConfig(oracle_observation=...)`.

- [ ] **Step 1: Add the proto field.** In `proto/game.proto`, `message EnvConfig`, append after `chongci_config = 5;`:

```proto
  // When true the observation appends the three opponents' concealed (closed)
  // hands as extra planes (39 -> 51 channels). Perfect-information oracle mode.
  bool oracle_observation = 6;
```

- [ ] **Step 2: Regenerate Go bindings.**

Run (from repo root): `protoc --go_out=. --go_opt=paths=source_relative proto/game.proto`
Expected: `proto/game.pb.go` updated; `git diff --stat proto/game.pb.go` shows changes; `grep -c OracleObservation proto/game.pb.go` ≥ 1.

- [ ] **Step 3: Regenerate Python bindings.**

Run (from repo root): `protoc --python_out=ai/src/fh_mahjong_ai/generated proto/game.proto`
Expected: `ai/src/fh_mahjong_ai/generated/proto/game_pb2.py` updated.

- [ ] **Step 4: Regenerate TS bindings.**

Run (from repo root):
```bash
web/node_modules/.bin/pbjs -t static-module -w es6 --null-semantics -o web/src/proto/game.js proto/game.proto
web/node_modules/.bin/pbts -o web/src/proto/game.d.ts web/src/proto/game.js
```
Expected: `web/src/proto/game.js` + `.d.ts` updated.

- [ ] **Step 5: Write the failing test** in `ai/tests/test_bridge.py` (add near the other `game_pb2` tests):

```python
def test_envconfig_proto_has_oracle_observation_flag():
    from fh_mahjong_ai.generated.proto import game_pb2
    msg = game_pb2.EnvConfig(oracle_observation=True)
    assert msg.oracle_observation is True
    assert game_pb2.EnvConfig().oracle_observation is False
```

- [ ] **Step 6: Run it.** `uv run --project ai pytest ai/tests/test_bridge.py::test_envconfig_proto_has_oracle_observation_flag -q` → PASS (field exists after regen).

- [ ] **Step 7: Build check + commit.**

```bash
go build ./...    # proto change compiles
git add proto/game.proto proto/game.pb.go ai/src/fh_mahjong_ai/generated/proto/game_pb2.py web/src/proto/game.js web/src/proto/game.d.ts ai/tests/test_bridge.py
git commit -m "feat(proto): add EnvConfig.oracle_observation flag; regen Go/Python/TS"
```

---

### Task 2: Go oracle observation encoding

**Files:**
- Modify: `internal/rl/observation.go` (constants, `encodeObservation`, `emptyObservation`, `EncodeObservation`)
- Modify: `internal/rl/env.go` (thread `e.config.OracleObservation` into the 2 `encodeObservation` + 8 `emptyObservation` call sites)
- Test: `internal/rl/observation_oracle_test.go` (new)

**Interfaces:**
- Consumes: `config.OracleObservation` (Task 1); existing `setThresholdPlanes(planes, baseChannel, counts)`, `faceCountsFromTiles(tiles) [42]int`, `channelOffset(channel) int`.
- Produces: `encodeObservation(state, seat, decisionIndex, oracle bool)` and `emptyObservation(state, decisionIndex, oracle bool)`; `OracleObservationPlaneChannels = 51`.

- [ ] **Step 1: Write the failing Go test** `internal/rl/observation_oracle_test.go`:

```go
package rl

import (
	"testing"

	pb "github.com/plasma/fh-mahjong/proto"
)

func oracleTestEnv(t *testing.T) *Env {
	t.Helper()
	config := &pb.EnvConfig{
		LearningSeats:      []uint32{0, 1, 2, 3},
		AutoPlayHeuristics: false,
		MaxDecisions:       128,
		MatchMode:          pb.MatchMode_MATCH_MODE_CHONGCI,
		ChongciConfig:      &pb.ChongciConfig{StartingScore: 2000, BustThreshold: 0, MaxHands: 50},
	}
	env := New(config)
	if _, err := env.Reset(&pb.EnvResetRequest{Seed: 7, Config: config}); err != nil {
		t.Fatalf("reset failed: %v", err)
	}
	return env
}

func TestOracleObservationAppendsOpponentHands(t *testing.T) {
	env := oracleTestEnv(t)
	state := env.game.State

	normal, err := encodeObservation(state, 0, 0, false)
	if err != nil {
		t.Fatalf("normal encode: %v", err)
	}
	oracle, err := encodeObservation(state, 0, 0, true)
	if err != nil {
		t.Fatalf("oracle encode: %v", err)
	}

	if normal.PlaneChannels != 39 {
		t.Fatalf("normal channels = %d, want 39", normal.PlaneChannels)
	}
	if oracle.PlaneChannels != 51 {
		t.Fatalf("oracle channels = %d, want 51", oracle.PlaneChannels)
	}

	// Prefix invariant: channels 0..38 are byte-identical.
	prefix := 39 * ObservationPlaneHeight * ObservationPlaneWidth
	for i := 0; i < prefix; i++ {
		if normal.Planes[i] != oracle.Planes[i] {
			t.Fatalf("prefix mismatch at %d: normal=%v oracle=%v", i, normal.Planes[i], oracle.Planes[i])
		}
	}

	// Appended planes equal opponents' closed-hand threshold encodings.
	// Seat 0's opponents: right=1, across=2, left=3; appended at channels 39,43,47.
	for offset, oppSeat := range []uint32{1, 2, 3} {
		baseChannel := 39 + offset*4
		counts := faceCountsFromTiles(state.Players[oppSeat].ClosedHand)
		want := make([]float32, 4*ObservationPlaneHeight*ObservationPlaneWidth)
		setThresholdPlanes(want, 0, counts) // write into a fresh 4-channel buffer
		for c := 0; c < 4; c++ {
			for f := 0; f < ObservationPlaneHeight*ObservationPlaneWidth; f++ {
				got := oracle.Planes[channelOffset(baseChannel+c)+f]
				exp := want[c*ObservationPlaneHeight*ObservationPlaneWidth+f]
				if got != exp {
					t.Fatalf("opp seat %d channel %d face %d: got %v want %v", oppSeat, c, f, got, exp)
				}
			}
		}
	}
}
```

- [ ] **Step 2: Run it to verify it fails.** `go test ./internal/rl/ -run TestOracleObservationAppendsOpponentHands` → FAIL (compile error: `encodeObservation` takes 3 args, not 4).

- [ ] **Step 3: Add the oracle channel constant.** In `internal/rl/observation.go`, in the `const` block, add:

```go
	// Oracle mode appends the three opponents' closed-hand threshold planes
	// (3 opponents x 4 threshold planes) after the 39 base channels.
	OracleObservationPlaneChannels = ObservationPlaneChannels + 12 // 51
```

- [ ] **Step 4: Thread `oracle` through `encodeObservation`.** Change the signature and size the planes by mode. Replace the function header and the planes allocation:

```go
func encodeObservation(state *pb.GameState, seat uint32, decisionIndex uint64, oracle bool) (*pb.SeatObservation, error) {
	mask, err := actionMask(state, seat)
	if err != nil {
		return nil, err
	}

	channels := ObservationPlaneChannels
	if oracle {
		channels = OracleObservationPlaneChannels
	}
	planes := make([]float32, channels*ObservationPlaneHeight*ObservationPlaneWidth)
	scalars := make([]float32, ObservationScalarCount)
```

(Leave the rest of the body unchanged — it writes channels 0–38.)

- [ ] **Step 5: Append the opponent-hand planes before building the result.** Immediately before the `return &pb.SeatObservation{` at the end of `encodeObservation`, add:

```go
	if oracle {
		// Append the three opponents' concealed hands, relative to `seat`,
		// mirroring the self closed-hand threshold encoding. right=+1, across=+2, left=+3.
		setThresholdPlanes(planes, 39, faceCountsFromTiles(right.ClosedHand))
		setThresholdPlanes(planes, 43, faceCountsFromTiles(across.ClosedHand))
		setThresholdPlanes(planes, 47, faceCountsFromTiles(left.ClosedHand))
	}
```

Then set the channel count in the returned struct:

```go
	planeChannels := uint32(ObservationPlaneChannels)
	if oracle {
		planeChannels = uint32(OracleObservationPlaneChannels)
	}
	return &pb.SeatObservation{
		Seat:            seat,
		Planes:          planes,
		PlaneChannels:   planeChannels,
		// ... rest unchanged ...
```

(`right`, `across`, `left` are already bound earlier in the function as `state.Players[rightSeat]` etc.)

- [ ] **Step 6: Thread `oracle` through `emptyObservation`** (terminal placeholder must match channel count). Change its signature and sizing:

```go
func emptyObservation(state *pb.GameState, decisionIndex uint64, oracle bool) *pb.SeatObservation {
	channels := ObservationPlaneChannels
	if oracle {
		channels = OracleObservationPlaneChannels
	}
	// ... existing activePlayer/phase logic ...
	return &pb.SeatObservation{
		Seat:            activePlayer,
		Planes:          make([]float32, channels*ObservationPlaneHeight*ObservationPlaneWidth),
		PlaneChannels:   uint32(channels),
		// ... rest unchanged ...
	}
}
```

- [ ] **Step 7: Update the public wrapper** in `internal/rl/observation.go` to default oracle off:

```go
func EncodeObservation(state *pb.GameState, seat uint32, decisionIndex uint64) (*pb.SeatObservation, error) {
	return encodeObservation(state, seat, decisionIndex, false)
}
```

- [ ] **Step 8: Update all call sites in `internal/rl/env.go`.** The two `encodeObservation(e.game.State, seat, e.decisionCount)` calls become `encodeObservation(e.game.State, seat, e.decisionCount, e.config.OracleObservation)`. The eight `emptyObservation(e.game.State, e.decisionCount)` calls become `emptyObservation(e.game.State, e.decisionCount, e.config.OracleObservation)`. (Use find/replace; verify counts with `grep -c "e.config.OracleObservation" internal/rl/env.go` == 10.)

- [ ] **Step 9: Run the new test + the full rl suite.**

Run: `go test ./internal/rl/ -run TestOracleObservationAppendsOpponentHands` → PASS
Run: `go test ./...` → PASS (regression guard: existing observation tests still pass because oracle defaults to false everywhere).

- [ ] **Step 10: Commit.**

```bash
git add internal/rl/observation.go internal/rl/env.go internal/rl/observation_oracle_test.go
git commit -m "feat(rl): oracle observation appends opponents' closed hands (39->51 ch)"
```

---

### Task 3: Python EnvConfig oracle flag + bridge serialization

**Files:**
- Modify: `ai/src/fh_mahjong_ai/config.py` (EnvConfig)
- Modify: `ai/src/fh_mahjong_ai/bridge.py` (`_config_message`)
- Test: `ai/tests/test_bridge.py`

**Interfaces:**
- Consumes: `game_pb2.EnvConfig.oracle_observation` (Task 1).
- Produces: `EnvConfig.oracle_observation: bool`; oracle `EnvConfig` resolves `plane_shape == (51,42,1)`.

- [ ] **Step 1: Write the failing test** in `ai/tests/test_bridge.py`:

```python
def test_envconfig_oracle_resolves_plane_shape_and_serializes():
    from fh_mahjong_ai.config import EnvConfig
    from fh_mahjong_ai.bridge import GoMahjongBridge
    # default oracle off -> 39ch, byte-identical default
    assert EnvConfig().oracle_observation is False
    assert EnvConfig().plane_shape == (39, 42, 1)
    # oracle on -> plane_shape auto-resolves to 51ch
    cfg = EnvConfig(oracle_observation=True)
    assert cfg.plane_shape == (51, 42, 1)
    # explicit plane_shape is respected (not overridden)
    cfg2 = EnvConfig(oracle_observation=True, plane_shape=(60, 42, 1))
    assert cfg2.plane_shape == (60, 42, 1)
    # the flag is serialized into the proto EnvConfig message
    msg = GoMahjongBridge.__new__(GoMahjongBridge)
    msg.config = cfg
    built = msg._config_message()
    assert built.oracle_observation is True
```

- [ ] **Step 2: Run it.** `uv run --project ai pytest ai/tests/test_bridge.py::test_envconfig_oracle_resolves_plane_shape_and_serializes -q` → FAIL (`oracle_observation` not a field).

- [ ] **Step 3: Add the field + post_init** in `ai/src/fh_mahjong_ai/config.py`, `EnvConfig`. Add the field after `chongci_max_hands`:

```python
    oracle_observation: bool = False

    def __post_init__(self) -> None:
        # Oracle mode appends the 3 opponents' closed hands (39 -> 51 channels);
        # resolve plane_shape so callers don't have to remember the channel count.
        # An explicitly-set non-default plane_shape is respected.
        if self.oracle_observation and tuple(self.plane_shape) == (39, 42, 1):
            self.plane_shape = (51, 42, 1)
```

- [ ] **Step 4: Serialize the flag** in `ai/src/fh_mahjong_ai/bridge.py`, `_config_message`, after the `learning_seats.extend(...)` line:

```python
        message.oracle_observation = bool(self.config.oracle_observation)
```

- [ ] **Step 5: Run it.** Same command → PASS.

- [ ] **Step 6: Regression — default path byte-identical.** Add and run:

```python
def test_envconfig_default_is_39_channels():
    from fh_mahjong_ai.config import EnvConfig
    cfg = EnvConfig()
    assert cfg.plane_shape == (39, 42, 1)
    assert cfg.oracle_observation is False
```

Run: `uv run --project ai pytest ai/tests/test_bridge.py -q` → PASS.

- [ ] **Step 7: Commit.**

```bash
git add ai/src/fh_mahjong_ai/config.py ai/src/fh_mahjong_ai/bridge.py ai/tests/test_bridge.py
git commit -m "feat(ai): EnvConfig.oracle_observation resolves 51ch plane_shape + serializes"
```

---

### Task 4: Oracle model warm-start helper

**Files:**
- Create: `ai/src/fh_mahjong_ai/oracle.py`
- Test: `ai/tests/test_oracle.py` (new)

**Interfaces:**
- Consumes: `PolicyValueNet(env_config, model_config)`; `load_compatible_checkpoint(path, model)`; `save_checkpoint(path, model)`; the model's input conv at `model.plane_stem[0].weight` (shape `[model_config.channels, plane_channels, 3, 3]`).
- Produces: `build_oracle_model(env_config, model_config, anchor_checkpoint, device="cpu") -> PolicyValueNet` — a 51ch net warm-started so its output equals the anchor's when the 12 oracle channels are zero.

- [ ] **Step 1: Write the failing test** `ai/tests/test_oracle.py`:

```python
import numpy as np
import torch

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.storage import save_checkpoint
from fh_mahjong_ai.oracle import build_oracle_model


def _mcfg():
    return ModelConfig(channels=8, residual_blocks=1, plane_feature_dim=16,
                       scalar_hidden_dim=16, trunk_hidden_dim=16, value_hidden_dim=16, q_hidden_dim=16)


def test_oracle_warmstart_matches_anchor_when_oracle_channels_zero(tmp_path):
    mcfg = _mcfg()
    anchor_env = EnvConfig()  # 39ch
    anchor = PolicyValueNet(anchor_env, mcfg).eval()
    ckpt = tmp_path / "anchor.pt"
    save_checkpoint(ckpt, anchor)

    oracle_env = EnvConfig(oracle_observation=True)  # 51ch
    oracle = build_oracle_model(oracle_env, mcfg, ckpt, device="cpu").eval()

    # input conv: first 39 channels copied from anchor, last 12 zeroed
    aw = anchor.plane_stem[0].weight.detach()
    ow = oracle.plane_stem[0].weight.detach()
    assert torch.allclose(ow[:, :39], aw)
    assert torch.count_nonzero(ow[:, 39:]) == 0

    # same observation, oracle channels zeroed -> identical policy logits
    rng = np.random.default_rng(0)
    planes39 = rng.standard_normal((1, 39, 42, 1)).astype(np.float32)
    planes51 = np.concatenate([planes39, np.zeros((1, 12, 42, 1), np.float32)], axis=1)
    scalars = rng.standard_normal((1, 58)).astype(np.float32)
    mask = np.ones((1, 204), np.int8)
    with torch.no_grad():
        la, _ = anchor(torch.from_numpy(planes39), torch.from_numpy(scalars), torch.from_numpy(mask))
        lo, _ = oracle(torch.from_numpy(planes51), torch.from_numpy(scalars), torch.from_numpy(mask))
    assert torch.allclose(la, lo, atol=1e-5)
```

- [ ] **Step 2: Run it.** `uv run --project ai pytest ai/tests/test_oracle.py -q` → FAIL (`oracle` module missing).

- [ ] **Step 3: Implement** `ai/src/fh_mahjong_ai/oracle.py`:

```python
"""Oracle-guiding helpers (Phase 1): build a perfect-information policy
warm-started from the 39-channel anchor."""
from __future__ import annotations

from pathlib import Path

import torch

from .config import EnvConfig, ModelConfig
from .model import PolicyValueNet
from .storage import load_compatible_checkpoint


def build_oracle_model(env_config: EnvConfig, model_config: ModelConfig,
                       anchor_checkpoint: Path, device: str = "cpu") -> PolicyValueNet:
    """Build a 51-channel oracle `PolicyValueNet` warm-started from the 39-channel
    anchor. Every layer except the first plane conv is loaded by shape
    (`load_compatible_checkpoint` skips the 39->51 conv); the input conv is then
    initialized so the oracle equals the anchor when the 12 oracle channels are 0:
    the anchor's weights occupy the first 39 input channels and the new 12 are
    zeroed."""
    oracle = PolicyValueNet(env_config, model_config).to(device)
    # Load all same-shape tensors (skips plane_stem.0.weight: [C,39,3,3] vs [C,51,3,3]).
    load_compatible_checkpoint(Path(anchor_checkpoint), oracle)
    # Read the anchor's input conv weight directly from the checkpoint.
    payload = torch.load(Path(anchor_checkpoint), map_location="cpu")
    anchor_w = payload["model"]["plane_stem.0.weight"]  # [C, 39, 3, 3]
    base = anchor_w.shape[1]  # 39
    with torch.no_grad():
        w = oracle.plane_stem[0].weight
        w.zero_()
        w[:, :base].copy_(anchor_w.to(w.device))
    oracle.eval()
    return oracle
```

- [ ] **Step 4: Run it.** `uv run --project ai pytest ai/tests/test_oracle.py -q` → PASS.

- [ ] **Step 5: Commit.**

```bash
git add ai/src/fh_mahjong_ai/oracle.py ai/tests/test_oracle.py
git commit -m "feat(ai): build_oracle_model warm-starts 51ch oracle from 39ch anchor"
```

---

### Task 5: Single-seat oracle rollout collector + train loop

**Files:**
- Modify: `ai/src/fh_mahjong_ai/oracle.py` (add `collect_oracle_rollouts`, `train_oracle`)
- Create: `ai/src/fh_mahjong_ai/scripts/train_oracle.py`
- Test: `ai/tests/test_oracle.py`

**Interfaces:**
- Consumes: `RolloutBatch`, `compute_gae`, `ppo_update`, `PPOConfig`, `masked_policy_distribution`, `_obs_to_tensors`, `_seat_step_reward`, `LEARNING_SEAT` from `ppo.py`; `MahjongEnv`, `build_bridge` from the env stack; `save_checkpoint`.
- Produces: `collect_oracle_rollouts(env_config, model, config, base_seed) -> RolloutBatch`; `train_oracle(env_config, model_config, anchor_checkpoint, checkpoint_dir, config, base_seed, run_eval) -> list[dict]`.

- [ ] **Step 1: Write the failing test** in `ai/tests/test_oracle.py`:

```python
def test_collect_oracle_rollouts_single_seat_mock():
    from fh_mahjong_ai.config import EnvConfig, ModelConfig
    from fh_mahjong_ai.model import PolicyValueNet
    from fh_mahjong_ai.ppo import PPOConfig
    from fh_mahjong_ai.oracle import collect_oracle_rollouts
    env_cfg = EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64,
                        oracle_observation=True)  # 51ch
    mcfg = _mcfg()
    model = PolicyValueNet(env_cfg, mcfg)
    cfg = PPOConfig(matches_per_iter=2, match_mode="classic", max_steps_per_episode=64, device="cpu")
    batch = collect_oracle_rollouts(env_cfg, model, cfg, base_seed=3)
    assert len(batch) >= 2
    assert batch.dones.sum() == 2          # one terminal per match
    assert batch.planes.shape[1] == 51     # oracle channels
```

- [ ] **Step 2: Run it.** `uv run --project ai pytest ai/tests/test_oracle.py::test_collect_oracle_rollouts_single_seat_mock -q` → FAIL (function missing).

- [ ] **Step 3: Implement `collect_oracle_rollouts`** in `ai/src/fh_mahjong_ai/oracle.py` (add imports at top: `import numpy as np`, `import torch`, and from `.ppo` import the helpers; from `.config` import already present; from `.env`/bridge as used by ppo). Model it on `collect_rollouts` but single-seat with auto-play opponents:

```python
import json
import numpy as np
import torch

from .bridge import build_bridge
from .env import MahjongEnv
from .ppo import (
    RolloutBatch, PPOConfig, compute_gae, ppo_update, masked_policy_distribution,
    _obs_to_tensors, _seat_step_reward, LEARNING_SEAT,
)
from .storage import save_checkpoint


def collect_oracle_rollouts(env_config: EnvConfig, model: PolicyValueNet,
                            config: PPOConfig, base_seed: int) -> RolloutBatch:
    """Single-seat PPO rollouts: the oracle is the only learning seat; the env
    auto-plays heuristic opponents. Records the learner's decisions with dense
    per-hand score-delta reward; done=1 at match end."""
    device = config.device
    cfg = EnvConfig(
        action_space_size=env_config.action_space_size,
        plane_shape=env_config.plane_shape,
        scalar_features=env_config.scalar_features,
        bridge_kind=env_config.bridge_kind,
        bridge_library_path=env_config.bridge_library_path,
        learning_seats=(LEARNING_SEAT,),
        auto_play_heuristics=True,
        max_steps_per_episode=config.max_steps_per_episode,
        match_mode=config.match_mode,
        oracle_observation=env_config.oracle_observation,
    )
    bridge = build_bridge(cfg)
    env = MahjongEnv(cfg, bridge=bridge)
    model.eval()
    planes_l, scalars_l, mask_l, actions_l = [], [], [], []
    logprobs_l, values_l, rewards_l, dones_l = [], [], [], []
    try:
        for m in range(config.matches_per_iter):
            obs = env.reset(seed=base_seed + m)
            torch.manual_seed(int(base_seed + m))
            reset_result = env.last_reset_result
            if reset_result is not None and (reset_result.terminated or reset_result.truncated):
                continue
            last_idx = None
            while True:
                planes, scalars, mask = _obs_to_tensors(obs, device)
                with torch.no_grad():
                    logits, value = model(planes, scalars, mask)
                    logits = logits / max(config.sample_temperature, 1e-6)
                    dist = masked_policy_distribution(logits)
                    action = int(dist.sample()[0].item())
                    logprob = float(dist.log_prob(torch.tensor([action], device=device))[0])
                    val = float(value[0].item())
                planes_l.append(np.asarray(obs.planes, dtype=np.float32))
                scalars_l.append(np.asarray(obs.scalars, dtype=np.float32))
                mask_l.append(np.asarray(obs.action_mask, dtype=np.int8))
                actions_l.append(action)
                logprobs_l.append(logprob)
                values_l.append(val)
                rewards_l.append(0.0)
                dones_l.append(0.0)
                last_idx = len(actions_l) - 1
                step = env.step(action)
                if last_idx is not None:
                    rewards_l[last_idx] += _seat_step_reward(step.rewards, LEARNING_SEAT)
                if step.terminated or step.truncated:
                    if last_idx is not None:
                        dones_l[last_idx] = 1.0
                    break
                obs = step.observation
    finally:
        close = getattr(bridge, "close", None)
        if callable(close):
            close()
    if not actions_l:
        raise RuntimeError("collect_oracle_rollouts produced no learning-seat decisions")
    return RolloutBatch(
        planes=np.stack(planes_l).astype(np.float32),
        scalars=np.stack(scalars_l).astype(np.float32),
        action_mask=np.stack(mask_l).astype(np.int8),
        actions=np.asarray(actions_l, dtype=np.int64),
        old_logprobs=np.asarray(logprobs_l, dtype=np.float32),
        values=np.asarray(values_l, dtype=np.float32),
        rewards=np.asarray(rewards_l, dtype=np.float32),
        dones=np.asarray(dones_l, dtype=np.float32),
    )
```

(These names all exist in `ppo.py`: `LEARNING_SEAT = 0`, `_seat_step_reward`, `_obs_to_tensors`, `masked_policy_distribution`, `RolloutBatch`, `compute_gae`, `ppo_update`, and `PPOConfig.sample_temperature`.)

- [ ] **Step 4: Run it.** `uv run --project ai pytest ai/tests/test_oracle.py::test_collect_oracle_rollouts_single_seat_mock -q` → PASS.

- [ ] **Step 5: Write the failing test for `train_oracle`** in `ai/tests/test_oracle.py`:

```python
def test_train_oracle_runs_on_mock_and_writes_checkpoint(tmp_path):
    from fh_mahjong_ai.config import EnvConfig, ModelConfig
    from fh_mahjong_ai.model import PolicyValueNet
    from fh_mahjong_ai.ppo import PPOConfig
    from fh_mahjong_ai.storage import save_checkpoint
    from fh_mahjong_ai.oracle import train_oracle
    mcfg = _mcfg()
    # 39ch anchor checkpoint to warm-start from
    anchor = tmp_path / "anchor.pt"
    save_checkpoint(anchor, PolicyValueNet(EnvConfig(), mcfg))
    env_cfg = EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64,
                        oracle_observation=True)
    cfg = PPOConfig(iterations=2, matches_per_iter=2, ppo_epochs=1, minibatch_size=8,
                    match_mode="classic", max_steps_per_episode=64, device="cpu")
    history = train_oracle(env_config=env_cfg, model_config=mcfg, anchor_checkpoint=anchor,
                           checkpoint_dir=tmp_path / "oracle", config=cfg, base_seed=1, run_eval=False)
    assert len(history) == 2
    assert (tmp_path / "oracle" / "iter_002.pt").exists()
    assert all(np.isfinite(h["policy_loss"]) for h in history)
```

- [ ] **Step 6: Run it.** → FAIL (`train_oracle` missing).

- [ ] **Step 7: Implement `train_oracle`** in `ai/src/fh_mahjong_ai/oracle.py` (imports `json`, `save_checkpoint`, `compute_gae`, `ppo_update` are already added in Step 3 / Task 4):

```python
def train_oracle(env_config: EnvConfig, model_config: ModelConfig, anchor_checkpoint: Path,
                 checkpoint_dir: Path, config: PPOConfig, base_seed: int = 0,
                 run_eval: bool = False) -> list[dict]:
    """Warm-start a 51ch oracle from the anchor and train it single-seat vs the
    env's heuristic with dense score reward (reuses compute_gae + ppo_update)."""
    device = config.device
    checkpoint_dir = Path(checkpoint_dir)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    model = build_oracle_model(env_config, model_config, anchor_checkpoint, device)
    model.train()
    optimizer = torch.optim.AdamW(model.parameters(), lr=config.lr)
    history: list[dict] = []
    for iteration in range(1, config.iterations + 1):
        iter_seed = base_seed + iteration * config.matches_per_iter
        batch = collect_oracle_rollouts(env_config, model, config, base_seed=iter_seed)
        advantages, returns = compute_gae(batch.rewards, batch.values, batch.dones,
                                          config.gamma, config.gae_lambda)
        metrics = ppo_update(model, optimizer, batch, advantages, returns, config)
        metrics["iteration"] = iteration
        metrics["mean_reward"] = float(np.sum(batch.rewards) / max(1.0, float(batch.dones.sum())))
        metrics["steps"] = len(batch)
        save_checkpoint(checkpoint_dir / f"iter_{iteration:03d}.pt", model)
        history.append(metrics)
        (checkpoint_dir / "history.json").write_text(json.dumps(history))
        print(f"iter {iteration}: policy_loss={metrics['policy_loss']:.4f} "
              f"value_loss={metrics['value_loss']:.4f} entropy={metrics['entropy']:.4f} "
              f"mean_reward={metrics['mean_reward']:.4f}")
    return history
```

- [ ] **Step 8: Run it.** `uv run --project ai pytest ai/tests/test_oracle.py -q` → PASS (all oracle tests).

- [ ] **Step 9: Add the CLI** `ai/src/fh_mahjong_ai/scripts/train_oracle.py` (mirror `scripts/train_ppo.py`'s arg wiring; key flags below). Then register it in `ai/pyproject.toml` `[project.scripts]` as `fh-mj-train-oracle = "fh_mahjong_ai.scripts.train_oracle:main"`:

```python
"""CLI for Phase-1 oracle training (single-seat, perfect-information)."""
from __future__ import annotations
import argparse
from pathlib import Path
from fh_mahjong_ai.config import EnvConfig
from fh_mahjong_ai.ppo import PPOConfig
from fh_mahjong_ai.oracle import train_oracle
from fh_mahjong_ai.scripts.model_config_args import add_model_config_args, model_config_from_args


def main() -> None:
    p = argparse.ArgumentParser(description="Phase-1 perfect-information oracle training")
    p.add_argument("--anchor-checkpoint", type=Path, required=True, help="39ch anchor to warm-start from")
    p.add_argument("--checkpoint-dir", type=Path, required=True)
    p.add_argument("--iterations", type=int, default=25)
    p.add_argument("--matches-per-iter", type=int, default=256)
    p.add_argument("--gamma", type=float, default=0.99)
    p.add_argument("--lr", type=float, default=1e-5)
    p.add_argument("--entropy-coef", type=float, default=0.0)
    p.add_argument("--ppo-epochs", type=int, default=2)
    p.add_argument("--minibatch-size", type=int, default=256)
    p.add_argument("--max-grad-norm", type=float, default=0.5)
    p.add_argument("--match-mode", choices=("classic", "chongci"), default="chongci")
    p.add_argument("--max-steps-per-episode", type=int, default=4000)
    p.add_argument("--bridge-kind", choices=("go", "mock"), default="go")
    p.add_argument("--bridge-lib", type=str, default=None)
    p.add_argument("--device", type=str, default="cpu")
    p.add_argument("--base-seed", type=int, default=0)
    add_model_config_args(p)
    args = p.parse_args()
    env_config = EnvConfig(bridge_kind=args.bridge_kind, bridge_library_path=args.bridge_lib,
                           match_mode=args.match_mode, max_steps_per_episode=args.max_steps_per_episode,
                           oracle_observation=True)
    config = PPOConfig(iterations=args.iterations, matches_per_iter=args.matches_per_iter,
                       gamma=args.gamma, lr=args.lr, entropy_coef=args.entropy_coef,
                       ppo_epochs=args.ppo_epochs, minibatch_size=args.minibatch_size,
                       max_grad_norm=args.max_grad_norm, match_mode=args.match_mode,
                       max_steps_per_episode=args.max_steps_per_episode, device=args.device)
    train_oracle(env_config=env_config, model_config=model_config_from_args(args),
                 anchor_checkpoint=args.anchor_checkpoint, checkpoint_dir=args.checkpoint_dir,
                 config=config, base_seed=args.base_seed, run_eval=False)


if __name__ == "__main__":
    main()
```

- [ ] **Step 10: Smoke-test the CLI on mock + commit.**

```bash
uv run --project ai fh-mj-train-oracle --anchor-checkpoint /tmp/none 2>&1 | head   # arg parse only; expect a clear error about missing anchor file is acceptable
git add ai/src/fh_mahjong_ai/oracle.py ai/src/fh_mahjong_ai/scripts/train_oracle.py ai/pyproject.toml ai/tests/test_oracle.py
git commit -m "feat(ai): single-seat oracle rollout collector + train_oracle + CLI"
```

---

### Task 6: Eval `--oracle` flag

**Files:**
- Modify: `ai/src/fh_mahjong_ai/scripts/evaluate.py` (add `--oracle`; build the eval env + model at 51ch)
- Test: `ai/tests/test_evaluate.py`

**Interfaces:**
- Consumes: `EnvConfig(oracle_observation=True)` (resolves 51ch plane_shape); the eval's model construction.

- [ ] **Step 1: Understand the two changes needed.** `scripts/evaluate.py:104` builds the eval model as `model = PolicyValueNet(EnvConfig(), model_config)` (39ch). The online eval ultimately builds an internal `EnvConfig(...)` inside `evaluate.py` (`evaluate_online` / `evaluate_policy_online`, ~line 475) and already **threads `max_steps_per_episode`** down through `evaluate_duplicate_seats` → `evaluate_online`. `--oracle` must (a) build the CLI model with `EnvConfig(oracle_observation=args.oracle)` so the net is 51ch, and (b) thread `oracle_observation` down the same call chain as `max_steps_per_episode` so the internal eval `EnvConfig` sets it (Go env emits 51ch). Add an `oracle_observation: bool = False` parameter to `evaluate_online`, `evaluate_policy_online`, `evaluate_duplicate_seats`, and `evaluate_duplicate_seats_policy` (wherever `max_steps_per_episode` is a parameter), passing it into the internal `EnvConfig(...)` exactly where `max_steps_per_episode=...` is passed.

- [ ] **Step 2: Write the failing test** in `ai/tests/test_evaluate.py`:

```python
def test_evaluate_cli_oracle_builds_51ch(tmp_path, monkeypatch):
    import sys
    from fh_mahjong_ai.config import EnvConfig, ModelConfig
    from fh_mahjong_ai.model import PolicyValueNet
    from fh_mahjong_ai.storage import save_checkpoint
    from fh_mahjong_ai.scripts import evaluate as ev
    mcfg = ModelConfig(channels=8, residual_blocks=1, plane_feature_dim=16,
                       scalar_hidden_dim=16, trunk_hidden_dim=16, value_hidden_dim=16, q_hidden_dim=16)
    ckpt = tmp_path / "oracle.pt"
    save_checkpoint(ckpt, PolicyValueNet(EnvConfig(oracle_observation=True), mcfg))
    argv = ["fh-mj-evaluate", "--checkpoint", str(ckpt), "--online-episodes", "1",
            "--bridge-kind", "mock", "--match-mode", "classic", "--oracle",
            "--model-channels", "8", "--model-residual-blocks", "1",
            "--model-plane-feature-dim", "16", "--model-scalar-hidden-dim", "16",
            "--model-trunk-hidden-dim", "16", "--model-value-hidden-dim", "16", "--model-q-hidden-dim", "16",
            "--report-output", str(tmp_path / "rep.json")]
    monkeypatch.setattr(sys, "argv", argv)
    ev.main()  # must not raise; 51ch model + 51ch mock obs are consistent
    assert (tmp_path / "rep.json").exists()
```

(If the eval CLI has no model-config flags, drop them and rely on defaults that match the saved checkpoint.)

- [ ] **Step 3: Run it.** → FAIL (`--oracle` unknown).

- [ ] **Step 4: Implement.**
  1. In `main()`'s parser: `parser.add_argument("--oracle", action="store_true", help="perfect-information oracle eval (51ch observation)")`.
  2. Change `model = PolicyValueNet(EnvConfig(), model_config)` → `model = PolicyValueNet(EnvConfig(oracle_observation=args.oracle), model_config)`.
  3. At the online-eval call site in `main()`, pass `oracle_observation=args.oracle` alongside the existing `max_steps_per_episode=...` argument.
  4. In `evaluate.py`, add `oracle_observation: bool = False` to the signatures of `evaluate_online`, `evaluate_policy_online`, `evaluate_duplicate_seats`, and `evaluate_duplicate_seats_policy`, threading it through each call (mirror `max_steps_per_episode`), and into the internal `EnvConfig(...)` constructor (add `oracle_observation=oracle_observation` next to `max_steps_per_episode=...`).

- [ ] **Step 5: Run it.** `uv run --project ai pytest ai/tests/test_evaluate.py::test_evaluate_cli_oracle_builds_51ch -q` → PASS.

- [ ] **Step 6: Regression.** `uv run --project ai pytest ai/tests/test_evaluate.py -q` → PASS (non-oracle path unchanged).

- [ ] **Step 7: Commit.**

```bash
git add ai/src/fh_mahjong_ai/scripts/evaluate.py ai/tests/test_evaluate.py
git commit -m "feat(ai): fh-mj-evaluate --oracle (51ch perfect-information eval)"
```

---

### Task 7: Training + gate runbook (no code; execute on the 4090)

**Files:** none (operational). Record results in the campaign notes.

- [ ] **Step 1: Build the Go bridge** with the oracle changes on the 4090, then **train**:

```bash
# on wsl (4090): rebuild the c-shared bridge so the Go oracle obs is live
# (use the repo's existing bridge build command for libfh_mahjong_bridge.so)
ANCHOR=/root/fh-mahjong-runs/chongci-broader-mixed-iql-20260607-034720/checkpoints/broader_mixed_iql_highrisk_pairwise/epoch_001.pt
LIB=/root/fh-mahjong/build/libfh_mahjong_bridge.so
FH_MAHJONG_BRIDGE_LIB=$LIB uv run fh-mj-train-oracle \
  --anchor-checkpoint "$ANCHOR" --checkpoint-dir /root/fh-mahjong-runs/oracle-phase1/ckpt \
  --iterations 25 --matches-per-iter 256 --match-mode chongci --max-steps-per-episode 4000 \
  --lr 1e-5 --entropy-coef 0 --ppo-epochs 2 --max-grad-norm 0.5 --bridge-kind go --device cuda
```

- [ ] **Step 2: Gate eval** (paired vs anchor baseline `-0.0528`):

```bash
FH_MAHJONG_BRIDGE_LIB=$LIB uv run fh-mj-evaluate \
  --checkpoint /root/fh-mahjong-runs/oracle-phase1/ckpt/iter_025.pt --oracle \
  --duplicate-seats --online-episodes 120 --start-seed 870000 --match-mode chongci \
  --chongci-max-hands 50 --max-steps-per-episode 4000 --large-loss-threshold -1.0 --device cuda \
  --report-output /root/fh-mahjong-runs/oracle-phase1/eval-oracle.json
```

- [ ] **Step 3: Verdict.** Compute the paired placement diff (oracle vs anchor on identical seeds, per `paired_analysis.py`). **PASS = oracle significantly beats the anchor on `mean_placement` (CI excludes 0).** If pass → Phase 2 (transfer to a deployable student) gets its own spec. If fail → partial observability is not the ceiling; stop and document.

---

## Notes for the implementer

- After Task 2, the Go bridge `.so` must be rebuilt before any `--bridge-kind go` run picks up oracle mode (mock-bridge tests don't need it).
- The mock bridge sizes random planes from `config.plane_shape`, so oracle-mode Python tests (51ch) work without the Go bridge.
- Keep `oracle_observation=false` paths untouched — the regression guard is that every existing Go and Python test still passes.
