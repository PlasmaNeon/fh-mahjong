from __future__ import annotations

import sys

import numpy as np
import pytest
import torch

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.evaluate import (
    action_family,
    compute_action_agreement,
    episode_placement,
    evaluate_duplicate_seats,
    evaluate_online,
    evaluate_policy_online,
    reward_summary,
)
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.policies import ActionChoice
from fh_mahjong_ai.scripts import evaluate as evaluate_cli
from fh_mahjong_ai.scripts.evaluate import parse_seed_windows, resolve_max_steps_per_episode
from fh_mahjong_ai.scripts.evaluate_tail_constrained import parse_family_risk_increases
from fh_mahjong_ai.types import Observation, StepResult, Transition


def _grp_dummy_transition(rewards):
    o = Observation(seat=0, planes=np.zeros((1, 1, 1), dtype=np.float32),
                    scalars=np.zeros(1, dtype=np.float32),
                    action_mask=np.ones(1, dtype=np.int8), metadata={})
    return Transition(observation=o, action_id=0, rewards=np.asarray(rewards, dtype=np.float32),
                      next_observation=o, terminated=True, truncated=False, info={})


def _obs(seat: int = 0, seed: int = 0) -> Observation:
    rng = np.random.default_rng(seed)
    mask = np.zeros(204, dtype=np.int8)
    mask[5:15] = 1  # some legal discard actions
    return Observation(
        seat=seat,
        planes=rng.standard_normal((39, 42, 1)).astype(np.float32),
        scalars=rng.standard_normal(42).astype(np.float32),
        action_mask=mask,
    )


def _transition(action_id: int, seed: int = 0) -> Transition:
    return Transition(
        observation=_obs(seed=seed),
        action_id=action_id,
        rewards=np.zeros(4, dtype=np.float32),
        next_observation=_obs(seed=seed + 1),
        terminated=False,
        info={},
    )


class TestActionAgreement:
    def test_action_family_mapping(self) -> None:
        assert action_family(0) == "pass"
        assert action_family(1) == "win"
        assert action_family(5) == "discard"
        assert action_family(47) == "pon"
        assert action_family(81) == "kan"
        assert action_family(183) == "chii"

    def test_perfect_agreement(self) -> None:
        model = PolicyValueNet(EnvConfig(), ModelConfig())
        # Get what the model would predict for this observation
        t = _transition(action_id=5, seed=42)
        with torch.inference_mode():
            planes = torch.from_numpy(t.observation.planes).unsqueeze(0)
            scalars = torch.from_numpy(t.observation.scalars).unsqueeze(0)
            mask = torch.from_numpy(t.observation.action_mask).unsqueeze(0)
            logits, _ = model(planes, scalars, mask)
            predicted = int(torch.argmax(logits, dim=1).item())

        t_matched = _transition(action_id=predicted, seed=42)
        report = compute_action_agreement(model, [t_matched], device="cpu")
        assert report["agreement_rate"] == 1.0
        assert report["family_agreement"]["discard"]["agreement_rate"] == 1.0

    def test_zero_agreement(self) -> None:
        model = PolicyValueNet(EnvConfig(), ModelConfig())
        t = _transition(action_id=5, seed=42)
        with torch.inference_mode():
            planes = torch.from_numpy(t.observation.planes).unsqueeze(0)
            scalars = torch.from_numpy(t.observation.scalars).unsqueeze(0)
            mask = torch.from_numpy(t.observation.action_mask).unsqueeze(0)
            logits, _ = model(planes, scalars, mask)
            predicted = int(torch.argmax(logits, dim=1).item())

        wrong_action = 5 if predicted != 5 else 6
        t_wrong = _transition(action_id=wrong_action, seed=42)
        report = compute_action_agreement(model, [t_wrong], device="cpu")
        assert report["agreement_rate"] == 0.0

    def test_returns_top3_rate(self) -> None:
        model = PolicyValueNet(EnvConfig(), ModelConfig())
        transitions = [_transition(action_id=i % 10 + 5, seed=i) for i in range(20)]
        report = compute_action_agreement(model, transitions, device="cpu")
        assert "top3_agreement_rate" in report
        assert "family_agreement" in report
        assert "discard" in report["family_agreement"]
        assert 0.0 <= report["top3_agreement_rate"] <= 1.0

    def test_batched_agreement_matches_single_item_batches(self) -> None:
        model = PolicyValueNet(EnvConfig(), ModelConfig())
        transitions = [_transition(action_id=i % 10 + 5, seed=i) for i in range(17)]

        single = compute_action_agreement(model, transitions, device="cpu", batch_size=1)
        batched = compute_action_agreement(model, transitions, device="cpu", batch_size=8)

        assert batched == single


