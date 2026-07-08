# ACH (Actor-Critic Hedge) Regret Objective — Design

**Date:** 2026-07-07
**Branch:** `claude/ach-regret-objective` (off `origin/main` @ 070f5c5, the iter_275 production baseline)
**Status:** Approved design → implementation plan next

## Goal

Add a clipped-NeuRD / **ACH** regret objective as a drop-in alternative to PPO in the
self-play + feature-dropout pipeline, and run a controlled A/B to test whether it beats
the current **+0.4722** paired-placement ceiling (vs the IQL anchor at −0.0528) without
regressing large-loss.

## Why now (campaign context)

Three non-algorithmic levers are exhausted:

1. **Scaling saturated** — batch 256→320 broke the plateau to +0.4722 (iter_275), but
   320→448 (Phase B #2) bought nothing.
2. **Not exploitable** — a fair-budget PPO best-response could not beat the champion
   (mean_reward ≤ 0 throughout).
3. **Hidden information is worth ~0** — the oracle-ceiling eval put the 51ch net *with
   perfect information* at +0.4361 vs the deployed 39ch student's +0.4722 (gap −0.036,
   within ±0.082 CI = parity). Belief modeling is ruled out: if the *true* hidden hands
   don't help, an *estimate* of them can't.

The remaining axis is the **learning objective**. ACH is the regret-minimizing objective
behind LuckyJ, the strongest published mahjong AI, and it is a contained swap in our
existing pipeline.

## What ACH is

