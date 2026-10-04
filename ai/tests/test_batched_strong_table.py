"""Strong-table evaluation through the env pool (`batched_eval` with `opponent_model`)."""

import json
import os

import numpy as np
import pytest
import torch

from conftest import small_model_config
from fh_mahjong_ai.batched_eval import (
    OpponentSampling,
    _rewindow,
    evaluate_duplicate_seats_batched,
    evaluate_seats_batched,
)
from fh_mahjong_ai.config import EnvConfig
from fh_mahjong_ai.evaluate import evaluate_duplicate_seats_policy, evaluate_policy_online
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.policies import SuitAveragedGreedyPolicy, TorchGreedyPolicy
from fh_mahjong_ai.storage import model_config_metadata, save_checkpoint

requires_go_lib = pytest.mark.skipif(
    not os.environ.get("FH_MAHJONG_BRIDGE_LIB"), reason="needs the Go bridge library"
)

# 415 and 616 resolve a hand during reset autoplay for some seat (nonzero reset rewards).
KW = dict(match_mode="chongci", chongci_max_hands=4, max_steps_per_episode=4000)
SEEDS = [41, 42, 43, 415, 616]
OPPONENTS = {"kind": "checkpoint", "checkpoint": "opp.pt", "checkpoint_sha256": "b" * 64,
             "event_window": 4, "decision": "greedy"}


def _model(seed: int, window: int) -> PolicyValueNet:
    torch.manual_seed(seed)
    return PolicyValueNet(EnvConfig(), small_model_config(event_window=window)).eval()


def _canon(report: dict) -> str:
    report = dict(report)
    report.pop("evaluator", None)
    report.pop("evaluator_timing", None)
    return json.dumps(report, sort_keys=True, default=str)


def test_rewindow_keeps_each_rows_newest_events():
    events = np.array([[1, 2, 3, 4, 0, 0], [5, 6, 0, 0, 0, 0], [0] * 6], dtype=np.uint32)
    lengths = np.array([4, 2, 0])
    out, kept = _rewindow(events, lengths, 3)
    assert out.tolist() == [[2, 3, 4], [5, 6, 0], [0, 0, 0]]
    assert kept.tolist() == [3, 2, 0]
    same, _ = _rewindow(events, lengths, 6)
    assert same is events
    with pytest.raises(ValueError, match="narrower"):
        _rewindow(events, lengths, 8)


def test_opponent_sampling_validates_and_records():
    with pytest.raises(ValueError, match="temperature"):
        OpponentSampling(temperature=0.0)
    with pytest.raises(ValueError, match="top_k"):
        OpponentSampling(temperature=0.7, top_k=-1)
    record = OpponentSampling(temperature=0.7, top_k=3).record()
    assert record["temperature"] == 0.7 and record["top_k"] == 3 and record["seed"] == 1
    a = OpponentSampling(temperature=0.7).match_rng(2, 41).random(3)
    assert np.array_equal(a, OpponentSampling(temperature=0.7).match_rng(2, 41).random(3))
    assert not np.array_equal(a, OpponentSampling(temperature=0.7).match_rng(1, 41).random(3))


def test_rejects_mismatched_opponent_arguments():
    with pytest.raises(ValueError, match="together"):
        evaluate_duplicate_seats_batched(_model(1, 0), seeds=[1], opponent_model=_model(2, 0))
    with pytest.raises(ValueError, match="opponent_model"):
        evaluate_seats_batched(_model(1, 0), {0: [1]}, opponent_sampling=OpponentSampling(0.7))
    with pytest.raises(ValueError, match="opponent event window"):
        evaluate_seats_batched(_model(1, 0), {0: [1]}, opponent_model=_model(2, 8),
                               event_history_window=0)


@pytest.fixture(scope="module")
def sequential_strong():
    # Candidate window 8 = the table's; the opponent's narrower window 4 exercises re-windowing.
    cand, opp = _model(1, 8), _model(2, 4)
    report = evaluate_duplicate_seats_policy(
        policy_factory=lambda seat: TorchGreedyPolicy(cand), seeds=SEEDS, event_history_window=8,
        opponent_policy=TorchGreedyPolicy(opp), opponents=OPPONENTS, **KW)
    return cand, opp, report


@requires_go_lib
@pytest.mark.parametrize("slots", [1, 6, 64])
def test_per_row_strong_table_is_byte_identical_to_the_sequential_evaluator(sequential_strong, slots):
    # 1 plays matches one at a time, 6 refills slots mid-run across seats, 64 exceeds the jobs.
    cand, opp, sequential = sequential_strong
    batched = evaluate_duplicate_seats_batched(
        cand, seeds=SEEDS, event_history_window=8, slots=slots, inference_mode="per_row",
        opponent_model=opp, opponents=OPPONENTS, **KW)
    assert _canon(batched) == _canon(sequential)
    assert batched["opponents"] == OPPONENTS
    assert batched["evaluator"] == {"kind": "batched-pool", "slots": min(slots, 4 * len(SEEDS)),
                                    "inference_mode": "per_row"}


