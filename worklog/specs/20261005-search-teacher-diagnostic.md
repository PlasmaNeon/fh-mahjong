# Search-teacher diagnostic — design

**Design approved in chat 2026-10-05** (approach, measurement, components, statistics). Codex consults are
suspended until the user re-enables them. A diagnostic, not a gate: it spends only screening seeds and decides
whether a registered gameplay probe of search is built at all.

## Question

Does belief-weighted determinized search, scored by the privileged critic, choose better than the suit-averaged
policy at the decisions where the policy is unsure? Expert iteration needs a teacher stronger than the policy; this
measures whether search can be that teacher before any gameplay or distillation is built.

The July search lost to the raw policy (`2026-07-11-testtime-search-design.md`): uniform re-deals, rollouts to round
end, the plain value head, and an argmax over candidates with no margin; a larger budget did worse because noisy
estimates overrode good greedy choices. Since then the B2b model gained a belief head (opponent tile thresholds)
and a privileged critic (value given the opponents' hands), and determinized clones already pair candidates on
common worlds, so a paired standard error can gate every override.

## Measurement

- **Policy.** `f9662491` (the strongest registered policy). The baseline decision is its suit-averaged greedy
  choice; every rollout continues with its plain greedy policy in all four seats.
- **States.** Self-play of `f9662491` (plain greedy, all four seats, chongci) on screening seeds 910,000+, never
  cited. A state is a root-seat discard decision where the suit-averaged policy's second-best action has
  probability ≥ 0.10; one in five such decisions is kept, until 4,000 states. Candidates are the suit-averaged
  policy's top three discards.
- **Ground truth.** For each candidate, a clone of the true state (real wall and hands, no re-deal) plays the
  candidate and continues to the end of the hand; R(a) is the root seat's dense reward summed to the round end
  (hand score delta / 1000). For a decision rule choosing a, Δ = R(a) − R(greedy). A single true-wall rollout is
  an unbiased sample of Q(a) − Q(greedy) for the information set, so the mean of Δ over states measures the
  rule's one-step improvement — what an expert-iteration teacher must deliver.
- **Search estimates.** Per candidate, 32 determinized worlds, paired across candidates:
  - **Sampler:** uniform re-deals, or belief-resampled — 256 uniform re-deals weighted by the belief head's
    likelihood at the root, 32 drawn by systematic resampling.
  - **Horizon:** to the root seat's next decision, scoring rewards plus the privileged critic's value there; or to
    the end of the hand, scoring rewards only.
  - **Decision rule:** choose the best candidate over the greedy one only if its paired gain exceeds z × SE,
    z ∈ {0, 1, 2}; otherwise keep the greedy choice. Resampling repeats worlds and a world's rollout is
    deterministic, so the belief sampler runs each distinct world once, weighted by its multiplicity, and the SE
    uses the effective number of worlds 1 / Σw²; with fewer than two distinct worlds only z = 0 may override.

  That is 2 samplers × 2 horizons × 3 margins = 12 rules, all scored on the same ground truth.

## Components

**Go (`internal/rl/searchpool.go`, proto `SearchPoolNewRequest`)**
- `oracle_planes`: clones emit oracle observations. Allowed because a re-dealt clone's hidden state is a sample,
  not the true hands; an oracle-configured live env is still refused.
- `true_state`: clones skip `RedealUnseen` and keep the real wall and hands. Ground truth only; combined with
  `oracle_planes` it is an error, so true hands never reach the network.
- `determinization_ids`: clone i re-deals world `ids[i % len(ids)]` (seed derived from the pool seed and the id,
  as today), so resampled worlds are reproduced exactly and stay paired across candidates.
- `RootObservations()` and an FFI export: each clone's root-seat observation before any step, so belief weights
  can be computed from the re-dealt hands.

**Python**
- `GoSearchPool` passes the three options and exposes `root_observations()`.
- `belief_weights.py`: the log-likelihood of a re-dealt world under the belief head at the root — the Bernoulli
  likelihood of the world's opponent threshold planes, the same target the head trains on (`ppo.py` belief
  loss) — and systematic resampling with the effective sample size reported.