Policy `π(a|s) = softmax(y(s,·))` over masked logits `y`. Where PPO's clipped surrogate
gives a logit gradient carrying a softmax `(1−π)` factor (vanilla policy gradient), **NeuRD**
removes that factor so the logit gradient *is* the advantage — logits then accumulate
advantage the way CFR accumulates regret, which is why the fixed point is Nash-seeking in
imperfect-information games. **ACH** = NeuRD + a **hedge threshold β** that bounds logit
magnitude (a trust region replacing PPO's ratio clip), + a PPO-style clipped importance
ratio so the batch can be reused across epochs.

## Architecture & integration surface

The objective is the **only** thing that changes. Collectors, `compute_gae`,
`RolloutBatch`, feature-dropout δ, 39ch extraction, and `fh-mj-evaluate --from-oracle` are
all objective-agnostic and reused unchanged.

### New module: `ai/src/fh_mahjong_ai/ach.py`

One entry point with the **same signature as `ppo_update`**:

```python
def ach_update(model, optimizer, batch: RolloutBatch,
               advantages: np.ndarray, returns: np.ndarray,
               config: PPOConfig) -> dict:
    ...
```

It imports `masked_policy_distribution` from `ppo.py`; nothing else is shared or
duplicated. It does **not** add any field to `RolloutBatch` — the hedge threshold reads the
*current* logit from the forward pass, and the importance ratio uses the `old_logprobs`
already stored.

### The loss (per sampled transition `t`, taken action `a_t`, GAE advantage `Â_t`)

```
masked_logits, value = model(planes, scalars, action_mask)   # forward, minibatched
y_t   = masked_logits[row_t, a_t]                 # current logit of the taken action
new_logp = Categorical(logits=masked_logits).log_prob(a_t)
ρ_t   = clip(exp(new_logp − old_logp), 1−ε, 1+ε)  # ε = config.clip_eps
adv   = normalize(Â) if config.normalize_advantages else Â
w_t   = ρ_t · adv                                  # effective replicator weight

# hedge threshold β = config.ach_beta — zero the logit's gradient when it is already
# saturated in the direction w_t would push it:
saturated = (y_t ≥ +β) & (w_t > 0)  |  (y_t ≤ −β) & (w_t < 0)
y_eff = where(saturated, y_t.detach(), y_t)        # gradient blocked when saturated

policy_loss = −(y_eff · w_t).mean()                # ascent adds w_t to the unsaturated logit
value_loss  = mse(value, returns)                  # identical to PPO
entropy     = Categorical(logits=masked_logits).entropy().mean()
loss = policy_loss + config.value_coef·value_loss − config.entropy_coef·entropy
```

The gradient on the taken logit is exactly `w_t` when unsaturated and **0** when
saturated. This is clipped-NeuRD. The minibatch/epoch loop, optimizer step, and grad-norm
clip are identical to `ppo_update`; only the per-sample loss differs.

**Reported metrics** (the returned dict, for history + MLflow): `policy_loss`,
`value_loss`, `entropy`, `approx_kl` (from `old_logp − new_logp`, as PPO),
`clip_fraction` (fraction with `ρ_t` at a clip bound), and `saturated_fraction` (fraction of
samples whose logit gradient was blocked by β — the health signal for β tuning). Also log
`mean_abs_logit` to watch for logit blow-up.

### Config

Extend `PPOConfig` (already the campaign's kitchen-sink config) with:

- `objective: str = "ppo"` — `"ppo"` | `"ach"`; default preserves current behavior.
- `ach_beta: float = 2.0` — the hedge/logit trust-region threshold.
- reuse existing `clip_eps` for the importance-ratio bound `ε`.

### Trainer wiring — one line

In `train_selfplay_oracle` (`oracle.py`), select the update function once:

```python
update_fn = ach_update if config.objective == "ach" else ppo_update
...
metrics = update_fn(model, optimizer, batch, advantages, returns, config)
```

History already records per-iter metrics; add `objective` and `ach_beta` to the recorded
dict. No other trainer change.

### CLI

`fh-mj-train-selfplay-oracle` (`scripts/train_selfplay_oracle.py`) gains
`--objective {ppo,ach}` (default `ppo`) and `--ach-beta` (default 2.0), threaded into the
`PPOConfig`. The PPO control run is just `--objective ppo` — same code path, no
special-casing.

## Data flow

Identical to the PPO self-play loop: collect self-play rollouts (all-4 symmetric,
feature-dropout δ) → `compute_gae` → **`update_fn`** → save 51ch checkpoint → extract 39ch
student at eval time. The A/B resumes the δ=1 champion, so oracle channels stay masked
throughout (no schedule interaction).

## Validation — the A/B that decides the next phase

Run **operationally on the 4090** via box orchestration scripts (the established Phase-B
pattern: build the 51ch net, load `iter_275.pt`, loop calling the repo's objective-selected
update, with the array-release-at-iteration-end memory discipline). The reviewable repo
artifact is `ach_update` + wiring + tests; the run orchestration stays operational, as it
has all campaign.

**Two runs, same warm-start `iter_275.pt` (51ch, δ=1), single GPU → sequential:**

| | objective | else |
|---|---|---|
| Run A (ACH) | `ach`, `ach_beta=2.0` | 320 matches/iter, 10 workers, ~40 iters, lr 2e-5, entropy 0, ppo-epochs 2, max-grad-norm 0.5, chongci, max-steps 4000, cuda, δ held at 1 |
| Run B (PPO control) | `ppo` | identical |

**Eval:** extract the 39ch student and run `fh-mj-evaluate --from-oracle` paired vs the
anchor (−0.0528) at intervals (catch divergence early) + final. Both runs logged to MLflow.

**Gate (decides the campaign's next phase):**

- **ACH final paired_diff > PPO-control final, CI-separated, and large_loss ≤ control** →
  ACH is the lever. Scale it (longer run, β sweep, optional from-scratch confirmation) and
  promote if it clears +0.4722.
- **Parity** → ACH neutral here; keep PPO, document, move on. (Does not refute ACH
  globally — a warm-started PPO-converged net may be a poor place to see the gap; the
  from-scratch A/B is the only tiebreaker, spent only if warranted.)
- **ACH worse, or logits blow up** → β sweep (2.0 → {1.0, 4.0}) before abandoning; β is the
  trust region, and `saturated_fraction` / `mean_abs_logit` diagnose which way to move it.

## Testing (`ai/tests/`, `uv run --project ai pytest`)

1. **Hedge-threshold correctness (core test).** With `normalize_advantages=False`, single
   epoch, and a fresh batch (ρ ≈ 1, so `w_t ≈ Â_t`), construct a batch with a taken action
   whose logit is `> β` and `Â > 0` → assert its logit gradient ≈ 0; and another with
   logit `< β`, `Â > 0` → assert its logit gradient is nonzero and ≈ `Â_t`. This is what
   makes it ACH and not vanilla NeuRD. (Use a hand-built tiny model or gradient hooks on the
   logits.)
2. **NeuRD reduction.** With `β = +inf`, single epoch, `normalize_advantages=False`, and a
   freshly-collected batch (ρ ≈ 1), the taken logit's gradient ≈ advantage. Pins the base
   replicator update.
3. **Optimization sanity.** On a fixed toy batch, repeated `ach_update` raises the
   probability of the positive-advantage action (loss moves the policy the right way).
4. **Mechanics.** Advantage normalization honored; minibatching over `minibatch_size`;
   `ach_update` does not mutate `batch`; returned metrics dict has finite values and the new
   `saturated_fraction` / `mean_abs_logit` keys.
5. **Trainer integration.** `train_selfplay_oracle(..., config with objective="ach")` for
   2 iters on the mock env writes checkpoints + a `history.json` carrying `objective` and
   `ach_beta`.
6. **PPO regression.** `objective="ppo"` path is byte-unchanged — existing `ppo_update`
   tests still pass, the trainer default stays PPO, and a 2-iter mock run with the default
   config produces the same result as before this change.

## Risks & handling

- **Objective switch destabilizes a converged net** → lr already low (2e-5); if it
  diverges, lower lr or a short warm-up. Monitored via `mean_reward` / eval intervals.
- **Importance ratio explosion across epochs** → clipped by existing `clip_eps`; keep
  `ppo_epochs=2`.
- **Logit blow-up** → β is the guard; `mean_abs_logit` and `saturated_fraction` in history
  make it observable, and the β sweep is the response.

## Out of scope (deferred)

- First-class `--resume-checkpoint` / `--mlflow` flags and array-release in the *repo*
  trainers (`train_selfplay_oracle` / `train_oracle` / `train_ppo`) — the already-queued
  hygiene PR. The A/B uses the operational box-script resume, as Phase B did.
- Pure-NeuRD (β=∞) and β-sweep runs — cheap follow-up ablations *after* the gate, only if
  Run A shows promise.
- Any change to the self-play structure (all-4 symmetric, per-seat-contiguous GAE) — one
  variable at a time; the A/B isolates the objective.
```
