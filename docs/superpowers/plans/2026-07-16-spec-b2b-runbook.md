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
     --iterations 150 --matches-per-iter 256 --num-workers 5 \
     --lr 2e-5 --entropy-coef 0 --ppo-epochs 2 --gamma 1.0 \
     --match-mode chongci --max-steps-per-episode 4000 --device cuda

   (No MLflow — fh-mj-train-b2b logs history.json + stdout, matching the
   champion phaseB1 precedent. Confirm exact flag names against
   `fh-mj-train-b2b --help`; matches-per-iter 256 matches the champion
   pipeline — cross-check the progress note's run command before launching.)

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
   docs/rl-papers/chongci-rl-experiment-progress.md (win or lose).
   On promotion: write the B2c spec (serving integration) BEFORE deployment.