@requires_go_lib
def test_per_row_matches_sequential_without_event_models():
    cand, opp = _model(3, 0), _model(4, 0)
    opponents = dict(OPPONENTS, event_window=0)
    sequential = evaluate_duplicate_seats_policy(
        policy_factory=lambda seat: TorchGreedyPolicy(cand), seeds=SEEDS[:3],
        opponent_policy=TorchGreedyPolicy(opp), opponents=opponents, **KW)
    batched = evaluate_duplicate_seats_batched(
        cand, seeds=SEEDS[:3], slots=5, inference_mode="per_row", opponent_model=opp,
        opponents=opponents, **KW)
    assert _canon(batched) == _canon(sequential)


@requires_go_lib
def test_per_row_suit_averaged_seats_match_the_sequential_benchmark_loop():
    # The benchmark's shape: disjoint seed ranges per seat, a suit-averaged candidate.
    cand, opp = _model(5, 8), _model(6, 8)
    seat_seeds = {0: [41, 42], 1: [43, 44], 2: [415, 46], 3: [616, 48]}
    run = evaluate_seats_batched(cand, seat_seeds, event_history_window=8, slots=3,
                                 inference_mode="per_row", symmetry="suits", opponent_model=opp,
                                 **KW)
    for seat, seeds in seat_seeds.items():
        sequential = evaluate_policy_online(
            policy=SuitAveragedGreedyPolicy(cand), episodes=len(seeds), seeds=seeds,
            learning_seat=seat, event_history_window=8, opponent_policy=TorchGreedyPolicy(opp),
            **KW)
        assert json.dumps(run["seat_reports"][seat], sort_keys=True, default=str) == \
            json.dumps(sequential, sort_keys=True, default=str)


@requires_go_lib
def test_batched_mode_runs_every_seat_in_one_pool():
    cand, opp = _model(1, 8), _model(2, 4)
    report = evaluate_duplicate_seats_batched(
        cand, seeds=SEEDS, event_history_window=8, slots=8, opponent_model=opp,
        opponents=OPPONENTS, symmetry="suits", **KW)
    assert report["episodes"] == 4 * len(SEEDS)
    assert report["truncation_rate"] == 0.0
    assert report["policy_transform"] == {"symmetry": "suits"}
    assert "policy_choice_counts" in report and "policy_choice_rates" in report["seat_summary"]["0"]
    timing = report["evaluator_timing"]
    assert timing["forward_rows"] > 0
    # Three opponent seats act about three times as often as the candidate.
    assert timing["opponent_forward_rows"] > 2 * timing["forward_rows"]
    decisions = sum(e["decision_count"] for e in report["episode_summaries"])
    assert decisions == timing["forward_rows"]


@requires_go_lib
def test_sampled_opponents_are_reproducible_across_slot_counts_and_differ_from_greedy():
    cand, opp = _model(1, 8), _model(2, 4)
    sampling = OpponentSampling(temperature=1.0, seed=3)
    runs = [evaluate_seats_batched(cand, {s: SEEDS[:3] for s in range(4)}, event_history_window=8,
                                   slots=slots, inference_mode="per_row", opponent_model=opp,
                                   opponent_sampling=sampling, **KW)
            for slots in (2, 7)]
    first, second = (json.dumps(r["seat_reports"], sort_keys=True, default=str) for r in runs)
    assert first == second
    greedy = evaluate_seats_batched(cand, {s: SEEDS[:3] for s in range(4)}, event_history_window=8,
                                    slots=7, inference_mode="per_row", opponent_model=opp, **KW)
    assert json.dumps(greedy["seat_reports"], sort_keys=True, default=str) != first


# --- CLIs -----------------------------------------------------------------------------

SMALL_FLAGS = ["--model-channels", "16", "--model-residual-blocks", "1",
               "--model-plane-feature-dim", "32", "--model-scalar-hidden-dim", "16",
               "--model-trunk-hidden-dim", "32", "--model-value-hidden-dim", "16",
               "--model-q-hidden-dim", "16"]


def _checkpoint(tmp_path, name: str, seed: int, window: int):
    model = _model(seed, window)
    path = tmp_path / name
    save_checkpoint(path, model, metadata={"model_config": model_config_metadata(model.model_config)})
    return path


