"""Determinized champion-rollout search (`SearchPolicy`).

At the root decision, take the checkpoint's top actions (by prior mass, capped
by `max_candidates` / `prior_mass_cutoff`), then score each by determinized
rollouts: clone the current decision point into `num_determinizations` worlds
per candidate, apply the candidate on the first step, and roll the champion
(masked greedy argmax over `evaluate_batch`) forward in lockstep. Each clone
accumulates the root seat's per-step reward, DISCOUNTED to match the champion
value head's training convention (see `_rollout_scores` for the derivation); a
round boundary or a truncation cap bootstraps with the discounted value head of
the returned observation; a terminal state is scored by the accumulated
(discounted, telescoping) rewards alone. A candidate's score is the mean over
its surviving clones. The best-scoring candidate's action is returned.

Fail-open: any exception in the search path (including the pool factory) yields
the plain greedy action and increments `fallback_count`. If *every* clone of a
candidate errors, that candidate scores ``-inf`` unless it is the greedy action
(kept at the root value estimate so it retains its prior rank), and a fallback
is counted.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Sequence

import numpy as np

from .envpool import PoolCommand
from .policies import ActionChoice


@dataclass(frozen=True)
class SearchConfig:
    num_determinizations: int = 16
    max_candidates: int = 4
    prior_mass_cutoff: float = 0.95
    max_rollout_decisions: int = 512
    seed: int = 1
    # Per-root-decision discount. The champion value head was trained with
    # gamma=0.99 GAE over per-seat-contiguous trajectories, so rollout scores
    # must discount by ROOT-seat decision horizon (not raw step count) to match
    # the value the head predicts. gamma=1.0 recovers the old undiscounted sum.
    discount_gamma: float = 0.99


PoolFactory = Callable[..., Any]


class SearchPolicy:
    """ActionChoice-protocol policy: determinized champion-rollout search.

    ``pool_factory(num_clones, seed, max_rollout_decisions, determinizations=K)
    -> pool`` with ``.step(commands) -> SearchStepResult`` and ``.close()``.
    ``determinizations`` is the common-random-numbers pairing group count K (the
    clone count num_clones is M candidates x K), passed as a keyword so clones
    sharing a determinization face a paired hidden world + sampled future.
    Production wires ``GoSearchPool`` over the live eval bridge; tests inject
    fakes.
    """

    def __init__(self, checkpoint_policy: Any, pool_factory: PoolFactory, config: SearchConfig) -> None:
        self._policy = checkpoint_policy
        self._pool_factory = pool_factory
        self._config = config
        self._fallbacks = 0

    @property
    def fallback_count(self) -> int:
        return self._fallbacks

    def choose(self, observation) -> ActionChoice:
        greedy = self._policy.choose(observation)
        try:
            probs, values = self._policy.evaluate_batch(
                observation.planes[None], observation.scalars[None], observation.action_mask[None]
            )
            prior = probs[0]
            root_value = float(values[0])
            order = np.argsort(-prior)
            candidates: list[int] = []
            mass = 0.0
            for a in order:
                if prior[a] <= 0.0 or len(candidates) >= self._config.max_candidates:
                    break
                candidates.append(int(a))
                mass += float(prior[a])
                if mass >= self._config.prior_mass_cutoff:
                    break
            if len(candidates) <= 1:
                return self._as_choice(greedy)

            K = self._config.num_determinizations
            pool = self._pool_factory(
                len(candidates) * K, self._config.seed, self._config.max_rollout_decisions,
                determinizations=K,
            )
            try:
                scores = self._rollout_scores(
                    pool, candidates, K, int(observation.seat), int(greedy.action_id), root_value
                )
            finally:
                pool.close()
            best = candidates[int(np.argmax(scores))]
            return ActionChoice(
                action_id=best,
                value=greedy.value,
                info={
                    "source": "search",
                    "greedy_action_id": int(greedy.action_id),
                    "candidates": candidates,
                    "scores": [float(s) for s in scores],
                },
            )
        except Exception:
            self._fallbacks += 1
            return self._as_choice(greedy)

    # --- internals ---------------------------------------------------------

    def _as_choice(self, greedy) -> ActionChoice:
        return ActionChoice(
            action_id=int(greedy.action_id),
            value=greedy.value,
            info={"source": "greedy", "greedy_action_id": int(greedy.action_id)},
        )

    def _rollout_scores(
        self,
        pool,
        candidates: Sequence[int],
        K: int,
        root_seat: int,
        greedy_action: int,
        root_value: float,
    ) -> np.ndarray:
        n = len(candidates) * K
        scores = np.zeros(n, dtype=np.float64)
        done = np.zeros(n, dtype=bool)
        errored = np.zeros(n, dtype=bool)
        # Per-clone ROOT-seat decision horizon t (see derivation below). The root
        # candidate apply is root-decision 0, so every clone starts at t=0.
        horizon = np.zeros(n, dtype=np.int64)

        # --- Discount convention (must match training) ----------------------
        # The champion value head is trained by compute_gae (ppo.py) over
        # PER-SEAT-CONTIGUOUS trajectories (oracle.py): one timestep = one
        # ROOT-seat decision, and the reward at root-decision k is the sum of the
        # root seat's score deltas that accrue between root decisions k and k+1
        # (oracle credits every step's delta to the seat's CURRENT last decision).
        # compute_gae's delta_t = r_t + gamma*V(t+1) - V(t) makes the value head
        # predict the return
        #     G_0 = sum_{k=0..T-1} gamma^k * r_k + gamma^T * V(s_T),
        # where r_k is root-decision chunk k and s_T is the root seat's next
        # decision state that stands one root-step past the last reward chunk.
        # A terminal (done=1) trajectory drops the bootstrap.
        #
        # So per clone we track t = the root-decision horizon:
        #   * t starts at 0 (the candidate apply IS root-decision 0);
        #   * a reward absorbed while the clone sits at horizon t carries gamma^t;
        #   * t increments the moment we ISSUE the clone's NEXT root-seat decision
        #     (its current observation row's seat == the fixed root seat), BEFORE
        #     absorbing that step's reward -- so every reward between root
        #     decisions k and k+1 carries gamma^k (chunk k), exactly like the
        #     oracle bucketing;
        #   * the round-end / truncation / cap bootstrap value carries gamma^(t+1)
        #     because the returned observation is the root's NEXT-decision state,
        #     one root-step past the last absorbed chunk (chunk index T = t+1).
        # Sanity: a round that ends on the very first apply (zero intermediate
        # root decisions) scores r_0 + gamma^1 * V(next) -- reward chunk 0 at
        # gamma^0 plus the one-step-ahead bootstrap at gamma^1. gamma=1.0 collapses
        # every weight to 1 and recovers the old undiscounted reward sum.

        # First step: apply each candidate to its clones. The response already
        # carries rewards and may terminate / end a round / truncate / error
        # some clones immediately, so absorb it exactly like any other step.
        commands = [PoolCommand(slot=s, action_id=int(candidates[s // K])) for s in range(n)]
        result = pool.step(commands)
        self._absorb(result, root_seat, scores, done, errored, horizon, active=set(range(n)))

        # Champion lockstep rollout of the still-live clones. Go defers ITS cap
        # (max_rollout_decisions) to the root seat's next decision, so a clone
        # can still be mid-foreign-seat-turn when Go's cap fires; this Python
        # loop bound is intentionally slack (2x + 32) so Go's truncated/
        # round_ended rows are the normal cutoff signal and reach `_absorb`
        # first. Go owns truncation semantics; this bound is a defensive
        # backstop only, in case a pool implementation never truncates.
        for _ in range(2 * self._config.max_rollout_decisions + 32):
            active = [s for s in range(n) if not done[s]]
            if not active:
                break
            rows = [(s, result.row_of_slot[s]) for s in active if s in result.row_of_slot]
            if not rows:
                break
            # A root-seat decision is about to be issued for any clone whose
            # current observation row is the root seat -> advance its horizon
            # BEFORE we absorb the reward this decision produces (chunk k+1).
            seat_of_slot = {meta.slot: int(meta.seat) for meta in result.slots}
            for s, _ in rows:
                if seat_of_slot.get(s) == root_seat:
                    horizon[s] += 1
            planes = np.stack([result.planes[r] for _, r in rows])
            scalars = np.stack([result.scalars[r] for _, r in rows])
            masks = np.stack([result.action_masks[r] for _, r in rows])
            probs, _ = self._policy.evaluate_batch(planes, scalars, masks)
            action_of = {s: int(np.argmax(probs[i])) for i, (s, _) in enumerate(rows)}

            active_set = set(action_of)
            commands = [
                PoolCommand(slot=s, action_id=action_of[s]) if s in active_set else PoolCommand(slot=s)
                for s in range(n)
            ]
            result = pool.step(commands)
            self._absorb(result, root_seat, scores, done, errored, horizon, active=active_set)
        else:
            # Decision cap hit with clones still live: bootstrap them like a
            # truncation with the value of their current observation row --
            # but ONLY if that row is a genuine root-seat decision. Go defers
            # its own cap to the root seat's next decision, so this Python
            # backstop firing mid-foreign-seat-turn means the clone never
            # reached a scoreable root-seat state; value-bootstrapping a
            # foreign-seat row would feed the value head an out-of-distribution
            # input (the exact OOD failure mode eliminated on the Go side).
            # Treat it like a per-clone error instead: exclude it from its
            # candidate's mean via the existing `errored` drop path.
            self._bootstrap_live(result, scores, done, errored, horizon, root_seat)

        return self._aggregate(scores, errored, candidates, K, greedy_action, root_value)

    def _absorb(self, result, root_seat, scores, done, errored, horizon, active) -> None:
        """Fold one step response into per-clone scores, batching value bootstraps.

        Rewards absorbed at a clone's current horizon t carry gamma^t; round-end /
        truncation bootstraps carry gamma^(t+1) (see the derivation in
        `_rollout_scores`).
        """
        gamma = self._config.discount_gamma
        bootstrap: list[tuple[int, int]] = []  # (slot, row)
        for meta in result.slots:
            s = meta.slot
            if s not in active:  # skip command -> already scored / done
                continue
            rewards = meta.step_rewards
            if rewards.size > root_seat:
                scores[s] += (gamma ** int(horizon[s])) * float(rewards[root_seat])
            if meta.error:
                errored[s] = True
                done[s] = True
                continue
            if meta.terminated:
                done[s] = True  # accumulated (discounted) reward is final, no bootstrap
                continue
            round_ended = result.round_ended.get(s, False)
            if meta.truncated or round_ended:
                if s in result.row_of_slot:
                    bootstrap.append((s, result.row_of_slot[s]))
                done[s] = True
                continue
            # else: still live with an observation -> keep rolling
        if bootstrap:
            self._add_value_bootstrap(result, scores, bootstrap, horizon)

    def _bootstrap_live(self, result, scores, done, errored, horizon, root_seat) -> None:
        seat_of_slot = {meta.slot: int(meta.seat) for meta in result.slots}
        live = [
            s
            for s in range(len(done))
            if not done[s] and s in result.row_of_slot
        ]
        bootstrap: list[tuple[int, int]] = []
        for s in live:
            done[s] = True
            if seat_of_slot.get(s) == root_seat:
                bootstrap.append((s, result.row_of_slot[s]))
            else:
                # Foreign-seat row at cutoff: the clone never reached a
                # scoreable root-seat state. Exclude it from its candidate's
                # mean via the same path used for per-clone errors, rather
                # than value-bootstrapping an out-of-distribution row.
                errored[s] = True
        if bootstrap:
            self._add_value_bootstrap(result, scores, bootstrap, horizon)

    def _add_value_bootstrap(self, result, scores, bootstrap: list[tuple[int, int]], horizon) -> None:
        planes = np.stack([result.planes[r] for _, r in bootstrap])
        scalars = np.stack([result.scalars[r] for _, r in bootstrap])
        # Bootstrap rows are now the root seat's GENUINE next decision state, which
        # the Go pool emits with its REAL action mask (in-distribution for the
        # champion value head). We pass the mask through UNCHANGED: an all-zero mask
        # reaching here would be a contract violation, so we let evaluate_batch's
        # no-legal-actions guard raise -> the search fails open (drops to greedy),
        # which is the correct response to a broken bootstrap row. (Sanitizing to
        # all-ones would silently mask that violation.)
        masks = np.stack([result.action_masks[r] for _, r in bootstrap])
        _, values = self._policy.evaluate_batch(planes, scalars, masks)
        gamma = self._config.discount_gamma
        for i, (s, _) in enumerate(bootstrap):
            # The bootstrap state stands one root-step past the last reward chunk
            # (chunk index T = horizon[s] + 1), so it carries gamma^(t+1).
            scores[s] += (gamma ** (int(horizon[s]) + 1)) * float(values[i])

    def _aggregate(self, scores, errored, candidates, K, greedy_action, root_value) -> np.ndarray:
        out = np.empty(len(candidates), dtype=np.float64)
        for c in range(len(candidates)):
            idxs = [c * K + k for k in range(K)]
            valid = [scores[i] for i in idxs if not errored[i]]
            if valid:
                out[c] = float(np.mean(valid))
            else:
                # Every clone of this candidate errored: fail open.
                out[c] = root_value if candidates[c] == greedy_action else float("-inf")
                self._fallbacks += 1
        return out
