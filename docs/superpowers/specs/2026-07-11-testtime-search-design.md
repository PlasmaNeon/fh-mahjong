# Test-Time Search (Phase 1 of Expert Iteration) — Design

**Date:** 2026-07-11
**Branch:** `claude/search-phase1` (off main @ f093071)
**Status:** Approved design → implementation plan next

## Goal

Wrap the frozen champion (`chongci_selfplay_deep4_phaseb1_iter275_39ch`, +0.4722 paired
placement vs the IQL anchor) in a pMCPA-style determinized search at decision time, and
gate it: **search-policy CI-beats the raw greedy champion in paired duplicate-seat eval.**
This is Phase 1 of expert iteration — the first mechanism that can *raise* the +0.4722
ceiling rather than approach it. Six training levers (batch scaling, exploitability,
hidden-info/belief, ACH, pool diversity, capacity/deep8) are tested and closed; the
plateau is pipeline-level.

Phase 1 targets **eval + data generation only** (offline, on the 4090). Live serving
stays the fast greedy champion; the search's strength reaches production via Phase-2
distillation (expert iteration), which is built only if Phase 1 gates.

## The correctness spine: honest determinization

`EvaluateBranches`/`CloneForBranch` clone the TRUE game state — the real wall order and
opponents' concealed hands. Rolling out on a raw clone is an oracle cheat (the campaign's
oracle-ceiling eval showed perfect info is worth ~0 as an *input*, but a search that
implicitly conditions on the true wall/hands is still dishonest and unshippable).