@requires_go_lib
def test_evaluate_cli_batched_strong_table_reproduces_the_sequential_report(tmp_path, monkeypatch):
    from fh_mahjong_ai.scripts import evaluate as evaluate_cli
    cand = _checkpoint(tmp_path, "cand.pt", 1, 8)
    opp = _checkpoint(tmp_path, "opp.pt", 2, 4)
    base = ["fh-mj-evaluate", "--checkpoint", str(cand), "--online-episodes", "2",
            "--seed-window", "41:2", "--duplicate-seats", "--opponent-checkpoint", str(opp),
            "--match-mode", "chongci", "--chongci-max-hands", "3", "--event-history-window", "8",
            "--model-event-window", "8", *SMALL_FLAGS]
    reports = {}
    for name, extra in (("sequential", []),
                        ("batched", ["--batched-eval-slots", "4", "--batched-eval-inference", "per_row"])):
        out = tmp_path / f"{name}.json"
        monkeypatch.setattr("sys.argv", base + extra + ["--report-output", str(out)])
        evaluate_cli.main()
        reports[name] = json.loads(out.read_text())["online"]
    assert reports["batched"]["opponents"]["decision"] == "greedy"
    assert reports["batched"]["evaluator"]["inference_mode"] == "per_row"
    assert _canon(reports["batched"]) == _canon(reports["sequential"])


@requires_go_lib
def test_benchmark_cli_batched_reproduces_the_sequential_payload(tmp_path):
    from fh_mahjong_ai.scripts import benchmark as benchmark_cli
    cand = _checkpoint(tmp_path, "cand.pt", 1, 8)
    opp = _checkpoint(tmp_path, "opp.pt", 2, 4)
    base = ["--checkpoint", str(cand), "--opponent-checkpoint", str(opp), "--symmetry-average",
            "suits", "--episodes-per-seat", "2", "--seed-base", "41", "--chongci-max-hands", "3",
            "--bootstrap-iters", "10"]
    payloads = {}
    for name, extra in (("sequential", []),
                        ("batched", ["--batched-eval-slots", "3", "--batched-eval-inference", "per_row"])):
        out = tmp_path / f"{name}.json"
        benchmark_cli.main(base + extra + ["--out", str(out)])
        payloads[name] = json.loads(out.read_text())
    assert "evaluator" not in payloads["sequential"]
    assert payloads["batched"]["evaluator"] == {"kind": "batched-pool", "slots": 3,
                                                "inference_mode": "per_row"}
    assert _canon(payloads["batched"]) == _canon(payloads["sequential"])


@requires_go_lib
def test_benchmark_cli_records_sampled_opponents(tmp_path):
    from fh_mahjong_ai.scripts import benchmark as benchmark_cli
    cand = _checkpoint(tmp_path, "cand.pt", 1, 0)
    opp = _checkpoint(tmp_path, "opp.pt", 2, 0)
    out = tmp_path / "sampled.json"
    benchmark_cli.main(["--checkpoint", str(cand), "--opponent-checkpoint", str(opp),
                        "--episodes-per-seat", "1", "--chongci-max-hands", "2",
                        "--bootstrap-iters", "10", "--batched-eval-slots", "4",
                        "--opponent-sample-temperature", "0.7", "--opponent-sample-top-k", "3",
                        "--out", str(out)])
    opponents = json.loads(out.read_text())["opponents"]
    assert opponents["decision"] == "sampled"
    assert opponents["sampling"]["temperature"] == 0.7 and opponents["sampling"]["top_k"] == 3


@pytest.mark.parametrize("argv, message", [
    (["--duplicate-seats", "--opponent-sample-temperature", "0.7"], "requires --opponent-checkpoint"),
    (["--duplicate-seats", "--opponent-checkpoint", "opp.pt", "--opponent-sample-temperature", "0.7"],
     "requires --batched-eval-slots"),
    (["--duplicate-seats", "--opponent-sample-top-k", "3"], "no effect"),
    (["--duplicate-seats", "--opponent-checkpoint", "opp.pt", "--batched-eval-slots", "8",
      "--opponent-sample-temperature", "0.7", "--opponent-sample-action-family", "dance"],
     "not a known action family"),
])
def test_evaluate_cli_validation(tmp_path, monkeypatch, capsys, argv, message):
    from fh_mahjong_ai.scripts import evaluate as evaluate_cli
    monkeypatch.setattr("sys.argv", ["fh-mj-evaluate", "--checkpoint", str(tmp_path / "x.pt")] + argv)
    with pytest.raises(SystemExit):
        evaluate_cli.main()
    assert message in capsys.readouterr().err


@pytest.mark.parametrize("argv, message", [
    (["--batched-eval-slots", "8", "--workers", "2"], "replaces --workers"),
    (["--batched-eval-slots", "8", "--route-study"], "--route-study"),
    (["--symmetry-average", "faces"], "requires --batched-eval-slots"),
    (["--batched-eval-inference", "per_row"], "requires --batched-eval-slots"),
    (["--opponent-sample-temperature", "0.7", "--batched-eval-slots", "8"],
     "requires --opponent-checkpoint"),
])
def test_benchmark_cli_validation(tmp_path, capsys, argv, message):
    from fh_mahjong_ai.scripts import benchmark as benchmark_cli
    with pytest.raises(SystemExit):
        benchmark_cli.main(["--checkpoint", str(tmp_path / "x.pt")] + argv)
    assert message in capsys.readouterr().err