def test_reward_summary_reports_distribution() -> None:
    report = reward_summary([1.0, 0.0, -2.0, 3.0])

    assert report["count"] == 4
    assert report["sum"] == 2.0
    assert report["positive_count"] == 2
    assert report["zero_count"] == 1
    assert report["negative_count"] == 1
    assert report["positive_rate"] == 0.5


def test_reward_summary_reports_sem_and_ci95() -> None:
    summary = reward_summary([1.0, 1.0, 1.0, 1.0])
    assert summary["sem"] == 0.0
    assert summary["ci95"] == 0.0

    summary = reward_summary([0.0, 2.0])
    # sample std (ddof=1) of [0, 2] is sqrt(2); sem = sqrt(2) / sqrt(2) = 1.0
    assert summary["sem"] == pytest.approx(1.0, abs=1e-6)
    assert summary["ci95"] == pytest.approx(1.96, abs=1e-6)


def test_reward_summary_empty_has_ci_fields() -> None:
    summary = reward_summary([])
    assert summary["sem"] == 0.0
    assert summary["ci95"] == 0.0


def test_parse_seed_windows_supports_non_contiguous_eval_windows() -> None:
    assert parse_seed_windows([], episodes=3, start_seed=10) == [10, 11, 12]
    assert parse_seed_windows(["100:2", "200"], episodes=3, start_seed=10) == [100, 101, 200, 201, 202]


def test_parse_family_risk_increases() -> None:
    assert parse_family_risk_increases(["discard=0.02", "chii=0.01"]) == {
        "discard": 0.02,
        "chii": 0.01,
    }


