import functools
import subprocess
import sys
import traceback
from dataclasses import replace

import numpy as np
import pytest

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.oracle import _b2b_model_env_config, collect_b2b_rollouts
from fh_mahjong_ai.ppo import PPOConfig, RolloutBatch
from fh_mahjong_ai.scripts import collect_bench
from fh_mahjong_ai.storage import save_checkpoint


def _perturbing_b2b_worker_loop(env_config, model_config, ppo_config, task_q, result_q,
                                *, field):
    """Test-only worker target (adversarial round 9, medium finding): mirrors
    `oracle._b2b_worker_loop` exactly, except two-match chunks have `field`
    perturbed before being returned to the parent. Passed to
    `ParallelB2bCollector`/`collect_bench.run_bench` as `worker_target` so
    these tests exercise the REAL spawn/queue/model lifecycle path -- proving
    the multi-worker can-fail property is genuine -- without any production
    env-var hook. Defined at module level (not a closure) so multiprocessing's
    spawn context can pickle it; the `field` selection travels via
    `functools.partial`, which pickles fine because its underlying function is
    a plain, importable module-level function."""
    import torch as _torch

    from fh_mahjong_ai.model import PolicyValueNet as _PVN

    _torch.set_num_threads(1)
    model = _PVN(_b2b_model_env_config(env_config), model_config)
    while True:
        task = task_q.get()
        if task is None:
            return
        worker_id, state_dict, base_seed, matches = task
        try:
            model.load_state_dict(state_dict)
            cfg = replace(ppo_config, matches_per_iter=matches, device="cpu")
            batch = collect_b2b_rollouts(env_config, model, cfg, base_seed=base_seed)
            if matches == 2:
                if field == "events":
                    batch.events[0, 0] ^= 1
                elif field in {"rewards", "old_logprobs"}:
                    getattr(batch, field)[0] += 1.0
                elif field == "dones":
                    batch.dones[0] = 1.0 - batch.dones[0]
                else:
                    raise RuntimeError(f"unknown test perturb field {field!r}")
            result_q.put((worker_id, batch, None))
        except Exception:  # noqa: BLE001 - report any worker failure to the parent
            result_q.put((worker_id, None, traceback.format_exc()))

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


def test_bench_uses_persistent_parallel_collector_for_warmup_and_steady_round(
        tmp_path, monkeypatch):
    calls = []

    class RecordingCollector:
        def __init__(self, env_config, model_config, ppo_config, num_workers, worker_target=None):
            calls.append(("init", num_workers))
            self.env_config = env_config
            self.ppo_config = ppo_config
            self.model = PolicyValueNet(_b2b_model_env_config(env_config), model_config)

        def start(self):
            calls.append(("start",))

        def collect(self, state_dict, base_seed, matches_per_iter):
            calls.append(("collect", base_seed, matches_per_iter))
            self.model.load_state_dict(state_dict)
            cfg = replace(self.ppo_config, matches_per_iter=matches_per_iter, device="cpu")
            return collect_b2b_rollouts(
                self.env_config, self.model, cfg, base_seed=base_seed)

        def close(self):
            calls.append(("close",))

    monkeypatch.setattr(collect_bench, "ParallelB2bCollector", RecordingCollector)
    kwargs = _bench_kwargs(tmp_path, [2])
    report = collect_bench.run_bench(**kwargs)
    assert calls == [
        ("init", 2),
        ("start",),
        ("collect", 100, 4),
        ("collect", 100, 4),
        ("close",),
    ]
    assert report["results"][2]["startup_seconds"] >= 0.0
    assert report["results"][2]["steady_seconds"] >= 0.0


def test_injected_perturbation_makes_digests_differ_and_names_it(tmp_path):
    kwargs = _bench_kwargs(tmp_path, [1, 2])
    worker_target = functools.partial(_perturbing_b2b_worker_loop, field="rewards")
    report = collect_bench.run_bench(**kwargs, worker_target=worker_target)
    assert report["all_digests_equal"] is False
    assert report["results"][1]["digest"] != report["results"][2]["digest"]


