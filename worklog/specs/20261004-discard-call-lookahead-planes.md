# Discard and call look-ahead planes — design and registration

**Design approved in chat 2026-10-04** (feature set, plumbing, protocol). Codex consults are suspended until
the user re-enables them. The protocol below is registered before any run; the pre-launch measurements are
appended before launch.

## Question

Does giving the policy per-action look-ahead features — shanten and useful-tile counts after every legal
discard and call — produce a checkpoint that beats an identical lap without them, both played suit-averaged?

The encoder computes after-discard shanten and useful tiles for every discard (`shanten.AnalyzeHand`'s
`DiscardOptions`) but keeps only the best discard (scalars 33–35, 37, 40). For every other action the 4-block
CNN must derive wild-aware, three-route shanten from raw counts. Evidence that this arithmetic is noisy rather
than under-capacity: suit averaging alone is worth +0.037 (`20260929-suit-symmetry-probe.md`), while depth,
width, 3× data and a 192×24 net all nulled. Suphx supplies per-discard look-ahead features to its policy for
the same reason.

## Features (`lookahead_version = 1`, K = 13 channels)

Each feature sits in the tile-face column (0–41) of the face its action acts on, only where that action is
legal; every other cell is 0. The legality planes 30–35 tell "illegal" apart from a real 0. Shanten uses
`normalizeShanten` (scalar 25's scale); useful-tile counts use `normalizeUsefulTileCount` (÷64, clamped).

**Live useful tiles** = Σ over the useful faces of max(0, `Remaining` − copies visible to the seat), where
`Remaining` is `findUsefulTiles`' own-hand count and the visible copies are `publicSeenCounts` plus the wild
indicator tile.

| Channel | Family | Column | Value |
|---|---|---|---|
| 39 | discard | discarded face | overall shanten after the discard |
| 40 | discard | discarded face | standard-route shanten after |
| 41 | discard | discarded face | seven-pairs shanten after |
| 42 | discard | discarded face | Independence shanten after |
| 43 | discard | discarded face | useful tiles after (raw `TotalUseful`) |
| 44 | discard | discarded face | live useful tiles after |
| 45 | discard | discarded face | `publicDangerScore` of discarding this face |
| 46 | pon | claimed face | best standard shanten after the pon and a discard |
| 47 | pon | claimed face | live useful tiles at that best |
| 48 | chii | sequence start face | best standard shanten after the chii and a discard |
| 49 | chii | sequence start face | live useful tiles at that best |
| 50 | kan | kan face | standard shanten after the kan, before the replacement draw |
| 51 | kan | kan face | live useful tiles after the kan |

- **Calls.** The hand after a call is the closed hand minus the action's `meld_tiles` (the engine's own legal
  action, so no rule is reimplemented), analysed by `AnalyzeHand` with one more meld for a pon, chii, direct
  or closed kan; an upgraded kan converts an existing pon, so its meld count is unchanged. A call forfeits
  the seven-pairs and Independence routes, so only the standard route is reported; the current route
  shanten are already scalars 29–31.
- **"Best" is chosen by value** — lowest shanten, then most live useful tiles — so tied options give identical
  numbers and the features stay exactly suit-equivariant.
- **Kan** covers direct, closed and upgraded kans in one pair of channels: one face never has two kinds legal
  at once (a direct kan is a claim; closed and upgraded kans are own-turn and need different holdings).
- **Chii** actions are unique per sequence start face (`ChiiBase + suit·7 + start`), so the start column
  identifies the action.

## Mechanism

Off by default. At `lookahead_version = 0` every observation is byte-identical to today.

- **Wire.** `EnvConfig.lookahead_version` (proto field 8, `uint32`). Go and Python reject versions above 1.
  Go, TypeScript and Python bindings are regenerated (Python with protoc 33.5).
- **Go encoder.** A new `internal/rl/lookahead.go` computes the 13 channels. `encodeObservation` takes the
  version: plane channels are 39 + K, and the oracle threshold planes start at 39 + K. `Env`, `FHEnvPoolNew`
  and `NewSearchPool` pass the version through. The serving entry point `EncodeObservationWithEvents` stays
  at version 0.
- **Plane layout.** Policy `[0, 39+K)`, privileged `[39+K, 51+K)`. Every Python site that hard-codes 39 or
  51 — `_value_features`, `_b2b_model_env_config`, the oracle feature-dropout range, pool row widths — is
  rewritten in terms of `policy_channels`.
