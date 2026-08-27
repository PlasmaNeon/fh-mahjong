"""Batched B2b collection: env pool + one batched forward per round.

Same round loop as `batched_selfplay.collect_selfplay_rollouts_batched`
(one pool call per round, per-match numpy RNG, seed-order emission) with
B2b's extra outputs: tail-windowed event histories, hindsight labels from
the pool's `round_outcome`, placement bonus and telemetry. Match-end
semantics come from `train_b2b._finalize_b2b_match`, shared with the
process collector; the log-probability of every action comes from
`ppo.masked_logprob` on the Torch logits row, so greedy + `per_row` output
is byte-identical to `collect_b2b_rollouts`.
"""
from __future__ import annotations

import logging
from dataclasses import replace
from typing import Optional

import numpy as np
import torch

from .batched_selfplay import sample_masked_action
from .config import EnvConfig
from .envpool import PoolCommand, PoolStepResult, make_selfplay_pool
from .model import PolicyValueNet
from .ppo import PPOConfig, RolloutBatch, masked_logprob
from .train_b2b import (
    _B2B_ROW_KEYS, _B2bMatchState, _check_chongci_outcomes, _finalize_b2b_match,
)

logger = logging.getLogger(__name__)


def make_b2b_pool(env_config: EnvConfig, model: PolicyValueNet, config: PPOConfig, slots: int):
    """Pool whose EnvConfig matches the one `collect_b2b_rollouts` builds:
    oracle observation on, event window bound to the model's."""
    window = int(model.model_config.event_window)
    b2b_env = replace(env_config, oracle_observation=True, event_history_window=window)
    pool = make_selfplay_pool(b2b_env, config, slots)
    if int(pool.env_config.event_history_window) != window:
        pool.close()
        raise RuntimeError(
            f"pool event_history_window {pool.env_config.event_history_window} != "
            f"model event_window {window}")
    if not pool.env_config.oracle_observation:
        pool.close()
        raise RuntimeError("B2b pool must use oracle_observation=True")
    return pool


class _SlotMatch:
    """One in-flight match on a pool slot."""

    def __init__(self, match_index: int, base_seed: int) -> None:
        self.match_index = match_index
        self.seed = int(base_seed + match_index)
        self.sample_rng = np.random.default_rng([self.seed, 17])
        self.state = _B2bMatchState()
        self.rows: dict[str, list] | None = None   # set at finalize
        self.telemetry: dict | None = None
        self.skipped = False                        # ended at reset: emits nothing