class TestEvaluateOnline:
    def test_runs_with_mock_bridge(self) -> None:
        model = PolicyValueNet(EnvConfig(), ModelConfig())
        report = evaluate_online(
            model=model,
            episodes=2,
            seeds=list(range(1, 3)),
            bridge_kind="mock",
            device="cpu",
        )
        assert "avg_reward" in report
        assert "win_rate" in report
        assert "large_loss_rate" in report
        assert "mean_reward" in report
        assert "reward_summary" in report
        assert "positive_reward_rate" in report
        assert report["match_mode"] == "classic"
        assert "action_family_counts" in report
        assert "action_family_rates" in report
        assert "round_outcome_counts" in report
        assert "round_outcome_rates" in report
        assert "episodes" in report
        assert report["episodes"] == 2
        assert report["reward_summary"]["count"] == 2
        assert report["round_outcome_counts"]["unknown"] == 2

    def test_policy_episode_summary_reports_guard_overrides(self) -> None:
        class CandidatePolicy:
            def choose(self, observation: Observation) -> ActionChoice:
                return ActionChoice(
                    action_id=observation.legal_actions[0],
                    info={
                        "source": "candidate",
                        "anchor_action_id": 5,
                        "anchor_action_label": "discard 1m",
                        "candidate_action_id": observation.legal_actions[0],
                        "candidate_action_label": "discard 2m",
                        "chosen_action_label": "discard 2m",
                        "q_margin": 0.25,
                        "candidate_q": 0.75,
                        "anchor_action_q": 0.50,
                    },
                )

        report = evaluate_policy_online(
            policy=CandidatePolicy(),
            episodes=2,
            seeds=[1, 2],
            bridge_kind="mock",
        )

        assert report["policy_choice_counts"]["candidate"] > 0
        assert report["policy_q_margin_summary"]["mean"] == 0.25
        assert len(report["policy_episode_summaries"]) == 2
        assert report["policy_episode_summaries"][0]["candidate_override_count"] > 0
        assert report["policy_episode_summaries"][0]["intervention_count"] > 0
        assert report["policy_episode_summaries"][0]["intervention_source_counts"]["candidate"] > 0
        assert report["policy_episode_summaries"][0]["first_candidate_override"]["q_margin"] == 0.25
        assert report["policy_episode_summaries"][0]["first_intervention"]["source"] == "candidate"
        assert report["policy_episode_outcome_summary"]["candidate_override_reward"]["count"] == 2
        assert report["policy_episode_outcome_summary"]["intervention_reward"]["count"] == 2

    def test_policy_episode_summary_reports_risk_guard_interventions(self) -> None:
        class RiskGuardPolicy:
            def choose(self, observation: Observation) -> ActionChoice:
                chosen = observation.legal_actions[0]
                return ActionChoice(
                    action_id=chosen,
                    info={
                        "source": "risk_guard",
                        "anchor_action_id": 5,
                        "anchor_action_label": "discard 1m",
                        "chosen_action_id": chosen,
                        "chosen_action_label": "discard 2m",
                        "anchor_risk": 0.72,
                        "chosen_risk": 0.31,
                        "risk_reduction": 0.41,
                    },
                )

        report = evaluate_policy_online(
            policy=RiskGuardPolicy(),
            episodes=1,
            seeds=[1],
            bridge_kind="mock",
        )

        summary = report["policy_episode_summaries"][0]
        assert summary["candidate_override_count"] == 0
        assert summary["intervention_count"] > 0
        assert summary["intervention_source_counts"]["risk_guard"] > 0
        assert summary["intervention_anchor_family_counts"]["discard"] > 0
        assert summary["intervention_chosen_family_counts"]
        assert summary["first_intervention"]["source"] == "risk_guard"
        assert summary["first_intervention"]["anchor_risk"] == 0.72
        assert report["policy_episode_outcome_summary"]["intervention_reward"]["count"] == 1

    def test_counts_terminal_reset_without_policy_action(self, monkeypatch) -> None:
        class TerminalResetBridge:
            def __init__(self) -> None:
                self.last_reset_result = None

            def reset(self, seed=None):
                mask = np.zeros(204, dtype=np.int8)
                observation = Observation(
                    seat=1,
                    planes=np.zeros((39, 42, 1), dtype=np.float32),
                    scalars=np.zeros(42, dtype=np.float32),
                    action_mask=mask,
                )
                self.last_reset_result = StepResult(
                    observation=observation,
                    rewards=np.asarray([0.0, 0.25, -0.1, -0.15], dtype=np.float32),
                    terminated=True,
                    truncated=False,
                    info={
                        "round_outcome": {
                            "is_draw": False,
                            "winner_seat": 1,
                            "win_type_name": "ACTION_RON",
                            "discarder_seat": 0,
                        }
                    },
                )
                return observation

            def step(self, action_id):
                raise AssertionError("terminal reset should not call step")

            def close(self):
                return None

        monkeypatch.setattr("fh_mahjong_ai.evaluate.build_bridge", lambda config: TerminalResetBridge())
        model = PolicyValueNet(EnvConfig(), ModelConfig())

        report = evaluate_online(
            model=model,
            episodes=1,
            seeds=[200010],
            bridge_kind="go",
            device="cpu",
            learning_seat=1,
        )

        assert report["episodes"] == 1
        assert report["avg_reward"] == 0.25
        assert report["mean_reward"] == 0.25
        assert report["reward_sum"] == 0.25
        assert report["win_count"] == 1
        assert report["action_family_counts"] == {}
        assert report["action_family_rates"] == {}
        assert report["round_outcome_counts"] == {"ron_win": 1}
        assert report["round_outcome_rates"] == {"ron_win": 1.0}
        assert report["episode_summaries"][0]["seed"] == 200010
        assert report["episode_summaries"][0]["seat"] == 1
        assert report["large_loss_episodes"] == []

    def test_forwards_chongci_eval_config(self, monkeypatch) -> None:
        captured: dict[str, EnvConfig] = {}

        class TerminalChongciBridge:
            def __init__(self) -> None:
                self.last_reset_result = None

            def reset(self, seed=None):
                mask = np.zeros(204, dtype=np.int8)
                observation = Observation(
                    seat=0,
                    planes=np.zeros((39, 42, 1), dtype=np.float32),
                    scalars=np.zeros(50, dtype=np.float32),
                    action_mask=mask,
                )
                self.last_reset_result = StepResult(
                    observation=observation,
                    rewards=np.asarray([0.75, -0.1, -0.2, -0.45], dtype=np.float32),
                    terminated=True,
                    truncated=False,
                    info={},
                )
                return observation

            def step(self, action_id):
                raise AssertionError("terminal reset should not call step")

            def close(self):
                return None

        def fake_build_bridge(config: EnvConfig):
            captured["config"] = config
            return TerminalChongciBridge()

        monkeypatch.setattr("fh_mahjong_ai.evaluate.build_bridge", fake_build_bridge)
        model = PolicyValueNet(EnvConfig(), ModelConfig())

        report = evaluate_online(
            model=model,
            episodes=1,
            seeds=[5000],
            bridge_kind="go",
            device="cpu",
            match_mode="chongci",
            chongci_starting_score=3000,
            chongci_bust_threshold=-100,
            chongci_max_hands=12,
            max_steps_per_episode=1024,
        )

        config = captured["config"]
        assert config.match_mode == "chongci"
        assert config.chongci_starting_score == 3000
        assert config.chongci_bust_threshold == -100
        assert config.chongci_max_hands == 12
        assert config.max_steps_per_episode == 1024
        assert report["match_mode"] == "chongci"
        assert report["chongci_config"] == {"starting_score": 3000, "bust_threshold": -100, "max_hands": 12}
        assert report["positive_reward_rate"] == 1.0
        assert report["round_outcome_counts"] == {"match_end": 1}

    def test_duplicate_seat_eval_runs_with_mock_bridge(self) -> None:
        model = PolicyValueNet(EnvConfig(), ModelConfig())
        report = evaluate_duplicate_seats(
            model=model,
            seeds=[1, 2],
            seats=(0, 1),
            bridge_kind="mock",
            device="cpu",
        )

        assert report["episodes"] == 4
        assert report["match_mode"] == "classic"
        assert report["seats"] == [0, 1]
        assert len(report["seat_reports"]) == 2
        assert set(report["seat_summary"]) == {"0", "1"}
        assert "episode_summaries" in report
        assert "large_loss_episodes" in report
        assert "reward_summary" in report
        assert "mean_reward_sem" in report
        assert "mean_reward_ci95" in report
        assert report["mean_reward_ci95"] >= 0.0
        assert "positive_reward_rate" in report
        assert "action_family_rates" in report
        assert "round_outcome_rates" in report