**Determinize = re-deal everything the acting seat cannot see.** For each clone:
collect the unseen pool (3 opponents' concealed hands + all undrawn wall tiles), shuffle
with a per-clone seed, deal back into the same slots preserving all counts. Everything
visible stays fixed: the acting seat's own hand, all open melds, flower melds, discards,
the wild indicator, scores, hand number, and the wall *count* / geometry.

**Dead-wall geometry constraint:** the wangpai boundary, wild-indicator index, and
already-consumed dead-wall indices are positions, not identities — they stay fixed; only
the identities of undrawn tiles shuffle. (The wild indicator itself is visible and never
re-dealt.)

**Testable honesty invariants:**
1. The acting seat's 39ch observation is bit-identical across all K determinizations.
2. Opponents' concealed hands differ across determinizations (for K > 1).
3. Unseen-pool conservation: the re-dealt multiset equals the original unseen multiset.
4. Seed determinism: same seed → same determinizations → same chosen action.

## Architecture (Approach A — Python drives, Go provides determinized clones)

Go remains the authoritative simulator; Python owns the model and the search loop, with
the champion **in-process on the GPU** (no HTTP anywhere in the hot path).

### 1. Go: determinized clone pool (`internal/rl/searchpool.go` + FFI in `cmd/rlbridge`)

- `NewSearchPool(env, K, seed)` — from the live env's current decision point, build K
  clones via `CloneForBranch`, each re-dealt per the rules above (per-clone seed derived
  from the pool seed).
- Apply: submit a candidate action id to a clone (decoded/validated through the same
  `legalActionMap` as everything else).
- Lockstep stepping à la `FHEnvPool`: each round of stepping returns, per live clone, the
  next acting seat's 39ch observation + action mask (all four seats are policy-driven),
  or the terminal result when the branch ends. Branch termination reuses the
  `stop_at_round_end` semantics from `EvaluateBranches` (Chongci round boundary), plus a
  `max_rollout_decisions` safety cap.
- Flat little-endian float32/uint8 buffers over the FFI, exactly like `FHEnvPool`.

### 2. Python: search loop (`ai/src/fh_mahjong_ai/search.py`)

```
priors, value = champion(obs)                      # the seat being searched
candidates = top-M legal actions by prior (M = max_candidates,
             cut when cumulative prior mass ≥ prior_mass_cutoff)
for each candidate:
    apply it to K determinized clones
roll ALL (M x K) clones forward in lockstep:
    every stepping round, batch every pending clone-decision through
    CheckpointPolicy.evaluate_batch; each clone's acting seat plays greedy champion
until each clone hits round end (or the decision cap)
score(clone)     = acting seat's realized round reward
                   + value_head(acting seat's next-round obs)     # match bootstrap
                   # next-round obs: the clone auto-acks the ROUND_END ready gate
                   # (existing chongci advanceToDecision behavior) and emits the
                   # first decision obs of the next hand. If the MATCH ended
                   # (bust / hand cap), there is no bootstrap: score = realized
                   # terminal match reward for the acting seat.
score(candidate) = mean over its K clones
chosen           = argmax over candidates
```

`SearchConfig`: `num_determinizations` (default 16), `max_candidates` (default 4),
`prior_mass_cutoff` (default 0.95), `max_rollout_decisions` (default 512), `seed`.

**Fail-open rule:** search must never crash or stall an eval. If a candidate's clones
error or hit the decision cap without a round end, that candidate keeps its prior-based
ranking (cap-hit clones score with the value head at the cap state); if the search as a
whole fails, the policy falls back to the greedy champion action for that decision.
Fallbacks are counted and reported.

### 3. Python: eval integration (`SearchPolicy` adapter)

`SearchPolicy` conforms to the same policy protocol the duplicate-seat eval harness
already accepts (the `SampledServingPolicy` precedent). The gate is literally
`fh-mj-evaluate --duplicate-seats` running SearchPolicy(champion) vs the raw champion on
identical seeds — fully paired, the campaign's standard 480-placement methodology.
Degenerate configs collapse cleanly: `max_candidates=1` ≡ greedy champion (regression
anchor).

## The Phase-1 gate

- Eval: 120 episodes × 4 duplicate rotations, seeds 870000+, chongci, max-hands 50 —
  SearchPolicy vs raw champion **paired**, anchor baseline alongside for ladder
  continuity.
- **PASS:** paired diff − CI95 > 0 vs the raw champion, and `large_loss_rate` no more
  than +0.02 worse. → Build Phase 2 (expert iteration; its own spec).
- **FAIL/parity:** one budget escalation (K 16→32, M 4→6). Still parity → stop; document
  that champion-rollout search adds nothing at feasible budgets and the plateau stands.
- Compute envelope: ~2–6 s/decision at K=16/M=4 on the 4090 (M×K rollouts × ~60 decisions,
  all net evals batched); the full gate ≈ 1–3 days of box time. Knobs trade this down.

## Phase-2 hook (designed now, built only if Phase 1 gates)

During search runs, an opt-in flag logs `(obs, per-candidate search scores, chosen
action)` NPZ rows in the existing IQL/BC dataset schema family. Distillation trains the
policy toward search-improved targets (cross-entropy on the search choice or soft targets
over candidate scores) and re-gates the **distilled net alone** vs the champion. Loop.
Details belong to the Phase-2 spec.

## Testing

1. **Go honesty invariants** (unit tests on constructed states): unseen-pool
   conservation; acting-seat observation invariance across determinizations; opponents
   differ across determinizations; dead-wall geometry (wangpai boundary, wild indicator,
   consumed indices) preserved; seed determinism.
2. **Go stepping:** lockstep semantics mirror `FHEnvPool` (reuse its test patterns);
   Chongci round-end stop; decision-cap truncation reported, not silently dropped.
3. **Python `SearchPolicy` on the mock bridge:** `max_candidates=1` exactly equals the
   greedy champion; fail-open on injected clone errors (falls back, counts it); output
   invariant to evaluate-batch chunk size.
4. **FFI determinism:** the same seed driven twice from Python yields identical chosen
   actions (batched-collector determinism-test pattern).
5. Full suites: `go test ./...` and `uv run --project ai pytest` green.

## Risks

- **Determinization bias:** uniform re-deal ignores inference from discards (a tenpai
  opponent's hand is not uniform). Accepted for v1 — the standard pMCPA simplification;
  weighting determinizations is a Phase-2+ refinement if the gate is marginal.
- **Value-head bootstrap error** at round boundaries — mitigated: it is the same value
  head trained on exactly these states all campaign.
- **Compute overrun:** bounded by the knobs and the single-escalation policy.
- **FFI lifecycle:** K clones are engine states (small); pool handles get explicit
  close + the same handle-registry discipline as `FHEnvPool`.

## Out of scope

- Live-serving search (latency engineering, prod compute) — Phase-2 distillation is the
  path to production strength.
- Weighted/inferred determinization, opponent modeling in rollouts.
- Phase-2 expert-iteration training loop — separate spec after the gate.