- `fh-mj-search-diagnostic`: collects states, runs the ground truth and the 12 rules, and writes per-state records
  and the summary. Forward passes are batched across every clone of a state.

## Statistics and go/no-go

- Per state, Δ in hand-score/1000 units; Δ = 0 whenever a rule keeps the greedy choice.
- States from one game are correlated: CIs are clustered by game (t-interval over per-game sums).
- **Primary rule, fixed now:** belief-resampled sampler, next-decision horizon with the privileged critic, z = 1.
- **Go iff** the primary rule's clustered CI95 lower bound > 0. Any other rule qualifies only with its lower bound
  > 0 at Bonferroni level α = 0.05 / 11; it is reported and the user decides whether it goes forward.
- Reported for every rule: mean Δ ± CI, override rate, mean Δ when overriding, the rate at which the rule picks the
  true-wall best candidate (vs greedy's rate), and for the belief sampler the effective-sample-size and
  distinct-world distributions.
- **No-go** closes search-as-teacher: the diagnostic is recorded, nothing is rerun with tuned settings, and no
  gameplay probe is built.
- **Go** leads to a separately registered gameplay probe — the search policy vs suit-averaged `f9662491`, paired, on
  fresh seeds — and distillation only after that passes.

## Correctness gates (tests, before any run)

- Honesty: a re-dealt clone's root observation without oracle planes is byte-identical to the live env's root
  observation; `true_state` with `oracle_planes` is refused; an oracle-configured live env is still refused.
- `determinization_ids` reproduces the same world for the same id, across pools and candidates.
- `true_state` clones' rollouts match the live env stepped with the same actions.
- The belief log-likelihood equals minus the head's training BCE (summed) on the same planes.
- The driver runs end to end on a few states through the Go bridge, and Δ = 0 for every state where a rule keeps
  the greedy choice.

## Outcome — 2026-10-06: NO-GO

Commit `e4c08253`, bridge `4260be54…`, checkpoint `f9662491…`; 4,000 contested discard states from 391 self-play games
(seeds 910,000+), 01:51 PDT, about 80 minutes on the 4090. Δ in hand-score/1000 units, game-clustered CIs.

| rule | mean Δ ± CI | override rate |
|---|---|---|
| **belief / next / z1 (primary)** | **+0.0021 ± 0.0022** (lower −0.0001) | 0.296 |
| belief / next / z0, z2 | +0.0016 ± 0.0051, −0.0002 ± 0.0018 | 0.607, 0.113 |
| belief / hand / z0, z1, z2 | −0.0016, −0.0008, −0.0003 | 0.569, 0.175, 0.016 |
| uniform / next / z0, z1, z2 | +0.0024 ± 0.0050, +0.0020 ± 0.0036, +0.0010 ± 0.0029 | 0.585, 0.379, 0.227 |
| uniform / hand / z0, z1, z2 | +0.0030 ± 0.0056, +0.0024 ± 0.0033, +0.0004 ± 0.0019 | 0.624, 0.256, 0.039 |

- The primary rule's lower bound is below 0, and no other rule clears the Bonferroni level: **no-go**.
- Every rule's hindsight-best rate (0.72–0.74) matches the greedy choice's (0.734): search picks the true-wall best
  candidate no more often than the policy does.
- Belief weights are sharply peaked: effective sample size 1.2 / 2.7 / 6.5 (10th / 50th / 90th percentile) of 256
  worlds, 3 / 7 / 13 distinct worlds of 32.

Even at its point estimate the primary rule gains about 2 points per contested decision. Search with the privileged
critic does not choose better than the suit-averaged policy, so search-as-teacher is closed: no gameplay probe, no
reruns with tuned settings. Records: `/root/fh-mahjong-runs/search-diagnostic-20261006/`.
