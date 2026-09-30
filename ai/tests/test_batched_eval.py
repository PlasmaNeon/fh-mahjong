"""Batched duplicate-seat evaluation through the env pool (`batched_eval`)."""

import json
import os

import pytest
import torch

from conftest import small_model_config
from fh_mahjong_ai.batched_eval import evaluate_duplicate_seats_batched
from fh_mahjong_ai.config import EnvConfig
from fh_mahjong_ai.evaluate import evaluate_duplicate_seats
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.scripts.compare_reports import paired_comparison

requires_go_lib = pytest.mark.skipif(
    not os.environ.get("FH_MAHJONG_BRIDGE_LIB"), reason="needs the Go bridge library"
)

# 415, 616 and 680 resolve a hand during reset autoplay for some seat (nonzero reset
# rewards), which the report must count exactly once.
KW = dict(seeds=list(range(41, 47)) + [415, 616, 680], match_mode="chongci",
          chongci_max_hands=6, max_steps_per_episode=4000)


def _model(window: int) -> PolicyValueNet:
    torch.manual_seed(7)
    return PolicyValueNet(EnvConfig(), small_model_config(event_window=window)).eval()


def _canon(report: dict) -> str:
    report = dict(report)
    report.pop("evaluator", None)
    report.pop("evaluator_timing", None)
    return json.dumps(report, sort_keys=True, default=str)


@requires_go_lib
@pytest.mark.parametrize("slots", [1, 4, 32])
def test_per_row_report_is_byte_identical_to_the_sequential_evaluator(slots):
    # slots=1 runs matches one at a time, 4 refills slots mid-seat, 32 is more
    # slots than seeds.
    model = _model(8)
    sequential = evaluate_duplicate_seats(model=model, event_history_window=8, **KW)
    batched = evaluate_duplicate_seats_batched(model, event_history_window=8, slots=slots,
                                               inference_mode="per_row", **KW)
    assert _canon(batched) == _canon(sequential)
    assert batched["evaluator"] == {"kind": "batched-pool", "slots": min(slots, len(KW["seeds"])),
                                    "inference_mode": "per_row"}


@requires_go_lib
def test_per_row_matches_sequential_for_a_model_without_events():
    model = _model(0)
    sequential = evaluate_duplicate_seats(model=model, **KW)
    batched = evaluate_duplicate_seats_batched(model, slots=3, inference_mode="per_row", **KW)
    assert _canon(batched) == _canon(sequential)


@requires_go_lib
def test_batched_mode_reports_the_same_seeds_and_shape():
    model = _model(8)
    report = evaluate_duplicate_seats_batched(model, event_history_window=8, slots=4, **KW)
    assert report["seeds"] == KW["seeds"]
    assert report["episodes"] == 4 * len(KW["seeds"])
    assert len(report["per_seed_mean_placements"]) == len(KW["seeds"])
    timing = report["evaluator_timing"]
    assert timing["rounds"] > 0 and timing["forward_rows"] > 0


def test_rejects_a_model_window_that_differs_from_the_env_window():
    with pytest.raises(ValueError, match="event window"):
        evaluate_duplicate_seats_batched(_model(8), event_history_window=4, bridge_kind="mock", **KW)


def test_rejects_unknown_inference_mode_and_bad_slots():
    with pytest.raises(ValueError, match="inference_mode"):
        evaluate_duplicate_seats_batched(_model(0), inference_mode="fast", **KW)
    with pytest.raises(ValueError, match="slots"):
        evaluate_duplicate_seats_batched(_model(0), slots=0, **KW)


def _report(evaluator=None):
    report = {
        "seeds": [1, 2],
        "per_seed_mean_placements": [0.1, -0.1],
        "mean_placement": 0.0,
        "large_loss_rate": 0.0,
        "seat_reports": [{"per_episode_placements": [0.1, -0.1]} for _ in range(4)],
        "match_mode": "chongci",
        "chongci_config": {"starting_score": 2000, "bust_threshold": 0, "max_hands": 50},
        "seats": [0, 1, 2, 3],
        "max_steps_per_episode": 4000,
        "oracle_observation": False,
        "event_history_window": 0,
        "large_loss_threshold": -800.0,
        "bridge_lib_sha256": "a" * 64,
    }
    if evaluator is not None:
        report["evaluator"] = evaluator
    return report


BATCHED = {"kind": "batched-pool", "slots": 256, "inference_mode": "batched"}


def test_compare_refuses_batched_vs_sequential_reports():
    with pytest.raises(ValueError, match="evaluator differs"):
        paired_comparison(_report(BATCHED), _report())
    with pytest.raises(ValueError, match="evaluator differs"):
        paired_comparison(_report(BATCHED), _report(dict(BATCHED, slots=128)))


def test_compare_accepts_same_evaluator():
    assert paired_comparison(_report(BATCHED), _report(BATCHED))["config_check"] == "strict"
    assert paired_comparison(_report(), _report())["config_check"] == "strict"


@pytest.mark.parametrize("argv, message", [
    (["--batched-eval-slots", "8"], "requires --duplicate-seats"),
    (["--duplicate-seats", "--batched-eval-slots", "-1"], ">= 0"),
    (["--duplicate-seats", "--batched-eval-inference", "per_row"], "requires --batched-eval-slots"),
    (["--duplicate-seats", "--batched-eval-slots", "8", "--sample-temperature", "0.5"], "greedy"),
    (["--duplicate-seats", "--ensemble-checkpoint", "other.pt"], "requires --batched-eval-slots"),
])
def test_cli_validation(tmp_path, monkeypatch, capsys, argv, message):
    from fh_mahjong_ai.scripts import evaluate as evaluate_cli
    ckpt = tmp_path / "missing.pt"
    monkeypatch.setattr("sys.argv", ["fh-mj-evaluate", "--checkpoint", str(ckpt)] + argv)
    with pytest.raises(SystemExit):
        evaluate_cli.main()
    assert message in capsys.readouterr().err
