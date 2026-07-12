"""Tests for `fh-mj-evaluate --search` (eval-harness integration, Task 6).

Mirrors the sampling-flags test pattern in test_evaluate.py: mock-bridge CLI
runs (no FFI / Go library needed), flag-validation via argparse SystemExit,
and report-shape assertions. `--search-max-candidates 1` keeps the run in
SearchPolicy's degenerate path (a single root candidate always equals greedy),
so the pool factory is never invoked and no real search pool is required.
"""
from __future__ import annotations

import json
import sys

import pytest

import functools

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.evaluate import _invoke_seat_policy_factory
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.policies import GuardedQPolicy
from fh_mahjong_ai.scripts import evaluate as ev
from fh_mahjong_ai.storage import save_checkpoint

_MODEL_ARGS = [
    "--model-channels", "8", "--model-residual-blocks", "1",
    "--model-plane-feature-dim", "16", "--model-scalar-hidden-dim", "16",
    "--model-trunk-hidden-dim", "16", "--model-value-hidden-dim", "16",
    "--model-q-hidden-dim", "16",
]


def _make_checkpoint(tmp_path, oracle_observation: bool = False):
    mcfg = ModelConfig(channels=8, residual_blocks=1, plane_feature_dim=16,
                       scalar_hidden_dim=16, trunk_hidden_dim=16, value_hidden_dim=16,
                       q_hidden_dim=16)
    ckpt = tmp_path / "m.pt"
    save_checkpoint(ckpt, PolicyValueNet(EnvConfig(oracle_observation=oracle_observation), mcfg))
    return ckpt


def _run(tmp_path, monkeypatch, extra, report_name="rep.json"):
    ckpt = _make_checkpoint(tmp_path)
    argv = ["fh-mj-evaluate", "--checkpoint", str(ckpt), "--match-mode", "classic",
            *_MODEL_ARGS, "--report-output", str(tmp_path / report_name), *extra]
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr(
        "fh_mahjong_ai.evaluate.build_bridge",
        lambda cfg: __import__("fh_mahjong_ai.bridge", fromlist=["MockMahjongBridge"]).MockMahjongBridge(cfg),
    )
    ev.main()
    return json.loads((tmp_path / report_name).read_text())


class TestSearchFlagValidation:
    def test_search_without_duplicate_seats_errors(self, tmp_path, monkeypatch):
        with pytest.raises(SystemExit):
            _run(tmp_path, monkeypatch, ["--online-episodes", "1", "--search"])

    def test_numeric_flags_without_search_error(self, tmp_path, monkeypatch):
        for flag, value in (
            ("--search-determinizations", "8"),
            ("--search-max-candidates", "2"),
            ("--search-prior-mass", "0.5"),
            ("--search-max-rollout-decisions", "10"),
            ("--search-seed", "7"),
        ):
            with pytest.raises(SystemExit):
                _run(tmp_path, monkeypatch,
                     ["--online-episodes", "1", "--duplicate-seats", flag, value])

    def test_search_determinizations_below_one_errors(self, tmp_path, monkeypatch):
        with pytest.raises(SystemExit):
            _run(tmp_path, monkeypatch,
                 ["--online-episodes", "1", "--duplicate-seats", "--search",
                  "--search-determinizations", "0"])

    def test_search_max_candidates_below_one_errors(self, tmp_path, monkeypatch):
        with pytest.raises(SystemExit):
            _run(tmp_path, monkeypatch,
                 ["--online-episodes", "1", "--duplicate-seats", "--search",
                  "--search-max-candidates", "0"])

    def test_search_prior_mass_out_of_range_errors(self, tmp_path, monkeypatch):
        for bad in ("0", "-0.1", "1.5"):
            with pytest.raises(SystemExit):
                _run(tmp_path, monkeypatch,
                     ["--online-episodes", "1", "--duplicate-seats", "--search",
                      "--search-prior-mass", bad])

    def test_search_max_rollout_decisions_below_one_errors(self, tmp_path, monkeypatch):
        with pytest.raises(SystemExit):
            _run(tmp_path, monkeypatch,
                 ["--online-episodes", "1", "--duplicate-seats", "--search",
                  "--search-max-rollout-decisions", "0"])

    def test_search_incompatible_with_sample_temperature(self, tmp_path, monkeypatch):
        with pytest.raises(SystemExit):
            _run(tmp_path, monkeypatch,
                 ["--online-episodes", "1", "--duplicate-seats", "--search",
                  "--sample-temperature", "0.5"])

    def test_search_incompatible_with_oracle_eval_env(self, tmp_path, monkeypatch):
        # --oracle without --from-oracle builds a 51ch oracle eval env; the Go
        # search pool rejects oracle envs, so the CLI must fail loudly instead.
        with pytest.raises(SystemExit):
            _run(tmp_path, monkeypatch,
                 ["--online-episodes", "1", "--duplicate-seats", "--search", "--oracle"])


