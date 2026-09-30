"""The pre-2026-09-27 `ppo_update`, kept verbatim as a test oracle.

It encodes the trunk twice per minibatch when aux heads are on and syncs the host
with `.item()` every step. The production update must match it: identical forward
values, gradients equal up to float summation order.
"""
import numpy as np
import torch

from fh_mahjong_ai import memprobe
from fh_mahjong_ai.ppo import AUX_LOSS_WEIGHT, PPOConfig, RolloutBatch, masked_policy_distribution


def reference_ppo_update(
    model,
    optimizer,
    batch: RolloutBatch,
    advantages: np.ndarray,
    returns: np.ndarray,
    config: PPOConfig,
) -> dict:
    device = config.device
    n = len(batch)
    host_transfer = bool(getattr(config, "minibatch_device_transfer", False))
    # Per-row 1-D vectors are device-resident in BOTH paths: they are tiny
    # (a few MB even at 960 matches) and the global advantage-normalization
    # reduction must run on the same device as the legacy path to stay
    # byte-identical (Amendment 5 gauntlet condition 2).
    actions = torch.from_numpy(np.asarray(batch.actions, dtype=np.int64)).to(device)
    old_logprobs = torch.from_numpy(np.asarray(batch.old_logprobs, dtype=np.float32)).to(device)
    adv_t = torch.from_numpy(np.asarray(advantages, dtype=np.float32)).to(device)
    ret_t = torch.from_numpy(np.asarray(returns, dtype=np.float32)).to(device)
    if config.normalize_advantages:
        adv_t = (adv_t - adv_t.mean()) / (adv_t.std() + 1e-8)

    planes = scalars = action_mask = None
    planes_h = scalars_h = action_mask_h = None
    if host_transfer:
        # from_numpy shares the batch's buffers — no host copy here; each
        # minibatch is gathered on CPU and moved synchronously in the loop.
        planes_h = torch.from_numpy(np.asarray(batch.planes, dtype=np.float32))
        scalars_h = torch.from_numpy(np.asarray(batch.scalars, dtype=np.float32))
        action_mask_h = torch.from_numpy(np.asarray(batch.action_mask, dtype=np.int8))
    else:
        planes = torch.from_numpy(np.asarray(batch.planes, dtype=np.float32)).to(device)
        scalars = torch.from_numpy(np.asarray(batch.scalars, dtype=np.float32)).to(device)
        action_mask = torch.from_numpy(np.asarray(batch.action_mask, dtype=np.int8)).to(device)

    events_t = lengths_t = dealin_t = rank_t = None
    events_np = None
    if batch.events is not None:
        lengths_t = torch.from_numpy(np.asarray(batch.event_lengths, dtype=np.int64)).to(device)
        dealin_t = torch.from_numpy(np.asarray(batch.dealin_labels, dtype=np.float32)).to(device)
        rank_t = torch.from_numpy(np.asarray(batch.rank_labels, dtype=np.int64)).to(device)
        if host_transfer:
            # The uint32->int64 cast happens per minibatch (gauntlet condition
            # 4 allows it: the resulting device tensor is byte-identical to
            # the legacy full-cast) instead of materializing a 2x-size int64
            # copy of the whole event history on the host.
            events_np = np.asarray(batch.events)
        else:
            events_t = torch.from_numpy(np.asarray(batch.events, dtype=np.int64)).to(device)
    memprobe.probe("ppo_tensors_ready", rows=int(n), device=str(device),
                   host_transfer=host_transfer)

    model_config = getattr(model, "model_config", None)
    has_aux = bool(getattr(model_config, "aux_heads", False))
    belief_target = None
    if has_aux:
        plane_channels = (planes_h if host_transfer else planes).shape[1]
        if plane_channels < 51:
            raise ValueError(
                f"model has aux_heads enabled but planes have only {plane_channels} "
                "channels (need 51 for the belief-target oracle-threshold planes "
                "39:51); this would silently compute wrong belief targets."
            )
        if not host_transfer:
            belief_target = (planes[:, 39:51] > 0).float().squeeze(-1)

    # Telemetry is aggregated over ALL minibatches (row-weighted, so the
    # ragged final minibatch counts by its true size) rather than reporting
    # only the final minibatch's values — final-minibatch-only metrics are a
    # single-slice sample that cannot be compared across batch scales
    # (data-scale-960 Stage 0 prerequisite). `optimizer_steps` counts every
    # optimizer.step() taken, i.e. ppo_epochs * ceil(n / minibatch_size).
    metric_totals: dict[str, float] = {}
    rows_seen = 0
    optimizer_steps = 0
    model.train()
    for _ in range(config.ppo_epochs):
        perm = torch.randperm(n, device=device)
        for start in range(0, n, config.minibatch_size):
            idx = perm[start : start + config.minibatch_size]
            mb_lengths = lengths_t[idx] if lengths_t is not None else None
            if host_transfer:
                idx_h = idx.cpu()
                mb_planes = planes_h.index_select(0, idx_h).to(device)
                mb_scalars = scalars_h.index_select(0, idx_h).to(device)
                mb_mask = action_mask_h.index_select(0, idx_h).to(device)
                mb_events = (torch.from_numpy(
                    events_np[idx_h.numpy()].astype(np.int64)).to(device)
                    if events_np is not None else None)
            else:
                mb_planes = planes[idx]
                mb_scalars = scalars[idx]
                mb_mask = action_mask[idx]
                mb_events = events_t[idx] if events_t is not None else None
            masked_logits, value = model(mb_planes, mb_scalars, mb_mask,
                                         events=mb_events, event_lengths=mb_lengths)
            dist = masked_policy_distribution(masked_logits)
            new_logprobs = dist.log_prob(actions[idx])
            ratio = torch.exp(new_logprobs - old_logprobs[idx])
            mb_adv = adv_t[idx]
            surr1 = ratio * mb_adv
            surr2 = torch.clamp(ratio, 1.0 - config.clip_eps, 1.0 + config.clip_eps) * mb_adv
            policy_loss = -torch.min(surr1, surr2).mean()
            value_loss = torch.nn.functional.mse_loss(value, ret_t[idx])
            entropy = dist.entropy().mean()
            loss = policy_loss + config.value_coef * value_loss - config.entropy_coef * entropy

            aux_metrics = {}
            if has_aux:
                # In the legacy path belief_target was precomputed from the
                # full device-resident planes; in the host-transfer path it is
                # derived per minibatch from the SAME plane values (an exact
                # comparison, so the result is byte-identical either way).
                mb_belief = (belief_target[idx] if belief_target is not None
                             else (mb_planes[:, 39:51] > 0).float().squeeze(-1))
                features = model.encode(mb_planes, mb_scalars, mb_events, mb_lengths)
                aux = model.aux_predictions(features)
                belief_loss = torch.nn.functional.binary_cross_entropy_with_logits(
                    aux["belief"], mb_belief)
                dealin_loss = torch.nn.functional.binary_cross_entropy_with_logits(
                    aux["dealin"], dealin_t[idx])
                rank_mask = rank_t[idx] >= 0
                if rank_mask.any():
                    rank_loss = torch.nn.functional.cross_entropy(
                        aux["rank"][rank_mask], rank_t[idx][rank_mask])
                else:
                    rank_loss = torch.zeros((), device=device)
                loss = loss + AUX_LOSS_WEIGHT * (belief_loss + dealin_loss + rank_loss)
                aux_metrics = {
                    "belief_loss": float(belief_loss.item()),
                    "dealin_loss": float(dealin_loss.item()),
                    "rank_loss": float(rank_loss.item()),
                }

            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), config.max_grad_norm)
            optimizer.step()

            with torch.no_grad():
                approx_kl = (old_logprobs[idx] - new_logprobs).mean()
                clip_fraction = (torch.abs(ratio - 1.0) > config.clip_eps).float().mean()
            step_metrics = {
                "policy_loss": float(policy_loss.item()),
                "value_loss": float(value_loss.item()),
                "entropy": float(entropy.item()),
                "approx_kl": float(approx_kl.item()),
                "clip_fraction": float(clip_fraction.item()),
                **aux_metrics,
            }
            mb_rows = int(idx.shape[0])
            rows_seen += mb_rows
            optimizer_steps += 1
            for key, value in step_metrics.items():
                metric_totals[key] = metric_totals.get(key, 0.0) + value * mb_rows
    if rows_seen:
        metrics = {key: total / rows_seen for key, total in metric_totals.items()}
    else:  # ppo_epochs == 0: keep the historical zeroed shape
        metrics = {"policy_loss": 0.0, "value_loss": 0.0, "entropy": 0.0,
                   "approx_kl": 0.0, "clip_fraction": 0.0}
    metrics["optimizer_steps"] = optimizer_steps
    memprobe.probe("ppo_update_done", rows=int(n), optimizer_steps=int(optimizer_steps))
    return metrics
