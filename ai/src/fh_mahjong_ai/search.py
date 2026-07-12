"""Determinized champion-rollout search (`SearchPolicy`).

At the root decision, take the checkpoint's top actions (by prior mass, capped
by `max_candidates` / `prior_mass_cutoff`), then score each by determinized
rollouts: clone the current decision point into `num_determinizations` worlds
per candidate, apply the candidate on the first step, and roll the champion
(masked greedy argmax over `evaluate_batch`) forward in lockstep. Each clone
accumulates the root seat's per-step reward; a round boundary or a truncation
cap bootstraps with the value head of the returned observation; a terminal
state is scored by the accumulated (telescoping) rewards alone. A candidate's
score is the mean over its surviving clones. The best-scoring candidate's action
is returned.

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


PoolFactory = Callable[[int, int, int], Any]


class SearchPolicy:
    """ActionChoice-protocol policy: determinized champion-rollout search.

    ``pool_factory(num_clones, seed, max_rollout_decisions) -> pool`` with
    ``.step(commands) -> SearchStepResult`` and ``.close()``. Production wires
    ``GoSearchPool`` over the live eval bridge; tests inject fakes.
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
                len(candidates) * K, self._config.seed, self._config.max_rollout_decisions
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

        # First step: apply each candidate to its clones. The response already
        # carries rewards and may terminate / end a round / truncate / error
        # some clones immediately, so absorb it exactly like any other step.
        commands = [PoolCommand(slot=s, action_id=int(candidates[s // K])) for s in range(n)]
        result = pool.step(commands)
        self._absorb(result, root_seat, scores, done, errored, active=set(range(n)))

        # Champion lockstep rollout of the still-live clones.
        for _ in range(self._config.max_rollout_decisions):
            active = [s for s in range(n) if not done[s]]
            if not active:
                break
            rows = [(s, result.row_of_slot[s]) for s in active if s in result.row_of_slot]
            if not rows:
                break
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
            self._absorb(result, root_seat, scores, done, errored, active=active_set)
        else:
            # Decision cap hit with clones still live: bootstrap them like a
            # truncation with the value of their current observation row.
            self._bootstrap_live(result, scores, done)

        return self._aggregate(scores, errored, candidates, K, greedy_action, root_value)

    def _absorb(self, result, root_seat, scores, done, errored, active) -> None:
        """Fold one step response into per-clone scores, batching value bootstraps."""
        bootstrap: list[tuple[int, int]] = []  # (slot, row)
        for meta in result.slots:
            s = meta.slot
            if s not in active:  # skip command -> already scored / done
                continue
            rewards = meta.step_rewards
            if rewards.size > root_seat:
                scores[s] += float(rewards[root_seat])
            if meta.error:
                errored[s] = True
                done[s] = True
                continue
            if meta.terminated:
                done[s] = True  # accumulated (telescoping) reward is final
                continue
            round_ended = result.round_ended.get(s, False)
            if meta.truncated or round_ended:
                if s in result.row_of_slot:
                    bootstrap.append((s, result.row_of_slot[s]))
                done[s] = True
                continue
            # else: still live with an observation -> keep rolling
        if bootstrap:
            self._add_value_bootstrap(result, scores, bootstrap)

    def _bootstrap_live(self, result, scores, done) -> None:
        bootstrap = [
            (s, result.row_of_slot[s])
            for s in range(len(done))
            if not done[s] and s in result.row_of_slot
        ]
        for s, _ in bootstrap:
            done[s] = True
        if bootstrap:
            self._add_value_bootstrap(result, scores, bootstrap)

    def _add_value_bootstrap(self, result, scores, bootstrap: list[tuple[int, int]]) -> None:
        planes = np.stack([result.planes[r] for _, r in bootstrap])
        scalars = np.stack([result.scalars[r] for _, r in bootstrap])
        masks = np.stack([result.action_masks[r] for _, r in bootstrap])
        _, values = self._policy.evaluate_batch(planes, scalars, masks)
        for i, (s, _) in enumerate(bootstrap):
            scores[s] += float(values[i])

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
