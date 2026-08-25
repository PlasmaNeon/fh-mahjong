# B2b Run Protocol (post-merge, RTX 4090 box)

Prereqs: merged main pulled on the box (`ssh wsl`, /root/fh-mahjong); bridge
rebuilt (`go build -buildmode=c-shared -o build/libfh_mahjong_bridge.so ./cmd/rlbridge`).
Champion: /root/fh-mahjong-runs/deploy/selfplay-deep4-student-iter275-39ch.pt.
Champion screening report: /root/fh-mahjong-runs/spec-a/champion-fixed.json.

1. Train (150 iters; checkpoint every iter — pruning later is cheaper than regret):

   /root/.local/bin/uv run --project ai fh-mj-train-b2b \
     --champion /root/fh-mahjong-runs/deploy/selfplay-deep4-student-iter275-39ch.pt \
     --checkpoint-dir /root/fh-mahjong-runs/b2b/ckpt \
     --model-residual-blocks 4 --event-window 128 \
     --iterations 150 --matches-per-iter 320 --num-workers 5 \
     --lr 2e-5 --entropy-coef 0 --ppo-epochs 2 --gamma 0.99 \
     --match-mode chongci --max-steps-per-episode 4000 --device cuda

   (Reward = dense per-hand score deltas at gamma 0.99, matches-per-iter
   320 — the exact champion phaseB1 recipe per the authoritative manifest
   (ai/checkpoints/best-checkpoints.json: matches_per_iter=320, gamma=0.99;
   the 256->320 batch increase was itself the Phase B improvement). The
   spec's earlier "GRP placement reward (gamma=1)" wording was stale
   nomenclature, corrected 2026-07-18. No MLflow — fh-mj-train-b2b
   logs history.json + stdout, matching the champion phaseB1 precedent.
   Watch dealin_positive_rate and rank_label_coverage in history.json: an
   all-zero deal-in rate is the corrupted-supervision signature (the
   collector also fails fast on zero outcomes). Confirm exact flag names against
   `fh-mj-train-b2b --help`; cross-check the progress note's run command before launching.)

2. Screening at iters 25/50/75/100/125/150:

   fh-mj-evaluate --checkpoint /root/fh-mahjong-runs/b2b/ckpt/iter_XXX.pt \
     --model-residual-blocks 4 --model-event-window 128 \
     --model-privileged-critic --model-aux-heads \
     --event-history-window 128 --duplicate-seats --online-episodes 120 \
     --start-seed 910000 --match-mode chongci --device cuda \
     --report-output /root/fh-mahjong-runs/b2b/screen-XXX.json

   then: fh-mj-compare /root/fh-mahjong-runs/b2b/screen-XXX.json \
           /root/fh-mahjong-runs/spec-a/champion-fixed.json --allow-missing-config
   (The champion report predates the persisted event_history_window key, so
   screening comparisons need the legacy opt-in — they are LOOKS, not gates.
   The confirmation gate below regenerates BOTH reports post-B2b and compares
   STRICT.)

3. KILL RULE: at iter >= 50, paired screening delta < -0.06 -> stop, diagnose,
   report (scratch run or aux-weight change is a NEW user decision).

4. Promotion gate: best screening checkpoint ->
   BOTH the candidate (flags as in step 2) AND the champion
   (--model-residual-blocks 4, no event/priv/aux flags, no window) evaluated on
   --start-seed 950000 --online-episodes 1500 (~6h each), same bridge, then
   fh-mj-compare candidate.json champion.json --allow-window-mismatch
   (Both reports post-B2b carry all keys; the ONLY config difference is
   event_history_window 128-vs-0 — the intervention under test. The flag
   permits exactly that mismatch and stamps window_check=mismatch-allowed
   in the verdict; everything else stays strict: same bridge digest, same
   seeds, same chongci config.)

5. Record the outcome + per-head loss curves (belief/dealin/rank) in
   worklog/rl-experiment/chongci-rl-experiment-progress.md (win or lose).
   On promotion: write the B2c spec (serving integration) BEFORE deployment.


---

# RATIFIED GATE PROTOCOL (2026-07-19)

Jointly agreed with Codex (GPT-5.6-Sol, debate to agreement per the standing
consult rule; side thread 019f7958-3acc-7061-93ab-7207c6772bd0 — future
consults live in the canonical session 019f49e8-8f48-7042-b176-df12d8719753).
This section SUPERSEDES steps 2-4 above where they differ. Transcribed
verbatim from Codex's ratification message:

The terminal fallback needs one correction: three champion repeats alone cannot estimate candidate-side run-level variance. Use three repeats of both the champion and the frozen selected candidate on the 120-seed screening window, then widen the promotion CI by both measured run-level variances. This remains conservative because screening-window run variance is carried unscaled into the larger confirmation window.

One consistency correction: B2b remains at `gamma=0.99`; `gamma=1` belongs to the separate deferred objective ablation and is not part of this run.

## RATIFIED 10-item next-step list

1. Continue the unchanged B2b run through iter 150 using the exact champion recipe: dense score-delta rewards, `gamma=0.99`, 320 matches per iteration, learning rate `2e-5`, entropy coefficient `0`, two PPO epochs, five workers, and event window 128. Run the already-chained screenings at iterations 75, 100, 125, and 150. Make no mid-run hyperparameter changes and launch no ablations.

2. Compare every screening checkpoint against one champion screening report produced on the identical current bridge and `910000+` seed window. Require matching seed lists, bridge digest, Chongci configuration, step cap, greedy protocol, and all other persisted configuration; `--allow-window-mismatch` is the only permitted relaxation because candidate window 128 versus champion window 0 is the intervention.

3. At iter 150, extend exactly once to iter 200 only if all three conditions hold: iter 150 is the best champion-relative screening checkpoint; the champion-relative point estimates at iterations 100, 125, and 150 are nondecreasing; and a direct iter-150-minus-iter-100 `fh-mj-compare` has a positive paired delta whose clustered 95% CI clears zero. That direct comparison is fully strict—both reports use window 128, so no relaxation is permitted. If extended, screen at iterations 175 and 200 and stop unconditionally at 200; otherwise stop at 150.

4. Select exactly one eligible checkpoint: the checkpoint with the largest same-bridge champion-relative screening delta among all planned checkpoints, including 175/200 only if the extension occurred. Eligibility requires healthy supervision telemetry and zero screening truncation; exact ties go to the later checkpoint. Freeze its path and SHA-256 before opening the confirmation window, and do not substitute a runner-up after seeing confirmation results.

5. Before confirmation, rerun the champion once on the current bridge and `910000+` screening window. Require exact equality with `champion-screen-current-bridge.json` for every seed’s four rotation-level placements and large-loss indicators; harmless JSON formatting or derived floating-summary differences do not count. If these discrete outcomes match exactly, proceed to confirmation.

6. On any repeatability mismatch, block confirmation and diagnose before using a tolerance fallback: run a third champion repeat, isolate the exact differing seeds and actions, and seek a deterministic execution path such as CPU inference or fixed deterministic CUDA configuration. If a deterministic path is found, verify exact repeatability and use that identical path for both confirmation sides. Do not proceed merely because two aggregate means agree within a numerical tolerance.

7. If no practical deterministic path can be obtained, use the terminal replicated-variance fallback. On the frozen `910000+` screen, obtain three complete repeats each for the champion and selected candidate; let `s_C²` and `s_B²` be the sample variances of their three run-level mean placements. For confirmation per-seed placement deltas `d_i`, calculate:

   `SE_seed² = Var(d_i) / 1500`

   `V_total = SE_seed² + s_C² + s_B²`

   `df = V_total² / (SE_seed⁴/1499 + s_C⁴/2 + s_B⁴/2)`

   Use the widened two-sided 95% half-width `t(0.975, df) × sqrt(V_total)`. Promotion requires `mean(d_i) - half_width > 0`. Record that the fallback was activated and preserve all six screening-repeat reports.

8. Apply the ratified tail-risk criterion: promotion additionally requires `candidate_large_loss_rate - champion_large_loss_rate ≤ +0.015` absolute on confirmation. For each confirmation seed `i`, record the exact paired seed-clustered value

   `d_i_LL = (1/4) × Σ_rotation [I(candidate large loss) - I(champion large loss)]`

   and record

   `Δ_LL = (1/1500) × Σ_i d_i_LL`

   together with its two-sided clustered 95% t-interval:

   `Δ_LL ± t(0.975,1499) × SD(d_i_LL)/sqrt(1500)`.

9. Run the selected candidate and champion back-to-back on `950000+`, 1500 seeds each, without pulling, rebuilding, changing dependencies, or replacing artifacts. Record the main commit, bridge digest, checkpoint SHA-256s, dependency-lock digest, Torch/CUDA versions, exact commands, both reports, and `fh-mj-compare --json` output. Require zero truncations, `config_check=strict`, `bridge_check=match`, only `window_check=mismatch-allowed`, a positive placement lower confidence bound under the applicable CI rule, and the item-8 tail criterion; do not optional-stop or gate another checkpoint on this window.

10. If all promotion criteria pass, record the outcome and write Spec B2c before any deployment. If any criterion fails, record the negative result, retire `950000+`, and make the next ablation a new explicit user decision—no automatic aux-weight, window, or scratch run. Independently document the historical champion shift from `+0.3500` to `+0.4035`, beginning with intervening simulator/rules changes and bridge/environment provenance, without allowing that cross-build level discrepancy to override a valid same-bridge result.
