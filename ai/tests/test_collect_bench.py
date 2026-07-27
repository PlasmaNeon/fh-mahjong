import subprocess
import sys

import pytest

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.oracle import _b2b_model_env_config
from fh_mahjong_ai.scripts import collect_bench
from fh_mahjong_ai.storage import save_checkpoint

_SMALL = dict(channels=16, residual_blocks=1, plane_feature_dim=32, scalar_hidden_dim=16,
              trunk_hidden_dim=32, value_hidden_dim=16, q_hidden_dim=16)


def _champion(tmp_path):
    env39 = EnvConfig(bridge_kind="mock")
    model = PolicyValueNet(env39, ModelConfig(**_SMALL))
    path = tmp_path / "champion.pt"
    save_checkpoint(path, model)
    return path


def _bench_kwargs(tmp_path, workers):
    champion = _champion(tmp_path)
    return dict(
        champion=champion,
        model_config=ModelConfig(**_SMALL, event_window=8),
        growth_blocks=0,
        workers=workers,
        matches=4,
        base_seed=100,
        match_mode="classic",
        bridge_kind="mock",
        bridge_lib=None,
        device="cpu",
        max_steps_per_episode=16,
        event_window=8,
    )


def test_same_worker_count_twice_gives_identical_digest(tmp_path):
    kwargs = _bench_kwargs(tmp_path, [2])
    report_a = collect_bench.run_bench(**kwargs)
    report_b = collect_bench.run_bench(**kwargs)
    assert report_a["results"][2]["digest"] == report_b["results"][2]["digest"]


def test_workers_one_vs_two_give_identical_digest(tmp_path):
    kwargs = _bench_kwargs(tmp_path, [1, 2])
    report = collect_bench.run_bench(**kwargs)
    assert report["all_digests_equal"] is True
    assert report["results"][1]["digest"] == report["results"][2]["digest"]


def test_injected_perturbation_makes_digests_differ_and_names_it(tmp_path, monkeypatch):
    real_collect = collect_bench.collect_b2b_rollouts

    def perturbing_collect(env_config, model, config, base_seed):
        batch = real_collect(env_config, model, config, base_seed=base_seed)
        # Only the worker_count=2 fan-out ever asks for a 2-match chunk
        # (matches=4 split across 2 workers); worker_count=1 asks for a
        # single 4-match chunk. Perturbing only the 2-match chunk's reward
        # simulates a worker-fan-out bug without touching the baseline.
        if config.matches_per_iter == 2:
            batch.rewards[0] += 1.0
        return batch

    monkeypatch.setattr(collect_bench, "collect_b2b_rollouts", perturbing_collect)
    kwargs = _bench_kwargs(tmp_path, [1, 2])
    report = collect_bench.run_bench(**kwargs)
    assert report["all_digests_equal"] is False
    assert report["results"][1]["digest"] != report["results"][2]["digest"]


def test_injected_event_perturbation_makes_digests_differ(tmp_path, monkeypatch):
    """A fan-out bug isolated to event-history handling (e.g. a worker
    reusing another worker's event-window buffer) must not slip past the
    digest silently: only perturbing `batch.events` (leaving planes, scalars,
    action_mask, actions, and rewards untouched) must still flip the digest.
    This is what catches finding 1 (events/event_lengths/action_mask omitted
    from the digest) if it regresses."""
    real_collect = collect_bench.collect_b2b_rollouts

    def perturbing_collect(env_config, model, config, base_seed):
        batch = real_collect(env_config, model, config, base_seed=base_seed)
        if config.matches_per_iter == 2:
            assert batch.events is not None, "test requires event_history_window > 0"
            batch.events[0, 0] ^= 1
        return batch

    monkeypatch.setattr(collect_bench, "collect_b2b_rollouts", perturbing_collect)
    kwargs = _bench_kwargs(tmp_path, [1, 2])
    report = collect_bench.run_bench(**kwargs)
    assert report["all_digests_equal"] is False
    assert report["results"][1]["digest"] != report["results"][2]["digest"]


def test_help_exits_zero():
    result = subprocess.run(
        [sys.executable, "-m", "fh_mahjong_ai.scripts.collect_bench", "--help"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert "--workers" in result.stdout


def _run_cli(tmp_path, extra_args):
    champion = _champion(tmp_path)
    args = [
        sys.executable, "-m", "fh_mahjong_ai.scripts.collect_bench",
        "--champion", str(champion),
        "--workers", "1,2",
        "--matches", "4",
        "--base-seed", "100",
        "--match-mode", "classic",
        "--bridge-kind", "mock",
        "--device", "cpu",
        "--max-steps-per-episode", "16",
        "--event-window", "8",
        "--model-channels", "16",
        "--model-residual-blocks", "1",
        "--model-plane-feature-dim", "32",
        "--model-scalar-hidden-dim", "16",
        "--model-trunk-hidden-dim", "32",
        "--model-value-hidden-dim", "16",
        "--model-q-hidden-dim", "16",
    ] + extra_args
    return subprocess.run(args, capture_output=True, text=True)


def test_cli_passing_run_exits_zero(tmp_path):
    result = _run_cli(tmp_path, [])
    assert result.returncode == 0, result.stderr
    assert "all_digests_equal: True" in result.stdout


_PERTURB_DRIVER = """
import runpy
import sys

from fh_mahjong_ai.scripts import collect_bench

_real = collect_bench.collect_b2b_rollouts


def _perturbing(env_config, model, config, base_seed):
    batch = _real(env_config, model, config, base_seed=base_seed)
    # Only the worker_count=2 fan-out ever asks for a 2-match chunk
    # (matches=4 split across 2 workers); perturbing only that chunk's
    # reward simulates a worker-fan-out bug without touching the baseline.
    if config.matches_per_iter == 2:
        batch.rewards[0] += 1.0
    return batch


collect_bench.collect_b2b_rollouts = _perturbing
sys.argv = ["collect_bench"] + sys.argv[1:]
collect_bench.main()
"""


def test_cli_injected_perturbation_exits_one_and_names_worker_counts(tmp_path):
    """End-to-end CLI invocation (finding 5): running main() with a
    perturbation injected into `collect_b2b_rollouts` must exit 1, and its
    output must name the differing worker counts, not just report failure."""
    driver = tmp_path / "_perturb_driver.py"
    driver.write_text(_PERTURB_DRIVER)
    champion = _champion(tmp_path)
    args = [
        sys.executable, str(driver),
        "--champion", str(champion),
        "--workers", "1,2",
        "--matches", "4",
        "--base-seed", "100",
        "--match-mode", "classic",
        "--bridge-kind", "mock",
        "--device", "cpu",
        "--max-steps-per-episode", "16",
        "--event-window", "8",
        "--model-channels", "16",
        "--model-residual-blocks", "1",
        "--model-plane-feature-dim", "32",
        "--model-scalar-hidden-dim", "16",
        "--model-trunk-hidden-dim", "32",
        "--model-value-hidden-dim", "16",
        "--model-q-hidden-dim", "16",
    ]
    result = subprocess.run(args, capture_output=True, text=True)
    combined = result.stdout + result.stderr
    assert result.returncode == 1, combined
    assert "all_digests_equal: False" in combined
    assert "workers=[1]" in combined
    assert "workers=[2]" in combined
