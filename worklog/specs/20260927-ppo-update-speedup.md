# PPO update and iteration speedup

Status: **MERGED 2026-09-27** — PRs #247, #248, #250 (default path), #251, #252 (opt-in
modes), plus the env-pool scratch buffers. Follows
[`20260926-batched-b2b-collector-speedup.md`](20260926-batched-b2b-collector-speedup.md),
which left the PPO update as ~74% of an iteration.

## Result

4090 box, big-arm recipe (192×24, k=1, rezero, 960 matches, mb768, 2 epochs, host transfer,
batched collector, 320 slots):

| Configuration | Iteration | vs start |
|---|---|---|
| Before #247 | 18.2 min | 1× |
| Default path (cabaabc), measured on the live lap | 6.4 min | 2.8× |
| `--trunk-dtype bfloat16 --pool-pipeline-groups 2`, 2 measured iterations | 3.6 min | **5.1×** |

Update per step (synthetic rows): big arm 161 → 45.6 ms fp32, 22.4 ms bf16; anchor075 (96×4,
mb256) 18.3 → 5.2 ms. Collection, big model, 320 matches: 45.3 s → 31.8 s with two pipeline
groups.

## Causes

| Cause | Fix | Class |
|---|---|---|
| With aux heads the trunk ran twice per minibatch (`model(...)` then `model.encode(...)`) | Encode once; `PolicyValueNet.policy_value` | summation order |
| ~11 host syncs per step (`.item()`, `rank_mask.any()`, boolean indexing, `idx.cpu()`, distribution argument validation) | Device-side telemetry, masked rank loss, per-epoch permutation copy, `validate_args=False` | exact |
| cuDNN's heuristic picked a non-tensor-core wgrad kernel (56% of GPU time) | `cudnn.benchmark` scoped to `ppo_update` | summation order |
| Launch-bound step at anchor size | One CUDA graph per full minibatch; clip and optimizer eager | exact kernels |
| Pool stepping and the forward serialised | Opt-in pipeline groups, Go step on a worker thread | batch composition |
| fp32 convs | Opt-in bf16 encoder with channels_last weights | precision |
| Fresh ~3 MB response buffers every round | `EnvPool.StepMarshaled` scratch reuse | byte-identical |

Rejected on measurement: packed event GRU (slower), conv1d (no change), channels_last in
fp32 (no change), forcing fp32 convs (slower), 3+ pipeline groups (per-forward latency ~4.5 ms
regardless of rows), `torch.compile` (no Python headers for Triton on the box).

## bfloat16 fidelity

Float32 vs bf16 encoder on real greedy observations (`bf16_fidelity` probe):

| | anchor075 | bc-big 192×24 |
|---|---|---|
| mean policy KL | 4.8e-5 | 1.3e-5 |
| p99 KL | 8.0e-4 | 1.9e-4 |
| argmax agreement | 99.8% | 99.9% |
| PPO-gradient cosine | 0.999996 | 0.99999 |

The perturbation is ~1–5% of one update's approx_kl (~1e-3). A lap still has to confirm it:
bf16 and the pipeline groups are recipe fields, rejected on resume, never adopted mid-lap.

## Rules

- **Benchmark each variant in its own process.** cuDNN fixes a shape's plan the first time it
  sees it; running the old update first handed it the new code's tuned plans.
- **Collection is host-bound once the forward is graphed.** Pool stepping, per-row Python
  and sink writes dominate; more pipeline groups add forward latency instead of hiding it.