class TestSearchReportKey:
    def test_report_contains_search_key_when_active(self, tmp_path, monkeypatch):
        report = _run(tmp_path, monkeypatch, [
            "--online-episodes", "1", "--duplicate-seats", "--search",
            "--search-max-candidates", "1",  # degenerate path: no pool constructed
            "--search-determinizations", "3",
            "--search-prior-mass", "0.8",
            "--search-max-rollout-decisions", "20",
            "--search-seed", "5",
        ])
        assert report["search"] == {
            "num_determinizations": 3,
            "max_candidates": 1,
            "prior_mass_cutoff": 0.8,
            "max_rollout_decisions": 20,
            "seed": 5,
            "fallback_count": 0,
        }
        assert report["online"]["episodes"] == 4  # 1 episode x 4 seats

    def test_report_lacks_search_key_when_inactive(self, tmp_path, monkeypatch):
        report = _run(tmp_path, monkeypatch, ["--online-episodes", "1", "--duplicate-seats"])
        assert "search" not in report

    def test_report_lacks_search_key_without_online_flag(self, tmp_path, monkeypatch):
        # No --online-episodes / --data at all: report is untouched by search.
        report = _run(tmp_path, monkeypatch, [])
        assert "search" not in report


class TestInvokeSeatPolicyFactory:
    """Unit tests for the arity-dispatch shim used by evaluate_duplicate_seats_policy.

    Regression: `len(inspect.signature(factory).parameters)` counted DEFAULTED
    params, so the standard capture-by-default idiom
    ``lambda _seat, selected_margin=margin: GuardedQPolicy(..., min_q_margin=selected_margin, ...)``
    (used by evaluate_guarded.py, evaluate_risk_guarded.py, evaluate_tail_constrained.py)
    was misdetected as a 2-required-arg factory and called as
    ``factory(seat, bridge)``, silently binding the live bridge object into the
    captured default instead of the seat's margin.
    """

    def test_plain_one_arg_factory_called_with_seat_only(self):
        calls = []

        def factory(seat):
            calls.append((seat,))
            return seat

        result = _invoke_seat_policy_factory(factory, 2, "BRIDGE")
        assert result == 2
        assert calls == [(2,)]

    def test_capture_by_default_lambda_is_not_given_the_bridge(self):
        # THE REGRESSION: a defaulted second parameter must NOT count as
        # "required" -- the factory takes only the seat, and its captured
        # default must remain untouched by the bridge object.
        calls = []

        def factory(seat, captured=0.5):
            calls.append((seat, captured))
            return (seat, captured)

        result = _invoke_seat_policy_factory(factory, 7, "BRIDGE_OBJ")
        assert result == (7, 0.5)
        assert calls == [(7, 0.5)]

    def test_genuine_two_required_arg_factory_receives_seat_and_bridge(self):
        calls = []

        def factory(seat, bridge):
            calls.append((seat, bridge))
            return (seat, bridge)

        result = _invoke_seat_policy_factory(factory, 3, "BRIDGE")
        assert result == (3, "BRIDGE")
        assert calls == [(3, "BRIDGE")]

    def test_functools_partial_reducing_required_args_to_one(self):
        def factory(seat, bridge):
            return (seat, bridge)

        partial_factory = functools.partial(factory, bridge="FIXED_BRIDGE")
        result = _invoke_seat_policy_factory(partial_factory, 9, "LIVE_BRIDGE")
        assert result == (9, "FIXED_BRIDGE")

    def test_factory_internal_typeerror_propagates(self):
        def factory(seat):
            raise TypeError("factory body blew up")

        with pytest.raises(TypeError, match="factory body blew up"):
            _invoke_seat_policy_factory(factory, 1, "BRIDGE")

    def test_guarded_style_capture_by_default_lambda_constructs_with_right_margin(self):
        # Integration-style: build the exact idiom evaluate_guarded.py:88 uses
        # and drive it through the shim (mock bridge, no real duplicate-seats
        # eval loop) to prove GuardedQPolicy ends up with the intended margin,
        # not the bridge object.
        anchor_model = object()
        candidate_model = object()
        margin = 0.75

        policy_factory = lambda _seat, selected_margin=margin: GuardedQPolicy(
            anchor_model=anchor_model,
            candidate_model=candidate_model,
            min_q_margin=selected_margin,
            device="cpu",
        )

        mock_bridge = object()
        policy = _invoke_seat_policy_factory(policy_factory, 2, mock_bridge)

        assert isinstance(policy, GuardedQPolicy)
        assert policy.min_q_margin == pytest.approx(0.75)
        assert policy.anchor_model is anchor_model
        assert policy.candidate_model is candidate_model