def collect_b2b_rollouts_batched(env_config: EnvConfig, model: PolicyValueNet,
                                 config: PPOConfig, base_seed: int, pool,
                                 inference_mode: str = "batched",
                                 action_selection: str = "sample",
                                 diagnostics: Optional[dict] = None) -> RolloutBatch:
    """`diagnostics` (tests and `fh-mj-collect-bench` only) receives
    `pool_slots` (allocated), `effective_slots`, `peak_live_slots` and
    `rounds`; if the caller pre-creates `diagnostics["logits"]` as a list,
    every decision's masked logits row is appended to it as
    `(match_seed, seat, np.ndarray[A])` in decision order (gate G0.1b)."""
    if inference_mode not in ("batched", "per_row"):
        raise ValueError(f"unknown inference_mode: {inference_mode}")
    if action_selection not in ("sample", "greedy"):
        raise ValueError(f"action_selection must be 'sample' or 'greedy', got {action_selection!r}")
    cfg: EnvConfig = pool.env_config
    window = int(model.model_config.event_window)
    if int(cfg.event_history_window) != window:
        raise RuntimeError(
            f"pool event_history_window {cfg.event_history_window} != model event_window {window}")
    total = int(config.matches_per_iter)
    device = config.device
    temperature = config.sample_temperature
    chongci = config.match_mode == "chongci"
    bonus_on = config.placement_bonus_values is not None
    effective_slots = min(int(pool.slots), total)
    logger.info("batched B2b collector: pool_slots=%d matches=%d effective_slots=%d "
                "inference_mode=%s", pool.slots, total, effective_slots, inference_mode)
    model.eval()
    logits_sink = diagnostics.get("logits") if diagnostics is not None else None
    peak_live_slots = 0
    rounds = 0

    active: dict[int, _SlotMatch] = {}
    pending_action: dict[int, int] = {}
    completed: dict[int, _SlotMatch] = {}
    next_match = 0
    emit_next = 0
    rows_l: dict[str, list] = {key: [] for key in _B2B_ROW_KEYS}
    match_telemetry: list[dict] = []
    truncated_matches = 0
    completed_matches = 0
    outcomes_seen = 0

    def flush_in_seed_order() -> None:
        nonlocal emit_next
        while emit_next in completed:
            sm = completed.pop(emit_next)
            emit_next += 1
            if sm.skipped:
                continue
            for key in _B2B_ROW_KEYS:
                rows_l[key].extend(sm.rows[key])
            match_telemetry.append(sm.telemetry)

    while emit_next < total:
        commands = []
        for slot in range(effective_slots):
            if slot in pending_action:
                commands.append(PoolCommand(slot=slot, action_id=pending_action.pop(slot)))
            elif slot not in active and next_match < total:
                sm = _SlotMatch(next_match, base_seed)
                next_match += 1
                active[slot] = sm
                commands.append(PoolCommand(slot=slot, reset_seed=sm.seed))
        if not commands:
            raise RuntimeError(
                f"env pool wedged: {len(active)} slots active, "
                f"{total - emit_next} matches unemitted")
        result: PoolStepResult = pool.step(commands)
        rounds += 1
        peak_live_slots = max(peak_live_slots, len(active))

        pending_rows = []  # (slot, sm, seat, planes, scalars, mask, row_events, ev_len)
        for meta in result.slots:
            sm = active.get(meta.slot)
            if sm is None:
                continue
            if meta.error:
                raise RuntimeError(
                    f"env pool slot {meta.slot} (match seed {sm.seed}) failed: {meta.error}")
            ms = sm.state
            if (meta.terminated or meta.truncated) and not any(ms.seat_actions):
                # Ended at reset (no decision was ever taken): the process
                # collector skips such a match entirely — no rows, no telemetry.
                if bonus_on:
                    raise RuntimeError(
                        f"placement bonus: match seed {sm.seed} ended at reset "
                        "(no four-seat terminal standing) — fail closed")
                del active[meta.slot]
                sm.skipped = True
                completed[sm.match_index] = sm
                continue
            ms.credit_step_rewards(meta.step_rewards)
            if ms.record_outcome(meta.round_outcome):
                outcomes_seen += 1
            if meta.terminated or meta.truncated:
                del active[meta.slot]
                ms.truncated = bool(meta.truncated)
                if ms.truncated:
                    truncated_matches += 1
                else:
                    completed_matches += 1
                sm.rows, sm.telemetry = _finalize_b2b_match(ms, config, cfg, sm.seed)
                completed[sm.match_index] = sm
                continue
            if not meta.has_observation:
                continue
            row = result.row_of_slot[meta.slot]
            planes_np = np.array(result.planes[row], dtype=np.float32, copy=True)
            scalars_np = np.array(result.scalars[row], dtype=np.float32, copy=True)
            mask_np = np.array(result.action_masks[row], dtype=np.int8, copy=True)
            row_events = np.zeros(window, dtype=np.uint32)
            ev = np.asarray(result.event_histories[row], dtype=np.uint32)
            ev_len = min(int(ev.shape[0]), window)
            if ev_len > 0:
                row_events[:ev_len] = ev[-ev_len:]  # tail = newest events
            pending_rows.append((meta.slot, sm, int(meta.seat), planes_np, scalars_np,
                                 mask_np, row_events, ev_len))
        flush_in_seed_order()
        if not pending_rows:
            continue

        if inference_mode == "batched":
            planes_t = torch.from_numpy(np.stack([r[3] for r in pending_rows])).to(device)
            scalars_t = torch.from_numpy(np.stack([r[4] for r in pending_rows])).to(device)
            masks_t = torch.from_numpy(np.stack([r[5] for r in pending_rows])).to(device)
            events_t = torch.from_numpy(
                np.stack([r[6] for r in pending_rows]).astype(np.int64)).to(device)
            lengths_t = torch.tensor([r[7] for r in pending_rows], dtype=torch.int64, device=device)
            with torch.no_grad():
                logits_t, values_t = model(planes_t, scalars_t, masks_t,
                                           events=events_t, event_lengths=lengths_t)
            # ONE device->host transfer per round; every per-row op below
            # (sampling, masked_logprob) then runs on CPU tensors. Per-row
            # `.item()`/log_prob on device tensors would be one CUDA sync per
            # decision, which is exactly the batch-1 shape this collector exists
            # to remove.
            logits_cpu = logits_t.detach().cpu()
            logits_rows = [logits_cpu[i] for i in range(len(pending_rows))]
            values_rows = values_t.detach().reshape(-1).cpu().numpy().astype(np.float32).tolist()
        else:  # per_row: batch-composition-independent floats
            logits_rows, values_rows = [], []
            for _, _, _, planes_np, scalars_np, mask_np, row_events, ev_len in pending_rows:
                with torch.no_grad():
                    logits_1, value_1 = model(
                        torch.from_numpy(planes_np).unsqueeze(0).to(device),
                        torch.from_numpy(scalars_np).unsqueeze(0).to(device),
                        torch.from_numpy(mask_np).unsqueeze(0).to(device),
                        events=torch.from_numpy(row_events.astype(np.int64)).unsqueeze(0).to(device),
                        event_lengths=torch.tensor([ev_len], dtype=torch.int64, device=device),
                    )
                logits_rows.append(logits_1[0].detach().cpu())
                values_rows.append(float(value_1.reshape(-1)[0].item()))

        for i, (slot, sm, seat, planes_np, scalars_np, mask_np, row_events, ev_len) \
                in enumerate(pending_rows):
            logits_row = logits_rows[i]
            if action_selection == "greedy":
                action = int(torch.argmax(logits_row).item())
            else:
                action, _ = sample_masked_action(
                    logits_row.detach().cpu().numpy(), mask_np, temperature, sm.sample_rng)
            with torch.no_grad():
                logprob = masked_logprob(logits_row, temperature, action)  # CPU tensor
            if logits_sink is not None:
                logits_sink.append((sm.seed, seat, logits_row.numpy().copy()))
            ms = sm.state
            ms.seat_planes[seat].append(planes_np)
            ms.seat_scalars[seat].append(scalars_np)
            ms.seat_masks[seat].append(mask_np)
            ms.seat_actions[seat].append(action)
            ms.seat_logprobs[seat].append(logprob)
            ms.seat_values[seat].append(values_rows[i])
            ms.seat_rewards[seat].append(0.0)
            ms.seat_events[seat].append(row_events)
            ms.seat_lengths[seat].append(ev_len)
            ms.seat_hand_ids[seat].append(ms.hand_id)
            pending_action[slot] = action

    _check_chongci_outcomes(chongci, completed_matches, outcomes_seen)
    if diagnostics is not None:
        diagnostics.update(pool_slots=int(pool.slots), effective_slots=effective_slots,
                           peak_live_slots=peak_live_slots, rounds=rounds)
    if not rows_l["actions"]:
        raise RuntimeError("collect_b2b_rollouts_batched produced no decisions")
    return RolloutBatch(
        planes=np.stack(rows_l["planes"]).astype(np.float32),
        scalars=np.stack(rows_l["scalars"]).astype(np.float32),
        action_mask=np.stack(rows_l["masks"]).astype(np.int8),
        actions=np.asarray(rows_l["actions"], dtype=np.int64),
        old_logprobs=np.asarray(rows_l["logprobs"], dtype=np.float32),
        values=np.asarray(rows_l["values"], dtype=np.float32),
        rewards=np.asarray(rows_l["rewards"], dtype=np.float32),
        dones=np.asarray(rows_l["dones"], dtype=np.float32),
        truncated_matches=truncated_matches,
        events=np.stack(rows_l["events"]).astype(np.uint32),
        event_lengths=np.asarray(rows_l["lengths"], dtype=np.int32),
        dealin_labels=np.asarray(rows_l["dealin"], dtype=np.float32),
        rank_labels=np.asarray(rows_l["rank"], dtype=np.int64),
        match_telemetry=match_telemetry,
    )
