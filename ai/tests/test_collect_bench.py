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


def test_help_exits_zero():
    result = subprocess.run(
        [sys.executable, "-m", "fh_mahjong_ai.scripts.collect_bench", "--help"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert "--workers" in result.stdout