def test_episode_placement_ranks_learning_seat():
    # learning seat 0 has the highest net -> placement value 1.0
    ep = [_grp_dummy_transition([3.0, 1.0, -1.0, -3.0])]
    pv = (1.0, 1.0 / 3.0, -1.0 / 3.0, -1.0)
    val = episode_placement(ep, fallback_rewards=np.zeros(4, dtype=np.float32),
                            learning_seat=0, placement_values=pv)
    assert val == 1.0
    # learning seat 3 has the lowest -> -1.0
    val3 = episode_placement(ep, fallback_rewards=np.zeros(4, dtype=np.float32),
                             learning_seat=3, placement_values=pv)
    assert val3 == -1.0


def test_episode_placement_includes_reset_reward_in_ranking():
    # net from steps alone ranks seat 0 LAST; the reset reward lifts it to FIRST,
    # so placement must rank on the reset-included (true final) net.
    pv = (1.0, 1.0 / 3.0, -1.0 / 3.0, -1.0)
    ep = [_grp_dummy_transition([0.0, 0.1, 0.2, 0.3])]
    assert episode_placement(ep, np.zeros(4, dtype=np.float32), 0, pv) == -1.0
    val = episode_placement(ep, np.zeros(4, dtype=np.float32), 0, pv,
                            reset_rewards=np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32))
    assert val == 1.0


def test_truncated_eval_scored_worst_placement(monkeypatch):
    # A step-limit truncation in eval is scored the WORST placement (matching the
    # training reward), not excluded. So a policy cannot lift mean_placement — the
    # gate metric vs the anchor — by driving losing matches into the step limit.
    from fh_mahjong_ai.bridge import MockMahjongBridge
    from fh_mahjong_ai.types import StepResult
    orig_reset = MockMahjongBridge.reset
    orig_step = MockMahjongBridge.step
    state = {"steps": 0}

    def patched_reset(self, seed=None):
        state["steps"] = 0
        return orig_reset(self, seed=seed)

    def patched_step(self, action_id):
        res = orig_step(self, action_id)
        state["steps"] += 1
        if state["steps"] >= 5:  # truncate every episode well before max_steps
            return StepResult(observation=res.observation, rewards=res.rewards,
                              terminated=False, truncated=True, info=res.info)
        return res

    monkeypatch.setattr(MockMahjongBridge, "reset", patched_reset)
    monkeypatch.setattr(MockMahjongBridge, "step", patched_step)

    model = PolicyValueNet(EnvConfig(), ModelConfig())
    report = evaluate_online(model=model, episodes=3, seeds=[1, 2, 3],
                             bridge_kind="mock", device="cpu")
    assert report["truncation_count"] == 3
    # placement now scores every completed episode (no censoring): sample == episodes
    assert report["placement_count"] == report["episodes"] == 3
    # every truncated episode gets the worst placement -> mean cannot be inflated
    assert report["mean_placement"] == -1.0
    assert all(p == -1.0 for p in report["per_episode_placements"])
    assert report["truncation_rate"] == 1.0