def test_injected_event_perturbation_makes_digests_differ(tmp_path):
    """A fan-out bug isolated to event-history handling (e.g. a worker
    reusing another worker's event-window buffer) must not slip past the
    digest silently: only perturbing `batch.events` (leaving planes, scalars,
    action_mask, actions, and rewards untouched) must still flip the digest.
    This is what catches finding 1 (events/event_lengths/action_mask omitted
    from the digest) if it regresses."""
    kwargs = _bench_kwargs(tmp_path, [1, 2])
    worker_target = functools.partial(_perturbing_b2b_worker_loop, field="events")
    report = collect_bench.run_bench(**kwargs, worker_target=worker_target)
    assert report["all_digests_equal"] is False
    assert report["results"][1]["digest"] != report["results"][2]["digest"]


@pytest.mark.parametrize("field", ["dones", "old_logprobs"])
def test_injected_ppo_field_perturbation_makes_digests_differ(tmp_path, field):
    worker_target = functools.partial(_perturbing_b2b_worker_loop, field=field)
    report = collect_bench.run_bench(**_bench_kwargs(tmp_path, [1, 2]), worker_target=worker_target)
    assert report["all_digests_equal"] is False
    assert report["results"][1]["digest"] != report["results"][2]["digest"]


def test_chunked_dispatch_digest_matches_single_dispatch(tmp_path):
    """Amendment 2 exact-parity gauntlet: bounded sequential dispatch must
    reproduce the single-dispatch batch BIT FOR BIT (per-match seeding makes
    trajectories chunk-invariant), at a match count the chunk cap does NOT
    divide (4 matches, cap 3 -> chunks of 3 + 1), and repeatably."""
    kwargs = _bench_kwargs(tmp_path, [2])  # matches=4
    single = collect_bench.run_bench(**kwargs)
    chunked = collect_bench.run_bench(**kwargs, dispatch_chunk=3)
    chunked_again = collect_bench.run_bench(**kwargs, dispatch_chunk=3)
    assert single["results"][2]["digest"] == chunked["results"][2]["digest"]
    assert chunked["results"][2]["digest"] == chunked_again["results"][2]["digest"]


def test_chunk_dispatch_covers_seed_blocks_in_order(monkeypatch):
    """Chunk accounting: contiguous seed blocks, canonical order, exact
    remainder handling, no duplication or omission, and the legacy single
    dispatch when the cap is 0 or >= the match count."""
    from dataclasses import replace as dc_replace

    from fh_mahjong_ai.oracle import ParallelB2bCollector

    env = EnvConfig(bridge_kind="mock")
    mcfg = ModelConfig(**_SMALL, event_window=8)

    def make_collector(cap):
        return ParallelB2bCollector(
            env, mcfg, dc_replace(PPOConfig(device="cpu"), collect_dispatch_chunk=cap), 2)

    def install_recorder(collector, calls):
        def fake(state_dict, base_seed, matches):
            calls.append((base_seed, matches))
            batch = _minimal_batch()
            batch.actions = np.zeros(matches, dtype=np.int64)
            batch.planes = np.zeros((matches, 1), dtype=np.float32)
            batch.scalars = np.zeros((matches, 1), dtype=np.float32)
            batch.action_mask = np.ones((matches, 1), dtype=np.int8)
            batch.old_logprobs = np.zeros(matches, dtype=np.float32)
            batch.values = np.zeros(matches, dtype=np.float32)
            batch.rewards = np.zeros(matches, dtype=np.float32)
            batch.dones = np.ones(matches, dtype=np.float32)
            batch.events = np.zeros((matches, 1), dtype=np.uint32)
            batch.event_lengths = np.ones(matches, dtype=np.int32)
            batch.dealin_labels = np.zeros(matches, dtype=np.float32)
            batch.rank_labels = np.zeros(matches, dtype=np.int64)
            return batch
        monkeypatch.setattr(collector, "_collect_dispatch", fake)

    calls: list = []
    collector = make_collector(320)
    install_recorder(collector, calls)
    batch = collector.collect({}, 700000, 960)
    assert calls == [(700000, 320), (700320, 320), (700640, 320)]
    assert len(batch) == 960

    calls.clear()
    collector = make_collector(3)
    install_recorder(collector, calls)
    batch = collector.collect({}, 100, 7)
    assert calls == [(100, 3), (103, 3), (106, 1)]
    assert len(batch) == 7

    for cap in (0, 7, 100):
        calls.clear()
        collector = make_collector(cap)
        install_recorder(collector, calls)
        collector.collect({}, 100, 7)
        assert calls == [(100, 7)], f"cap={cap}"


