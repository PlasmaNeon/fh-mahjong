# Chongci Risk Target And Input Design

Status: first implementation calibrated and rejected. The model/trainer now
support action-conditioned risk heads over the 204-action catalog, but the first
calibration-only run on the existing input shape produced near-random large-loss
AUC. Visible match-history inputs and guarded evaluation remain future work.

## Problem

The current large-loss auxiliary is state-only and predicts:

```text
terminal_return <= -1.0
severity = max(-1.0 - terminal_return, 0)
```

This did not work well enough:

- filtered first-divergence replay kept too few exact rows,
- sparse-row oversampling exposed those rows but still did not improve policy,
- shared-gradient large-loss auxiliary training regressed the tail guardrail,
- lower auxiliary weights reproduced the same rejected behavior,
- calibration showed near-random large-loss AUC and flat risk bands.
- action-conditioned risk heads without richer visible history also failed the
  calibration gate.

The failure mode is not just coefficient tuning. The target and input are too
weak for the question we need answered.

## Design Goal

Learn a visible-information risk signal that answers:

```text
Given this seat state and a candidate operation, how much does this action
increase the probability and severity of a bad Chongci match outcome?
```

The key change is action-conditioned critic-side risk, not another state-only
auxiliary.

## Target

### Primary Target: Action-Conditioned Tail Value

For every stored transition, train the risk head only on the action that was
actually taken:

```text
risk_label = 1[terminal_match_return <= large_loss_threshold]
risk_severity = max(large_loss_threshold - terminal_match_return, 0)
```

The model predicts legal-action vectors:

```text
risk_logit(s, a)      for P(large loss | s, a)
risk_severity(s, a)   for expected severity beyond threshold
```

Loss is gathered at the dataset action:

```text
BCEWithLogits(risk_logit(s, action_id), risk_label)
SmoothL1(risk_severity(s, action_id), risk_severity)
```

Do not train risk on all unobserved legal actions yet. Offline data only tells
us the outcome after the observed action sequence.

### Secondary Target: Tail Advantage

After the action-conditioned risk head calibrates, derive:

```text
risk_advantage(s, a) = risk(s, a) - mean_legal_action_risk(s)
```

This is useful for a guard because it compares actions inside the same state,
instead of asking a poorly calibrated global risk probability to make the whole
decision.

### Avoid For Now

Do not use:

- discounted return for large-loss labels; the auxiliary was trained on terminal
  match return, so calibration should also use terminal match return,
- broad large-loss sample weighting over every transition,
- state-only risk probability as a serving guard,
- hidden tiles or wall information in deployed risk inputs.

## Inputs

The first version should stay visible-only and avoid a transformer. Use compact
history scalars that the Go environment can export deterministically.

### Existing Inputs To Keep

Current Chongci scalar context already includes:

- mode flag,
- hand progress,
- hands remaining,
- rank strength,
- leader pressure,
- large-loss safety margin,
- own bust safety,
- opponent large-loss pressure.

These should remain in the observation.

### New Visible History Inputs

Add a small match-history block to the scalar vector. Suggested features:

| Feature | Meaning |
|---------|---------|
| previous hand net delta | this seat's score delta in the previous hand |
| rolling 3-hand net delta | short-term score trend |
| largest single-hand loss so far | realized tail exposure |
| hands since last win | pressure / stagnation |
| hands since last deal-in or negative hand | defensive instability |
| own win count normalized | match momentum |
| own negative-hand count normalized | downside frequency |
| opponent max recent gain | whether another seat is accelerating |
| opponent max recent loss | whether a target is near bust |
| current hand number normalized | phase of match |

All of these are visible match history. None require concealed opponent hands.

Implementation note: if the Go engine does not yet preserve enough per-hand
history in `GameState`, add a small visible Chongci history accumulator to the
RL env wrapper or match state, then encode it into `SeatObservation.scalars`.

### Later History Model

If scalar history does not calibrate risk, use a short visible
action-observation sequence:

```text
last K decisions for this seat:
  action family
  action id
  immediate score delta if a hand ended
  hand number
  score vector summary
  scalar snapshot subset
```

Start with K = 16 or 32. A GRU/DTQN-style encoder is enough before trying a
larger transformer.

## Model

### V1 Risk Critic

Add a risk critic head parallel to the Q head:

```text
shared trunk
  policy head: logits over 204 actions
  value head
  q head
  risk probability head: 204 action logits
  risk severity head: 204 non-negative action values
```

Keep deployed action selection unchanged initially. The first checkpoint is a
calibration checkpoint, not a serving checkpoint.

### Loss

Use:

```text
total_loss =
  existing_iql_loss
  + risk_prob_weight * BCE(gathered_risk_logit, large_loss_label)
  + risk_severity_weight * SmoothL1(gathered_severity, severity_target)
```

Use class balancing or focal weighting because large-loss labels are sparse.
Recommended first setting:

```text
risk_prob_weight: 0.05
risk_severity_weight: 0.02
positive_class_weight: derived from batch label rate, capped at 10
detach_risk_features: false for training ablation, true for calibration-only ablation
```

Do not let the risk head directly override policy logits until calibration
passes.

## Guard Design After Calibration

Only if calibration passes, test a guard:

```text
policy_action = argmax(policy_logits over legal actions)
safe_candidates = top policy actions within policy_margin of policy_action
choose candidate with best:
  q_value - lambda * risk_advantage - mu * severity_advantage
```

Guard constraints:

- only consider legal actions,
- only choose among top policy candidates,
- never replace a legal win action unless explicitly tested as an ablation,
- require risk advantage margin before overriding,
- report override rate and action-family override table.

## Calibration Gate

Before online evaluation, the risk head must pass offline calibration on a held
out dataset:

```text
large-loss AUC >= 0.60
positive mean probability > negative mean probability by at least 0.05
risk bands mostly monotonic:
  higher predicted risk -> higher realized large-loss rate
severity MAE improves over constant mean baseline
```

If these fail, do not run guarded online evaluation.

## Promotion Gate

If calibration passes and a guard is tested, use the selected-window quick screen
first:

```text
seed windows: 534000:6, 544001:4, 554001:1
duplicate seats: true
compare against promoted anchor
```

Promote to repeated deterministic gate only if:

```text
mean reward >= anchor mean reward
large-loss rate <= anchor large-loss rate
positive reward rate does not regress materially
override rate is explainable and not broad policy drift
```

## Implementation Plan

1. Add scalar history features:
   - update `rlenv` scalar count,
   - encode visible previous-hand and rolling score history,
   - add Go tests proving values are visible-only and deterministic.
2. Add sharded storage for new scalar shape:
   - keep old checkpoint compatibility padding,
   - update AI docs and tests.
3. Add action-conditioned risk critic heads:
   - probability logits over 204 actions,
   - severity values over 204 actions,
   - gathered dataset-action losses.
   - Status: implemented in `PolicyValueNet.action_risk_predictions()` and the
     IQL large-loss auxiliary loss.
4. Add risk calibration report:
   - AUC/Brier/risk bands by action family,
   - severity baseline comparison,
   - top-risk action-family diagnostics.
   - Status: action-conditioned calibration is supported through
     `fh-mj-reward-calibration --large-loss-risk-mode action`.
5. Train calibration-only risk critic:
   - start from promoted anchor,
   - use current64 plus all-anchor risk-seed data,
   - no serving changes.
   - Status: first run completed and rejected at calibration gate
     (`large-loss AUC 0.4998`, Brier `0.3329`). Add visible history and
     score-pressure inputs before retraining.
6. If calibration passes, add guarded evaluator:
   - top-policy-candidate risk guard,
   - selected-window quick screen,
   - override diagnostics.

## Expected Outcome

This design should answer a more useful question than the failed auxiliary:

```text
Not "is this state globally risky?"
But "is this action riskier than nearby legal alternatives in this visible
match context?"
```

That is the signal needed for Chongci tail-risk control without flattening the
agent into overly defensive play.