class _FakeChongciMatchBridge:
    """Mimics the Go chongci env's step-limit semantics for eval tests.

    A full chongci match runs ``MATCH_DECISIONS`` decisions -- more than the
    classic ``EnvConfig`` cap of 256 -- and then ends with ``PHASE_MATCH_END``,
    which the Go env reports as ``Terminated``. If the bridge decision cap
    (``config.max_steps_per_episode``) is reached first, the Go env reports
    ``Truncated`` instead (internal/rl/env.go sets ``Truncated`` only at the
    step limit). This fake reproduces exactly that branch so the eval CLI's
    per-mode step-cap default can be exercised end to end.
    """

    MATCH_DECISIONS = 300

    def __init__(self, config: EnvConfig) -> None:
        self.config = config
        self.last_reset_result: StepResult | None = None
        self._steps = 0

    def _observe(self) -> Observation:
        channels, height, width = self.config.plane_shape
        mask = np.zeros(self.config.action_space_size, dtype=np.int8)
        mask[5:15] = 1  # some legal discard actions
        return Observation(
            seat=0,
            planes=np.zeros((channels, height, width), dtype=np.float32),
            scalars=np.zeros(self.config.scalar_features, dtype=np.float32),
            action_mask=mask,
        )

    def reset(self, seed: int | None = None) -> Observation:
        self._steps = 0
        observation = self._observe()
        self.last_reset_result = StepResult(
            observation=observation,
            rewards=np.zeros(4, dtype=np.float32),
            terminated=False,
            truncated=False,
            info={"reset": True},
        )
        return observation

    def step(self, action_id: int) -> StepResult:
        self._steps += 1
        terminal_rewards = np.asarray([0.4, 0.1, -0.2, -0.3], dtype=np.float32)
        if self._steps >= self.config.max_steps_per_episode:
            # Step-limit reached before the match ended -> Go env truncates.
            return StepResult(self._observe(), terminal_rewards, terminated=False, truncated=True, info={})
        if self._steps >= self.MATCH_DECISIONS:
            # Natural PHASE_MATCH_END -> Go env terminates.
            return StepResult(self._observe(), terminal_rewards, terminated=True, truncated=False, info={})
        return StepResult(self._observe(), np.zeros(4, dtype=np.float32), terminated=False, truncated=False, info={})

    def close(self) -> None:
        return None


def _truncation_rate(report: dict) -> float:
    summaries = report["episode_summaries"]
    return sum(1 for summary in summaries if summary["truncated"]) / len(summaries)