def test_chunk_dispatch_propagates_later_chunk_failure(monkeypatch):
    from dataclasses import replace as dc_replace

    from fh_mahjong_ai.oracle import ParallelB2bCollector

    env = EnvConfig(bridge_kind="mock")
    mcfg = ModelConfig(**_SMALL, event_window=8)
    collector = ParallelB2bCollector(
        env, mcfg, dc_replace(PPOConfig(device="cpu"), collect_dispatch_chunk=2), 2)
    calls: list = []

    def fake(state_dict, base_seed, matches):
        calls.append((base_seed, matches))
        if len(calls) == 2:
            raise RuntimeError("worker died in chunk 2")
        batch = _minimal_batch()
        return batch

    monkeypatch.setattr(collector, "_collect_dispatch", fake)
    with pytest.raises(RuntimeError, match="chunk 2"):
        collector.collect({}, 0, 4)


def test_cli_dispatch_chunk_flag_passes(tmp_path):
    result = _run_cli(tmp_path, ["--dispatch-chunk", "3"])
    assert result.returncode == 0, result.stderr
    assert "all_digests_equal: True" in result.stdout


def _full_cycle_settings():
    return collect_bench.FullCycleSettings(
        minibatch_size=8, ppo_epochs=1, gamma=0.99, gae_lambda=0.95,
        lr=2e-5, entropy_coef=0.0, device="cpu", update_seed=0,
    )


