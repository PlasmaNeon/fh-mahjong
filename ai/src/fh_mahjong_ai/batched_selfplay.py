"""Batched self-play collection: env pool + one batched forward per round.

Round loop: every live slot has exactly one pending decision (a mahjong match
has one acting seat at a time). Each round we ship one pool call (reset/step
commands), δ-mask the returned rows with per-match RNGs, run ONE model forward
over all pending rows (batched on config.device, or per-row for the CPU
exactness tests), sample per-match, and repeat. Completed matches are emitted
into the RolloutBatch in SEED ORDER so per_row-CPU output is invariant to the
slot count. Sampling never touches the global torch RNG.
"""
from __future__ import annotations

import numpy as np
import torch

from .config import EnvConfig
from .envpool import PoolCommand, PoolStepResult
from .model import PolicyValueNet
from .ppo import PPOConfig, RolloutBatch, _seat_step_reward

ORACLE_LO, ORACLE_HI = 39, 51  # oracle channels masked by feature-dropout


def sample_masked_action(logits_row, mask_row, temperature, rng):
    """Sample one action from temperature-scaled masked logits with `rng`.

    Same distribution family as the process collectors (Categorical over the
    legal actions' scaled logits); the RNG is a per-match numpy Generator, so
    the draw is independent of how rows were batched for inference."""
    legal = np.flatnonzero(np.asarray(mask_row) > 0)
    if legal.size == 0:
        raise RuntimeError("observation has no legal actions")
    scaled = np.asarray(logits_row, dtype=np.float64)[legal] / max(float(temperature), 1e-6)
    shifted = scaled - scaled.max()                      # stable log-softmax,
    log_probs = shifted - np.log(np.exp(shifted).sum())  # no scipy dependency
    index = int(rng.choice(legal.size, p=np.exp(log_probs)))
    return int(legal[index]), float(log_probs[index])


class _MatchState:
    """Per-slot bookkeeping for one match (mirrors collect_selfplay_rollouts)."""

    def __init__(self, match_index: int, base_seed: int) -> None:
        self.match_index = match_index
        self.seed = int(base_seed + match_index)
        self.mask_rng = np.random.default_rng(self.seed)            # δ stream (same as today)
        self.sample_rng = np.random.default_rng([self.seed, 17])    # action stream
        self.seat_planes = [[], [], [], []]
        self.seat_scalars = [[], [], [], []]
        self.seat_masks = [[], [], [], []]
        self.seat_actions = [[], [], [], []]
        self.seat_logprobs = [[], [], [], []]
        self.seat_values = [[], [], [], []]
        self.seat_rewards = [[], [], [], []]

    def record_decision(self, seat, planes_np, scalars_np, mask_np, action, logprob, value):
        self.seat_planes[seat].append(planes_np)
        self.seat_scalars[seat].append(scalars_np)
        self.seat_masks[seat].append(mask_np)
        self.seat_actions[seat].append(action)
        self.seat_logprobs[seat].append(logprob)
        self.seat_values[seat].append(value)
        self.seat_rewards[seat].append(0.0)

    def credit_step_rewards(self, step_rewards) -> None:
        # Credit each seat's step delta to ITS current last decision.
        for k in range(4):
            if self.seat_rewards[k]:
                self.seat_rewards[k][-1] += _seat_step_reward(step_rewards, k)

    def emit_into(self, sink) -> None:
        # Per-seat contiguous blocks, seats 0..3, done=1 at each block's end.
        for k in range(4):
            n = len(self.seat_actions[k])
            if n == 0:
                continue
            sink["planes"].extend(self.seat_planes[k])
            sink["scalars"].extend(self.seat_scalars[k])
            sink["masks"].extend(self.seat_masks[k])
            sink["actions"].extend(self.seat_actions[k])
            sink["logprobs"].extend(self.seat_logprobs[k])
            sink["values"].extend(self.seat_values[k])
            sink["rewards"].extend(self.seat_rewards[k])
            sink["dones"].extend([0.0] * (n - 1) + [1.0])