class TestChongciMaxStepsDefault:
    def test_resolve_defaults_chongci_to_training_budget(self) -> None:
        # Classic mode is unchanged: an unset cap falls through to EnvConfig's default.
        assert resolve_max_steps_per_episode("classic", None) is None
        # Chongci with no flag gets a budget large enough to reach MATCH_END.
        assert resolve_max_steps_per_episode("chongci", None) == 4000
        # An explicit flag always wins, in either mode.
        assert resolve_max_steps_per_episode("chongci", 50) == 50
        assert resolve_max_steps_per_episode("classic", 512) == 512

    def test_chongci_default_terminates_without_truncation(self, monkeypatch) -> None:
        monkeypatch.setattr("fh_mahjong_ai.evaluate.build_bridge", _FakeChongciMatchBridge)
        model = PolicyValueNet(EnvConfig(), ModelConfig())

        report = evaluate_duplicate_seats(
            model=model,
            seeds=[1],
            seats=(0, 1),
            bridge_kind="go",
            device="cpu",
            match_mode="chongci",
            max_steps_per_episode=resolve_max_steps_per_episode("chongci", None),
        )

        assert _truncation_rate(report) == 0.0
        assert report["round_outcome_counts"].get("match_truncated", 0) == 0
        assert report["round_outcome_counts"]["match_end"] == report["episodes"]

    def test_explicit_low_cap_still_truncates(self, monkeypatch) -> None:
        monkeypatch.setattr("fh_mahjong_ai.evaluate.build_bridge", _FakeChongciMatchBridge)
        model = PolicyValueNet(EnvConfig(), ModelConfig())

        report = evaluate_duplicate_seats(
            model=model,
            seeds=[1],
            seats=(0, 1),
            bridge_kind="go",
            device="cpu",
            match_mode="chongci",
            max_steps_per_episode=resolve_max_steps_per_episode("chongci", 50),
        )

        assert _truncation_rate(report) == 1.0
        assert report["round_outcome_counts"].get("match_end", 0) == 0
        assert report["round_outcome_counts"]["match_truncated"] == report["episodes"]

    def test_main_wires_resolved_cap_into_eval(self, monkeypatch) -> None:
        # Guards the CLI wiring: main() must forward the *resolved* cap, not the
        # raw argparse value. Without this, a regression that passed
        # args.max_steps_per_episode straight through would silently reintroduce
        # the 256-step chongci truncation while every resolver unit test stayed green.
        captured: dict = {}

        def fake_duplicate_seats(**kwargs):
            captured.clear()
            captured.update(kwargs)
            return {
                "match_mode": kwargs["match_mode"],
                "episodes": 1,
                "avg_reward": 0.0,
                "positive_reward_count": 0,
                "positive_reward_rate": 0.0,
                "win_count": 0,
                "win_rate": 0.0,
                "large_loss_rate": 0.0,
            }

        monkeypatch.setattr(evaluate_cli, "load_checkpoint", lambda *args, **kwargs: 0)
        monkeypatch.setattr(evaluate_cli, "evaluate_duplicate_seats", fake_duplicate_seats)

        base_argv = ["fh-mj-evaluate", "--checkpoint", "ckpt.pt", "--online-episodes", "1", "--duplicate-seats"]

        monkeypatch.setattr(sys, "argv", base_argv + ["--match-mode", "chongci"])
        evaluate_cli.main()
        assert captured["max_steps_per_episode"] == 4000

        monkeypatch.setattr(sys, "argv", base_argv + ["--match-mode", "classic"])
        evaluate_cli.main()
        assert captured["max_steps_per_episode"] is None

        monkeypatch.setattr(sys, "argv", base_argv + ["--match-mode", "chongci", "--max-steps-per-episode", "123"])
        evaluate_cli.main()
        assert captured["max_steps_per_episode"] == 123


def test_evaluate_cli_from_oracle_extracts_39ch(tmp_path, monkeypatch):
    import sys
    from fh_mahjong_ai.config import EnvConfig, ModelConfig
    from fh_mahjong_ai.model import PolicyValueNet
    from fh_mahjong_ai.storage import save_checkpoint
    from fh_mahjong_ai.scripts import evaluate as ev
    mcfg = ModelConfig(channels=8, residual_blocks=1, plane_feature_dim=16,
                       scalar_hidden_dim=16, trunk_hidden_dim=16, value_hidden_dim=16, q_hidden_dim=16)
    # a 51ch oracle-style checkpoint
    ckpt = tmp_path / "selfplay.pt"
    save_checkpoint(ckpt, PolicyValueNet(EnvConfig(oracle_observation=True), mcfg))
    argv = ["fh-mj-evaluate", "--checkpoint", str(ckpt), "--from-oracle",
            "--online-episodes", "1", "--match-mode", "classic",
            "--model-channels", "8", "--model-residual-blocks", "1",
            "--model-plane-feature-dim", "16", "--model-scalar-hidden-dim", "16",
            "--model-trunk-hidden-dim", "16", "--model-value-hidden-dim", "16", "--model-q-hidden-dim", "16",
            "--report-output", str(tmp_path / "rep.json")]
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr("fh_mahjong_ai.evaluate.build_bridge",
                        lambda cfg: __import__("fh_mahjong_ai.bridge", fromlist=["MockMahjongBridge"]).MockMahjongBridge(cfg))
    ev.main()  # must not raise: a 39ch student runs in the non-oracle (39ch) eval
    assert (tmp_path / "rep.json").exists()