def test_full_cycle_reports_update_metrics_and_invariance(tmp_path):
    """data-scale-960 Stage 0 preflight: the bench must measure a FULL
    collect + PPO update cycle per worker count — transition rows, optimizer
    steps, throughput, label coverage, truncation, KL, clip fraction, host
    peak RSS — and prove rows/labels are worker-count-invariant."""
    kwargs = _bench_kwargs(tmp_path, [1, 2])
    report = collect_bench.run_bench(**kwargs, full_cycle=_full_cycle_settings())
    assert report["all_digests_equal"] is True
    assert report["rows_and_labels_equal"] is True

    cycles = {w: report["results"][w]["full_cycle"] for w in (1, 2)}
    for fc in cycles.values():
        assert fc["transition_rows"] > 0
        expected_steps = -(-fc["transition_rows"] // 8)  # ceil, 1 epoch
        assert fc["optimizer_steps"] == expected_steps
        assert fc["matches_per_second"] > 0.0
        assert fc["update_seconds"] >= 0.0
        for key in ("policy_loss", "value_loss", "entropy", "approx_kl", "clip_fraction"):
            assert np.isfinite(fc[key])
        # B2b batches always carry aux labels; their coverage is the
        # spec-mandated label-coverage measurement.
        assert 0.0 <= fc["dealin_positive_rate"] <= 1.0
        assert 0.0 <= fc["rank_label_coverage"] <= 1.0
        assert fc["truncated_matches"] >= 0
        assert 0.0 <= fc["truncation_rate"] <= 1.0
        assert fc["host_peak_rss_bytes"] > 0
        assert fc["cuda_peak_allocated_bytes"] is None  # cpu update: no CUDA stats

    # Identical batch (digest-equal) + identical warm-start weights + fixed
    # update seed on cpu => the PPO update itself must be worker-count
    # invariant, bit for bit.
    for key in ("transition_rows", "optimizer_steps", "policy_loss", "value_loss",
                "entropy", "approx_kl", "clip_fraction",
                "dealin_positive_rate", "rank_label_coverage",
                "truncated_matches"):
        assert cycles[1][key] == cycles[2][key], key


def test_full_cycle_cli_exits_zero_and_prints_cycle_table(tmp_path):
    result = _run_cli(tmp_path, [
        "--full-cycle", "--minibatch-size", "8", "--ppo-epochs", "1",
        "--gamma", "0.99", "--gae-lambda", "0.95", "--lr", "2e-5",
        "--entropy-coef", "0", "--ppo-device", "cpu",
    ])
    assert result.returncode == 0, result.stderr
    assert "all_digests_equal: True" in result.stdout
    assert "rows_and_labels_equal: True" in result.stdout
    assert "optimizer_steps" in result.stdout


def test_full_cycle_json_report_includes_cycle_metrics(tmp_path):
    import json as json_mod
    out = tmp_path / "report.json"
    result = _run_cli(tmp_path, [
        "--full-cycle", "--minibatch-size", "8", "--ppo-epochs", "1",
        "--ppo-device", "cpu", "--json", str(out),
    ])
    assert result.returncode == 0, result.stderr
    payload = json_mod.loads(out.read_text())
    assert payload["all_digests_equal"] is True
    assert payload["rows_and_labels_equal"] is True
    for w in ("1", "2"):
        fc = payload[w]["full_cycle"]
        assert fc["transition_rows"] > 0
        assert fc["optimizer_steps"] > 0
        assert np.isfinite(fc["approx_kl"])


def _minimal_batch() -> RolloutBatch:
    return RolloutBatch(
        planes=np.zeros((1, 1), dtype=np.float32),
        scalars=np.zeros((1, 1), dtype=np.float32),
        action_mask=np.ones((1, 1), dtype=np.int8),
        actions=np.zeros(1, dtype=np.int64),
        old_logprobs=np.zeros(1, dtype=np.float32),
        values=np.zeros(1, dtype=np.float32),
        rewards=np.zeros(1, dtype=np.float32),
        dones=np.ones(1, dtype=np.float32),
        events=np.zeros((1, 1), dtype=np.uint32),
        event_lengths=np.ones(1, dtype=np.int32),
        dealin_labels=np.zeros(1, dtype=np.float32),
        rank_labels=np.zeros(1, dtype=np.int64),
    )


def test_digest_includes_per_field_shapes_and_dtypes():
    batch = _minimal_batch()
    baseline = collect_bench._digest_batch(100, 1, batch)

    batch.planes = batch.planes.reshape(1, 1, 1)
    assert collect_bench._digest_batch(100, 1, batch) != baseline

    batch = _minimal_batch()
    batch.actions = batch.actions.astype(np.int32)
    assert collect_bench._digest_batch(100, 1, batch) != baseline


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


def test_cli_injected_perturbation_exits_one_and_names_worker_counts(
        tmp_path, monkeypatch, capsys):
    """The CLI's failure-reporting path (exit 1, naming the differing worker
    counts) is exercised in-process against a manufactured differing-digest
    report, not via any production perturbation hook (adversarial round 9,
    medium finding: a previous version had the production worker consult
    `FH_MAHJONG_TEST_B2B_PERTURB_FIELD` from the environment, which a spawned
    child process inherits -- any process that happened to have that variable
    set, in production, would silently corrupt real training data). The
    spawn-path can-fail property itself -- that a genuine perturbation in one
    worker's output really does flip the digest -- is covered by
    `test_injected_perturbation_makes_digests_differ_and_names_it` and its
    siblings above, which inject a test-only `worker_target` instead."""
    champion = _champion(tmp_path)
    fake_report = {
        "results": {
            1: {"startup_seconds": 0.0, "steady_seconds": 0.0, "digest": "aaa"},
            2: {"startup_seconds": 0.0, "steady_seconds": 0.0, "digest": "bbb"},
        },
        "all_digests_equal": False,
        "model_config": ModelConfig(**_SMALL, event_window=8),
    }
    monkeypatch.setattr(collect_bench, "run_bench", lambda **kwargs: fake_report)
    argv = [
        "fh-mj-collect-bench",
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
    monkeypatch.setattr(sys, "argv", argv)

    with pytest.raises(SystemExit) as excinfo:
        collect_bench.main()

    assert excinfo.value.code == 1
    combined = capsys.readouterr().out
    assert "all_digests_equal: False" in combined
    assert "workers=[1]" in combined
    assert "workers=[2]" in combined
