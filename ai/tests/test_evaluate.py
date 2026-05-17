from __future__ import annotations

import numpy as np
import torch

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.evaluate import action_family, compute_action_agreement, evaluate_duplicate_seats, evaluate_online, reward_summary
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.types import Observation, StepResult, Transition


def _obs(seat: int = 0, seed: int = 0) -> Observation:
    rng = np.random.default_rng(seed)
    mask = np.zeros(204, dtype=np.int8)
    mask[5:15] = 1  # some legal discard actions
    return Observation(
        seat=seat,
        planes=rng.standard_normal((39, 42, 1)).astype(np.float32),
        scalars=rng.standard_normal(29).astype(np.float32),
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
        assert "action_family_counts" in report
        assert "action_family_rates" in report
        assert "round_outcome_counts" in report
        assert "round_outcome_rates" in report
        assert "episodes" in report
        assert report["episodes"] == 2
        assert report["reward_summary"]["count"] == 2
        assert report["round_outcome_counts"]["unknown"] == 2

    def test_counts_terminal_reset_without_policy_action(self, monkeypatch) -> None:
        class TerminalResetBridge:
            def __init__(self) -> None:
                self.last_reset_result = None

            def reset(self, seed=None):
                mask = np.zeros(204, dtype=np.int8)
                observation = Observation(
                    seat=1,
                    planes=np.zeros((39, 42, 1), dtype=np.float32),
                    scalars=np.zeros(29, dtype=np.float32),
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
        assert report["seats"] == [0, 1]
        assert len(report["seat_reports"]) == 2
        assert set(report["seat_summary"]) == {"0", "1"}
        assert "reward_summary" in report
        assert "action_family_rates" in report
        assert "round_outcome_rates" in report