def test_evaluate_cli_oracle_and_from_oracle_together_no_shape_mismatch(tmp_path, monkeypatch):
    """--oracle --from-oracle together must not crash with a shape mismatch.

    The model is extracted as a 39ch student (from-oracle), so the eval env must
    also use 39ch observations (oracle_observation=False). The guard
    ``eval_oracle = args.oracle and not args.from_oracle`` ensures this.
    """
    from fh_mahjong_ai.config import EnvConfig, ModelConfig
    from fh_mahjong_ai.model import PolicyValueNet
    from fh_mahjong_ai.storage import save_checkpoint
    from fh_mahjong_ai.scripts import evaluate as ev

    mcfg = ModelConfig(channels=8, residual_blocks=1, plane_feature_dim=16,
                       scalar_hidden_dim=16, trunk_hidden_dim=16, value_hidden_dim=16, q_hidden_dim=16)
    ckpt = tmp_path / "oracle.pt"
    save_checkpoint(ckpt, PolicyValueNet(EnvConfig(oracle_observation=True), mcfg))

    argv = [
        "fh-mj-evaluate",
        "--checkpoint", str(ckpt),
        "--from-oracle",  # extract 39ch student
        "--oracle",       # historically caused 51ch env with 39ch model -> crash
        "--online-episodes", "1",
        "--match-mode", "classic",
        "--model-channels", "8", "--model-residual-blocks", "1",
        "--model-plane-feature-dim", "16", "--model-scalar-hidden-dim", "16",
        "--model-trunk-hidden-dim", "16", "--model-value-hidden-dim", "16",
        "--model-q-hidden-dim", "16",
        "--report-output", str(tmp_path / "rep.json"),
    ]
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr(
        "fh_mahjong_ai.evaluate.build_bridge",
        lambda cfg: __import__("fh_mahjong_ai.bridge", fromlist=["MockMahjongBridge"]).MockMahjongBridge(cfg),
    )
    ev.main()  # must not raise; 39ch student runs in the non-oracle (39ch) eval
    assert (tmp_path / "rep.json").exists()


def test_evaluate_cli_oracle_builds_51ch(tmp_path, monkeypatch):
    from fh_mahjong_ai.bridge import MockMahjongBridge
    from fh_mahjong_ai.storage import save_checkpoint

    mcfg = ModelConfig(
        channels=8,
        residual_blocks=1,
        plane_feature_dim=16,
        scalar_hidden_dim=16,
        trunk_hidden_dim=16,
        value_hidden_dim=16,
        q_hidden_dim=16,
    )
    ckpt = tmp_path / "oracle.pt"
    save_checkpoint(ckpt, PolicyValueNet(EnvConfig(oracle_observation=True), mcfg))
    # Inject the mock bridge so no Go library is needed.
    monkeypatch.setattr("fh_mahjong_ai.evaluate.build_bridge", MockMahjongBridge)
    argv = [
        "fh-mj-evaluate",
        "--checkpoint", str(ckpt),
        "--online-episodes", "1",
        "--match-mode", "classic",
        "--oracle",
        "--model-channels", "8",
        "--model-residual-blocks", "1",
        "--model-plane-feature-dim", "16",
        "--model-scalar-hidden-dim", "16",
        "--model-trunk-hidden-dim", "16",
        "--model-value-hidden-dim", "16",
        "--model-q-hidden-dim", "16",
        "--report-output", str(tmp_path / "rep.json"),
    ]
    monkeypatch.setattr(sys, "argv", argv)
    evaluate_cli.main()  # must not raise; 51ch model + 51ch mock obs are consistent
    assert (tmp_path / "rep.json").exists()


