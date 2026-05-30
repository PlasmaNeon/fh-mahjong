from __future__ import annotations

import numpy as np
import torch

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.evaluate import (
    action_family,
    compute_action_agreement,
    evaluate_duplicate_seats,
    evaluate_online,
    evaluate_policy_online,
    reward_summary,
)
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.policies import ActionChoice
from fh_mahjong_ai.scripts.evaluate import parse_seed_windows
from fh_mahjong_ai.types import Observation, StepResult, Transition


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


def test_parse_seed_windows_supports_non_contiguous_eval_windows() -> None:
    assert parse_seed_windows([], episodes=3, start_seed=10) == [10, 11, 12]
    assert parse_seed_windows(["100:2", "200"], episodes=3, start_seed=10) == [100, 101, 200, 201, 202]


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
        assert report["policy_episode_summaries"][0]["first_candidate_override"]["q_margin"] == 0.25
        assert report["policy_episode_outcome_summary"]["candidate_override_reward"]["count"] == 2

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
        assert "positive_reward_rate" in report
        assert "action_family_rates" in report
        assert "round_outcome_rates" in report