- **Model.** `ModelConfig.lookahead_version` is saved in checkpoint metadata; checkpoints without it read as 0.
  The plane stem and `policy_channels` take 39 + K input channels. Construction fails closed when the env's
  and the model's versions differ.
- **Warm start.** `build_b2b_model` widens the stem as `oracle.py` does: the init's 39 input columns are copied,
  the K new columns are zero, and `plane_stem.0.weight` joins the surgical tensor set.
- **Training.** `fh-mj-train-b2b --lookahead-version 1`, rejected-on-change by `--resume-from-state`.
- **Evaluation.** `fh-mj-evaluate` and `fh-mj-benchmark` take the version from checkpoint metadata; an explicit
  flag that disagrees is an error. Reports persist `lookahead_version`. `fh-mj-compare` gains
  `--allow-lookahead-mismatch`, labelled in its output like `--allow-window-mismatch`; the simulator digest
  must still match.
- **Serving.** `fh-mj-serve-policy` and the review tool refuse to load a checkpoint with version > 0. Serving
  support (the backend requesting the planes, as `RL_AGENT_EVENT_WINDOW` does for events) is a separate
  change, made only after a pass.

## Correctness gates (tests, before any run)

- Version 0: the three process-collector golden digests and the batched-collector parity and digest tests are
  unchanged.
- Version 1 feature values match hand-computed values on constructed states: each discard channel, a pon, a
  chii with two legal variants, a direct, a closed and an upgraded kan, a wild face, and a hand with
  Independence alive.
- The Go suit-equivariance test (`observation_symmetry_test.go`) covers version 1, and the Python
  `permute_rows` transform reproduces the encoder's version-1 rows for a permuted state.
- Oracle observations at version 1 put the opponents' hands at channels 52–63.
- Warm start from the real init gives identical step-zero logits, values, aux outputs and greedy actions.
- The CLI, resume, evaluator, compare and serving contracts above raise as specified.

## Protocol

| | features | control |
|---|---|---|
| Init | the winner of `20261003-control-confirmation.md`: control `iter_150` (`ea6d4d41…`) on a pass, else extension `iter_150` (`3fdfe246…`) | same |
| Recipe | batched collector, 256 slots, 1 group, 320 matches/iteration, minibatch 256, 2 epochs, lr 2e-5, entropy 0, γ 0.99, chongci, step cap 4000, event window 128, privileged critic, aux heads, fp32, `--suit-augment` | same |
| `--lookahead-version` | **1** | 0 |
| Iterations | 150 | 150 |
| Training seeds | 3,210,000–3,257,999 (never used) | the same seeds (paired) |

- Code: the implementation PR's merge commit, which descends from both rules fixes (`6c354655` wild runs,
  `785b3b85` prevailing wind); one bridge build at that commit for training and evaluation.
- The arms run one after the other on the box, never side by side (two arms outgrew the 24 GB GPU and
  stalled on 2026-10-03). Nothing else uses the GPU during an arm; peer sessions are told before each starts.

## Pre-launch measurements (recorded before launch; they do not change the protocol)

1. Step-zero parity of the widened net on the real init.
2. Pace, three iterations of each arm. If the features arm's collection takes more than 1.5× the control's,
   the lap does not launch and the slowdown is reported as an engineering problem, not a result.

## Evaluation (fixed now; no screening, no selection)

Only `iter_150` of each arm is evaluated, through the batched evaluator (256 slots, greedy,
`--symmetry-average suits`), on fresh seeds **3,260,000–3,269,999** (10,000 × 4 duplicate seats).

- **Primary:** features vs control. **Pass iff** clustered CI95 lower bound > 0 and large-loss(features) ≤
  large-loss(control) + 0.015.
- **Promotion:** features `iter_150` (suit-averaged) becomes the strongest registered policy iff the primary
  passes and features − init passes the same rule.
- **Descriptive:** control vs init.

A fail records the null: the arms are not extended, re-evaluated on another window, or rerun with another
feature set.

## Stage 2 (future, separate registration)

`lookahead_version = 2` adds, per legal discard, the solitaire win probability and expected hand score within
k wall draws, wild-aware — the deeper half of Suphx's look-ahead features. It needs its own design (search
depth, draw model, compute budget per decision) and registration whatever version 1's result.