def test_evaluate_cli_sampled_duplicate_seats_is_seeded_and_reported(tmp_path, monkeypatch):
    """--sample-temperature routes the duplicate-seat eval through the serving
    sampler (CheckpointPolicy): reproducible under --sample-seed, and the
    sampling config is recorded in the report."""
    import json
    import sys

    from fh_mahjong_ai.config import EnvConfig, ModelConfig
    from fh_mahjong_ai.model import PolicyValueNet
    from fh_mahjong_ai.storage import save_checkpoint
    from fh_mahjong_ai.scripts import evaluate as ev

    mcfg = ModelConfig(channels=8, residual_blocks=1, plane_feature_dim=16,
                       scalar_hidden_dim=16, trunk_hidden_dim=16, value_hidden_dim=16, q_hidden_dim=16)
    ckpt = tmp_path / "m.pt"
    save_checkpoint(ckpt, PolicyValueNet(EnvConfig(), mcfg))

    def run(report_name):
        argv = ["fh-mj-evaluate", "--checkpoint", str(ckpt),
                "--online-episodes", "2", "--duplicate-seats", "--match-mode", "classic",
                "--sample-temperature", "0.7", "--sample-top-k", "3", "--sample-seed", "11",
                "--model-channels", "8", "--model-residual-blocks", "1",
                "--model-plane-feature-dim", "16", "--model-scalar-hidden-dim", "16",
                "--model-trunk-hidden-dim", "16", "--model-value-hidden-dim", "16",
                "--model-q-hidden-dim", "16",
                "--report-output", str(tmp_path / report_name)]
        monkeypatch.setattr(sys, "argv", argv)
        monkeypatch.setattr("fh_mahjong_ai.evaluate.build_bridge",
                            lambda cfg: __import__("fh_mahjong_ai.bridge", fromlist=["MockMahjongBridge"]).MockMahjongBridge(cfg))
        ev.main()
        return json.loads((tmp_path / report_name).read_text())

    first = run("a.json")
    second = run("b.json")

    assert first["sampling"] == {"temperature": 0.7, "top_k": 3, "action_family": "all", "seed": 11}
    assert first["online"]["per_episode_placements"] == second["online"]["per_episode_placements"]
    assert first["online"]["episodes"] == second["online"]["episodes"]


def test_evaluate_cli_sampling_flag_validation_and_t0_report_unchanged(tmp_path, monkeypatch):
    """T=0 reports omit the 'sampling' key entirely (byte-identical greedy
    reports), and misused sampling flags fail loudly instead of silently
    degrading to greedy."""
    import json
    import sys

    import pytest

    from fh_mahjong_ai.config import EnvConfig, ModelConfig
    from fh_mahjong_ai.model import PolicyValueNet
    from fh_mahjong_ai.storage import save_checkpoint
    from fh_mahjong_ai.scripts import evaluate as ev

    mcfg = ModelConfig(channels=8, residual_blocks=1, plane_feature_dim=16,
                       scalar_hidden_dim=16, trunk_hidden_dim=16, value_hidden_dim=16, q_hidden_dim=16)
    ckpt = tmp_path / "m.pt"
    save_checkpoint(ckpt, PolicyValueNet(EnvConfig(), mcfg))
    model_args = ["--model-channels", "8", "--model-residual-blocks", "1",
                  "--model-plane-feature-dim", "16", "--model-scalar-hidden-dim", "16",
                  "--model-trunk-hidden-dim", "16", "--model-value-hidden-dim", "16",
                  "--model-q-hidden-dim", "16"]

    def run(extra, report_name="rep.json"):
        argv = ["fh-mj-evaluate", "--checkpoint", str(ckpt), "--match-mode", "classic",
                *model_args, "--report-output", str(tmp_path / report_name), *extra]
        monkeypatch.setattr(sys, "argv", argv)
        monkeypatch.setattr("fh_mahjong_ai.evaluate.build_bridge",
                            lambda cfg: __import__("fh_mahjong_ai.bridge", fromlist=["MockMahjongBridge"]).MockMahjongBridge(cfg))
        ev.main()
        return json.loads((tmp_path / report_name).read_text())

    # Default greedy report carries NO sampling key at all.
    report = run(["--online-episodes", "1", "--duplicate-seats"])
    assert "sampling" not in report

    # Misused flags fail loudly (argparse SystemExit).
    for bad in (["--sample-temperature", "-0.5", "--duplicate-seats"],
                ["--sample-temperature", "nan", "--duplicate-seats"],
                ["--sample-temperature", "0.5", "--sample-top-k", "-1", "--duplicate-seats"],
                ["--sample-top-k", "3", "--duplicate-seats"],           # top-k without temperature
                ["--sample-temperature", "0.5"],                        # temperature without duplicate-seats
                ["--sample-temperature", "0.5", "--sample-action-family", "bogus", "--duplicate-seats"]):
        with pytest.raises(SystemExit):
            run(["--online-episodes", "1", *bad], report_name="bad.json")