def collect_selfplay_rollouts_batched(env_config: EnvConfig, model: PolicyValueNet,
                                      config: PPOConfig, base_seed: int, drop_prob: float,
                                      pool, inference_mode: str = "batched") -> RolloutBatch:
    if inference_mode not in ("batched", "per_row"):
        raise ValueError(f"unknown inference_mode: {inference_mode}")
    total = int(config.matches_per_iter)
    device = config.device
    model.eval()

    active: dict[int, _MatchState] = {}   # slot -> in-flight match
    pending_action: dict[int, int] = {}   # slot -> action sampled last round
    completed: dict[int, _MatchState] = {}  # match_index -> finished match
    next_match = 0                        # next match index to assign to a free slot
    emit_next = 0                         # next match index to flush (seed order)
    sink = {name: [] for name in
            ("planes", "scalars", "masks", "actions", "logprobs", "values", "rewards", "dones")}

    def flush_in_seed_order() -> None:
        nonlocal emit_next
        while emit_next in completed:
            completed.pop(emit_next).emit_into(sink)
            emit_next += 1

    while emit_next < total:
        commands = []
        for slot in range(pool.slots):
            if slot in pending_action:
                commands.append(PoolCommand(slot=slot, action_id=pending_action.pop(slot)))
            elif slot not in active and next_match < total:
                state = _MatchState(next_match, base_seed)
                next_match += 1
                active[slot] = state
                commands.append(PoolCommand(slot=slot, reset_seed=state.seed))
            # idle slots get no command (absent == skip)
        if not commands:
            break  # defensive: nothing in flight and nothing left to assign
        result: PoolStepResult = pool.step(commands)

        pending_rows = []  # (slot, state, planes_np, scalars_np, mask_np, seat)
        for meta in result.slots:
            state = active.get(meta.slot)
            if state is None:
                continue
            if meta.error:
                raise RuntimeError(
                    f"env pool slot {meta.slot} (match seed {state.seed}) failed: {meta.error}")
            state.credit_step_rewards(meta.step_rewards)
            if meta.terminated or meta.truncated:
                # A match that ends during reset has no decisions and emits nothing.
                completed[state.match_index] = state
                del active[meta.slot]
                continue
            if not meta.has_observation:
                continue
            row = result.row_of_slot[meta.slot]
            planes_np = np.array(result.planes[row], dtype=np.float32, copy=True)
            if planes_np.shape[0] >= ORACLE_HI and state.mask_rng.random() < drop_prob:
                planes_np[ORACLE_LO:ORACLE_HI] = 0.0  # feature-dropout; record the MASKED obs
            scalars_np = np.asarray(result.scalars[row], dtype=np.float32)
            mask_np = np.asarray(result.action_masks[row], dtype=np.int8)
            pending_rows.append((meta.slot, state, planes_np, scalars_np, mask_np, meta.seat))
        flush_in_seed_order()
        if not pending_rows:
            continue

        if inference_mode == "batched":
            planes_t = torch.from_numpy(np.stack([r[2] for r in pending_rows])).to(device)
            scalars_t = torch.from_numpy(np.stack([r[3] for r in pending_rows])).to(device)
            masks_t = torch.from_numpy(np.stack([r[4] for r in pending_rows])).to(device)
            with torch.no_grad():
                logits_t, values_t = model(planes_t, scalars_t, masks_t)
            logits_np = logits_t.detach().cpu().numpy()
            values_np = values_t.detach().reshape(-1).cpu().numpy()
        else:  # per_row: identical orchestration, batch-composition-independent floats
            logits_rows, values_rows = [], []
            for _, _, planes_np, scalars_np, mask_np, _ in pending_rows:
                with torch.no_grad():
                    logits_1, value_1 = model(
                        torch.from_numpy(planes_np).unsqueeze(0).to(device),
                        torch.from_numpy(scalars_np).unsqueeze(0).to(device),
                        torch.from_numpy(mask_np).unsqueeze(0).to(device),
                    )
                logits_rows.append(logits_1[0].detach().cpu().numpy())
                values_rows.append(float(value_1.reshape(-1)[0].item()))
            logits_np = np.stack(logits_rows)
            values_np = np.asarray(values_rows, dtype=np.float32)

        for i, (slot, state, planes_np, scalars_np, mask_np, seat) in enumerate(pending_rows):
            action, logprob = sample_masked_action(
                logits_np[i], mask_np, config.sample_temperature, state.sample_rng)
            state.record_decision(seat, planes_np, scalars_np, mask_np,
                                  action, logprob, float(values_np[i]))
            pending_action[slot] = action

    if not sink["actions"]:
        raise RuntimeError("collect_selfplay_rollouts_batched produced no decisions")
    return RolloutBatch(
        planes=np.stack(sink["planes"]).astype(np.float32),
        scalars=np.stack(sink["scalars"]).astype(np.float32),
        action_mask=np.stack(sink["masks"]).astype(np.int8),
        actions=np.asarray(sink["actions"], dtype=np.int64),
        old_logprobs=np.asarray(sink["logprobs"], dtype=np.float32),
        values=np.asarray(sink["values"], dtype=np.float32),
        rewards=np.asarray(sink["rewards"], dtype=np.float32),
        dones=np.asarray(sink["dones"], dtype=np.float32),
    )
